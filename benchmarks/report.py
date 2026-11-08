"""Generate CSV tables and standalone SVG figures from retained evidence; standard library only."""

import argparse
import csv
import gzip
import hashlib
import html
import json
import re
import statistics
from bisect import bisect_right
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from benchmarks.headline import HEADLINE, REFRESH
from benchmarks.resources import annotate


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def table(path, rows):
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="", encoding="utf-8") as stream:
        fields = list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def svg(path, title, bars, unit):
    width, height = 1050, 100 + len(bars) * 36
    scale = max((float(value) for label, value, status in bars if value is not None), default=1) or 1
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#fff"/>',
        '<g font-family="Arial,sans-serif" fill="#152536">',
        f'<text x="20" y="30" font-size="18">{html.escape(title)}</text>',
    ]
    for index, (label, value, status) in enumerate(bars):
        y = 60 + index * 36
        parts.append(f'<text x="20" y="{y + 17}" font-size="12">{html.escape(label)}</text>')
        if value is not None and status == "passed":
            length = float(value) / scale * 420
            parts.append(f'<rect x="475" y="{y}" width="{length:.2f}" height="23" fill="#357b89"/>')
            text = f"{float(value):.6g} {unit}"
        else:
            length, text = (
                0,
                "FAILED" if status == "failed" else "NOT HEADLINE" if "not headline" in label else "correctness only",
            )
        parts.append(f'<text x="{485 + length:.2f}" y="{y + 17}" font-size="12">{html.escape(text)}</text>')
    parts.append("</g></svg>")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8", newline="\n")


def noise(rows):
    groups = defaultdict(list)
    baseline = {
        (row["engine"], row["clients"]): row
        for row in rows
        if row["output"] == "baseline_roundtrip" and row["p50_ms"] and row["status"] == "passed"
    }
    for row in rows:
        if row["output"].startswith(("B1_", "B4_")) and row["p50_ms"] and row["status"] == "passed":
            if row["variant"] != "documents_hinted":
                groups[row["output"], row["clients"]].append(row)
            if row["output"] == "B1_broad" and row["variant"] != "documents":
                groups["B1_broad_hinted", row["clients"]].append(row)
    result = []
    for (output, clients), group in sorted(groups.items()):
        if len(group) < 2:
            continue
        fast, slow = min(group, key=lambda r: float(r["p50_ms"])), max(group, key=lambda r: float(r["p50_ms"]))
        engines = sorted({fast["engine"], slow["engine"]})
        if any((engine, clients) not in baseline for engine in engines):
            continue
        gap = float(slow["p50_ms"]) - float(fast["p50_ms"])
        bases = [baseline[engine, clients] for engine in engines]
        baseline_noise = max(float(base["p95_ms"]) - float(base["p50_ms"]) for base in bases)
        baseline_used = "+".join(base["engine"] + "/" + base["variant"] for base in bases)
        fast_range = float(fast["p50_ms_max"]) - float(fast["p50_ms_min"])
        threshold = max(baseline_noise, fast_range)
        saturated = any(str(r.get("client_saturated", "")).lower() == "true" for r in group + bases)
        result.append(
            {
                "output": output,
                "clients": clients,
                "fastest": fast["engine"] + "/" + fast["variant"],
                "slowest": slow["engine"] + "/" + slow["variant"],
                "fastest_p50_ms": fast["p50_ms"],
                "slowest_p50_ms": slow["p50_ms"],
                "gap_ms": gap,
                "baseline_used": baseline_used,
                "baseline_p95_minus_p50_ms": baseline_noise,
                "fastest_p50_range_ms": fast_range,
                "threshold_ms": threshold,
                "inside_noise": "yes" if gap <= threshold else "no",
                "client_saturated": saturated,
                "headline": not saturated and all(r.get("runner_cpu_median_percent") for r in group + bases),
            }
        )
    return result


