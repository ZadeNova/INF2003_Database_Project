from io import StringIO

import pytest
from bson import Decimal128
from django.core.management import call_command
from django.core.management.base import CommandError
from pymongo.errors import DuplicateKeyError, WriteError

from config.mongo_schema import VALIDATORS


def spec():
    return {
        "_id": 1,
        "category_id": 1,
        "description": "Generated description",
        "attributes": {"arbitrary_category_field": "allowed"},
        "photo_file_id": None,
        "rating_summary": {
            "count": 0,
            "sum": 0,
            "average": Decimal128("0"),
            "distribution": {},
            "bayesian": Decimal128("4"),
        },
        "latest_reviews": [],
        "has_generated_content": True,
    }


def test_setup_is_idempotent_with_readwrite_on_the_real_test_database(mongo_db):
    for _ in range(2):
        call_command("mongo_setup", database=mongo_db.name, stdout=StringIO())
    assert set(VALIDATORS) <= set(mongo_db.list_collection_names())
    for name, validator in VALIDATORS.items():
        assert mongo_db[name].options()["validator"] == validator
    assert mongo_db.reviews.index_information()["review_order_line_unique"]["unique"]
    assert not mongo_db.reviews.index_information()["review_olist_source"].get("unique", False)


@pytest.mark.parametrize("field", list(spec()))
def test_spec_missing_outer_field_is_rejected(mongo_db, field):
    document = spec()
    document.pop(field)
    # MongoDB generates _id if omitted, so the server-generated ObjectId is
    # rejected by the product-ID identity rule as well.
    with pytest.raises(WriteError) as error:
        mongo_db.product_specs.insert_one(document)
    assert error.value.code == 121


def test_photo_lookup_uses_its_index_not_a_collection_scan(mongo_db):
    from bson import ObjectId

    call_command("mongo_setup", database=mongo_db.name, stdout=StringIO())
    photo = ObjectId()
    mongo_db.product_specs.insert_many(
        [{**spec(), "_id": n, "photo_file_id": photo if n == 7 else None} for n in range(1, 21)]
    )
    plan = mongo_db.product_specs.find({"photo_file_id": photo}, {"_id": 1}).explain()["queryPlanner"]["winningPlan"]
    assert "spec_photo_file" in str(plan) and "COLLSCAN" not in str(plan)


def test_flexible_attributes_need_no_collmod(mongo_db):
    mongo_db.product_specs.insert_one(spec())
    mongo_db.product_specs.update_one({"_id": 1}, {"$set": {"attributes.new_field": ["new", "shape"]}})
    assert mongo_db.product_specs.find_one({"_id": 1})["attributes"]["new_field"] == ["new", "shape"]


@pytest.mark.django_db(transaction=True)
def test_second_review_for_order_line_is_rejected_but_olist_id_is_not_unique(imported, mongo_db):
    review = mongo_db.reviews.find_one({})
    review.pop("_id")
    with pytest.raises(DuplicateKeyError):
        mongo_db.reviews.insert_one(dict(review))
    review["order_line_id"] = 999999
    mongo_db.reviews.insert_one(review)
    assert mongo_db.reviews.count_documents({"olist_review_id": review["olist_review_id"]}) >= 2


def test_mongo_filter_metacharacters_are_literal_values(mongo_db):
    mongo_db.product_specs.insert_one(spec())
    assert mongo_db.product_specs.find_one({"_id": {"$eq": "$where; dropDatabase()"}}) is None
    assert mongo_db.product_specs.count_documents({}) == 1


def test_setup_database_injection_is_refused_without_touching_collections(mongo_db):
    with pytest.raises(CommandError, match="configured application or test"):
        call_command("mongo_setup", database="test_mercer; db.dropDatabase()", stdout=StringIO())
    assert set(VALIDATORS) <= set(mongo_db.list_collection_names())
