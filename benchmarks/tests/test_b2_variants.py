"""The pre-registered B2 variants (amendment m): every pair exists, every variant equals the golden, the summaries rebuild."""

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest

from benchmarks import db, idiomatic_sql, summaries
from benchmarks.canonical import csv_bytes
from benchmarks.headline import HEADLINE, REFRESH
from benchmarks.report import b2_headline
from benchmarks.source import ZONE
from benchmarks.workloads import b2

GOLDEN = Path("/app/benchmarks/golden/fixture")


@pytest.fixture(scope="module")
def queries(database):
    as_of = date.fromisoformat(json.loads((GOLDEN / "source.json").read_text())["as_of"])
    return b2.queries(as_of, database.platform_stats.find_one({"_id": "bayesian"}))


def find(queries, output, engine, variant):
    return next((q for q in queries if (q.output, q.engine, q.variant) == (output, engine, variant)), None)


def test_every_pre_registered_variant_exists_on_both_engines(queries):
    for output, layers in HEADLINE.items():
        for layer, (postgres, mongo) in layers.items():
            assert find(queries, output, "postgres", postgres), (output, layer, "postgres", postgres)
            assert find(queries, output, "mongo", mongo), (output, layer, "mongo", mongo)
    for name, (postgres, mongo) in REFRESH.items():
        assert find(queries, "B2refresh", "postgres", postgres), name
        assert find(queries, "B2refresh", "mongo", mongo), name


def test_every_variant_equals_the_independent_golden_output(database, queries):
    checked = 0
    for query in queries:
        if not query.golden:
            continue
        with query.open() as operation:
            assert csv_bytes(query.golden, operation()) == (GOLDEN / f"{query.golden}.csv").read_bytes(), (
                query.output,
                query.engine,
                query.variant,
            )
        checked += 1
    assert checked >= 20  # the originals, the idiomatic variants and the summaries


def test_originals_are_kept_beside_the_new_variants(queries):
    for output, engine, variant in [
        ("B2a", "mongo", "live"),
        ("B2b", "mongo", "live"),
        ("B2b", "postgres", "live"),
        ("B2b", "postgres", "view"),
        ("B2a", "postgres", "live"),
        ("B2a", "postgres", "view"),
        ("B2b", "postgres", "app"),
        ("B2b", "postgres", "app_summary"),
        ("B2c", "mongo", "live"),
        ("B2d", "mongo", "live"),
        ("B2d", "postgres", "live"),
    ]:
        assert find(queries, output, engine, variant), (output, engine, variant)


def test_the_postgres_idiomatic_queries_ask_for_the_golden_columns_only(queries):
    """No display joins: names, shops, checkout and customer rows are not needed by any benchmark column."""
    for output, variant in [
        ("B2a", "idiomatic"),
        ("B2a", "summary"),
        ("B2b", "idiomatic"),
        ("B2b", "summary"),
        ("B2d", "idiomatic"),
    ]:
        statement = find(queries, output, "postgres", variant).statement
        for table in (
            "catalogue_category",
            "accounts_seller",
            "orders_checkout",
            "accounts_customerprofile",
            "accounts_geolocation",
        ):
            assert table not in statement, (output, variant, table)
    assert idiomatic_sql.DELAY_IDIOMATIC.count("JOIN") == 2  # delays with scores, and the lateral delay expression


def test_refresh_pipelines_end_in_out_and_other_pipelines_end_in_a_sort(queries):
    for query in queries:
        if query.engine != "mongo":
            continue
        last = query.pipeline[-1]
        if query.output == "B2refresh":
            assert "$out" in last and query.golden is None
        else:
            assert "$sort" in last, (query.output, query.variant)


@pytest.mark.parametrize("variant", ["refresh", "refresh_scores"])
def test_rebuilding_a_mongo_summary_is_repeatable_and_keeps_its_index(database, queries, variant):
    query = find(queries, "B2refresh", "mongo", variant)
    name = summaries.DAILY if variant == "refresh" else summaries.ORDER_SCORES
    before = database[name].count_documents({})
    with query.open() as operation:
        operation()
        operation()
    assert before > 0 and database[name].count_documents({}) == before
    if name == summaries.DAILY:
        assert database[name].index_information()["bench_daily_sales_product_day"]["unique"]


