"""Append-only raw evidence. Failed checks never contribute accepted measurements."""
import csv
import json
import math
import statistics
from pathlib import Path


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def assess(records, passed, *, mode, phase, elapsed_ns):
    passed = bool(passed and records and not any(row.get("error") for row in records))
    accepted = passed and mode == "measure" and phase == "measured"
    timing = [row["latency_ns"] / 1_000_000 for row in records]
    return {"status": "passed" if passed else "failed", "accepted": accepted, "operations": len(records),
            "errors": sum(bool(row.get("error")) for row in records), "retries": sum(row.get("retries", 0) for row in records),
            "p50_ms": percentile(timing, .5) if accepted else None, "p95_ms": percentile(timing, .95) if accepted else None,
            "throughput_ops_s": len(records) * 1_000_000_000 / elapsed_ns if accepted and elapsed_ns else None}


class Recorder:
    def __init__(self, directory, mode, provenance):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        if (self.directory / "raw.jsonl").exists():
            raise ValueError("Refusing to overwrite an existing run")
        self.mode = mode
        self.provenance = provenance
        self.rows = []
        self.failed = False
        self._write_provenance()

    def _write_provenance(self):
        (self.directory / "provenance.json").write_text(json.dumps(self.provenance, indent=2, sort_keys=True, default=str) + "\n")

    def record(self, output, engine, variant, clients, run, phase, records, elapsed_ns, passed, evidence=None):
        check = assess(records, passed, mode=self.mode, phase=phase, elapsed_ns=elapsed_ns)
        base = {"output": output, "engine": engine, "variant": variant, "clients": clients, "run": run, "phase": phase, "seed": 82}
        starts = [r["started_at_ns"] for r in records if r.get("started_at_ns") is not None]
        ends = [r["ended_at_ns"] for r in records if r.get("ended_at_ns") is not None]
        self.rows.append({**base, **check, "window_start_ns": min(starts) if starts else None, "window_end_ns": max(ends) if ends else None,
                          "runner_cpu_median_percent": None, "client_saturated": None})
        self.failed |= check["status"] == "failed"
        with (self.directory / "raw.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"kind": "check", **base, **check, "evidence": evidence}, default=str, sort_keys=True) + "\n")
            for operation, row in enumerate(records):
                stream.write(json.dumps({"kind": "operation", **base, **row, "operation": operation, "status": check["status"],
                                         "accepted": check["accepted"], "accepted_latency_ns": row["latency_ns"] if check["accepted"] else None}, sort_keys=True) + "\n")
        print(f"{output} {engine}/{variant} clients={clients} run={run} {phase}: {check['status']}", flush=True)
        self.finish()

    def plan(self, name, data):
        target = self.directory / "plans"
        target.mkdir(exist_ok=True)
        from bson import json_util
        # Compound index keyPattern objects carry semantic field order in MongoDB explain output.
        (target / (name + ".json")).write_text(json_util.dumps(data, indent=2) + "\n", encoding="utf-8")

    def finish(self):
        self._write_provenance()
        with (self.directory / "runs.csv").open("w", newline="", encoding="utf-8") as stream:
            fields = list(self.rows[0]) if self.rows else []
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(self.rows)
        summarize(self.directory, self.rows)


def summarize(directory, rows):
    groups = {}
    for row in rows:
        if row["phase"] == "warmup" and row["status"] == "passed":
            continue
        key = tuple(row[k] for k in ("output", "engine", "variant", "clients"))
        groups.setdefault(key, []).append(row)
    fields = ["output", "engine", "variant", "clients", "status", "accepted_runs", "failed_runs", "retries", "errors",
              "runner_cpu_median_percent", "runner_cpu_median_percent_min", "runner_cpu_median_percent_max",
              "client_saturated_runs", "client_saturated", "headline", "not_headline_reason"]
    metrics = ("p50_ms", "p95_ms", "throughput_ops_s")
    fields += [key + suffix for key in metrics for suffix in ("", "_min", "_max")]
    summary_path = Path(directory) / "summary.csv"
    temporary = summary_path.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for key, group in sorted(groups.items()):
            accepted = [row for row in group if row["accepted"]]
            failed = sum(row["status"] == "failed" for row in group)
            result = dict(zip(fields[:4], key))
            result.update(status="failed" if failed else "passed", accepted_runs=len(accepted), failed_runs=failed,
                          retries=sum(row["retries"] for row in group), errors=sum(row["errors"] for row in group))
            cpus = [row["runner_cpu_median_percent"] for row in accepted if row.get("runner_cpu_median_percent") is not None]
            saturated = sum(row.get("client_saturated") is True for row in accepted)
            reason = ("failed_check" if failed else "no_accepted_timing" if not accepted else "client_saturated" if saturated else
                      "client_cpu_unavailable" if len(cpus) != len(accepted) else "hinted_comparison" if key[2] == "documents_hinted" else "")
            result.update(runner_cpu_median_percent=statistics.median(cpus) if cpus else "",
                          runner_cpu_median_percent_min=min(cpus) if cpus else "", runner_cpu_median_percent_max=max(cpus) if cpus else "",
                          client_saturated_runs=saturated, client_saturated=bool(saturated), headline=not reason, not_headline_reason=reason)
            for metric in metrics:
                values = [row[metric] for row in accepted if row[metric] is not None]
                result.update({metric: statistics.median(values) if values else "", metric + "_min": min(values) if values else "", metric + "_max": max(values) if values else ""})
            writer.writerow(result)
    temporary.replace(summary_path)
