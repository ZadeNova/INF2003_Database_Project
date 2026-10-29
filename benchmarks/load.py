"""Load the same verified clean files through the app importer, then add bench-only models."""

import argparse
import itertools
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from bson import Decimal128, json_util
from psycopg.types.json import Jsonb

from benchmarks import db
from benchmarks.source import csv_rows, instant, manifest, ndjson, sha256

DDL = """
CREATE TABLE bench_meta (id integer PRIMARY KEY CHECK(id=1), manifest jsonb NOT NULL);
CREATE TABLE bench_attribute_eav (
 product_id bigint REFERENCES catalogue_product(id), key text NOT NULL,
 value_text text, value_int bigint, value_bool boolean,
 PRIMARY KEY(product_id,key), CHECK(num_nonnulls(value_text,value_int,value_bool)=1));
CREATE TABLE bench_attribute_jsonb (product_id bigint PRIMARY KEY REFERENCES catalogue_product(id), attributes jsonb NOT NULL CHECK(jsonb_typeof(attributes)='object'));
CREATE TABLE reviews (id bigint PRIMARY KEY, product_id bigint NOT NULL REFERENCES catalogue_product(id),
 order_id bigint NOT NULL REFERENCES orders_order(id), score integer NOT NULL CHECK(score BETWEEN 1 AND 5),
 answered_at timestamptz NOT NULL, from_order_review boolean NOT NULL, taken_down boolean NOT NULL);
CREATE INDEX bench_eav_text ON bench_attribute_eav(key,value_text,product_id) WHERE value_text IS NOT NULL;
CREATE INDEX bench_eav_int ON bench_attribute_eav(key,value_int,product_id) WHERE value_int IS NOT NULL;
CREATE INDEX bench_eav_bool ON bench_attribute_eav(key,value_bool,product_id) WHERE value_bool IS NOT NULL;
CREATE INDEX bench_jsonb_gin ON bench_attribute_jsonb USING gin(attributes jsonb_path_ops);
CREATE INDEX bench_jsonb_age_months ON bench_attribute_jsonb (((attributes->>'age_months')::bigint));
CREATE INDEX bench_jsonb_age_years ON bench_attribute_jsonb (((attributes->>'age_years')::bigint));
CREATE INDEX bench_jsonb_volume_ml ON bench_attribute_jsonb (((attributes->>'volume_ml')::bigint));
CREATE INDEX bench_jsonb_capacity_ml ON bench_attribute_jsonb (((attributes->>'capacity_ml')::bigint));
CREATE INDEX bench_review_product_date ON reviews(product_id,answered_at);
CREATE INDEX bench_review_visible ON reviews(answered_at,order_id) WHERE NOT taken_down AND NOT from_order_review;
"""
STATE_ROOT = Path("/app/benchmarks/results/.state")


def batches(iterable, size=500):
    iterator = iter(iterable)
    while batch := list(itertools.islice(iterator, size)):
        yield batch


