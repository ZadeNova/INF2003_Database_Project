"""Real time-series writes, TTL/index configuration, window calculations and seller isolation."""

import json
from collections import Counter
from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from account_helpers import make_operator
from checkout_helpers import customer, paid_order, product
from db_helpers import timestamp_guard_off
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.utils import timezone
from django.utils.crypto import salted_hmac

import activity.services as activity_services
from activity.services import EVENT_WRITE_CONCERN, seller_insights, trending_pipeline
from catalogue.models import Product
from config.mongo_schema import EVENT_TTL_SECONDS, setup_events
from orders.models import Order, OrderLine

pytestmark = pytest.mark.django_db(transaction=True)


def event(item, now, *, user=None, session=None, generated=False, kind="view"):
    meta = {"type": kind, "product_id": item.pk, "category": item.category_id}
    if user:
        meta["user_id"] = user.pk
    else:
        meta["session_key"] = session or "synthetic-test-session"
    return {"ts": now, "meta": meta, "is_generated": generated}


def test_collection_is_timeseries_with_30_day_ttl_and_secondary_indexes(mongo_db):
    for _ in range(2):
        call_command("mongo_setup", database=mongo_db.name, stdout=StringIO())
    options = mongo_db.events.options()
    assert options["timeseries"]["timeField"] == "ts" and options["timeseries"]["metaField"] == "meta"
    assert options["expireAfterSeconds"] == EVENT_TTL_SECONDS == 2592000
    indexes = mongo_db.events.index_information()
    assert indexes["event_product_time"]["key"] == [("meta.product_id", 1), ("ts", -1)]
    assert indexes["event_user_time"]["key"] == [("meta.user_id", 1), ("ts", -1)]
    assert EVENT_WRITE_CONCERN.document["w"] == 1


def test_product_view_and_search_write_once_with_trimmed_literal_query(mongo_db):
    buyer, item = customer(), product()
    client = Client()
    client.force_login(buyer)
    assert client.get(f"/products/{item.pk}/").status_code == 200
    views = list(mongo_db.events.find({}))
    assert len(views) == 1 and views[0]["meta"] == {
        "type": "view",
        "product_id": item.pk,
        "category": item.category_id,
        "user_id": buyer.pk,
    }
    assert views[0]["is_generated"] is False
    payload = "  ' OR 1=1 -- {$where: sleep(999)} <script>bad</script>  "
    assert client.get("/products/", {"q": payload}).status_code == 200
    searches = list(mongo_db.events.find({"meta.type": "search"}))
    assert len(searches) == 1 and searches[0]["query"] == payload.strip()
    # The normal catalogue validates name length; the writer still caps its own record independently.
    from django.test import RequestFactory

    from activity.services import record_event

    request = RequestFactory().get("/products/")
    request.user = buyer
    record_event(request, "search", query=" " + "x" * 120 + " ")
    assert mongo_db.events.find_one({"query": "x" * 100}) is not None
    assert Product.objects.filter(pk=item.pk).exists()
    assert client.head(f"/products/{item.pk}/").status_code == 200
    assert mongo_db.events.count_documents({"meta.type": "view"}) == 1


def test_anonymous_identity_is_keyed_hash_and_histories_remain_separate(mongo_db):
    item, other = product(), product("other-anonymous")
    anonymous, second = Client(), Client()
    assert anonymous.get(f"/products/{item.pk}/").status_code == 200
    row = mongo_db.events.find_one({})
    raw_key = anonymous.session.session_key
    assert row["meta"]["session_key"] != raw_key
    assert row["meta"]["session_key"] == salted_hmac("mercer.activity.visitor", raw_key).hexdigest()
    assert "user_id" not in row["meta"]
    page = anonymous.get("/products/", {"q": "private visitor"})
    assert [p.pk for p in page.context["recent_products"]] == [item.pk]
    assert second.get("/products/").context["recent_products"] == []
    assert second.get(f"/products/{other.pk}/").status_code == 200
    assert [p.pk for p in second.get("/products/").context["recent_products"]] == [other.pk]
    assert [p.pk for p in anonymous.get("/products/").context["recent_products"]] == [item.pk]
    rows = list(mongo_db.events.find({}))
    assert all("user_id" not in r["meta"] for r in rows)
    assert {r["meta"]["session_key"] for r in rows} == {
        salted_hmac("mercer.activity.visitor", raw_key).hexdigest(),
        salted_hmac("mercer.activity.visitor", second.session.session_key).hexdigest(),
    }
    stored = json.dumps(rows, default=str)
    assert raw_key not in stored and second.session.session_key not in stored
    buyer = customer()
    anonymous.force_login(buyer)
    assert anonymous.get("/products/").context["recent_products"] == []