def test_the_load_built_both_summaries_on_both_engines(database):
    from benchmarks import db

    with db.pg() as conn:
        assert conn.execute("SELECT count(*) AS n FROM bench_order_delivery_scores").fetchone()["n"] > 0
        assert conn.execute("SELECT count(*) AS n FROM daily_product_sales").fetchone()["n"] > 0
    assert database[summaries.DAILY].count_documents({}) > 0
    assert database[summaries.ORDER_SCORES].count_documents({}) > 0


def row(output, engine, variant, clients, p50, *, headline=True, status="passed"):
    return {
        "output": output,
        "engine": engine,
        "variant": variant,
        "clients": clients,
        "p50_ms": p50,
        "status": status,
        "headline": headline,
    }


def test_the_headline_table_pairs_only_the_registered_variants():
    rows = [
        row("B2a", "postgres", "idiomatic", "1", "10"),
        row("B2a", "mongo", "idiomatic", "1", "30"),
        row("B2a", "mongo", "live", "1", "300"),  # an original: reported elsewhere, never a headline
        row("B2refresh", "postgres", "refresh", "1", "5"),
        row("B2refresh", "mongo", "refresh", "1", "10"),
    ]
    table = {(r["output"], r["layer"]): r for r in b2_headline(rows) if r["status"] == "ok"}
    assert [(r["postgres_variant"], r["mongo_variant"]) for r in table.values()] == [
        ("idiomatic", "idiomatic"),
        ("refresh", "refresh"),
    ]
    assert table[("B2a", "live")]["mongo_over_postgres"] == 3.0
    assert table[("B2refresh", "refresh: daily product sales")]["mongo_over_postgres"] == 2.0


def test_a_registered_pair_with_a_failed_or_missing_row_is_listed_not_dropped():
    rows = [
        row("B2d", "postgres", "idiomatic", "1", "10"),
        row("B2d", "mongo", "idiomatic", "1", "20", status="failed"),
        row("B2d", "postgres", "idiomatic", "10", "10"),
        row("B2d", "mongo", "idiomatic", "10", "20", headline=False),
    ]
    live = {r["clients"]: r for r in b2_headline(rows) if r["output"] == "B2d" and r["layer"] == "live"}
    assert live["1"]["status"] == "postgres ok, mongo failed" and live["1"]["mongo_over_postgres"] == ""
    assert live["1"]["headline"] is False
    assert live["10"]["status"] == "ok" and live["10"]["headline"] is False
    maintained = {r["clients"]: r for r in b2_headline(rows) if r["output"] == "B2d" and r["layer"] == "maintained"}
    assert maintained["1"]["status"] == "postgres missing, mongo missing"


def test_an_output_with_no_rows_still_lists_its_registered_pairs():
    rows = [row("B2a", "postgres", "idiomatic", "1", "10"), row("B2a", "mongo", "idiomatic", "1", "30")]
    pairs = {(r["output"], r["layer"]): r for r in b2_headline(rows)}
    assert (
        pairs[("B2d", "live")]["status"] == "postgres missing, mongo missing"
        and pairs[("B2d", "live")]["headline"] is False
    )
    assert pairs[("B2a", "live")]["status"] == "ok"


def test_pairs_from_different_sessions_are_not_one_comparison_even_with_equal_counts():
    postgres = {**row("B2a", "postgres", "idiomatic", "1", "10"), "sessions": 2, "session_numbers": "1;2"}
    mongo = {**row("B2a", "mongo", "idiomatic", "1", "30"), "sessions": 2, "session_numbers": "2;3"}
    live = next(r for r in b2_headline([postgres, mongo]) if r["output"] == "B2a" and r["layer"] == "live")
    assert live["status"] == "ok" and live["headline"] is False
    assert (live["postgres_sessions"], live["mongo_sessions"]) == ("1;2", "2;3")


def test_a_pair_built_from_different_numbers_of_sessions_is_not_a_headline():
    postgres = {**row("B2a", "postgres", "idiomatic", "1", "10"), "sessions": 3}
    mongo = {**row("B2a", "mongo", "idiomatic", "1", "30"), "sessions": 2}
    live = next(r for r in b2_headline([postgres, mongo]) if r["output"] == "B2a" and r["layer"] == "live")
    assert (
        live["status"] == "ok"
        and live["headline"] is False
        and (live["postgres_sessions"], live["mongo_sessions"]) == (3, 2)
    )


