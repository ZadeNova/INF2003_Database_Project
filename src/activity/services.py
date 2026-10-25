"""Best-effort activity writes and bounded, explicit cross-store reads."""
import logging
from datetime import timedelta
from decimal import Decimal
from itertools import islice

from django.db.models import Sum
from django.utils import timezone
from django.utils.crypto import salted_hmac
from pymongo.errors import PyMongoError
from pymongo.write_concern import WriteConcern

from catalogue.models import Product
from catalogue.search import attach_photos, visible_products
from config import mongo
from orders.models import OrderLine

logger = logging.getLogger("mercer.errors")
EVENT_WRITE_CONCERN = WriteConcern(w=1, wtimeout=1000)


def visitor(request, *, create=False):
    if request.user.is_authenticated:
        return {"user_id": request.user.pk}
    if not request.session.session_key and create:
        request.session.create()
    if not request.session.session_key:
        return None
    return {"session_key": salted_hmac("mercer.activity.visitor", request.session.session_key).hexdigest()}


def record_event(request, event_type, *, product=None, query="", category=None):
    if request.method != "GET" or event_type not in {"view", "search"}:
        return
    identity = visitor(request, create=True)
    meta = {"type": event_type, **identity}
    if product is not None:
        meta.update(product_id=product.pk, category=product.category_id)
    elif category is not None:
        meta["category"] = category.pk
    event = {"ts": timezone.now(), "meta": meta, "is_generated": False}
    if event_type == "search":
        event["query"] = str(query).strip()[:100]
    try:
        with mongo.client() as client:
            events = client[mongo.database_name()].events.with_options(write_concern=EVENT_WRITE_CONCERN)
            # Never let an insert silently create a regular collection before mongo_setup has run.
            if events.options().get("timeseries", {}).get("timeField") != "ts":
                logger.warning("activity.event_write_failed")
                return
            events.insert_one(event)
    except PyMongoError:
        # No query, user/session identifier or database exception message enters the log.
        logger.warning("activity.event_write_failed")


def recently_viewed_pipeline(identity, now):
    return [{"$match": {"meta.type": "view", **{"meta." + key: value for key, value in identity.items()},
                        "ts": {"$gte": now - timedelta(days=30), "$lte": now}}},
            {"$sort": {"ts": -1}},
            {"$group": {"_id": "$meta.product_id", "last_viewed": {"$max": "$ts"}}},
            {"$sort": {"last_viewed": -1, "_id": 1}}]


def trending_pipeline(now, category=None):
    match = {"meta.type": "view", "ts": {"$gte": now - timedelta(hours=24), "$lte": now}}
    if category is not None:
        match["meta.category"] = category
    return [{"$match": match},
            {"$group": {"_id": "$meta.product_id", "views": {"$sum": 1},
                "generated_views": {"$sum": {"$cond": [{"$eq": ["$is_generated", True]}, 1, 0]}}}},
            {"$setWindowFields": {"sortBy": {"views": -1}, "output": {"rank": {"$rank": {}}}}},
            # Sorting by the computed rank keeps the ID tie-breaker after the rank stage. Sorting by
            # views + ID can be coalesced into the window's ordering by the MongoDB optimizer.
            {"$sort": {"rank": 1, "_id": 1}}]


def _visible_ranked(database, rows, limit):
    """Resolve at most fifty IDs per cross-store read; continue past withdrawn products."""
    selected = []
    iterator = iter(rows)
    while len(selected) < limit:
        batch = list(islice(iterator, 50))
        if not batch:
            break
        products = {p.pk: p for p in visible_products().filter(pk__in=[row["_id"] for row in batch])}
        for row in batch:
            item = products.get(row["_id"])
            if item is not None:
                item.event_views = row.get("views")
                item.event_rank = row.get("rank")
                item.generated_views = row.get("generated_views", 0)
                selected.append(item)
                if len(selected) == limit:
                    break
    return attach_photos(database, selected)


def browsing_panels(request, *, category=None):
    now = timezone.now()
    identity = visitor(request)
    try:
        with mongo.client() as client:
            database = client[mongo.database_name()]
            recent = _visible_ranked(database, database.events.aggregate(recently_viewed_pipeline(identity, now)), 10) if identity else []
            trending = _visible_ranked(database, database.events.aggregate(trending_pipeline(now, category)), 8)
        return {"recent_products": recent, "trending_products": trending}
    except PyMongoError:
        logger.warning("activity.panels_unavailable")
        return {"recent_products": [], "trending_products": []}


def conversion_pipeline(product_ids, now):
    return [{"$match": {"meta.type": "view", "meta.product_id": {"$in": list(product_ids)},
                        "ts": {"$gte": now - timedelta(days=30), "$lte": now}}},
            {"$group": {"_id": "$meta.product_id", "views": {"$sum": 1},
                "generated_views": {"$sum": {"$cond": [{"$eq": ["$is_generated", True]}, 1, 0]}}}}]


def seller_insights(seller, *, now=None):
    now = now or timezone.now()
    products = list(Product.objects.filter(seller=seller).order_by("-id"))
    ids = [item.pk for item in products]
    unavailable = False
    try:
        with mongo.client() as client:
            views = {row["_id"]: row for row in client[mongo.database_name()].events.aggregate(conversion_pipeline(ids, now))}
    except PyMongoError:
        logger.warning("activity.insights_unavailable")
        views = {}
        unavailable = True
    # Both seller predicates matter: never aggregate another seller's orders or products.
    units = dict(OrderLine.objects.filter(seller=seller, product__seller=seller, product_id__in=ids,
        order__placed_at__gte=now-timedelta(days=30), order__placed_at__lte=now).exclude(order__status="cancelled")
        .values("product_id").annotate(units=Sum("quantity")).values_list("product_id", "units"))
    rows = []
    for item in products:
        count = views.get(item.pk, {}).get("views", 0)
        sold = units.get(item.pk, 0)
        rows.append({"product": item, "views": None if unavailable else count, "units": sold,
            "conversion_percent": Decimal(sold) * 100 / count if count and not unavailable else None,
            "generated_views": views.get(item.pk, {}).get("generated_views", 0)})
    return {"insights": rows, "events_unavailable": unavailable, "window_start": now-timedelta(days=30), "window_end": now}
