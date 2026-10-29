"""Attribute the host's one-second Docker CPU sample intervals to each driver run."""

import csv
import json
import statistics
from pathlib import Path

from benchmarks.results import summarize

CLIENT_SATURATION_PERCENT = 180.0


def runner_cpu_intervals(path):
    result = []
    previous = {}
    if not Path(path).exists():
        return result
    for line in Path(path).read_text().splitlines():
        row = json.loads(line)
        if not row.get("Name", "").endswith("-load-client"):
            continue
        now = row["time_ns"]
        start = previous.get(row["Name"], now - 1_000_000_000)
        previous[row["Name"]] = now
        result.append((start, now, float(row["CPUPerc"].rstrip("%"))))
    return result


def cpu_for_window(intervals, start, end):
    values = [
        cpu
        for left, right, cpu in intervals
        if start is not None and end is not None and left <= end and right >= start
    ]
    return statistics.median(values) if values else None


def annotate(directory):
    directory = Path(directory)
    path = directory / "runs.csv"
    if not path.exists():
        return
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    intervals = runner_cpu_intervals(directory / "stats.jsonl")
    for row in rows:
        for key in ("clients", "run", "seed", "operations", "errors", "retries", "window_start_ns", "window_end_ns"):
            row[key] = int(row[key]) if row.get(key) else None
        for key in ("p50_ms", "p95_ms", "throughput_ops_s"):
            row[key] = float(row[key]) if row.get(key) else None
        row["accepted"] = str(row["accepted"]).lower() == "true"
        cpu = cpu_for_window(intervals, row["window_start_ns"], row["window_end_ns"])
        row["runner_cpu_median_percent"] = cpu
        row["client_saturated"] = cpu >= CLIENT_SATURATION_PERCENT if cpu is not None else None
    if rows:
        temporary = path.with_suffix(".csv.tmp")
        with temporary.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(path)
    summarize(directory, rows)
