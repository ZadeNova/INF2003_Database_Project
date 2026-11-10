from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from accounts.models import Seller
from catalogue.category_names import display_name
from catalogue.models import Product
from config import mongo, redis_keys, redis_store
from config.mongo_schema import ensure_collection

from .queries import CATEGORY_PERFORMANCE, DELAY_BUCKETS, DELIVERY_SUMMARY, STOCK_PLANNING_FAST

ORDER_SCORES = "order_review_scores"
DASHBOARD_LOCK_WAIT_SECONDS = (
    10  # a request waits at most this long for another to finish computing (worker timeout: 30)
)
HISTORY_SHAPE = 1  # raise whenever `history_blocks` changes its structure: older cached entries then become misses
HISTORY_KEYS = {"category_rows", "delay_rows", "seller_rows", "seller_excluded_count", "poor_reviews"}


def _history_valid(blocks):
    """False for an entry cached by an older shape of `history_blocks`: it is then recomputed, not trusted."""
    return (
        isinstance(blocks, dict)
        and set(blocks) >= HISTORY_KEYS
        and all(isinstance(row, dict) and "seller_id" in row for row in blocks["seller_rows"])
        and all({"product_id", "count", "average"} <= set(row) for row in blocks["poor_reviews"])
    )


BUCKET_LABELS = {
    "early_over_7": "Early by more than 7 days",
    "early_up_to_7_or_on_time": "Early by up to 7 days or on time",
    "late_1_to_7": "Late by up to 7 days",
    "late_8_to_14": "Late by more than 7 to 14 days",
    "late_over_14": "Late by more than 14 days",
}
LATE_RISK_THRESHOLD = Decimal("0.20")
LATE_RISK_MIN_ORDERS = 10


def as_of_date():
    with connection.cursor() as cursor:
        cursor.execute("SELECT public.dashboard_as_of()")
        return cursor.fetchone()[0]


def end_of_day(as_of):
    if type(as_of) is not date:
        raise ValidationError("A reporting date is required.")
    return timezone.make_aware(datetime.combine(as_of + timedelta(days=1), time.min))


def query_rows(query, parameters):
    with connection.cursor() as cursor:
        cursor.execute(query, parameters)
        names = [column.name for column in cursor.description]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def refresh_sales():
    # The two views and the MongoDB score summary are refreshed under one PostgreSQL transaction. Its advisory lock
    # (taken by the first refresh function and held to the commit) also serialises two refreshes. If the MongoDB step
    # fails the views roll back, and `$out` has left the old summary in place; the next refresh rebuilds everything.
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT public.refresh_daily_product_sales()")
            cursor.execute("SELECT public.refresh_order_delivery_summary()")
        with mongo.database() as database:
            refresh_order_scores(database, as_of_date())
    # After the refresh has committed, never before; inside an enclosing transaction this waits for its commit.
    transaction.on_commit(redis_store.bump_dashboard)


def refresh_order_scores(database, as_of):
    """Rebuild the per-order review score summary: an on-demand materialized view, rebuilt with `$out`.

    `$out` replaces the collection atomically and keeps its validator and indexes, so a reader sees the old summary or
    the new one, never half of it, and a refused or failed run leaves the old summary in place. It also drops orders
    whose visible reviews are gone, with no sweep. (`$merge` rewrites every document of a full rebuild and measured
    slower on the full data.) Without a reporting date (no Olist orders yet) the summary is empty.
    """
    ensure_collection(
        database, ORDER_SCORES
    )  # `$out` would otherwise create a missing collection without its validator
    if as_of is None:
        database[ORDER_SCORES].delete_many({})
        return
    list(  # an $out aggregation returns no documents; consuming the cursor runs it
        database.reviews.aggregate(
            order_scores_pipeline(end_of_day(as_of)) + [{"$set": {"as_of": as_of.isoformat()}}, {"$out": ORDER_SCORES}]
        )
    )


def _view_populated(view):
    # PostgreSQL exposes materialization state through its system catalogue; the name is a fixed constant below.
    with connection.cursor() as cursor:
        cursor.execute("SELECT relispopulated FROM pg_class WHERE oid = %s::regclass", [view])
        return cursor.fetchone()[0]


def sales_populated():
    return _view_populated("public.daily_product_sales")


def delivery_summary_populated():
    return _view_populated("public.order_delivery_summary")


def stock_planning(as_of, category=None, seller=None):
    end_of_day(as_of)  # Reject malformed dates before SQL; category and seller remain bound typed values.
    return query_rows(STOCK_PLANNING_FAST, {"as_of": as_of, "category": category, "seller": seller})