def b2_headline(rows):
    """The pre-registered B2 pairs (benchmarks/headline.py): live against live, maintained against maintained, and the
    refresh cost of each maintained summary. A pair is a headline only when both of its rows are."""
    index = {(r["output"], r["engine"], r["variant"], r["clients"]): r for r in rows}

    def usable(row):
        return bool(row and row["status"] == "passed" and row["p50_ms"])

    result = []
    pairs = [(output, layer, *pair) for output, layers in HEADLINE.items() for layer, pair in layers.items()]
    pairs += [("B2refresh", "refresh: " + name, *pair) for name, pair in REFRESH.items()]
    for output, layer, postgres_variant, mongo_variant in pairs:
        for clients in sorted({r["clients"] for r in rows if r["output"] == output}, key=int):
            postgres = index.get((output, "postgres", postgres_variant, clients))
            mongo = index.get((output, "mongo", mongo_variant, clients))
            if not (usable(postgres) and usable(mongo)):
                continue
            result.append(
                {
                    "output": output,
                    "layer": layer,
                    "clients": clients,
                    "postgres_variant": postgres_variant,
                    "mongo_variant": mongo_variant,
                    "postgres_p50_ms": postgres["p50_ms"],
                    "mongo_p50_ms": mongo["p50_ms"],
                    "mongo_over_postgres": float(mongo["p50_ms"]) / float(postgres["p50_ms"]),
                    "headline": str(postgres["headline"]).lower() == "true"
                    and str(mongo["headline"]).lower() == "true",
                }
            )
    return result


def memory_bytes(value):
    """Interpret Docker's rounded display values, preserving SI versus IEC units."""
    units = {
        "B": 1,
        "kB": 1000,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "TB": 1000**4,
        "KiB": 1024,
        "MiB": 1024**2,
        "GiB": 1024**3,
        "TiB": 1024**4,
    }
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)\s*", value)
    return int(Decimal(match[1]) * units[match[2]]) if match and match[2] in units else None


def memory_settings(directory):
    """Publish the recorded caps/caches and checksum-verified input footprint."""
    directory = Path(directory)
    if not (directory / "host.json").exists() or not (directory / "provenance.json").exists():
        return []
    host = json.loads((directory / "host.json").read_text())
    provenance = json.loads((directory / "provenance.json").read_text())
    source_name = provenance.get("source", "")
    source = Path(source_name)
    if not source.is_dir():
        relative = source_name.removeprefix("/app/")
        source = Path(__file__).resolve().parents[1] / (
            "tests/" + relative if relative.startswith("fixtures/") else relative
        )
    input_bytes, input_status = None, "unavailable"
    if provenance.get("files") and source.is_dir():
        total = 0
        for name, expected in provenance["files"].items():
            path = (source / name).resolve()
            if not path.is_relative_to(source.resolve()) or not path.is_file():
                break
            sha256 = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    sha256.update(chunk)
            digest = sha256.hexdigest()
            if digest != expected:
                input_status = "checksum_mismatch"
                break
            total += path.stat().st_size
        else:
            input_bytes, input_status = total, "checksum_verified"
    containers = [(row["name"].lstrip("/"), row["limits"]) for row in host.get("containers", [])]
    runner = host.get("runner_actual_limits")
    if runner:
        containers.append((host["project"] + "-load-client", runner))
    mongo = host.get("mongo_server_readback", {})
    cache_gb = (
        mongo.get("options", {}).get("storage", {}).get("wiredTiger", {}).get("engineConfig", {}).get("cacheSizeGB")
    )
    return [
        {
            "container": name,
            "limit_bytes": limits.get("Memory"),
            "cpu_limit": limits["NanoCpus"] / 1e9 if limits.get("NanoCpus") is not None else None,
            "postgres_shared_buffers": provenance.get("settings", {}).get("postgres", {}).get("shared_buffers")
            if name.endswith("-bench-db-1")
            else None,
            "wiredtiger_cache_size_gb_setting": cache_gb if name.endswith("-bench-mongo-1") else None,
            "wiredtiger_cache_bytes": mongo.get("cache_bytes") if name.endswith("-bench-mongo-1") else None,
            "source_input_bytes": input_bytes,
            "source_input_decimal_mb": input_bytes / 1000**2 if input_bytes is not None else None,
            "source_input_status": input_status,
            "docker_vm_memory_bytes": host.get("docker_vm", {}).get("MemTotal"),
            "docker_vm_cpus": host.get("docker_vm", {}).get("NCPU"),
        }
        for name, limits in containers
    ]


