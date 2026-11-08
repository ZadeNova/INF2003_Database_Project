"""The pre-registered B2 variants (amendment m): every pair exists, every variant equals the golden, the summaries rebuild."""

import json
from datetime import date
from pathlib import Path

import pytest

from benchmarks import summaries
from benchmarks.canonical import csv_bytes
from benchmarks.headline import HEADLINE, REFRESH
from benchmarks.report import b2_headline
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
        ("B2c", "mongo", "live"),
        ("B2d", "mongo", "live"),
        ("B2d", "postgres", "live"),
    ]:
        assert find(queries, output, engine, variant), (output, engine, variant)


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
        row("B2a", "postgres", "live", "1", "10"),
        row("B2a", "mongo", "idiomatic", "1", "30"),
        row("B2a", "mongo", "live", "1", "300"),  # an original: reported elsewhere, never a headline
        row("B2refresh", "postgres", "refresh", "1", "5"),
        row("B2refresh", "mongo", "refresh", "1", "10"),
    ]
    table = b2_headline(rows)
    assert [(r["output"], r["layer"], r["postgres_variant"], r["mongo_variant"]) for r in table] == [
        ("B2a", "live", "live", "idiomatic"),
        ("B2refresh", "refresh: daily product sales", "refresh", "refresh"),
    ]
    assert table[0]["mongo_over_postgres"] == 3.0 and table[1]["mongo_over_postgres"] == 2.0


def test_a_pair_is_dropped_when_either_row_failed_and_flagged_when_either_is_not_a_headline():
    rows = [
        row("B2d", "postgres", "live", "1", "10"),
        row("B2d", "mongo", "idiomatic", "1", "20", status="failed"),
        row("B2d", "postgres", "live", "10", "10"),
        row("B2d", "mongo", "idiomatic", "10", "20", headline=False),
    ]
    table = b2_headline(rows)
    assert [(r["clients"], r["headline"]) for r in table] == [("10", False)]
