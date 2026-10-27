"""Run B1--B6 with independent correctness gates and retained failures."""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from benchmarks import db
from benchmarks.canonical import SCHEMA_PATH, csv_bytes
from benchmarks.query import Query
from benchmarks.results import Recorder
from benchmarks.source import sha256
from benchmarks.state import isolated_run, verify_manifest
from benchmarks.workloads import b1, b2, b3, b4, b5, b6


def golden_files(directory, provenance):
    directory = Path(directory)
    source = json.loads((directory / "source.json").read_text())
    if source["manifest_sha256"] != provenance["manifest_sha256"] or source["files"] != provenance["files"]:
        raise ValueError("Golden source does not match loaded manifest")
    hashes = {}
    for line in (directory / "checksums.txt").read_text().splitlines():
        digest, name = line.split("  ", 1)
        if Path(name).name != name or sha256(directory / name) != digest:
            raise ValueError("Golden checksum failed")
        hashes[name] = digest
    outputs = {p.stem: p.read_bytes() for p in directory.glob("*.csv")}
    return outputs, json.loads((directory / "parameters.json").read_text()), source, hashes


def query_run(query, clients, operations, expected, *, refresh_check=None):
    def worker(indices):
        records = []
        with query.open() as operation:
            for _ in indices:
                started = time.perf_counter_ns()
                error = None
                try:
                    rows = operation()
                    latency = time.perf_counter_ns() - started
                    if query.golden and csv_bytes(query.golden, rows) != expected[query.golden]:
                        error = "GoldenMismatch"
                    if refresh_check:
                        refresh_check()
                except Exception as exc:
                    latency = time.perf_counter_ns() - started
                    error = type(exc).__name__
                records.append({"latency_ns": latency, "retries": 0, "error": error})
        return records

    started = time.perf_counter_ns()
    with ThreadPoolExecutor(max_workers=clients) as pool:
        records = [row for group in pool.map(worker, [range(i, operations, clients) for i in range(clients)]) for row in group]
    return records, time.perf_counter_ns() - started, not any(row["error"] for row in records)


def failed_record(recorder, output, engine, variant, clients, run, phase, exc, evidence=None):
    recorder.record(output, engine, variant, clients, run, phase, [{"latency_ns": 0, "retries": 0, "error": type(exc).__name__}], 0, False,
                    {"exception_class": type(exc).__name__, **(evidence or {})})


def run_queries(queries, recorder, expected, operations, *, clients=(1, 10, 50), refresh_check=None, output=None, variant=None):
    for query in queries:
        name, model = output or query.output, variant or query.variant
        matrix = clients if recorder.mode == "measure" else (1,)
        for count in matrix:
            rounds = [(0, "correctness")] if recorder.mode == "correctness" else [(0, "warmup")] + [(n, "measured") for n in range(1, 6)]
            for run, phase in rounds:
                try:
                    records, elapsed, passed = query_run(query, count, operations if phase == "measured" else 1, expected,
                                                        refresh_check=refresh_check if query.output == "B2refresh" else None)
                    recorder.record(name, query.engine, model, count, run, phase, records, elapsed, passed)
                except Exception as exc:
                    failed_record(recorder, name, query.engine, model, count, run, phase, exc)
            # The plan is a separate untimed pass, once per representation rather than once per client count.
            if count == matrix[0]:
                try:
                    recorder.plan(f"{name}_{query.engine}_{model}", query.explain())
                except Exception as exc:
                    failed_record(recorder, name, query.engine, model, count, -1, "plan", exc)


def run_mutations(recorder, database, provenance, selected):
    if "B3" in selected:
        for engine, triggers in (("postgres", False), ("postgres", True), ("mongo", True)):
            variant = "triggers_on" if engine == "postgres" and triggers else "triggers_off" if engine == "postgres" else "snapshot"
            for clients in (1, 10, 50):
                rounds = [(0, "correctness")] if recorder.mode == "correctness" else [(0, "warmup")] + [(n, "measured") for n in range(1, 6)]
                for run, phase in rounds:
                    evidence = {}
                    try:
                        with isolated_run(database, provenance, evidence):
                            result = b3.race(engine, clients, triggers, database)
                        records, elapsed, passed, checks = result
                        recorder.record("B3", engine, variant, clients, run, phase, records, elapsed, passed, {**evidence, **checks})
                    except Exception as exc:
                        failed_record(recorder, "B3", engine, variant, clients, run, phase, exc, evidence)
    if "B6" in selected:
        for engine, strategies in b6.STRATEGIES.items():
            for strategy in strategies:
                evidence = {}
                try:
                    with isolated_run(database, provenance, evidence):
                        result = b6.demonstrate(engine, strategy, database)
                    records, elapsed, passed, checks = result
                    recorder.record("B6", engine, strategy, 2, 1, "demonstration", records, elapsed, passed,
                                    {**evidence, **checks, "observed_throughput_ops_s": 2e9 / elapsed})
                except Exception as exc:
                    failed_record(recorder, "B6", engine, strategy, 2, 1, "demonstration", exc, evidence)


