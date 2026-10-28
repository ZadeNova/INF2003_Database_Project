"""Physical footprint after checkpoints; data and index bytes stay separate."""
import time
from datetime import datetime, timezone

from benchmarks import db
from benchmarks.state import restore_mongo, restores_since_load

STORAGE_RELATIVE_TOLERANCE = 0.10
STORAGE_ABSOLUTE_TOLERANCE = 64 * 1024
MONGO_STORAGE_SETTLE_SECONDS = 65


def settle_storage(database):
    # The readWrite user cannot issue cluster-wide fsync. The bench server explicitly checkpoints
    # every 60 seconds; wait one interval plus a margin after the last load/restore instead.
    state = database.meta.find_one({"_id": "state"})
    if state is None or state.get("restoration_in_progress"):
        raise ValueError("Missing or incomplete physical load state")
    changed = state["physical_state_changed_at"]
    if changed.tzinfo is None:
        changed = changed.replace(tzinfo=timezone.utc)
    remaining = MONGO_STORAGE_SETTLE_SECONDS - (datetime.now(timezone.utc) - changed).total_seconds()
    if remaining > 0:
        print("Waiting for the automatic MongoDB checkpoint before physical storage statistics.", flush=True)
    deadline = time.monotonic() + max(0, remaining)
    while time.monotonic() < deadline:
        time.sleep(max(0, min(1, deadline - time.monotonic())))


def mongo_footprint(database):
    settle_storage(database)
    result = []
    for name in ("products", "orders", "reviews"):
        stats = next(database[name].aggregate([{"$collStats": {"storageStats": {"scale": 1}}}]))["storageStats"]
        result.append({"engine": "mongo", "representation": name, "data_bytes": stats["storageSize"], "index_bytes": stats["totalIndexSize"], "cache_bytes": int(.75 * 1024**3)})
    return result


def restore_storage_audit(database, provenance, baseline):
    """A correctness audit, not accepted B5 storage measurements after restoration."""
    if restores_since_load(database) != 0:
        raise ValueError("Storage restore audit requires a freshly loaded project")
    rows = [{**row, "cycle": 0, "within_tolerance": True} for row in baseline if row["engine"] == "mongo" and row["representation"] in {"products", "orders"}]
    fresh = {row["representation"]: row for row in rows}
    for cycle in (1, 2):
        restore_mongo(database, provenance)
        for row in mongo_footprint(database):
            if row["representation"] not in fresh:
                continue
            original = fresh[row["representation"]]
            tolerance = {key: max(STORAGE_ABSOLUTE_TOLERANCE, original[key] * STORAGE_RELATIVE_TOLERANCE) for key in ("data_bytes", "index_bytes")}
            passed = all(abs(row[key] - original[key]) <= tolerance[key] for key in tolerance)
            rows.append({**row, "cycle": cycle, "within_tolerance": passed})
    return rows


def footprint(database):
    if restores_since_load(database) != 0:
        raise ValueError("B5 requires no restore since load; use a fresh project")
    tables = ("catalogue_product", "orders_checkout", "orders_order", "orders_orderline", "orders_payment", "reviews",
              "bench_attribute_eav", "bench_attribute_jsonb", "daily_product_sales")
    result = []
    with db.pg() as conn:
        conn.execute("VACUUM (ANALYZE)")
        conn.execute("CHECKPOINT")
        for table in tables:
            row = conn.execute("SELECT pg_relation_size(%s::regclass) AS data_bytes, pg_indexes_size(%s::regclass) AS index_bytes", [table, table]).fetchone()
            result.append({"engine": "postgres", "representation": table, **row, "cache_bytes": 512 * 1024 * 1024})
    return result + mongo_footprint(database)
