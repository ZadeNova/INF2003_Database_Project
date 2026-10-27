"""Physical footprint after a checkpoint; data and index bytes stay separate."""
from benchmarks import db


def footprint(database):
    tables = ("catalogue_product", "orders_checkout", "orders_order", "orders_orderline", "orders_payment", "reviews",
              "bench_attribute_eav", "bench_attribute_jsonb", "daily_product_sales")
    result = []
    with db.pg() as conn:
        conn.execute("VACUUM (ANALYZE)")
        conn.execute("CHECKPOINT")
        for table in tables:
            row = conn.execute("SELECT pg_relation_size(%s::regclass) AS data_bytes, pg_indexes_size(%s::regclass) AS index_bytes", [table, table]).fetchone()
            result.append({"engine": "postgres", "representation": table, **row, "cache_bytes": 512 * 1024 * 1024})
    for name in ("products", "orders", "reviews"):
        stats = next(database[name].aggregate([{"$collStats": {"storageStats": {"scale": 1}}}]))["storageStats"]
        result.append({"engine": "mongo", "representation": name, "data_bytes": stats["storageSize"], "index_bytes": stats["totalIndexSize"], "cache_bytes": int(.75 * 1024**3)})
    return result
