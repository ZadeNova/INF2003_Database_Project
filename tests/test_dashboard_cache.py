"""The dashboard's history blocks are cached under a version; stock planning, product names and shop names stay live."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import pytest
from account_helpers import make_operator
from django.db import connection, transaction
from django.http import Http404
from django.test import Client
from django.utils import timezone

from accounts.models import AuditLog, Seller
from catalogue.models import Product
from config import mongo, redis_keys, redis_store
from dashboard.services import (
    HISTORY_KEYS,
    HISTORY_SHAPE,
    as_of_date,
    cached_history,
    dashboard_data,
    history_blocks,
    refresh_sales,
)
from reviews.services import moderate_review

pytestmark = pytest.mark.django_db(transaction=True)


def comparable(data):
    """The data without its cache bookkeeping, with every value tagged by its type: `Decimal("2")` is not `2`."""
    return shape({key: value for key, value in data.items() if key not in {"cache_status", "computed_at"}})


def shape(value):
    if isinstance(value, dict):
        return {key: shape(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, [shape(item) for item in value])
    return (type(value).__name__, value)


def status(as_of):
    return dashboard_data(as_of)["cache_status"]


def as_of_text():
    return as_of_date().isoformat()


def test_history_is_cached_and_stock_planning_stays_live(imported):
    as_of = as_of_date()
    first, second = dashboard_data(as_of), dashboard_data(as_of)
    assert (first["cache_status"], second["cache_status"]) == ("miss", "hit")
    assert comparable(first) == comparable(second)  # a type-exact round trip: Decimals, dates, lists
    assert second["computed_at"] <= timezone.now()
    target = second["stock_rows"][0]["product_id"]
    Product.objects.filter(pk=target).update(stock=987)
    third = dashboard_data(as_of)
    assert third["cache_status"] == "hit"  # the history did not need recomputing...
    assert next(row for row in third["stock_rows"] if row["product_id"] == target)["stock"] == 987  # ...stock is live


def test_the_data_is_identical_cold_warm_and_with_redis_off(imported, settings):
    as_of = as_of_date()
    cold, warm = dashboard_data(as_of), dashboard_data(as_of)
    settings.REDIS_ENABLED = False
    off = dashboard_data(as_of)
    assert (cold["cache_status"], warm["cache_status"], off["cache_status"]) == ("miss", "hit", "off")
    assert comparable(cold) == comparable(warm) == comparable(off)


def test_a_sales_history_refresh_makes_the_cached_entry_unreachable(imported):
    as_of = as_of_date()
    assert (status(as_of), status(as_of)) == ("miss", "hit")
    refresh_sales()
    assert (status(as_of), status(as_of)) == ("miss", "hit")


def test_a_review_takedown_and_a_restore_each_invalidate(imported, mongo_db):
    as_of = as_of_date()
    line_id = mongo_db.reviews.find_one({"taken_down": {"$ne": True}})["order_line_id"]
    operator = make_operator()
    assert (status(as_of), status(as_of)) == ("miss", "hit")
    moderate_review(operator, line_id, "takedown", "Test reason")
    assert (status(as_of), status(as_of)) == ("miss", "hit")
    moderate_review(operator, line_id, "restore", "Test reason")
    assert (status(as_of), status(as_of)) == ("miss", "hit")


def test_a_failed_takedown_does_not_invalidate(imported, mongo_db):
    as_of = as_of_date()
    assert (status(as_of), status(as_of)) == ("miss", "hit")
    with pytest.raises(Http404):
        moderate_review(make_operator(), 987654321, "takedown", "Test reason")  # no such review
    assert status(as_of) == "hit"


def test_product_and_shop_names_are_read_live_from_a_cached_entry(imported):
    as_of = as_of_date()
    item = Product.objects.select_related("seller").filter(active=True).first()
    blocks = {
        "category_rows": [],
        "delay_rows": [],
        "seller_rows": [{"seller_id": item.seller_id, "orders": 12, "late": 1, "at_risk": False}],
        "seller_excluded_count": 0,
        "poor_reviews": [{"product_id": item.pk, "count": 6, "average": Decimal("1.50")}],
    }
    full_key = f"dashboard:{redis_store.dashboard_version()}:{as_of.isoformat()}"
    envelope = redis_store.dumps({"shape": HISTORY_SHAPE, "value": blocks, "computed_at": timezone.now()})
    redis_store.call(lambda client: client.set(redis_store.key(full_key), envelope, ex=60))
    before = dashboard_data(as_of)
    assert before["cache_status"] == "hit" and before["poor_rows"][0]["product"].name == item.name
    Product.objects.filter(pk=item.pk).update(name="Renamed product")
    Seller.objects.filter(pk=item.seller_id).update(shop_name="Renamed shop")
    after = dashboard_data(as_of)
    assert after["cache_status"] == "hit"
    assert after["poor_rows"][0]["product"].name == "Renamed product"
    assert after["seller_rows"][0]["shop_name"] == "Renamed shop" and after["poor_rows"][0]["average"] == Decimal("1.5")


def test_concurrent_cold_requests_compute_the_history_once(imported, mongo_db):
    as_of = as_of_date()

    def request(_):
        with mongo.using_database(mongo_db.name):
            try:
                return cached_history(as_of)
            finally:
                connection.close()

    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(request, range(4)))
    statuses = [result.status for result in results]
    assert statuses.count("miss") == 1 and set(statuses) <= {"miss", "wait", "hit"}
    assert all(result.value == results[0].value for result in results)


def test_the_view_says_where_the_data_came_from(imported):
    client = Client()
    client.force_login(make_operator())
    first = client.get("/operator/dashboard/")
    second = client.get("/operator/dashboard/")
    assert (first["X-Cache"], second["X-Cache"]) == ("MISS", "HIT")
    assert b"served from cache" not in first.content and b"served from cache" in second.content
    assert b"Stock is always live" in second.content
    client.post("/operator/dashboard/refresh/")
    assert client.get("/operator/dashboard/")["X-Cache"] == "MISS"


def test_only_the_version_and_one_dashboard_entry_are_stored(imported):
    dashboard_data(as_of_date())
    keys = redis_store.call(lambda client: sorted(client.scan_iter(match=redis_store.key("*"))))
    version = redis_store.key("dashboard:version")
    assert len(keys) == 2 and version in keys
    entry = next(found for found in keys if found != version)
    assert entry.startswith(redis_store.key("dashboard:")) and entry.endswith(as_of_text())
    assert 0 < redis_store.call(lambda client: client.pttl(entry)) <= redis_keys.DASHBOARD_TTL_SECONDS * 1000
    assert redis_store.call(lambda client: client.pttl(version)) == -1  # the version is the one key without an expiry


def test_the_dashboard_renders_when_redis_is_unreachable(imported, settings):
    settings.REDIS_PORT = 1
    redis_store.reset_for_tests()
    client = Client()
    client.force_login(make_operator())
    response = client.get("/operator/dashboard/")
    assert response.status_code == 200 and response["X-Cache"] == "DOWN"
    assert b"served from cache" not in response.content
    assert timedelta(0) <= timezone.now() - response.context["computed_at"] < timedelta(minutes=1)


def test_invalidation_waits_for_the_enclosing_transaction_and_a_rollback_never_bumps(imported):
    first = redis_store.dashboard_version()
    with pytest.raises(RuntimeError), transaction.atomic():
        refresh_sales()
        assert redis_store.dashboard_version() == first  # not yet: the change has not committed
        raise RuntimeError("rolled back")
    assert redis_store.dashboard_version() == first  # a rollback leaves the cache as it was
    with transaction.atomic():
        refresh_sales()
        assert redis_store.dashboard_version() == first
    assert int(redis_store.dashboard_version()) > int(first)  # bumped once the transaction committed


def test_a_takedown_that_committed_in_mongodb_but_failed_in_postgresql_still_invalidates(imported, mongo_db):
    as_of = as_of_date()
    line_id = mongo_db.reviews.find_one({"taken_down": {"$ne": True}})["order_line_id"]
    operator = make_operator()
    assert (status(as_of), status(as_of)) == ("miss", "hit")
    table = AuditLog._meta.db_table
    with connection.cursor() as cursor:  # PostgreSQL refuses the commit, after MongoDB has already committed
        cursor.execute(
            "CREATE FUNCTION test_refuse_at_commit() RETURNS trigger LANGUAGE plpgsql "
            "AS $$ BEGIN RAISE EXCEPTION 'refused at commit'; END $$"
        )
        cursor.execute(
            f"CREATE CONSTRAINT TRIGGER test_refuse_at_commit AFTER INSERT ON {table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION test_refuse_at_commit()"
        )
    try:
        with pytest.raises(Exception, match="refused at commit"):
            moderate_review(operator, line_id, "takedown", "Test reason")
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP TRIGGER test_refuse_at_commit ON {table}")
            cursor.execute("DROP FUNCTION test_refuse_at_commit()")
    assert mongo_db.reviews.find_one({"order_line_id": line_id})["taken_down"] is True  # MongoDB did change
    assert status(as_of) == "miss"  # so the cached dashboard was not allowed to outlive it


def test_an_entry_in_an_older_shape_is_recomputed_not_a_server_error(imported):
    as_of = as_of_date()
    envelope = redis_store.dumps(
        {"shape": HISTORY_SHAPE, "value": {"category_rows": []}, "computed_at": timezone.now()}
    )
    full_key = f"dashboard:{redis_store.dashboard_version()}:{as_of.isoformat()}"
    redis_store.call(lambda client: client.set(redis_store.key(full_key), envelope, ex=60))
    assert (status(as_of), status(as_of)) == ("miss", "hit")  # recomputed once, then served from the new entry


# Pinned structure of the cached blocks for each shape number. Changing `history_blocks` without raising HISTORY_SHAPE
# would let a Redis that still holds the old entries serve a value the page cannot read; this test fails instead.
SHAPES = {
    1: {
        "category_rows": {
            "category", "category_id", "change_percent", "month", "month_to_date", "previous_month",
            "previous_revenue", "revenue", "revenue_rank", "units",
        },
        "delay_rows": {"average_score", "distance_km", "key", "label", "orders", "reviewed_orders"},
        "seller_rows": {"at_risk", "average_score", "late", "late_percent", "late_share", "orders", "seller_id"},
        "poor_reviews": {"average", "count", "product_id"},
    }
}  # fmt: skip


def test_the_cached_blocks_have_the_structure_pinned_for_their_shape_number(imported):
    blocks = history_blocks(as_of_date())
    assert set(blocks) == HISTORY_KEYS
    for name, row_keys in SHAPES[HISTORY_SHAPE].items():
        for row in blocks[name]:
            assert set(row) == row_keys, f"{name} changed: raise HISTORY_SHAPE and add the new structure to SHAPES"
    assert blocks["delay_rows"]  # the five delay buckets always exist, so this check always has rows to compare


def test_an_entry_with_another_shape_number_is_recomputed(imported):
    as_of = as_of_date()
    assert (status(as_of), status(as_of)) == ("miss", "hit")
    full_key = redis_store.key(f"dashboard:{redis_store.dashboard_version()}:{as_of.isoformat()}")
    current = redis_store.loads(redis_store.call(lambda client: client.get(full_key)))
    stale = redis_store.dumps({**current, "shape": HISTORY_SHAPE + 1})
    redis_store.call(lambda client: client.set(full_key, stale, ex=60))
    assert (status(as_of), status(as_of)) == ("miss", "hit")


def test_a_takedown_invalidates_even_if_its_enclosing_transaction_rolls_back(imported, mongo_db):
    as_of = as_of_date()
    line_id = mongo_db.reviews.find_one({"taken_down": {"$ne": True}})["order_line_id"]
    operator = make_operator()
    assert (status(as_of), status(as_of)) == ("miss", "hit")
    with pytest.raises(RuntimeError), transaction.atomic():
        moderate_review(operator, line_id, "takedown", "Test reason")
        raise RuntimeError("the outer transaction rolls back")
    assert mongo_db.reviews.find_one({"order_line_id": line_id})["taken_down"] is True  # MongoDB cannot roll back
    assert status(as_of) == "miss"