def demonstrate_bm4(recorder, database, provenance, expected, parameters):
    query = b1.queries(parameters[0])[0]
    corrupted = {**expected, query.golden: b"deliberately corrupted independent result"}
    records, elapsed, passed = query_run(query, 1, 1, corrupted)
    recorder.record("BM4_corrupted_result", query.engine, "expected_failure", 1, 1, "measured", records, elapsed, passed,
                    {"expected_failure": True, "purpose": "a wrong result cannot supply accepted timing"})
    evidence = {}
    with isolated_run(database, provenance, evidence):
        records, elapsed, passed, checks = b3.race("mongo", 10, True, database)
        if not passed:
            raise ValueError("BM4 setup race did not pass its own checks")
        database.products.update_one({"_id": 1}, {"$set": {"stock": 1}})
        observed = database.products.find_one({"_id": 1})["stock"]
        passed = observed == 0
    recorder.record("BM4_violated_invariant", "mongo", "expected_failure", 10, 1, "measured", records, elapsed, passed,
                    {**evidence, "expected_failure": True, "expected_stock": 0, "observed_stock": observed})


def run(args):
    with db.mongo() as database:
        provenance = verify_manifest(database, args.source)
        expected, parameters, golden_source, hashes = golden_files(args.golden, provenance)
        host_file = args.output / "host.json"
        provenance.update(mode=args.mode, label=args.label, host=json.loads(host_file.read_text()) if host_file.exists() else {},
                          settings=db.settings(database), golden_checksums=hashes, output_schema_sha256=sha256(SCHEMA_PATH), seed=82,
                          operations=args.operations, fixed_b3_buyers=50, measured_runs=5, clients=[1, 10, 50],
                          libraries={name: importlib.metadata.version(name) for name in ("psycopg", "pymongo", "Django")},
                          telemetry="disabled", application_caches="none", buffer_state="warm", throughput_includes="connection setup and correctness validation",
                          final=False, trigger_policy="B3 PostgreSQL USER off headline and USER on separate; internal FK triggers always enabled")
        recorder = Recorder(args.output, args.mode, provenance)
        b1_queries = [query for parameter in parameters for query in b1.queries(parameter)]
        b2_queries = b2.queries(date.fromisoformat(golden_source["as_of"]), database.platform_stats.find_one({"_id": "bayesian"}))

        def refresh_check():
            for query in b2_queries:
                if query.variant == "view":
                    with query.open() as operation:
                        if csv_bytes(query.golden, operation()) != expected[query.golden]:
                            raise ValueError("Refreshed materialized view differs from golden")

        selected = set(args.only.split(","))
        if "BM4" in selected:
            demonstrate_bm4(recorder, database, provenance, expected, parameters)
        if "baseline" in selected:
            run_queries([Query("baseline", "python", "noop")], recorder, expected, args.operations)
        if "B1" in selected:
            run_queries(b1_queries, recorder, expected, args.operations)
        if "B2" in selected:
            for query in b2_queries:
                run_queries([query], recorder, expected, args.operations, clients=(1,) if query.output == "B2refresh" else (1, 10, 50), refresh_check=refresh_check)
        if "B4" in selected:
            for kind, index, query in b4.cases(b1_queries, b2_queries, parameters):
                evidence = {}
                try:
                    with b4.dropped(query, index, database, evidence) as restore:
                        run_queries([query], recorder, expected, max(1, args.operations // 10), clients=(1,), output="B4_" + index, variant="before")
                        restore()
                        run_queries([query], recorder, expected, max(1, args.operations // 10), clients=(1,), output="B4_" + index, variant="after")
                    recorder.record("B4_" + index, query.engine, "restore", 1, 0, "invariant", [{"latency_ns": 0}], 0, evidence["index_set_restored"], evidence)
                except Exception as exc:
                    failed_record(recorder, "B4_" + index, query.engine, "restore", 1, 0, "invariant", exc, evidence)
        if "B5" in selected:
            try:
                rows = b5.footprint(database)
                with (args.output / "storage.csv").open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
                    writer.writeheader()
                    writer.writerows(rows)
                recorder.record("B5", "both", "footprint", 0, 0, "storage", [{"latency_ns": 0}], 0,
                                all(r["data_bytes"] >= 0 and r["index_bytes"] >= 0 for r in rows), rows)
            except Exception as exc:
                failed_record(recorder, "B5", "both", "footprint", 0, 0, "storage", exc)
        run_mutations(recorder, database, provenance, selected)
        recorder.finish()
        # Tie the summary to the exact append-only operation evidence.
        recorder.provenance["raw_sha256"] = hashlib.sha256((args.output / "raw.jsonl").read_bytes()).hexdigest()
        recorder.finish()
        return int(recorder.failed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("correctness", "measure"), required=True)
    parser.add_argument("--only", default="baseline,B1,B2,B3,B4,B5,B6")
    parser.add_argument("--operations", type=int, default=50)
    parser.add_argument("--label", default="correctness")
    args = parser.parse_args()
    if args.operations < 50 or not set(args.only.split(",")) <= {"baseline", "B1", "B2", "B3", "B4", "B5", "B6", "BM4"}:
        parser.error("Use at least fifty operations and named workloads")
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
