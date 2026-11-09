"""Stampede and limiter-cost experiments (docs/plans/redis.md).

Stampede: N simultaneous requests for a cold dashboard, with Redis on and off. The metric is how many ran the expensive
history computation: with the lock one request computes and the others wait; without Redis every request computes. The web
server has two workers, which bounds the real parallelism, and the report says so.

Limiter cost: the sliding-window limiter call timed on its own, beside a bare Redis round trip, inside the web container.

    python -m benchmarks.redis_stampede --project mercer-redis-final --base-url http://127.0.0.1:18083
"""

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from benchmarks.pooling import summarise
from benchmarks.redis_stack import ColdHelper, Stack, now_iso, redis_restored
from benchmarks.redis_stats import ExperimentError, join_responses, stampede_outcome
from benchmarks.request_timing import ROOT, TimingError, fetch, write_csv

WORKERS = 2


def fire(stack, opener, simultaneous):
    barrier = Barrier(simultaneous)

    def one(_):
        barrier.wait()
        row, _body, _headers = fetch(opener, stack.base_url, "/operator/dashboard/")
        if row["status"] != 200:
            raise ExperimentError(f"A simultaneous dashboard request returned status {row['status']}")
        return {**row, "page": "dashboard"}

    with ThreadPoolExecutor(simultaneous) as pool:
        return list(pool.map(one, range(simultaneous)))


def run(args):
    stack = Stack(args.project, args.base_url, args.env_file, args.source)
    commit, dirty = stack.commit()
    if args.require_clean and dirty:
        raise TimingError("This run requires a clean committed tree")
    output = (
        ROOT
        / "benchmarks/results"
        / f"{time.strftime('%Y-%m-%dT%H%M%S')}_{commit[:8]}{'-dirty' if dirty else ''}_redis-stampede"
    )
    output.mkdir(parents=True, exist_ok=False)
    started_at = now_iso()
    rows = []
    with redis_restored(stack):
        for mode, enabled in (("redis_on", True), ("redis_off", False)):
            stack.recreate_web(enabled)
            _, operator = stack.openers()
            for _ in range(2 * WORKERS):
                stack.timed_get(operator, "dashboard", "/operator/dashboard/")  # untimed: workers and databases warm
            helper = ColdHelper(stack) if enabled else None
            try:
                for repetition in range(1, args.repetitions + 1):
                    if helper:
                        helper.clear("dashboard")  # a version nobody has cached: the next dashboard request is a miss
                    since = now_iso()
                    responses = fire(stack, operator, args.simultaneous)
                    logs = stack.logs(since, {r["request_id"] for r in responses})
                    outcome = stampede_outcome(join_responses(responses, logs))
                    rows.append({"mode": mode, "repetition": repetition, "simultaneous": args.simultaneous, **outcome})
                    print(mode, repetition, outcome, flush=True)
            finally:
                if helper:
                    helper.close()
        stack.recreate_web(True)
        timings = stack.limiter_timings(args.limiter_calls)
    write_csv(output / "stampede.csv", rows)
    limiter = []
    for name, values in timings.items():  # the values are microseconds
        summary = summarise(values)
        limiter.append(
            {
                "operation": name.removesuffix("_us"),
                "calls": summary["samples"],
                "p50_us": summary["p50_ms"],
                "p95_us": summary["p95_ms"] if summary["p95_ms"] is not None else summary["p95_label"],
                "p99_us": summary["p99_ms"] if summary["p99_ms"] is not None else summary["p99_label"],
                "min_us": summary["min_ms"],
                "max_us": summary["max_ms"],
            }
        )
    write_csv(output / "limiter.csv", limiter)
    provenance = {
        "commit": commit + ("-dirty" if dirty else ""),
        "project": args.project,
        "host": stack.host(),
        "started_at": started_at,
        "finished_at": now_iso(),
        "simultaneous": args.simultaneous,
        "repetitions": args.repetitions,
        "limiter_calls": args.limiter_calls,
        "workers": WORKERS,
        "pilot": args.simultaneous < 8 or args.repetitions < 5,
        "note": f"the web server has {WORKERS} workers, which bounds how many requests truly run in parallel",
        "metric": "computed = requests whose cache status is miss, off or down (they ran the history computation)",
    }
    (output / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({"results": str(output), "rows": len(rows)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--source", type=Path, default=ROOT / "data/derived/olist/clean")
    parser.add_argument("--simultaneous", type=int, default=8)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--limiter-calls", type=int, default=2000)
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args()
    if min(args.simultaneous, args.repetitions, args.limiter_calls) < 1:
        parser.error("Counts must be positive")
    try:
        run(args)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        safe = isinstance(error, (TimingError, ExperimentError))
        print(f"redis stampede failed: {error if safe else type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