def category_performance(as_of):
    end_of_day(as_of)
    return query_rows(CATEGORY_PERFORMANCE, {"as_of": as_of})


def label_month_to_date(rows, as_of):
    """Mark the month the reporting date cuts short and drop its change (part of a month against a whole one).

    The SQL itself stays unchanged: benchmark B2a and its golden output run the same query.
    """
    labelled = []
    for row in rows:
        next_month = (row["month"].replace(day=28) + timedelta(days=4)).replace(day=1)
        partial = next_month - timedelta(days=1) > as_of
        labelled.append({**row, "month_to_date": partial, "change_percent": None if partial else row["change_percent"]})
    return labelled


def order_scores_pipeline(end):
    """Per order, the integer sum of its visible scores and how many there are.

    Integers keep the average exact without converting every review to Decimal128, which cost more than the
    aggregation itself. Copies of an order's review share its score, so averaging them leaves the order's score
    unchanged: they need no filter, and multi-line orders are no longer dropped.
    """
    return [
        {"$match": {"taken_down": {"$ne": True}, "answered_at": {"$lt": end}}},
        {"$group": {"_id": "$order_id", "total": {"$sum": "$score"}, "count": {"$sum": 1}}},
    ]


def poor_reviews_pipeline(end):
    return [
        {"$match": {"taken_down": {"$ne": True}, "answered_at": {"$lt": end}}},
        {"$group": {"_id": "$product_id", "count": {"$sum": 1}, "average": {"$avg": {"$toDecimal": "$score"}}}},
        {"$match": {"count": {"$gte": 5}, "average": {"$lte": 2}}},
        {"$sort": {"average": 1, "count": -1, "_id": 1}},
    ]


def recompute_order_score(database, order_id, session=None):
    """Bring one order's summary document in line with its visible reviews, inside the caller's transaction.

    Called after every review write that can change a historical score (takedown, restore, edit, delete). It reads the
    order's reviews and replaces one document, rather than adding or subtracting the change, so it cannot drift. The
    document gets the summary's own reporting date. Returns whether the summary changed. Before the first refresh there
    is no summary and nothing to maintain.
    """
    collection = database[ORDER_SCORES]
    reference = collection.find_one({}, {"as_of": 1}, session=session)
    if reference is None:
        return False
    end = end_of_day(date.fromisoformat(reference["as_of"]))
    previous = collection.find_one({"_id": order_id}, session=session)
    pipeline = [{"$match": {"order_id": order_id}}, *order_scores_pipeline(end)]
    fresh = next(iter(database.reviews.aggregate(pipeline, session=session)), None)
    if fresh is None:
        collection.delete_one({"_id": order_id}, session=session)
        return previous is not None
    document = {**fresh, "as_of": reference["as_of"]}
    collection.replace_one({"_id": order_id}, document, upsert=True, session=session)
    return previous != document


def live_inputs(as_of, database):
    """The order scores and delivery rows computed from the reviews and the orders themselves (the source of truth)."""
    end = end_of_day(as_of)
    scores = {
        row["_id"]: Decimal(row["total"]) / row["count"]
        for row in database.reviews.aggregate(order_scores_pipeline(end))
    }
    return scores, query_rows(DELAY_BUCKETS, {"end": end})


def summary_inputs(as_of, database):
    """The same two inputs read from the maintained summaries, or None when they cannot be trusted.

    They cannot be trusted when either is missing or empty, or when either was built for another reporting date (for
    example after a half-failed refresh): the dashboard then computes from the source instead.
    """
    if not delivery_summary_populated():
        return None
    reference = database[ORDER_SCORES].find_one({}, {"as_of": 1})
    if reference is None or reference["as_of"] != as_of.isoformat():
        return None
    deliveries = query_rows(DELIVERY_SUMMARY, {})
    if not deliveries or {row["as_of"] for row in deliveries} != {as_of}:
        return None
    scores = {
        document["_id"]: Decimal(document["total"]) / document["count"]
        for document in database[ORDER_SCORES].find({}, {"total": 1, "count": 1})
    }
    return scores, deliveries


