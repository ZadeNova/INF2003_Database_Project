"""Verified restoration after successful and failed mutating runs."""
import hashlib
import json
from contextlib import contextmanager

from bson import json_util

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
        digest.update((json_util.dumps(doc, json_options=json_util.CANONICAL_JSON_OPTIONS, sort_keys=True) + "\n").encode())
    return digest.hexdigest()


def restore_mongo(database, provenance):
    source = STATE_ROOT / provenance["manifest_sha256"]
    checksums = json.loads((source / "checksums.json").read_text())
    for name in ("products", "orders"):
        path = source / (name + ".ndjson")
        if sha256(path) != checksums[path.name]:
            raise ValueError("Restore snapshot checksum mismatch")
    for name in ("products", "orders"):
        database[name].delete_many({})
        with (source / (name + ".ndjson")).open(encoding="utf-8") as stream:
            for batch in batches(json_util.loads(line) for line in stream):
                database[name].insert_many(batch)


def verify_initial(database, provenance):
    source = STATE_ROOT / provenance["manifest_sha256"]
    checksums = json.loads((source / "checksums.json").read_text())
    for name in ("products", "orders"):
        if mongo_digest(database[name]) != checksums[name + ".ndjson"]:
            raise ValueError("MongoDB baseline differs from snapshot")
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
