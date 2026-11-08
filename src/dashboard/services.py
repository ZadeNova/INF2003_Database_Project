from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import connection
from django.utils import timezone

from catalogue.category_names import display_name
from catalogue.models import Product
from config import mongo

from .queries import CATEGORY_PERFORMANCE, DELAY_BUCKETS, STOCK_PLANNING_FAST

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
        return [dict(zip(names, row)) for row in cursor.fetchall()]


def refresh_sales():
    with connection.cursor() as cursor:
        cursor.execute("SELECT public.refresh_daily_product_sales()")


def sales_populated():
    # PostgreSQL exposes materialization state through its system catalogue.
    with connection.cursor() as cursor:
        cursor.execute("SELECT relispopulated FROM pg_class WHERE oid = 'public.daily_product_sales'::regclass")
        return cursor.fetchone()[0]


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


def delivery_analysis(as_of, database):
    end = end_of_day(as_of)
    scores = {
        row["_id"]: Decimal(row["total"]) / row["count"]
        for row in database.reviews.aggregate(order_scores_pipeline(end))
    }
    deliveries = query_rows(DELAY_BUCKETS, {"end": end})
    buckets = {
        key: {"key": key, "label": label, "orders": 0, "scores": [], "distances": []}
        for key, label in BUCKET_LABELS.items()
    }
    sellers = defaultdict(lambda: {"orders": 0, "late": 0, "scores": []})
    for row in deliveries:
        bucket, seller = buckets[row["bucket"]], sellers[row["seller_id"]]
        bucket["orders"] += 1
        seller["orders"] += 1
        seller["seller_id"], seller["shop_name"] = row["seller_id"], row["shop_name"]
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


def dashboard_data(as_of, category=None, seller=None):
    with mongo.client() as client:
        database = client[mongo.database_name()]
        buckets, sellers, excluded = delivery_analysis(as_of, database)
        poor = list(database.reviews.aggregate(poor_reviews_pipeline(end_of_day(as_of))))
    # Review history may include retired products; operators can still inspect their names.
    products = Product.objects.in_bulk([row["_id"] for row in poor])
    poor = [
        {"product": products[row["_id"]], "count": row["count"], "average": row["average"].to_decimal()}
        for row in poor
        if row["_id"] in products
    ]
    return {
        "stock_rows": _readable_categories(stock_planning(as_of, category, seller)),
        "category_rows": _readable_categories(label_month_to_date(category_performance(as_of), as_of)),
        "delay_rows": buckets,
        "seller_rows": sellers,
        "poor_rows": poor,
        "seller_min_orders": LATE_RISK_MIN_ORDERS,
        "seller_excluded_count": excluded,
    }