def bson_value(value):
    if isinstance(value, Decimal):
        return Decimal128(value)
    if isinstance(value, dict):
        return {k: bson_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [bson_value(v) for v in value]
    return value


def build_models(source, database, provenance):
    with db.pg() as conn:
        with conn.transaction():
            conn.execute(DDL)
            conn.execute("INSERT INTO bench_meta VALUES (1,%s)", [Jsonb(provenance)])
            with conn.cursor().copy("COPY bench_attribute_eav FROM STDIN") as copy:
                for spec in ndjson(source, "product_specs"):
                    for key, value in spec["attributes"].items():
                        copy.write_row(
                            (
                                spec["_id"],
                                key,
                                value if type(value) is str else None,
                                value if type(value) is int else None,
                                value if type(value) is bool else None,
                            )
                        )
            with conn.cursor().copy("COPY bench_attribute_jsonb FROM STDIN") as copy:
                for spec in ndjson(source, "product_specs"):
                    copy.write_row((spec["_id"], Jsonb(spec["attributes"])))
            with conn.cursor().copy("COPY reviews FROM STDIN") as copy:
                for review in ndjson(source, "reviews"):
                    copy.write_row(
                        (
                            review["_id"],
                            review["product_id"],
                            review["order_id"],
                            review["score"],
                            review["answered_at"],
                            review["from_order_review"],
                            review.get("taken_down", False),
                        )
                    )
        conn.execute("VACUUM (ANALYZE)")
        conn.execute("CHECKPOINT")
    products = {int(p["id"]): p for p in csv_rows(source, "products")}
    sellers = {int(s["id"]): s for s in csv_rows(source, "sellers")}
    checkouts = {int(c["id"]): int(c["customer_id"]) for c in csv_rows(source, "checkouts")}
    database.create_collection(
        "products",
        validator={
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["_id", "seller_id", "category_id", "price", "stock", "attributes"],
                "properties": {
                    "price": {"bsonType": "decimal", "minimum": Decimal128("0")},
                    "stock": {"bsonType": "int", "minimum": 0},
                    "attributes": {"bsonType": "object"},
                },
            }
        },
    )
    database.create_collection(
        "orders",
        validator={
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["_id", "seller_id", "lines", "paid_amount"],
                "properties": {
                    "paid_amount": {"bsonType": "decimal", "minimum": Decimal128("0")},
                    "lines": {"bsonType": "array", "minItems": 1},
                },
            }
        },
    )

    def product_docs():
        for spec in ndjson(source, "product_specs"):
            p = products[spec["_id"]]
            yield {
                "_id": spec["_id"],
                "seller_id": int(p["seller_id"]),
                "category_id": int(p["category_id"]),
                "price": Decimal128(p["price"]),
                "freight": Decimal128(p["freight"]),
                "stock": int(p["stock"]),
                "lead_time_days": int(p["lead_time_days"]),
                "purchasable": p["active"] == "True"
                and p["taken_down"] != "True"
                and sellers[int(p["seller_id"])]["status"] == "approved",
                "attributes": spec["attributes"],
                "has_generated_content": p["has_generated_content"] == "True",
                "is_generated": False,
            }

    for batch in batches(product_docs()):
        database.products.insert_many(batch)
    lines = defaultdict(list)
    for line in csv_rows(source, "order_lines"):
        lines[int(line["order_id"])].append(
            {
                "product_id": int(line["product_id"]),
                "category_id": int(products[int(line["product_id"])]["category_id"]),
                "quantity": int(line["quantity"]),
                "unit_price": Decimal128(line["unit_price"]),
                "freight": Decimal128(line["freight"]),
            }
        )

    def order_docs():
        for order in csv_rows(source, "orders"):
            yield {
                "_id": int(order["id"]),
                "checkout_id": int(order["checkout_id"]),
                "customer_id": checkouts[int(order["checkout_id"])],
                "seller_id": int(order["seller_id"]),
                "status": order["status"],
                "paid_amount": Decimal128(order["total"]),
                **{
                    key: instant(order[key])
                    for key in ("placed_at", "delivered_at", "cancelled_at", "estimated_delivery")
                },
                "lines": lines[int(order["id"])],
                "is_generated": False,
            }

    for batch in batches(order_docs()):
        database.orders.insert_many(batch)
    database.products.create_index([("attributes.$**", 1)], name="spec_attributes")
    database.products.create_index(
        [("purchasable", 1), ("_id", 1)], partialFilterExpression={"purchasable": True}, name="bench_product_visible"
    )
    database.orders.create_index([("status", 1), ("placed_at", 1)], name="bench_order_status_date")
    database.orders.create_index([("lines.product_id", 1), ("placed_at", 1)], name="bench_order_product_date")
    database.reviews.create_index([("order_id", 1), ("answered_at", 1)], name="bench_review_order_date")
    database.reviews.create_index(
        [("answered_at", 1), ("order_id", 1)],
        partialFilterExpression={"taken_down": False, "from_order_review": False},
        name="bench_review_visible",
    )
    # Missing taken_down is visible in app documents; the partial-index example uses a bench-normalised flag.
    database.reviews.update_many({"taken_down": {"$exists": False}}, {"$set": {"taken_down": False}})
    database.meta.insert_one({"_id": "source", **provenance})
    database.meta.insert_one(
        {
            "_id": "state",
            "restores_since_load": 0,
            "restoration_in_progress": False,
            "physical_state_changed_at": datetime.now(timezone.utc),
        }
    )
    snapshot(database, provenance)


def snapshot(database, provenance):
    target = STATE_ROOT / provenance["manifest_sha256"]
    target.mkdir(parents=True, exist_ok=True)
    files = {}
    for name in ("products", "orders"):
        path = target / (name + ".ndjson")
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            for doc in database[name].find().sort("_id", 1):
                stream.write(json_util.dumps(doc, json_options=json_util.CANONICAL_JSON_OPTIONS, sort_keys=True) + "\n")
        files[path.name] = sha256(path)
    metadata = {}
    for name in ("products", "orders"):
        metadata[name] = {
            "options": database[name].options(),
            "indexes": [{**dict(index), "key": list(index["key"].items())} for index in database[name].list_indexes()],
        }
    path = target / "collections.json"
    path.write_text(json_util.dumps(metadata, json_options=json_util.CANONICAL_JSON_OPTIONS) + "\n", encoding="utf-8")
    files[path.name] = sha256(path)
    (target / "checksums.json").write_text(json.dumps(files, sort_keys=True))


def load(source):
    db.guard()
    provenance = manifest(source)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.core.management import call_command
    from django.db import connections

    call_command("migrate", interactive=False)
    call_command("import_olist", source=str(source))
    connections.close_all()
    with db.mongo() as database:
        build_models(source, database, provenance)
    db.recreate("bench_template", "bench")
    print(json.dumps({"load": "passed", **provenance}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    load(parser.parse_args().source)


if __name__ == "__main__":
    main()