# ------------------------------------------------------------------------------------------------------ B1: refreshes
def delivery_summary_rows(queries, engine):
    """The delivery-score summary's bucket counts, as the engine's own `summary` query reports them."""
    query = find(queries, "B2d", engine, "summary")
    with query.open() as operation:
        return {row["bucket"]: row["orders"] for row in operation()}


def live_rows(queries, engine):
    query = find(queries, "B2d", engine, "idiomatic")
    with query.open() as operation:
        return {row["bucket"]: row["orders"] for row in operation()}


def refresh(queries, engine):
    with find(queries, "B2refresh", engine, "refresh_scores").open() as operation:
        operation()


def move_delivery(database, order_id, delivered_at):
    """Change one order's delivery time in both engines. PostgreSQL's change and its trigger switch share one transaction
    (DDL is transactional), so a failure rolls both back and cannot leave the guard trigger off."""
    with db.pg() as conn, conn.transaction():
        conn.execute("ALTER TABLE orders_order DISABLE TRIGGER order_timestamp_guard")
        conn.execute("UPDATE orders_order SET delivered_at = %s WHERE id = %s", (delivered_at, order_id))
        conn.execute(
            "SET CONSTRAINTS ALL IMMEDIATE"
        )  # run the deferred checks now: ALTER TABLE refuses pending trigger events
        conn.execute("ALTER TABLE orders_order ENABLE TRIGGER order_timestamp_guard")
    database.orders.update_one({"_id": order_id}, {"$set": {"delivered_at": delivered_at}})


def test_the_bench_delivery_summary_is_built_from_orders_and_reviews_alone():
    """It must not read the application's richer delivery view: that would charge PostgreSQL display work MongoDB never does."""
    sql = summaries.postgres_order_scores(date(2018, 8, 29))
    assert "order_delivery_summary" not in sql and "geolocation" not in sql and "orders_checkout" not in sql
    assert "FROM orders_order" in sql and "FROM reviews" in sql and "'2018-08-30T00:00:00+08:00'" in sql


def test_each_engines_delivery_refresh_recomputes_a_changed_delivery(database, queries):
    """The refresh must pay for the delay side too: a delivery moved 30 days late has to move its bucket in both summaries."""
    as_of = date.fromisoformat(json.loads((GOLDEN / "source.json").read_text())["as_of"])
    end = datetime.combine(as_of + timedelta(days=1), time.min, ZONE)
    with db.pg() as conn:
        victim = conn.execute(
            "SELECT id, delivered_at, estimated_delivery + interval '30 days' AS later FROM orders_order "
            "WHERE status = 'delivered' AND placed_at < %(end)s AND delivered_at < %(end)s "
            "AND estimated_delivery + interval '30 days' < %(end)s "
            "AND (delivered_at AT TIME ZONE 'Asia/Singapore')::date - (estimated_delivery AT TIME ZONE 'Asia/Singapore')::date <= 14 "
            "ORDER BY id LIMIT 1",
            {"end": end},
        ).fetchone()
    assert victim, "the fixture needs a delivered order that can be moved 30 days late"
    before = {engine: delivery_summary_rows(queries, engine) for engine in ("postgres", "mongo")}
    try:
        move_delivery(database, victim["id"], victim["later"])
        for engine in ("postgres", "mongo"):
            assert delivery_summary_rows(queries, engine) == before[engine], "the summary changed before any refresh"
            assert live_rows(queries, engine) != before[engine], "the live query did not see the moved delivery"
            refresh(queries, engine)
            after = delivery_summary_rows(queries, engine)
            assert after != before[engine], f"{engine}: the refresh left the old bucket in place"
            assert after == live_rows(queries, engine), f"{engine}: the refreshed summary differs from the live query"
            assert after.get("late_over_14", 0) == before[engine].get("late_over_14", 0) + 1
    finally:
        move_delivery(database, victim["id"], victim["delivered_at"])
        for engine in ("postgres", "mongo"):
            refresh(queries, engine)