def delivery_analysis(as_of, database, *, use_summaries=True):
    inputs = summary_inputs(as_of, database) if use_summaries else None
    scores, deliveries = inputs if inputs is not None else live_inputs(as_of, database)
    buckets = {
        key: {"key": key, "label": label, "orders": 0, "scores": [], "distances": []}
        for key, label in BUCKET_LABELS.items()
    }
    sellers = defaultdict(lambda: {"orders": 0, "late": 0, "scores": []})
    for row in deliveries:
        bucket, seller = buckets[row["bucket"]], sellers[row["seller_id"]]
        bucket["orders"] += 1
        seller["orders"] += 1
        seller["seller_id"] = row["seller_id"]
        seller["late"] += int(row["delay_days"] > 0)
        if row["distance_km"] is not None:
            bucket["distances"].append(Decimal(str(row["distance_km"])))
        if row["order_id"] in scores:
            bucket["scores"].append(scores[row["order_id"]])
            seller["scores"].append(scores[row["order_id"]])
    for bucket in buckets.values():
        bucket["reviewed_orders"] = len(bucket["scores"])
        bucket["average_score"] = (
            sum(bucket["scores"], Decimal(0)) / len(bucket["scores"]) if bucket["scores"] else None
        )
        bucket["distance_km"] = (
            sum(bucket["distances"], Decimal(0)) / len(bucket["distances"]) if bucket["distances"] else None
        )
        del bucket["scores"], bucket["distances"]
    eligible = [seller for seller in sellers.values() if seller["orders"] >= LATE_RISK_MIN_ORDERS]
    for seller in eligible:
        seller["late_share"] = Decimal(seller["late"]) / seller["orders"]
        seller["late_percent"] = seller["late_share"] * 100
        seller["average_score"] = (
            sum(seller["scores"], Decimal(0)) / len(seller["scores"]) if seller["scores"] else None
        )
        seller["at_risk"] = seller["late_share"] > LATE_RISK_THRESHOLD
        del seller["scores"]
    return (
        list(buckets.values()),
        sorted(eligible, key=lambda s: (not s["at_risk"], -s["late_share"], s["seller_id"])),
        len(sellers) - len(eligible),
    )


def _readable_categories(rows):
    """Show corrected category names on the page; the SQL (and benchmark B2, which runs it) is unchanged."""
    return [{**row, "category": display_name(row["category"])} for row in rows]


def history_blocks(as_of):
    """The expensive blocks. They depend on the reporting date only (not on the filters, live stock, product names or
    shop names), so they can be cached; the names are read live afterwards, so a rename never waits for the cache."""
    with mongo.database() as database:
        buckets, sellers, excluded = delivery_analysis(as_of, database)
        poor = list(database.reviews.aggregate(poor_reviews_pipeline(end_of_day(as_of))))
    return {
        "category_rows": _readable_categories(label_month_to_date(category_performance(as_of), as_of)),
        "delay_rows": buckets,
        "seller_rows": sellers,
        "seller_excluded_count": excluded,
        "poor_reviews": [
            {"product_id": row["_id"], "count": row["count"], "average": row["average"].to_decimal()} for row in poor
        ],
    }


def cached_history(as_of):
    """The history blocks from Redis when it can be used (keyed by version and reporting date, one entry for every
    filter, one request recomputing a missing entry while the others wait), otherwise computed from the databases."""
    version = (
        redis_store.dashboard_version()
    )  # read once, before computing: a refresh meanwhile makes this entry unreachable
    if version is None:
        return redis_store.bypass(lambda: history_blocks(as_of))
    return redis_store.cached(
        f"dashboard:{version}:{as_of.isoformat()}",
        redis_keys.DASHBOARD_TTL_SECONDS,
        lambda: history_blocks(as_of),
        lock_wait=DASHBOARD_LOCK_WAIT_SECONDS,
        valid=_history_valid,
        shape=HISTORY_SHAPE,
    )


def dashboard_data(as_of, category=None, seller=None):
    history = cached_history(as_of)
    blocks = history.value
    # Review history may include retired products; operators can still inspect their names.
    products = Product.objects.in_bulk([row["product_id"] for row in blocks["poor_reviews"]])
    poor = [
        {"product": products[row["product_id"]], "count": row["count"], "average": row["average"]}
        for row in blocks["poor_reviews"]
        if row["product_id"] in products
    ]
    shops = dict(
        Seller.objects.filter(pk__in=[row["seller_id"] for row in blocks["seller_rows"]]).values_list("pk", "shop_name")
    )
    return {
        "stock_rows": _readable_categories(stock_planning(as_of, category, seller)),
        "category_rows": blocks["category_rows"],
        "delay_rows": blocks["delay_rows"],
        "seller_rows": [{**row, "shop_name": shops.get(row["seller_id"], "")} for row in blocks["seller_rows"]],
        "poor_rows": poor,
        "seller_min_orders": LATE_RISK_MIN_ORDERS,
        "seller_excluded_count": blocks["seller_excluded_count"],
        "cache_status": history.status,
        "computed_at": history.computed_at,
    }
