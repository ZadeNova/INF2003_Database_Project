"""MongoDB outer schemas and indexes. Flexible attributes are governed by templates."""
from pymongo import ASCENDING, DESCENDING, IndexModel

ID = {"bsonType": ["int", "long"], "minimum": 1}
REVIEW_FIELDS = {
    "order_line_id": ID, "order_id": ID, "checkout_id": ID, "product_id": ID, "seller_id": ID, "customer_id": ID,
    "score": {"bsonType": ["int", "long"], "minimum": 1, "maximum": 5},
    "title_pt": {"bsonType": "string"}, "text_pt": {"bsonType": "string"},
    "title_en": {"bsonType": "string"}, "text_en": {"bsonType": "string"},
    "machine_translated": {"bsonType": "bool"}, "from_order_review": {"bsonType": "bool"},
    "created_at": {"bsonType": "date"}, "answered_at": {"bsonType": "date"},
    "olist_review_id": {"bsonType": ["string", "null"]},
}
SPEC_FIELDS = {
    "_id": ID, "category_id": ID, "description": {"bsonType": "string"},
    "attributes": {"bsonType": "object"}, "photo_file_id": {"bsonType": ["objectId", "null"]},
    "rating_summary": {"bsonType": "object", "required": ["count", "sum", "average", "distribution", "bayesian"],
                       "properties": {"count": {"bsonType": ["int", "long"], "minimum": 0},
                                      "sum": {"bsonType": ["int", "long"], "minimum": 0},
                                      "average": {"bsonType": "decimal"}, "bayesian": {"bsonType": "decimal"},
                                      "distribution": {"bsonType": "object"}}},
    "latest_reviews": {"bsonType": "array", "maxItems": 5}, "has_generated_content": {"bsonType": "bool"},
}


def schema(fields):
    return {"$jsonSchema": {"bsonType": "object", "required": list(fields), "properties": fields}}


VALIDATORS = {
    "reviews": schema(REVIEW_FIELDS),
    "product_specs": schema(SPEC_FIELDS),
    "platform_stats": schema({"_id": {"enum": ["bayesian"]}, "m": {"bsonType": "decimal"}, "C": {"bsonType": "decimal"}}),
    "category_templates": schema({"_id": ID, "category_id": ID, "attributes": {"bsonType": "object"},
                                  "rich": {"bsonType": "bool"}, "has_generated_content": {"bsonType": "bool"},
                                  "version": {"bsonType": ["int", "long"], "minimum": 1}}),
}
INDEXES = {
    "reviews": [IndexModel([("order_line_id", ASCENDING)], unique=True, name="review_order_line_unique"),
                IndexModel([("olist_review_id", ASCENDING)], name="review_olist_source"),
                IndexModel([("product_id", ASCENDING), ("answered_at", DESCENDING)], name="review_product_date")],
    "product_specs": [IndexModel([("category_id", ASCENDING)], name="spec_category")],
    "category_templates": [IndexModel([("category_id", ASCENDING)], unique=True, name="template_category_unique")],
}


def setup(database):
    existing = set(database.list_collection_names())
    for name, validator in VALIDATORS.items():
        if name not in existing:
            database.create_collection(name, validator=validator, validationLevel="strict", validationAction="error")
        else:
            options = database[name].options()
            if options.get("validator") != validator or options.get("validationLevel", "strict") != "strict" or options.get("validationAction", "error") != "error":
                raise ValueError(f"{name}: existing validator differs; reset the local databases or use an explicitly approved schema migration")
        if name in INDEXES:
            database[name].create_indexes(INDEXES[name])