def memory_rows(directory):
    """Map memory sample timestamps to merged run windows without interpolation.

    Whole-run rows also include preparation/restoration. Untimed workloads keep
    blank memory figures rather than borrowing neighbouring workload samples.
    The median is sample-weighted; bytes are approximate because MemUsage is rounded.
    """
    directory = Path(directory)
    stats = directory / "stats.jsonl"
    if not stats.exists():
        return []
    workloads = defaultdict(list)
    for row in read_csv(directory / "runs.csv"):
        output = row["output"]
        workload = next(
            (name for name in ("baseline", "BM4", "B1", "B2", "B3", "B4", "B5", "B6") if output.startswith(name)),
            output,
        )
        windows = workloads[workload]
        if row.get("window_start_ns") and row.get("window_end_ns"):
            left, right = int(row["window_start_ns"]), int(row["window_end_ns"])
            if right < left:
                raise ValueError("Memory attribution requires nonnegative run windows")
            windows.append((left, right))
    samples = defaultdict(list)
    with stats.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            parts = row.get("MemUsage", "").split("/")
            if len(parts) != 2 or not row.get("Name"):
                continue
            used, limit = (memory_bytes(part) for part in parts)
            if used is None or limit is None or limit <= 0:
                continue
            samples[row["Name"]].append((int(row["time_ns"]), used, limit, row["MemUsage"]))

    def memory_row(scope, workload, container, values, windows):
        used = [value[1] for value in values]
        peak = max(values, key=lambda value: value[1]) if values else None
        limits = sorted({value[2] for value in samples[container]})
        median = statistics.median(used) if used else None
        return {
            "scope": scope,
            "workload": workload,
            "container": container,
            "status": "sampled" if values else "no_samples" if windows else "no_windows",
            "window_count": len(windows) if scope == "workload" else "",
            "sample_count": len(values),
            "median_memory_bytes": median,
            "peak_memory_bytes": peak[1] if peak else None,
            "median_memory_gib": median / 1024**3 if median is not None else None,
            "peak_memory_gib": peak[1] / 1024**3 if peak else None,
            "limit_bytes": limits[0] if len(limits) == 1 else None,
            "observed_limits_bytes": json.dumps(limits),
            "peak_percent_of_limit": 100 * peak[1] / peak[2] if peak else None,
            "peak_time_ns": peak[0] if peak else None,
            "peak_memory_text": peak[3] if peak else None,
        }

    result = [memory_row("run", "all", name, values, []) for name, values in sorted(samples.items())]
    for workload, intervals in sorted(workloads.items()):
        merged = []
        for left, right in sorted(intervals):
            if merged and left <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
            else:
                merged.append((left, right))
        starts = [left for left, right in merged]
        for name, values in sorted(samples.items()):
            selected = []
            for value in values:
                index = bisect_right(starts, value[0]) - 1
                if index >= 0 and value[0] <= merged[index][1]:
                    selected.append(value)
            result.append(memory_row("workload", workload, name, selected, merged))
    return result


