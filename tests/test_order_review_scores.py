"""The MongoDB per-order review score summary: its schema and the bulk `$out` refresh."""

from datetime import timedelta

import pytest
from db_helpers import timestamp_guard_off
from django.db.models import F
from pymongo.errors import PyMongoError, WriteError

from config import redis_store
from config.mongo_schema import VALIDATORS, ensure_collection, setup
from dashboard import services
from dashboard.services import ORDER_SCORES, as_of_date, end_of_day, order_scores_pipeline, query_rows, refresh_sales
from orders.models import Order

pytestmark = pytest.mark.django_db(transaction=True)

GOOD = {"_id": 1, "total": 9, "count": 2, "as_of": "2026-10-24"}
DELIVERIES = "SELECT order_id, delay_days FROM order_delivery_summary ORDER BY order_id"


def stored(mongo_db):
    return {doc["_id"]: doc for doc in mongo_db[ORDER_SCORES].find()}


def live(mongo_db, as_of):
    """What the dashboard computes from the reviews themselves."""
    return {
        row["_id"]: (row["total"], row["count"])
        for row in mongo_db.reviews.aggregate(order_scores_pipeline(end_of_day(as_of)))
    }


def test_the_validator_accepts_a_well_formed_document_and_refuses_malformed_ones(mongo_db):
    mongo_db[ORDER_SCORES].insert_one(dict(GOOD))
    bad = [
        {key: value for key, value in GOOD.items() if key != "as_of"},  # a field missing
        {**GOOD, "_id": 2, "count": 0},  # a summary exists only for an order with a visible score
        {**GOOD, "_id": 3, "total": "9"},  # a string, not an integer
        {**GOOD, "_id": 4, "as_of": "24 October"},  # not an ISO date
        {**GOOD, "_id": 0},  # not an order id
    ]
    for document in bad:
        with pytest.raises(WriteError):
            mongo_db[ORDER_SCORES].insert_one(dict(document))
    assert list(stored(mongo_db)) == [1]


def test_setup_is_repeatable_and_ensure_collection_recreates_it_with_its_validator(mongo_db):
    setup(mongo_db)
    setup(mongo_db)
    mongo_db[ORDER_SCORES].drop()
    ensure_collection(mongo_db, ORDER_SCORES)
    ensure_collection(mongo_db, ORDER_SCORES)
    options = mongo_db[ORDER_SCORES].options()
    assert options["validator"] == VALIDATORS[ORDER_SCORES]
    assert (options["validationLevel"], options["validationAction"]) == ("strict", "error")
    with pytest.raises(WriteError):
        mongo_db[ORDER_SCORES].insert_one({"_id": 1})  # created by ensure_collection, so the validator applies


def test_the_import_leaves_a_summary_equal_to_the_reviews_it_is_derived_from(imported, mongo_db):
    as_of = as_of_date()
    documents = stored(mongo_db)
    assert documents and {key: (doc["total"], doc["count"]) for key, doc in documents.items()} == live(mongo_db, as_of)
    assert {doc["as_of"] for doc in documents.values()} == {as_of.isoformat()}


def test_a_second_refresh_gives_the_same_summary_and_keeps_the_validator_and_indexes(imported, mongo_db):
    first = stored(mongo_db)
    refresh_sales()
    assert stored(mongo_db) == first
    options = mongo_db[ORDER_SCORES].options()
    assert options["validator"] == VALIDATORS[ORDER_SCORES]  # `$out` replaced the contents, not the collection's rules
    assert list(mongo_db[ORDER_SCORES].index_information()) == ["_id_"]


def test_a_refresh_drops_orders_whose_reviews_are_gone_and_documents_nothing_derived(imported, mongo_db):
    documents = stored(mongo_db)
    gone = next(key for key, doc in documents.items() if doc["count"] == 1)
    mongo_db.reviews.update_many({"order_id": gone}, {"$set": {"taken_down": True}})
    mongo_db[ORDER_SCORES].insert_one({**GOOD, "_id": 999_999_999})  # in the summary, but in no review
    refresh_sales()
    after = stored(mongo_db)
    assert gone not in after and 999_999_999 not in after
    assert {key: (doc["total"], doc["count"]) for key, doc in after.items()} == live(mongo_db, as_of_date())


def test_a_review_answered_after_the_reporting_date_is_not_counted(imported, mongo_db):
    as_of = as_of_date()
    gone = next(key for key, doc in stored(mongo_db).items() if doc["count"] == 1)
    mongo_db.reviews.update_many(
        {"order_id": gone}, {"$set": {"answered_at": end_of_day(as_of)}}
    )  # the first instant after
    refresh_sales()
    assert gone not in stored(mongo_db)


def test_a_refused_rebuild_leaves_the_old_summary_in_place(imported, mongo_db, monkeypatch):
    before = stored(mongo_db)
    end = end_of_day(as_of_date())

    class Garbled:  # a reporting date that would write a document the validator refuses
        def isoformat(self):
            return "not a date"

    monkeypatch.setattr(services, "end_of_day", lambda as_of: end)
    with pytest.raises(PyMongoError):
        services.refresh_order_scores(mongo_db, Garbled())
    assert stored(mongo_db) == before  # `$out` swaps the collection only when the whole result was accepted


def test_without_a_reporting_date_the_summary_is_empty(imported, mongo_db):
    assert stored(mongo_db)
    services.refresh_order_scores(mongo_db, None)
    assert stored(mongo_db) == {}


def test_a_failed_mongodb_step_rolls_the_views_back_and_leaves_the_cache_alone(imported, monkeypatch):
    before = query_rows(DELIVERIES, {})
    version = redis_store.dashboard_version()
    with timestamp_guard_off():
        Order.objects.filter(pk=before[0]["order_id"]).update(
            estimated_delivery=F("estimated_delivery") - timedelta(days=10)
        )

    def broken(database, as_of):
        raise PyMongoError("simulated outage")

    monkeypatch.setattr(services, "refresh_order_scores", broken)
    with pytest.raises(PyMongoError):
        refresh_sales()
    assert query_rows(DELIVERIES, {}) == before  # the refresh of the delivery view was rolled back with it
    assert redis_store.dashboard_version() == version  # and nothing was invalidated
