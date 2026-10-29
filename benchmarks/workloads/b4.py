"""One-index-at-a-time comparisons, restoring the full index catalogue even on failure."""

from contextlib import contextmanager
from dataclasses import replace

from psycopg import sql

from benchmarks import db


def cases(b1_queries, b2_queries, parameters):
    def find(queries, output, engine, variant):
        return next(q for q in queries if (q.output, q.engine, q.variant) == (output, engine, variant))

    range_key = next(p for p in parameters if p["name"] == "range")["predicates"][0][0]
    rating = find(b2_queries, "B2c", "mongo", "live")
    # A fixed selective example isolates the index's benefit without multiplying a full review scan
    # by every product after its lookup index is removed. Its golden comes from the independent oracle.
    rating = replace(
        rating,
        output="B2c_index",
        golden="B2c_index",
        pipeline=[{"$match": {"_id": 1}}] + rating.pipeline + [{"$match": {"entity": "product"}}],
    )
    return [
        ("btree", "bench_jsonb_" + range_key, find(b1_queries, "B1_range", "postgres", "jsonb")),
        ("composite", "bench_eav_text", find(b1_queries, "B1_selective", "postgres", "eav")),
        ("partial", "bench_eav_bool", find(b1_queries, "B1_boolean", "postgres", "eav")),
        ("gin", "bench_jsonb_gin", find(b1_queries, "B1_selective", "postgres", "jsonb")),
        ("compound", "review_product_date", rating),
        ("wildcard", "spec_attributes", find(b1_queries, "B1_selective", "mongo", "documents")),
        ("partial", "bench_product_visible", find(b2_queries, "B2b", "mongo", "live")),
    ]


def index_catalogue(database):
    with db.pg() as conn:
        postgres = conn.execute(
            "SELECT indexname,indexdef FROM pg_indexes WHERE schemaname=%s ORDER BY indexname", ["public"]
        ).fetchall()
    return {
        "postgres": postgres,
        "mongo": {
            name: sorted(
                (
                    {**dict(index), "key_sequence": list(index["key"].items())}
                    for index in database[name].list_indexes()
                ),
                key=lambda i: i["name"],
            )
            for name in ("products", "orders", "reviews")
        },
    }


@contextmanager
def dropped(query, name, database, evidence):
    initial = index_catalogue(database)
    evidence["initial_index_catalogue"] = initial
    if query.engine == "postgres":
        definition = next(row["indexdef"] for row in initial["postgres"] if row["indexname"] == name)
        with db.pg() as conn:
            conn.execute(sql.SQL("DROP INDEX {}").format(sql.Identifier(name)))
    else:
        collection = next(
            coll for coll, indexes in initial["mongo"].items() if any(row["name"] == name for row in indexes)
        )
        definition = next(row.copy() for row in initial["mongo"][collection] if row["name"] == name)
        database[collection].drop_index(name)
    restored = False

    def restore():
        nonlocal restored
        if restored:
            return
        if query.engine == "postgres":
            with db.pg() as conn:
                conn.execute(definition)
                conn.execute("ANALYZE")
        else:
            options = {k: v for k, v in definition.items() if k not in {"key", "v", "ns", "key_sequence"}}
            database[collection].create_index(list(definition["key"].items()), **options)
        restored = True

    try:
        yield restore
    finally:
        restore()
        evidence["index_set_restored"] = index_catalogue(database) == initial
        if not evidence["index_set_restored"]:
            raise ValueError("Index set did not return to its initial state")