def report(directory):
    directory = Path(directory)
    destination = directory / "report"
    destination.mkdir(exist_ok=True)
    annotate(directory)
    rows = read_csv(directory / "summary.csv")
    table(destination / "memory.csv", memory_rows(directory))
    table(destination / "b2-headline.csv", b2_headline(rows))
    table(destination / "memory-settings.csv", memory_settings(directory))
    outputs = defaultdict(list)
    for row in rows:
        outputs[row["output"]].append(row)
    ratios = []
    for output, group in outputs.items():
        rendered = []
        for row in group:
            comparable = [
                r
                for r in group
                if r["clients"] == row["clients"]
                and r["p50_ms"]
                and r["status"] == "passed"
                and r["variant"] != "restore"
                and str(r.get("headline", "")).lower() == "true"
            ]
            fastest = min((float(r["p50_ms"]) for r in comparable), default=0)
            before = next((r for r in comparable if r["variant"] == "before"), None)
            pg_live = next((r for r in comparable if r["engine"] == "postgres" and r["variant"] == "live"), None)
            value = (
                float(row["p50_ms"])
                if row["p50_ms"] and row["status"] == "passed" and str(row.get("headline", "")).lower() == "true"
                else None
            )
            ratio = (
                float(before["p50_ms"]) / value
                if before and value
                else float(pg_live["p50_ms"]) / value
                if pg_live and value
                else value / fastest
                if value and fastest
                else None
            )
            enriched = {
                **row,
                "ratio": ratio,
                "ratio_basis": "before/variant"
                if before
                else "postgres_live/variant"
                if pg_live
                else "variant/fastest",
            }
            rendered.append(enriched)
            ratios.append(enriched)
        table(destination / (output + ".csv"), rendered)
        svg(
            destination / (output + ".svg"),
            output + " ratios (see CSV for ranges and absolute ms)",
            [
                (
                    r["engine"]
                    + "/"
                    + r["variant"]
                    + " c="
                    + r["clients"]
                    + (" (not headline)" if r.get("not_headline_reason") else ""),
                    r["ratio"],
                    r["status"],
                )
                for r in rendered
            ],
            "x",
        )
    table(destination / "ratios.csv", ratios)
    table(destination / "amendment-j.csv", noise(rows))
    table(
        destination / "matrix-evidence.csv",
        [
            {"criterion": criterion, "postgres_sources": pg, "mongo_sources": mongo, "run_evidence": evidence}
            for criterion, pg, mongo, evidence in (
                (
                    "Data modelling",
                    "docs/DATA_MODEL.md;src/orders/models.py",
                    "docs/DATA_MODEL.md;benchmarks/load.py;src/config/mongo_schema.py",
                    "provenance.json",
                ),
                (
                    "Integrity",
                    "src/orders/migration_sql.py;src/wishlist/migrations/0001_wishlist_restock.py",
                    "src/config/mongo_schema.py;src/reviews/services.py",
                    ("raw.jsonl" if (directory / "raw.jsonl").exists() else "raw.jsonl.gz") + ";report/B3-states.csv",
                ),
                (
                    "Transactions and consistency",
                    "src/orders/services.py;benchmarks/workloads/b3.py;benchmarks/workloads/b6.py",
                    "src/reviews/services.py;benchmarks/workloads/b3.py;benchmarks/workloads/b6.py",
                    "report/B3-states.csv;report/B6-states.csv",
                ),
                (
                    "Schema evolution",
                    "src/catalogue/migrations/0001_initial.py",
                    "src/catalogue/services.py;src/config/mongo_schema.py",
                    "provenance.json",
                ),
                (
                    "Query expressiveness",
                    "src/dashboard/queries.py;src/dashboard/migrations/0001_daily_product_sales.py",
                    "benchmarks/workloads/b2.py;src/activity/services.py",
                    "plans/;report/B2a.csv;report/B2b.csv;report/B2c.csv;report/B2d.csv",
                ),
                (
                    "Security",
                    "src/docker/10-roles.sh;src/config/privileges.py",
                    "src/docker/mongo-start.sh;src/docker/bench-mongo-start.sh",
                    "provenance.json",
                ),
                (
                    "Storage and indexing",
                    "benchmarks/load.py;benchmarks/workloads/b4.py;benchmarks/workloads/b5.py",
                    "benchmarks/load.py;benchmarks/workloads/b4.py;benchmarks/workloads/b5.py",
                    "plans/;storage.csv",
                ),
            )
        ],
    )
    raw = directory / "raw.jsonl"
    opener = raw.open if raw.exists() else lambda **kwargs: gzip.open(str(raw) + ".gz", "rt", **kwargs)
    checks, demonstrations, races = [], [], []
    with opener(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            if record["kind"] != "check":
                continue
            checks.append(
                {
                    key: record.get(key)
                    for key in ("output", "engine", "variant", "clients", "run", "phase", "status", "accepted")
                }
            )
            if record["output"] == "B6":
                demonstrations.append(
                    {
                        "engine": record["engine"],
                        "strategy": record["variant"],
                        "status": record["status"],
                        **record["evidence"],
                    }
                )
            if record["output"] == "B3":
                evidence = record.get("evidence") or {}
                races.append(
                    {
                        **{
                            key: record.get(key)
                            for key in ("engine", "variant", "clients", "run", "phase", "status", "retries")
                        },
                        **{
                            key: evidence.get(key)
                            for key in ("successes", "refusals", "stock", "orders", "initial_verified", "restored")
                        },
                    }
                )
    table(destination / "checks.csv", checks)
    if races:
        table(destination / "B3-states.csv", races)
        svg(
            destination / "B3-outcomes.svg",
            "B3 accepted and refused buyers (all checks must pass)",
            [
                (r["engine"] + "/" + r["variant"] + " c=" + str(r["clients"]) + "/" + key, r.get(key), r["status"])
                for r in races
                for key in ("successes", "refusals")
            ],
            "buyers",
        )
    if demonstrations:
        table(destination / "B6-states.csv", demonstrations)
        svg(
            destination / "B6.svg",
            "B6 expected and observed final stock",
            [(r["engine"] + "/" + r["strategy"], r.get("observed_stock"), r["status"]) for r in demonstrations],
            "units",
        )
    if (directory / "storage.csv").exists():
        storage = read_csv(directory / "storage.csv")
        table(destination / "B5.csv", storage)
        svg(
            destination / "B5.svg",
            "B5 physical data and indexes (different representations; see model contract)",
            [
                (row["engine"] + "/" + row["representation"] + "/" + kind, float(row[kind + "_bytes"]), "passed")
                for row in storage
                for kind in ("data", "index")
            ],
            "bytes",
        )
    if (directory / "storage-restores.csv").exists():
        table(destination / "B5-restores.csv", read_csv(directory / "storage-restores.csv"))
    print(
        json.dumps({"report": str(destination), "outputs": sorted(outputs), "amendment_j": noise(rows)}, sort_keys=True)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    report(parser.parse_args().directory)


if __name__ == "__main__":
    main()
