"""Combine independent benchmark sessions into one headline (amendment l3); standard library only.

The rule is fixed here, before any session runs: the headline value of a measure is the MEDIAN ACROSS USABLE SESSIONS of
each session's own run-level median (the p50, p95 and throughput columns of its summary.csv). Every session is kept in
sessions.csv. A session is left out of the headline, with its number and the reason in excluded.csv, when a check failed
in it, its runner exited nonzero, or a container died or restarted during it; no session is left out for being slow or
for disagreeing with the others. The spread between sessions is reported next to every headline value.

    python -m benchmarks.sessions benchmarks/results/<session-1> benchmarks/results/<session-2> ... --output <folder>
"""

import argparse
import csv
import json
import statistics
from pathlib import Path

from benchmarks.pooling import pooled
from benchmarks.report import b2_headline, table

MINIMUM_SESSIONS = 3
METRICS = ("p50_ms", "p95_ms", "throughput_ops_s")
KEY = ("output", "engine", "variant", "clients")


def read_rows(path):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def load_session(directory, number):
    directory = Path(directory)
    rows = read_rows(directory / "summary.csv")
    host_file = directory / "host.json"
    host = json.loads(host_file.read_text(encoding="utf-8")) if host_file.exists() else {}
    reasons = []
    # run.py writes host.json at the start and adds the exit code at the end, and summary.csv is rewritten after every
    # record, so a killed run leaves a valid-looking partial session: only an explicit exit code 0 and a finished report count.
    if host.get("exit_code") is None:
        reasons.append("the run did not finish (no exit code recorded)")
    elif host["exit_code"] != 0:
        reasons.append(f"runner exit code {host['exit_code']}")
    elif not (directory / "report").is_dir():
        reasons.append("the run recorded no report")
    if host.get("container_events"):
        reasons.append("container event: " + "; ".join(host["container_events"]))
    failed = sorted({"/".join(row[k] for k in KEY[:3]) for row in rows if row["status"] == "failed"})
    if failed:
        reasons.append(f"failed checks in {len(failed)} measures, for example {failed[0]}")
    drift_file = directory / "report" / "drift.csv"
    drift = [row for row in read_rows(drift_file) if row["drift"] != "no"] if drift_file.exists() else []
    return {
        "number": number,
        "directory": directory,
        "rows": rows,
        "reasons": reasons,
        "drift_flagged": bool(drift),
        "commit": host.get("commit", ""),
    }


def number_or_none(value):
    return float(value) if value not in ("", None) else None


def combine(sessions):
    usable = [s for s in sessions if not s["reasons"]]
    by_key = {}
    for session in usable:
        for row in session["rows"]:
            if row["status"] != "passed" or not row["p50_ms"]:
                continue
            by_key.setdefault(tuple(row[k] for k in KEY), []).append((session["number"], row))
    headline = []
    pools = pooled([s["directory"] for s in usable])
    for key, entries in sorted(by_key.items()):
        result = dict(zip(KEY, key))
        result["sessions"] = len(entries)
        for metric in METRICS:
            values = [v for _, row in entries if (v := number_or_none(row[metric])) is not None]
            result[metric] = statistics.median(values) if values else ""
            if metric == "p50_ms" and values:
                result["p50_session_min_ms"], result["p50_session_max_ms"] = min(values), max(values)
                result["session_spread_percent"] = 100 * (max(values) - min(values)) / statistics.median(values)
        result["headline"] = all(str(row.get("headline", "")).lower() == "true" for _, row in entries)
        pool = pools.get(key)
        if pool:
            result.update(
                pooled_samples=pool["samples"],
                pooled_p95_ms=pool["p95_ms"] if pool["p95_ms"] is not None else pool["p95_label"],
                pooled_p99_ms=pool["p99_ms"] if pool["p99_ms"] is not None else pool["p99_label"],
            )
        headline.append(result)
    return usable, headline


def aggregate(directories, output):
    sessions = [load_session(directory, number) for number, directory in enumerate(directories, start=1)]
    usable, headline = combine(sessions)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    table(output / "headline.csv", headline)
    table(
        output / "sessions.csv",
        [
            {
                "session": session["number"],
                "directory": session["directory"].name,
                "commit": session["commit"],
                "in_headline": not session["reasons"],
                "baseline_drift_flagged": session["drift_flagged"],
                **{
                    "output": row["output"],
                    "engine": row["engine"],
                    "variant": row["variant"],
                    "clients": row["clients"],
                },
                **{metric: row[metric] for metric in METRICS},
            }
            for session in sessions
            for row in session["rows"]
            if row["status"] == "passed" and row["p50_ms"]
        ],
    )
    table(
        output / "excluded.csv",
        [
            {"session": s["number"], "directory": s["directory"].name, "reason": "; ".join(s["reasons"])}
            for s in sessions
            if s["reasons"]
        ],
    )
    pairs = [
        {
            "output": r["output"],
            "engine": r["engine"],
            "variant": r["variant"],
            "clients": r["clients"],
            "p50_ms": r["p50_ms"],
            "status": "passed",
            "headline": r["headline"],
            "sessions": r["sessions"],
        }
        for r in headline
    ]
    table(output / "b2-headline.csv", b2_headline(pairs))
    commits = {s["commit"] for s in usable}
    notes = []
    if len(usable) < MINIMUM_SESSIONS:
        notes.append(f"only {len(usable)} usable sessions; the plan calls for {MINIMUM_SESSIONS}")
    if len(commits) > 1:
        notes.append("the usable sessions come from different commits: " + ", ".join(sorted(commits)))
    (output / "NOTES.txt").write_text("\n".join(notes) + ("\n" if notes else ""), encoding="utf-8", newline="\n")
    return {"sessions": len(sessions), "usable": len(usable), "excluded": len(sessions) - len(usable), "notes": notes}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sessions", nargs="+", type=Path, help="session result folders, in the order they ran")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = aggregate(args.sessions, args.output)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
