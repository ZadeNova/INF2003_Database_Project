import csv
import gzip
import hashlib
import json

import pytest

from benchmarks.report import memory_rows, memory_settings, report, table
from benchmarks.resources import runner_cpu_intervals
from benchmarks.results import Recorder


@pytest.mark.parametrize("invalid", ["--", None, "nan", "inf"])
def test_invalid_cpu_sample_is_skipped_without_bridging_its_interval(tmp_path, invalid):
    samples = [
        {"Name": "fixture-load-client", "time_ns": 1_000_000_000, "CPUPerc": "50%"},
        {"Name": "fixture-load-client", "time_ns": 2_000_000_000, "CPUPerc": invalid},
        {"Name": "fixture-load-client", "time_ns": 3_000_000_000, "CPUPerc": "190%"},
    ]
    path = tmp_path / "stats.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in samples))
    assert runner_cpu_intervals(path) == [(0, 1_000_000_000, 50.0), (2_000_000_000, 3_000_000_000, 190.0)]


def test_memory_uses_window_union_units_and_whole_run_peaks(tmp_path):
    table(
        tmp_path / "runs.csv",
        [
            {"output": "B1_selective", "window_start_ns": 10, "window_end_ns": 20},
            {"output": "B1_broad", "window_start_ns": 15, "window_end_ns": 25},
            {"output": "B2a", "window_start_ns": 30, "window_end_ns": 40},
            {"output": "baseline_roundtrip", "window_start_ns": 50, "window_end_ns": 51},
            {"output": "B5", "window_start_ns": "", "window_end_ns": ""},
            {"output": "B6", "window_start_ns": "", "window_end_ns": ""},
        ],
    )
    samples = [
        ("postgres", 10, "100MiB / 2GiB", "10%"),
        ("postgres", 20, "300MiB / 2GiB", "10%"),
        ("postgres", 25, "500MiB / 2GiB", "10%"),
        ("postgres", 27, "1.5GiB / 2GiB", "10%"),  # Untimed restore: only whole-run peak.
        ("postgres", 30, "700MiB / 2GiB", "10%"),
        ("postgres", 40, "900MiB / 2GiB", "10%"),
        ("mongo", 10, "0.5GiB / 2GiB", "10%"),
        ("mongo", 20, "1GiB / 2GiB", "--"),  # Memory remains usable independently of CPU.
        ("mongo", 25, "1.5GiB / 2GiB", "10%"),
        ("mongo", 35, "1900MB / 2GiB", "10%"),
        ("mongo", 41, "0B / 0B", "--"),  # A stopped container is not zero memory at a valid cap.
        ("client", 40, "1500kB / 2GiB", "10%"),
    ]
    (tmp_path / "stats.jsonl").write_text(
        "".join(
            json.dumps({"Name": name, "time_ns": stamp, "MemUsage": memory, "CPUPerc": cpu}) + "\n"
            for name, stamp, memory, cpu in samples
        )
    )
    rows = {(row["scope"], row["workload"], row["container"]): row for row in memory_rows(tmp_path)}
    b1 = rows["workload", "B1", "postgres"]
    assert b1["sample_count"] == 3 and b1["window_count"] == 1
    assert b1["median_memory_bytes"] == 300 * 1024**2 and b1["peak_memory_bytes"] == 500 * 1024**2
    assert rows["run", "all", "postgres"]["peak_memory_bytes"] == 1536 * 1024**2
    assert rows["workload", "B2", "postgres"]["median_memory_bytes"] == 800 * 1024**2
    assert rows["workload", "B1", "mongo"]["median_memory_bytes"] == 1024**3
    assert rows["run", "all", "mongo"]["peak_memory_bytes"] == 1_900_000_000
    assert rows["run", "all", "client"]["peak_memory_bytes"] == 1_500_000
    assert rows["run", "all", "mongo"]["sample_count"] == 4
    assert rows["workload", "baseline", "postgres"]["status"] == "no_samples"
    for workload in ("B5", "B6"):
        row = rows["workload", workload, "postgres"]
        assert row["status"] == "no_windows" and row["median_memory_bytes"] is None and row["peak_memory_bytes"] is None


def test_report_writes_memory_table_and_keeps_failed_checks(tmp_path):
    recorder = Recorder(tmp_path, "measure", {})
    operation = {"latency_ns": 10, "started_at_ns": 1_000_000_000, "ended_at_ns": 1_000_000_010}
    recorder.record("B3", "mongo", "snapshot", 1, 1, "measured", [operation], 10, False)
    raw = tmp_path / "raw.jsonl"
    with gzip.open(str(raw) + ".gz", "wb") as stream:
        stream.write(raw.read_bytes())
    raw.unlink()
    (tmp_path / "stats.jsonl").write_text(
        json.dumps(
            {"Name": "fixture-bench-mongo-1", "time_ns": 1_000_000_005, "MemUsage": "1GiB / 2GiB", "CPUPerc": "--"}
        )
        + "\n"
    )
    report(tmp_path)
    with (tmp_path / "report/memory.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert next(row for row in rows if row["scope"] == "workload")["peak_memory_bytes"] == str(1024**3)
    with (tmp_path / "report/checks.csv").open(newline="") as stream:
        assert next(csv.DictReader(stream))["status"] == "failed"
    with (tmp_path / "report/matrix-evidence.csv").open(newline="") as stream:
        integrity = next(row for row in csv.DictReader(stream) if row["criterion"] == "Integrity")
    assert integrity["run_evidence"].startswith("raw.jsonl.gz;")


def test_memory_settings_checks_original_input_hashes(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    payload = b"the checksummed source input\n"
    (source / "input.csv").write_bytes(payload)
    provenance = {
        "source": str(source),
        "files": {"input.csv": hashlib.sha256(payload).hexdigest()},
        "settings": {"postgres": {"shared_buffers": "512MB"}},
    }
    (tmp_path / "provenance.json").write_text(json.dumps(provenance))
    limit = {"Memory": 2 * 1024**3, "NanoCpus": 2_000_000_000}
    host = {
        "project": "fixture",
        "containers": [
            {"name": "/fixture-bench-db-1", "limits": limit},
            {"name": "/fixture-bench-mongo-1", "limits": limit},
        ],
        "runner_actual_limits": limit,
        "mongo_server_readback": {
            "cache_bytes": 805306368,
            "options": {"storage": {"wiredTiger": {"engineConfig": {"cacheSizeGB": 0.75}}}},
        },
    }
    (tmp_path / "host.json").write_text(json.dumps(host))
    rows = memory_settings(tmp_path)
    assert len(rows) == 3
    assert all(
        row["source_input_bytes"] == len(payload) and row["source_input_status"] == "checksum_verified" for row in rows
    )
    assert next(row for row in rows if row["container"].endswith("-bench-db-1"))["postgres_shared_buffers"] == "512MB"
    assert (
        next(row for row in rows if row["container"].endswith("-bench-mongo-1"))["wiredtiger_cache_bytes"] == 805306368
    )
    (source / "input.csv").write_bytes(payload + b"changed")
    assert all(
        row["source_input_bytes"] is None and row["source_input_status"] == "checksum_mismatch"
        for row in memory_settings(tmp_path)
    )