def test_recently_viewed_last_ten_distinct_newest_first_and_hidden_filtered(mongo_db):
    buyer = customer()
    items = [product(str(n)) for n in range(12)]
    now = timezone.now()
    mongo_db.events.insert_many(
        [event(item, now - timedelta(minutes=n + 1), user=buyer) for n, item in enumerate(items)]
    )
    mongo_db.events.insert_one(event(items[3], now - timedelta(seconds=1), user=buyer))
    client = Client()
    client.force_login(buyer)
    page = client.get("/products/")
    expected = [items[3].pk] + [i.pk for i in items if i.pk != items[3].pk]
    assert [p.pk for p in page.context["recent_products"]] == expected[:10]
    Product.objects.filter(pk=items[0].pk).update(taken_down=True)
    page = client.get("/products/")
    assert [p.pk for p in page.context["recent_products"]] == [pk for pk in expected if pk != items[0].pk][:10]
    assert b"Recently viewed" in page.content


def test_trending_rank_ties_category_and_time_window_match_direct_counts(mongo_db):
    items = [product("trend" + str(n)) for n in range(4)]
    from catalogue.models import Category

    category = Category.objects.create(slug="other", name_en="Other", name_pt="Other")
    Product.objects.filter(pk=items[3].pk).update(category=category)
    items[3].refresh_from_db()
    now = timezone.now()
    for item, count in zip(items, [5, 3, 3, 7], strict=True):
        mongo_db.events.insert_many([event(item, now - timedelta(hours=1), generated=True) for _ in range(count)])
    mongo_db.events.insert_many(
        [
            event(items[1], now - timedelta(hours=25)),
            event(items[1], now + timedelta(seconds=1)),
            event(items[1], now - timedelta(hours=1), kind="search"),
        ]
    )
    actual = list(mongo_db.events.aggregate(trending_pipeline(now)))
    assert [(r["_id"], r["views"], r["rank"]) for r in actual] == [
        (items[3].pk, 7, 1),
        (items[0].pk, 5, 2),
        (items[1].pk, 3, 3),
        (items[2].pk, 3, 3),
    ]
    category_rows = list(mongo_db.events.aggregate(trending_pipeline(now, items[0].category_id)))
    assert [(r["_id"], r["rank"]) for r in category_rows] == [(items[0].pk, 1), (items[1].pk, 2), (items[2].pk, 2)]
    page = Client().get("/products/")
    assert page.status_code == 200 and b"Includes generated views" in page.content
    assert b"Popular picks will appear here soon" not in page.content
    page = Client().get("/products/category/example/")
    assert {p.pk for p in page.context["trending_products"]} == {i.pk for i in items[:3]}


def test_event_collection_failure_is_logged_and_does_not_break_product_or_search(mongo_db, caplog):
    item = product()
    mongo_db.drop_collection("events")
    activity_services.EVENTS_READY = False
    # Real incompatible storage state, not a mocked insert exception. The writer refuses to create
    # ordinary events accidentally; catalogue reads still use their healthy collections.
    mongo_db.create_collection(
        "events", validator={"$jsonSchema": {"bsonType": "object", "required": ["blocked_write"]}}
    )
    try:
        client = Client()
        assert client.get(f"/products/{item.pk}/").status_code == 200
        assert client.get("/products/", {"q": "private-search-sentinel"}).status_code == 200
        assert any(r.message == "activity.event_write_failed" for r in caplog.records)
        assert "private-search-sentinel" not in " ".join(r.message for r in caplog.records)
        assert mongo_db.events.count_documents({}) == 0
    finally:
        mongo_db.drop_collection("events")
        setup_events(mongo_db)


def test_missing_events_collection_is_not_silently_created_as_regular_storage(mongo_db):
    item = product()
    mongo_db.drop_collection("events")
    activity_services.EVENTS_READY = False
    try:
        assert Client().get(f"/products/{item.pk}/").status_code == 200
        assert "events" not in mongo_db.list_collection_names()
    finally:
        setup_events(mongo_db)


