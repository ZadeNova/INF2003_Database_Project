"""MongoDB outer schemas and indexes. Flexible attributes are governed by templates."""

from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.errors import CollectionInvalid

ID = {"bsonType": ["int", "long"], "minimum": 1}
REVIEW_FIELDS = {
    "order_line_id": ID,
    "order_id": ID,
    "checkout_id": ID,
    "product_id": ID,
    "seller_id": ID,
    "customer_id": ID,
    "score": {"bsonType": ["int", "long"], "minimum": 1, "maximum": 5},
    "title_pt": {"bsonType": "string"},
    "text_pt": {"bsonType": "string"},
    "title_en": {"bsonType": "string"},
    "text_en": {"bsonType": "string"},
    "machine_translated": {"bsonType": "bool"},
    "from_order_review": {"bsonType": "bool"},
    "created_at": {"bsonType": "date"},
    "answered_at": {"bsonType": "date"},
    "olist_review_id": {"bsonType": ["string", "null"]},
}
SPEC_FIELDS = {
    "_id": ID,
    "category_id": ID,
    "description": {"bsonType": "string"},
    "attributes": {"bsonType": "object"},
    "photo_file_id": {"bsonType": ["objectId", "null"]},
    "rating_summary": {
        "bsonType": "object",
        "required": ["count", "sum", "average", "distribution", "bayesian"],
        "properties": {
            "count": {"bsonType": ["int", "long"], "minimum": 0},
            "sum": {"bsonType": ["int", "long"], "minimum": 0},
            "average": {"bsonType": "decimal"},
            "bayesian": {"bsonType": "decimal"},
            "distribution": {"bsonType": "object"},
        },
    },
    "latest_reviews": {"bsonType": "array", "maxItems": 5},
    "has_generated_content": {"bsonType": "bool"},
}
# One document per order that has visible scores up to the reporting date: the integer sum and count of those scores.
# It is derived from `reviews` (an on-demand materialized view rebuilt with `$out`,
# docs/plans/dashboard_summaries.md) and is never edited by hand.
ORDER_SCORE_FIELDS = {
    "_id": ID,  # the order id
    "total": {"bsonType": ["int", "long"], "minimum": 1},
    "count": {"bsonType": ["int", "long"], "minimum": 1},
    "as_of": {"bsonType": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},  # the reporting date, ISO
}


def schema(fields):
    return {"$jsonSchema": {"bsonType": "object", "required": list(fields), "properties": fields}}


VALIDATORS = {
    "reviews": schema(REVIEW_FIELDS),
    "product_specs": schema(SPEC_FIELDS),
    "platform_stats": schema(
        {"_id": {"enum": ["bayesian"]}, "m": {"bsonType": "decimal"}, "C": {"bsonType": "decimal"}}
    ),
    "category_templates": schema(
        {
            "_id": ID,
            "category_id": ID,
            "attributes": {"bsonType": "object"},
            "rich": {"bsonType": "bool"},
            "has_generated_content": {"bsonType": "bool"},
            "version": {"bsonType": ["int", "long"], "minimum": 1},
        }
    ),
    "order_review_scores": schema(ORDER_SCORE_FIELDS),
}
INDEXES = {
    "reviews": [
        IndexModel([("order_line_id", ASCENDING)], unique=True, name="review_order_line_unique"),
        IndexModel([("olist_review_id", ASCENDING)], name="review_olist_source"),
        IndexModel([("product_id", ASCENDING), ("answered_at", DESCENDING)], name="review_product_date"),
        IndexModel([("seller_id", ASCENDING), ("answered_at", DESCENDING)], name="review_seller_date"),
        # Recomputing one order's score summary after a review write reads that order's reviews.
        IndexModel([("order_id", ASCENDING)], name="review_order"),
        # The operator list sorts every review newest first; without this it sorts them all in memory on each page.
        IndexModel(
            [("answered_at", DESCENDING), ("olist_review_id", DESCENDING), ("order_line_id", DESCENDING)],
            name="review_newest",
        ),
    ],
    "product_specs": [
        IndexModel([("category_id", ASCENDING)], name="spec_category"),
        # Wildcard indexing includes future template fields and becomes multikey for array values.
        IndexModel([("attributes.$**", ASCENDING)], name="spec_attributes"),
        # The photo endpoint resolves a GridFS id to its product; without this every image is a scan.
        IndexModel([("photo_file_id", ASCENDING)], name="spec_photo_file"),
    ],
    "category_templates": [IndexModel([("category_id", ASCENDING)], unique=True, name="template_category_unique")],
}

EVENT_TTL_SECONDS = 30 * 24 * 60 * 60
EVENT_INDEXES = [
    IndexModel([("meta.product_id", ASCENDING), ("ts", DESCENDING)], name="event_product_time"),
    IndexModel([("meta.user_id", ASCENDING), ("ts", DESCENDING)], name="event_user_time"),
    IndexModel([("meta.session_key", ASCENDING), ("ts", DESCENDING)], name="event_session_time"),
    IndexModel([("meta.type", ASCENDING), ("ts", DESCENDING)], name="event_type_time"),
    IndexModel(
        [("meta.category", ASCENDING), ("meta.type", ASCENDING), ("ts", DESCENDING)], name="event_category_time"
    ),
]


def setup_events(database):
    if "events" not in database.list_collection_names():
        database.create_collection(
            "events",
            timeseries={"timeField": "ts", "metaField": "meta", "granularity": "seconds"},
            expireAfterSeconds=EVENT_TTL_SECONDS,
        )
    options = database.events.options()
    if (
        options.get("timeseries", {}).get("timeField") != "ts"
        or options.get("timeseries", {}).get("metaField") != "meta"
        or options.get("timeseries", {}).get("granularity") != "seconds"
        or options.get("expireAfterSeconds") != EVENT_TTL_SECONDS
    ):
        raise ValueError("events: existing time-series options differ; use an explicitly approved schema migration")
    database.events.create_indexes(EVENT_INDEXES)


def create_validated(database, name):
    database.create_collection(name, validator=VALIDATORS[name], validationLevel="strict", validationAction="error")


def ensure_collection(database, name):
    """Create a validated collection if it is missing, so that a `$merge` never creates it without its validator."""
    if name not in database.list_collection_names():
        try:
            create_validated(database, name)
        except CollectionInvalid:  # created by another request meanwhile
            pass


def setup(database):
    existing = set(database.list_collection_names())
    for name, validator in VALIDATORS.items():
        if name not in existing:
            create_validated(database, name)
        else:
            options = database[name].options()
            if (
                options.get("validator") != validator
                or options.get("validationLevel", "strict") != "strict"
                or options.get("validationAction", "error") != "error"
            ):
                raise ValueError(
                    f"{name}: existing validator differs; reset the local databases or use an explicitly approved schema migration"
                )
        if name in INDEXES:
            database[name].create_indexes(INDEXES[name])
    setup_events(database)
