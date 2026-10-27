import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest

from benchmarks import db
from benchmarks.canonical import canonical
from benchmarks.harness import golden_files, query_run
from benchmarks.reference.compute import generate
from benchmarks.report import report
from benchmarks.results import Recorder
from benchmarks.source import sha256
from benchmarks.state import isolated_run, verify_initial, verify_manifest
from benchmarks.workloads import b1, b2, b3, b4, b6


def test_reference_determinism_and_committed_outputs(source, tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    generate(source, first)
    generate(source, second)
    committed = Path("/app/benchmarks/golden/fixture")
    for path in first.iterdir():
        assert path.read_bytes() == (second / path.name).read_bytes() == (committed / path.name).read_bytes()
    reference_sources = [p.read_text() for p in Path("/app/benchmarks/reference").glob("*.py")]
    assert all("psycopg" not in text and "pymongo" not in text and "dashboard.queries" not in text for text in reference_sources)


def test_canonical_half_even_and_exact_types():
    rows = [{"entity": "product", "entity_id": 1, "review_count": 1, "score_sum": 1, "bayesian": Decimal("1.2345665")}]
    assert canonical("B2c", rows)[0][-1] == "1.234566"
    rows[0]["bayesian"] = 1.2
    with pytest.raises(ValueError):
        canonical("B2c", rows)


def test_manifest_disagreement_refuses_before_timing(database, source):
    original = database.meta.find_one({"_id": "source"})
    try:
        database.meta.update_one({"_id": "source"}, {"$set": {"manifest_sha256": "0" * 64}})
        with pytest.raises(ValueError, match="manifests disagree"):
            verify_manifest(database, source)
    finally:
        database.meta.replace_one({"_id": "source"}, original)
    verify_manifest(database, source)


def test_live_sales_cte_equals_materialized_view(database):
    definition = b2.view_select()
    with db.pg() as conn:
        assert not conn.execute("WITH live AS (" + definition + ") (SELECT * FROM live EXCEPT SELECT * FROM daily_product_sales) UNION ALL (SELECT * FROM daily_product_sales EXCEPT SELECT * FROM live)").fetchall()


@pytest.mark.parametrize("engine", ["eav", "jsonb", "documents"])
def test_b1_injection_is_literal_on_real_engines(database, engine):
    query = next(q for q in b1.queries({"name": "injection", "predicates": [["material", "eq", "' OR 1=1; DROP TABLE catalogue_product; --"]]}) if q.variant == engine)
    with query.open() as operation:
        assert operation() == []
    with db.pg() as conn:
        assert conn.execute("SELECT count(*) AS n FROM catalogue_product").fetchone()["n"] > 0


@pytest.mark.parametrize("value", [{"$ne": None}, ["cotton"], {"$where": "return true"}, None])
def test_mongo_operator_injection_and_non_scalars_rejected(value):
    with pytest.raises(ValueError):
        b1.queries({"name": "injection", "predicates": [["material", "eq", value]]})


def test_range_and_identifiers_reject_injection(database):
    for predicate in (["age_months", "gte", "0); DROP TABLE reviews; --"], ["$where", "eq", "x"], ["material.foo", "eq", "x"]):
        with pytest.raises(ValueError):
            b1.queries({"name": "injection", "predicates": [predicate]})
    with pytest.raises(ValueError):
        db.recreate("bench; DROP DATABASE bench", "bench_template")
    with db.pg() as conn:
        with pytest.raises(psycopg.errors.InvalidDatetimeFormat):
            conn.execute("SELECT public.dashboard_as_of() < %s::date", ["2026-01-01'; DROP TABLE reviews; --"])
        assert conn.execute("SELECT count(*) AS n FROM reviews").fetchone()["n"] > 0


@pytest.mark.parametrize("engine,triggers,clients", [("postgres", False, 50), ("postgres", True, 50), ("mongo", True, 50)])
def test_b3_real_constraints_and_race(database, provenance, engine, triggers, clients):
    evidence = {}
    with isolated_run(database, provenance, evidence):
        records, elapsed, passed, invariants = b3.race(engine, clients, triggers, database)
        assert passed, invariants
        assert len(records) == 50 and elapsed > 0
        assert (invariants["successes"], invariants["refusals"], invariants["stock"], invariants["orders"]) == (10, 40, 0, 10)
        if engine == "postgres":
            assert all(row["tgenabled"] == ("O" if triggers else "D") for row in invariants["trigger_state"])
    assert evidence == {"initial_verified": True, "restored": True}


@pytest.mark.parametrize("engine,strategy", [(engine, strategy) for engine, strategies in b6.STRATEGIES.items() for strategy in strategies])
def test_b6_deterministic_anomalies_and_retries(database, provenance, engine, strategy):
    evidence = {}
    with isolated_run(database, provenance, evidence):
        records, elapsed, passed, invariants = b6.demonstrate(engine, strategy, database)
        assert passed, invariants
        assert not any(row["error"] for row in records)
    assert evidence["restored"]


@pytest.mark.parametrize("force_failure", [False, True])
def test_restore_after_success_and_forced_failure(database, provenance, force_failure):
    evidence = {}
    try:
        with isolated_run(database, provenance, evidence):
            with db.pg("bench_run") as conn:
                conn.execute("UPDATE catalogue_product SET stock=stock+1")
            database.products.update_many({}, {"$inc": {"stock": 1}})
            if force_failure:
                raise RuntimeError("deliberate failure after committed writes")
    except RuntimeError:
        assert force_failure
    assert evidence["initial_verified"] and evidence["restored"]
    assert verify_initial(database, provenance)


def test_b4_restores_indexes_after_failure(database, provenance):
    expected, parameters, source, hashes = golden_files("/app/benchmarks/golden/fixture", provenance)
    query = b1.queries(parameters[0])[1]
    before = b4.index_catalogue(database)
    evidence = {}
    with pytest.raises(RuntimeError):
        with b4.dropped(query, "bench_jsonb_gin", database, evidence):
            raise RuntimeError("forced index test failure")
    assert evidence["index_set_restored"] and b4.index_catalogue(database) == before


def test_bm4_corrupted_result_and_real_violated_invariant_supply_no_accepted_timing(database, provenance, tmp_path):
    expected, parameters, source, hashes = golden_files("/app/benchmarks/golden/fixture", provenance)
    query = b1.queries(parameters[0])[0]
    expected[query.golden] = b"deliberately corrupted golden rows"
    records, elapsed, passed = query_run(query, 1, 1, expected)
    assert not passed and records[0]["error"] == "GoldenMismatch"
    recorder = Recorder(tmp_path, "measure", {"test": "BM4"})
    recorder.record(query.output, query.engine, query.variant, 1, 1, "measured", records, elapsed, passed)
    evidence = {}
    with isolated_run(database, provenance, evidence):
        database.products.update_one({"_id": 1}, {"$set": {"stock": 1}})
        observed = database.products.find_one({"_id": 1})["stock"]
        recorder.record("B3", "mongo", "deliberate_invariant_failure", 1, 1, "measured", [{"latency_ns": 123}], 123, observed == 0,
                        {"expected_stock": 0, "observed_stock": observed})
    summary = list(csv.DictReader((tmp_path / "summary.csv").open()))
    assert len(summary) == 2 and all(row["status"] == "failed" and row["p50_ms"] == row["p95_ms"] == row["throughput_ops_s"] == "" for row in summary)
    raw = [json.loads(line) for line in (tmp_path / "raw.jsonl").read_text().splitlines()]
    assert all(not row["accepted"] for row in raw)
    assert all(row["accepted_latency_ns"] is None for row in raw if row["kind"] == "operation")
    assert recorder.failed and evidence["restored"]


def test_golden_schema_and_source_checksums_are_recordable(provenance):
    path = Path("/app/benchmarks/golden/fixture/checksums.txt")
    assert len(sha256(path)) == 64
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sha256(path)


def test_report_preserves_success_and_failure_with_different_diagnostic_fields(tmp_path):
    recorder = Recorder(tmp_path, "correctness", {})
    recorder.record("B6", "postgres", "read_committed", 2, 1, "demonstration", [{"latency_ns": 1}], 1, True,
                    {"expected_stock": 9, "observed_stock": 9, "retries": 0})
    recorder.record("B6", "mongo", "transaction", 2, 1, "demonstration", [{"latency_ns": 0, "error": "DeliberateFailure"}], 0, False,
                    {"exception_class": "DeliberateFailure", "restored": True})
    report(tmp_path)
    states = list(csv.DictReader((tmp_path / "report/B6-states.csv").open()))
    assert [row["status"] for row in states] == ["passed", "failed"]
    assert "FAILED" in (tmp_path / "report/B6.svg").read_text()


def test_real_mongo_plan_preserves_compound_index_key_order(database, tmp_path):
    plan = database.command("explain", {"find": "reviews", "filter": {"product_id": 1}, "hint": "review_product_date"}, verbosity="executionStats")
    recorder = Recorder(tmp_path, "correctness", {})
    recorder.plan("compound", plan)
    saved = json.loads((tmp_path / "plans/compound.json").read_text())

    def patterns(value):
        if isinstance(value, dict):
            return ([list(value["keyPattern"])] if "keyPattern" in value else []) + [p for child in value.values() for p in patterns(child)]
        if isinstance(value, list):
            return [p for child in value for p in patterns(child)]
        return []

    assert patterns(plan) == patterns(saved)
    assert ["product_id", "answered_at"] in patterns(saved)
    index = next(row for row in b4.index_catalogue(database)["mongo"]["reviews"] if row["name"] == "review_product_date")
    assert index["key_sequence"] == [("product_id", 1), ("answered_at", -1)]