def test_collection_check_is_remembered_after_it_passes_and_retried_after_it_fails(mongo_db):
    item = product()
    activity_services.EVENTS_READY = False
    assert Client().get(f"/products/{item.pk}/").status_code == 200
    assert activity_services.EVENTS_READY is True
    mongo_db.drop_collection("events")
    activity_services.EVENTS_READY = False
    try:
        assert Client().get(f"/products/{item.pk}/").status_code == 200
        assert activity_services.EVENTS_READY is False
    finally:
        setup_events(mongo_db)


def test_insights_views_units_ratio_and_seller_scoping(mongo_db):
    buyer, item, other = customer(), product(), product("other")
    now = timezone.now()
    for target in [item, other]:
        mongo_db.events.insert_many([event(target, now - timedelta(hours=2), generated=True) for _ in range(4)])
        _, order = paid_order(buyer, target)
        with timestamp_guard_off():
            Order.objects.filter(pk=order.pk).update(placed_at=now - timedelta(days=1))
        OrderLine.objects.create(
            order=order, seller=target.seller, product=target, quantity=1, unit_price=10, freight=2
        )
    mongo_db.events.insert_one(event(item, now - timedelta(days=31)))
    _, cancelled = paid_order(buyer, item, status="cancelled")
    OrderLine.objects.create(order=cancelled, seller=item.seller, product=item, quantity=1, unit_price=10, freight=2)
    _, future = paid_order(buyer, item)
    with timestamp_guard_off():
        Order.objects.filter(pk=future.pk).update(placed_at=now + timedelta(days=1))
    OrderLine.objects.create(order=future, seller=item.seller, product=item, quantity=1, unit_price=10, freight=2)
    result = seller_insights(item.seller, now=now)
    assert len(result["insights"]) == 1
    row = result["insights"][0]
    assert row["views"] == 4 and row["units"] == 1 and row["conversion_percent"] == Decimal(25)
    assert row["generated_views"] == 4
    client = Client()
    client.force_login(item.seller.user)
    page = client.get("/seller/insights/", {"seller_id": other.seller_id, "product_id": other.pk})
    assert page.status_code == 200 and [r["product"].pk for r in page.context["page_obj"]] == [item.pk]
    assert b"other" not in page.content
    client.force_login(buyer)
    assert client.get("/seller/insights/").status_code == 403
    client.force_login(make_operator())
    assert client.get("/seller/insights/").status_code == 403
    assert Client().get("/seller/insights/").status_code == 302


def test_seed_activity_weighted_by_real_sales_labelled_and_relative_to_now(mongo_db):
    buyer, most, least = customer(), product("popular"), product("quiet")
    for n in range(10):
        target = most if n < 9 else least
        checkout, order = paid_order(buyer, target)
        checkout.olist_order_id = f"{n:032d}"
        checkout.save(update_fields=["olist_order_id"])
        OrderLine.objects.create(
            order=order, seller=target.seller, product=target, quantity=1, unit_price=10, freight=2
        )
    start = timezone.now()
    output = StringIO()
    call_command("seed_activity", count=10000, seed=82, stdout=output)
    rows = list(mongo_db.events.find({}))
    assert len(rows) == 10000 and all(r["is_generated"] is True for r in rows)
    assert all("user_id" not in r["meta"] for r in rows)
    assert {r["meta"]["session_key"] for r in rows} == {"generated-demo-activity"}
    from datetime import timezone as dt_timezone

    assert all(start - timedelta(days=30) <= r["ts"].replace(tzinfo=dt_timezone.utc) <= timezone.now() for r in rows)
    counts = Counter(r["meta"]["product_id"] for r in rows)
    assert 8500 < counts[most.pk] < 9500 and sum(counts.values()) == 10000
    assert json.loads(output.getvalue().splitlines()[-1])["events_written"] == len(rows)
    assert Client().get("/products/").context["trending_products"]


@pytest.mark.parametrize("count", [0, -1, 1000001])
def test_seed_rejects_unbounded_or_invalid_counts(count):
    with pytest.raises(CommandError):
        call_command("seed_activity", count=count, stdout=StringIO())
