"""Pooled tail percentiles from the raw operation latencies, gated by sample size (amendment l4); standard library only.

A run of five measured operations per client has too few operations for a tail: with 100 of them the 99th percentile is
the single slowest. The raw evidence of every accepted run (and, for several sessions, of every session) is therefore
pooled, p95 is shown only with at least 100 pooled samples and p99 only with at least 500, and below that the table says
"not enough data" and shows the median, minimum and maximum.
"""

import gzip
import json
import math
from collections import defaultdict
from pathlib import Path

P95_MINIMUM_SAMPLES = 100
P99_MINIMUM_SAMPLES = 500
NOT_ENOUGH = "not enough data"


def percentile(ordered, fraction):
    """Nearest rank on an ascending list."""
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def summarise(latencies_ms):
    ordered = sorted(latencies_ms)
    count = len(ordered)
    return {
        "samples": count,
        "p50_ms": percentile(ordered, 0.5),
        "p95_ms": percentile(ordered, 0.95) if count >= P95_MINIMUM_SAMPLES else None,
        "p99_ms": percentile(ordered, 0.99) if count >= P99_MINIMUM_SAMPLES else None,
        "min_ms": ordered[0],
        "max_ms": ordered[-1],
        "p95_label": "" if count >= P95_MINIMUM_SAMPLES else NOT_ENOUGH,
        "p99_label": "" if count >= P99_MINIMUM_SAMPLES else NOT_ENOUGH,
    }


def operations(directory):
    """Accepted operation latencies of one run directory as ((output, engine, variant, clients), milliseconds)."""
    directory = Path(directory)
    plain, packed = directory / "raw.jsonl", directory / "raw.jsonl.gz"
    if plain.exists():
        stream = plain.open(encoding="utf-8")
    elif packed.exists():
        stream = gzip.open(packed, "rt", encoding="utf-8")  # noqa: SIM115 - both closed by the with below
    else:
        return
    with stream:
        for line in stream:
            row = json.loads(line)
            if row.get("kind") != "operation" or not row.get("accepted") or row.get("accepted_latency_ns") is None:
                continue
            yield (row["output"], row["engine"], row["variant"], str(row["clients"])), row["accepted_latency_ns"] / 1e6


def pooled(directories):
    groups = defaultdict(list)
    for directory in directories:
        for key, milliseconds in operations(directory):
            groups[key].append(milliseconds)
    return {key: summarise(values) for key, values in sorted(groups.items())}


def pooled_rows(directories):
    return [
        {"output": output, "engine": engine, "variant": variant, "clients": clients, **summary}
        for (output, engine, variant, clients), summary in pooled(directories).items()
    ]
