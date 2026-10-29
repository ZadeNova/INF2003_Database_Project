"""Verified restoration after successful and failed mutating runs."""

import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timezone

from bson import json_util
from pymongo import IndexModel

from benchmarks import db
from benchmarks.load import STATE_ROOT, batches
from benchmarks.source import manifest, sha256


def verify_manifest(database, source):
    expected = manifest(source)
    with db.pg() as conn:
        sql_manifest = conn.execute("SELECT manifest FROM bench_meta WHERE id=1").fetchone()["manifest"]
    mongo_manifest = database.meta.find_one({"_id": "source"}, {"_id": 0})
    if sql_manifest != mongo_manifest or sql_manifest != expected:
        raise ValueError("Loaded manifests disagree; reload identical verified files")
    return expected


def mongo_digest(collection):
    digest = hashlib.sha256()
    for doc in collection.find().sort("_id", 1):
        digest.update(
            (json_util.dumps(doc, json_options=json_util.CANONICAL_JSON_OPTIONS, sort_keys=True) + "\n").encode()
        )
    return digest.hexdigest()


def restore_mongo(database, provenance):
    source = STATE_ROOT / provenance["manifest_sha256"]
    checksums = json.loads((source / "checksums.json").read_text())
    for name, expected in checksums.items():
        if sha256(source / name) != expected:
            raise ValueError("Restore snapshot checksum mismatch")
    metadata = json_util.loads((source / "collections.json").read_text())
    database.meta.update_one(
        {"_id": "state"}, {"$inc": {"restores_since_load": 1}, "$set": {"restoration_in_progress": True}}
    )
    for name in ("products", "orders"):
        database[name].drop()
        database.create_collection(name, **metadata[name]["options"])
        with (source / (name + ".ndjson")).open(encoding="utf-8") as stream:
            for batch in batches(json_util.loads(line) for line in stream):
                database[name].insert_many(batch)
        # Match a fresh load: insert in source-ID order first, then bulk-build secondary indexes.
        indexes = [
            IndexModel(index["key"], **{k: v for k, v in index.items() if k not in {"key", "ns"}})
            for index in metadata[name]["indexes"]
            if index["name"] != "_id_"
        ]
        if indexes:
            database[name].create_indexes(indexes)
    verify_mongo(database, provenance)
    database.meta.update_one(
        {"_id": "state"},
        {"$set": {"restoration_in_progress": False, "physical_state_changed_at": datetime.now(timezone.utc)}},
    )


def restores_since_load(database):
    state = database.meta.find_one({"_id": "state"})
    if state is None or state.get("restoration_in_progress"):
        raise ValueError("Missing load state or incomplete restoration; reload this project")
    return state["restores_since_load"]


def verify_mongo(database, provenance):
    source = STATE_ROOT / provenance["manifest_sha256"]
    checksums = json.loads((source / "checksums.json").read_text())
    metadata = json_util.loads((source / "collections.json").read_text())
    for name in ("products", "orders"):
        if mongo_digest(database[name]) != checksums[name + ".ndjson"]:
            raise ValueError("MongoDB baseline differs from snapshot")
        actual = [
            {**dict(index), "key": [list(pair) for pair in index["key"].items()]}
            for index in database[name].list_indexes()
        ]
        if sorted(actual, key=lambda i: i["name"]) != sorted(metadata[name]["indexes"], key=lambda i: i["name"]):
            raise ValueError("MongoDB index catalogue differs from snapshot")
        if database[name].options() != metadata[name]["options"]:
            raise ValueError("MongoDB collection options differ from snapshot")
    return True


def verify_initial(database, provenance):
    restores_since_load(database)
    verify_mongo(database, provenance)
    # PostgreSQL's template clone has identical physical contents. Check the data that these workloads mutate.
    with db.pg() as base, db.pg("bench_run") as run:
        for statement in (
            "SELECT count(*) AS n, sum(stock) AS stock FROM catalogue_product",
            "SELECT count(*) AS n, sum(total) AS total FROM orders_order",
            "SELECT count(*) AS n, sum(total) AS total FROM orders_checkout",
            "SELECT count(*) AS n, sum(amount) AS total FROM orders_payment",
            "SELECT count(*) AS n, sum(quantity) AS units, sum(quantity*unit_price) AS total FROM orders_orderline",
        ):
            if base.execute(statement).fetchone() != run.execute(statement).fetchone():
                raise ValueError("PostgreSQL baseline differs from template source")
    return True


@contextmanager
def isolated_run(database, provenance, evidence):
    db.recreate("bench_run", "bench_template")
    verify_initial(database, provenance)
    evidence["initial_verified"] = True
    try:
        yield
    finally:
        # Both restores are attempted even if one fails. Failure remains visible to the caller.
        try:
            db.recreate("bench_run", "bench_template")
        finally:
            restore_mongo(database, provenance)
        evidence["restored"] = verify_initial(database, provenance)
