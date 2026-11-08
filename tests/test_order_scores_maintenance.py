"""Every review write keeps the per-order score summary equal to the reviews it is derived from."""

import pytest
from account_helpers import make_operator
from checkout_helpers import customer, paid_order, product
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from config import redis_store
from dashboard.services import ORDER_SCORES, as_of_date, end_of_day, order_scores_pipeline
from orders.models import Order, OrderLine
from reviews import services as review_services
from reviews.ratings import empty_summary
from reviews.services import moderate_review, write_review

pytestmark = pytest.mark.django_db(transaction=True)


def stored(mongo_db):
    return {doc["_id"]: (doc["total"], doc["count"]) for doc in mongo_db[ORDER_SCORES].find()}


def live(mongo_db):
    pipeline = order_scores_pipeline(end_of_day(as_of_date()))
    return {row["_id"]: (row["total"], row["count"]) for row in mongo_db.reviews.aggregate(pipeline)}


def imported_review(mongo_db, *, several):
    """A visible imported review of a delivered order whose summary counts one score, or several (copies of one)."""
    for document in mongo_db[ORDER_SCORES].find({"count": {"$gt": 1} if several else 1}):
        if Order.objects.filter(pk=document["_id"], status="delivered").exists():
            return mongo_db.reviews.find_one({"order_id": document["_id"], "taken_down": {"$ne": True}})
    raise AssertionError("the fixture has no such order")


def owner(review):
    return get_user_model().objects.get(pk=review["customer_id"])


def test_takedown_and_restore_of_the_only_review_remove_and_bring_back_the_order(imported, mongo_db):
    review = imported_review(mongo_db, several=False)
    before = stored(mongo_db)
    assert before == live(mongo_db)
    operator = make_operator()
    moderate_review(operator, review["order_line_id"], "takedown", "Test reason")
    assert review["order_id"] not in stored(mongo_db)
    assert stored(mongo_db) == live(mongo_db)
    moderate_review(operator, review["order_line_id"], "restore", "Test reason")
    assert stored(mongo_db) == before == live(mongo_db)


def test_takedown_of_one_review_among_copies_lowers_that_orders_total_and_count(imported, mongo_db):
    review = imported_review(mongo_db, several=True)
    total, count = stored(mongo_db)[review["order_id"]]
    moderate_review(make_operator(), review["order_line_id"], "takedown", "Test reason")
    assert stored(mongo_db)[review["order_id"]] == (total - review["score"], count - 1)
    assert stored(mongo_db) == live(mongo_db)


@pytest.mark.parametrize("action", ["edit", "delete"])
def test_a_customer_editing_or_deleting_a_historical_review_updates_the_summary_and_the_cache(
    imported, mongo_db, action
):
    review = imported_review(mongo_db, several=False)
    version = redis_store.dashboard_version()
    write_review(owner(review), review["order_line_id"], action, {"score": 5, "title": "", "text": ""})
    # An edit stamps the review with today's date, which is after the reporting date; a delete removes it.
    assert review["order_id"] not in stored(mongo_db)
    assert stored(mongo_db) == live(mongo_db)
    assert redis_store.dashboard_version() != version  # the cached dashboard blocks were built from the old score


def test_a_new_review_after_the_reporting_date_changes_neither_the_summary_nor_the_cache(imported, mongo_db):
    buyer = customer("newcomer")
    item = product("newcomer")
    mongo_db.product_specs.insert_one(
        {
            "_id": item.pk,
            "category_id": item.category_id,
            "description": "Example",
            "attributes": {},
            "photo_file_id": None,
            "rating_summary": empty_summary(mongo_db.platform_stats.find_one({"_id": "bayesian"})),
            "latest_reviews": [],
            "has_generated_content": False,
        }
    )
    _, order = paid_order(buyer, item, status="delivered")
    line = OrderLine.objects.create(order=order, seller=item.seller, product=item, quantity=1, unit_price=10, freight=2)
    before, version = stored(mongo_db), redis_store.dashboard_version()
    write_review(buyer, line.pk, "create", {"score": 4})
    assert stored(mongo_db) == before == live(mongo_db)
    assert redis_store.dashboard_version() == version


def test_a_failure_later_in_the_same_transaction_rolls_the_summary_back_with_the_review(
    imported, mongo_db, monkeypatch
):
    review = imported_review(mongo_db, several=False)
    before = stored(mongo_db)

    def broken(*args, **kwargs):
        raise ValidationError("the product summary could not be written")

    monkeypatch.setattr(review_services, "_summary", broken)  # runs after the order summary was recomputed
    with pytest.raises(ValidationError):
        moderate_review(make_operator(), review["order_line_id"], "takedown", "Test reason")
    assert stored(mongo_db) == before
    assert mongo_db.reviews.find_one({"order_line_id": review["order_line_id"]}).get("taken_down", False) is False


def test_without_a_built_summary_a_review_write_creates_nothing(imported, mongo_db):
    review = imported_review(mongo_db, several=False)
    mongo_db[ORDER_SCORES].delete_many({})
    moderate_review(make_operator(), review["order_line_id"], "takedown", "Test reason")
    assert stored(mongo_db) == {}  # the first refresh builds it; nothing is half-built by a review write
