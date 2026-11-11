"""Measure what Redis does for the shop: off, cold, warm and down, in a seeded Latin-square order (docs/plans/redis.md).

Run it alone (never beside a benchmark), after the full benchmark, against an isolated app stack that has the Olist data,
`seed_demo` and `seed_activity` loaded (see the README):

    python -m benchmarks.redis_experiment --project mercer-redis-final --base-url http://127.0.0.1:18083 --require-clean

Each condition recreates the web container (so its workers and connections start clean), runs an untimed pass of twice the
worker count per page, then times sequential requests. cold clears the cached entry before every timed request of a
cached page, warm is primed once, down pauses the Redis container, off runs with REDIS_ENABLED=false. Requests are joined
to the server's own request log by ID, and benchmarks/redis_stats.py decides which samples count.
"""

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from benchmarks.redis_report import write_reports
from benchmarks.redis_stack import ColdHelper, Stack, now_iso, redis_restored
from benchmarks.redis_stats import (
    CACHED_PAGES,
    CONDITIONS,
    DATA_DIGEST_VERSION,
    REQUEST_FIELDS,
    ExperimentError,
    digest,
    join_responses,
    latin_square,
    product_links,
    settle,
    trending_leader,
)
from benchmarks.request_timing import ROOT, TimingError, write_csv

PAGE_ORDER = ("shop", "search", "dashboard", "product_detail", "category_trending")
WORKERS = 2  # gunicorn --workers in src/Dockerfile
DEFAULT_CHEAP, DEFAULT_DASHBOARD = 150, 15
FIELDS = (
    "round", "condition", "page", "request_id", "path", "status", "client_ms", "x_cache", "digest", "cache",
    "received_at", "condition_elapsed_ms",
)  # fmt: skip
DIAGNOSTICS_SCHEMA_VERSION = 1


class Diagnostics:
    """Retain public link signatures and priming metadata, never HTML, cookies or visitor identities."""

    def __init__(self):
        self.signatures = {}
        self.warm_up = []

    def signature(self, page, body):
        value = digest(page, body) or ""
        if page in ("shop", "search") and (page, value) not in self.signatures:
            self.signatures[page, value] = product_links(body)
        return value

    def write(self, output):
        payload = {
            "schema_version": DIAGNOSTICS_SCHEMA_VERSION,
            "signatures": [
                {"page": page, "digest": value, "product_ids": ids}
                for (page, value), ids in sorted(self.signatures.items())
            ],
        }
        (output / "data-signatures.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
        write_csv(output / "warm-up.csv", self.warm_up)


def measure(stack, condition, round_index, pages, cheap, dashboard, diagnostics):
    if condition == "down":
        stack.unpause_redis()
    stack.recreate_web(condition != "off")
    anonymous, operator = stack.openers()
    opener = {"dashboard": operator}
    started = now_iso()
    condition_started = time.perf_counter()

    def get(page):
        row, body, headers, elapsed = stack.timed_get(opener.get(page, anonymous), page, pages[page])
        # Capture receipt time before digest/diagnostic work, outside the existing client and server timing boundaries.
        received_at = now_iso()
        condition_elapsed_ms = (time.perf_counter() - condition_started) * 1000
        return {
            **row,
            "page": page,
            "client_ms": elapsed,
            "x_cache": headers.get("X-Cache") or "",
            "digest": diagnostics.signature(page, body),
            "received_at": received_at,
            "condition_elapsed_ms": condition_elapsed_ms,
        }

    warm_up = []
    for _ in range(2 * WORKERS):  # untimed: both workers and both databases warm, the cache primed where it is on
        for page in PAGE_ORDER:
            warm_up.append(get(page))
    helper = ColdHelper(stack) if condition == "cold" else None
    if condition == "down":
        stack.pause_redis()
    responses = []
    try:
        for page in PAGE_ORDER:
            for _ in range(dashboard if page == "dashboard" else cheap):
                if helper and page in ("shop", "search"):
                    helper.clear("trending")
                elif helper and page == "dashboard":
                    helper.clear("dashboard")
                responses.append(get(page))
    finally:
        if helper:
            helper.close()
        if condition == "down":
            stack.unpause_redis()
    logs = stack.logs(started, {r["request_id"] for r in [*warm_up, *responses]})
    diagnostics.warm_up += [{**r, "condition": condition, "round": round_index} for r in join_responses(warm_up, logs)]
    return [{**r, "condition": condition, "round": round_index} for r in join_responses(responses, logs)]


def settle_ranking(stack, pages, anonymous):
    """Untimed: distinct anonymous visitors make the control lead, then its ranking must hold still (redis_stats.settle)."""
    helper = ColdHelper(stack)
    control = int(re.search(r"/products/(\d+)/", pages["product_detail"])[1])
    latest = {}
    try:

        def ranking():
            helper.clear("trending")  # never read the cached copy
            _row, body, _headers, _elapsed = stack.timed_get(anonymous, "shop", pages["shop"])
            latest["leader"] = trending_leader(body)
            return digest("shop", body)

        def view():
            # Trending counts distinct visitors, so one cookie jar's repeated views would count only once. Keep this
            # traffic separate from the ranking probe and the measured conditions, which retain their own sessions.
            stack.timed_get(stack.anonymous_opener(), "product_detail", pages["product_detail"])

        return settle(view, ranking, leader=lambda: latest.get("leader") == control)
    finally:
        helper.close()


def run(args):
    stack = Stack(args.project, args.base_url, args.env_file, args.source)
    commit, dirty = stack.commit()
    if args.require_clean and dirty:
        raise TimingError("This run requires a clean committed tree")
    square = latin_square(args.seed)
    pilot = args.requests < DEFAULT_CHEAP or args.dashboard_requests < DEFAULT_DASHBOARD
    stamp = time.strftime("%Y-%m-%dT%H%M%S")
    output = ROOT / "benchmarks/results" / f"{stamp}_{commit[:8]}{'-dirty' if dirty else ''}_redis"
    output.mkdir(parents=True, exist_ok=False)
    started_at = now_iso()
    samples, rounds = [], []
    diagnostics = Diagnostics()
    with redis_restored(stack):
        stack.recreate_web(True)
        anonymous, _ = stack.openers()
        pages = stack.pages(anonymous)
        burn_in = settle_ranking(stack, pages, anonymous)
        for index, order in enumerate(square, start=1):
            events_start = stack.events()
            for condition in order:
                print(f"round {index} {condition}", flush=True)
                samples += measure(stack, condition, index, pages, args.requests, args.dashboard_requests, diagnostics)
            rounds.append(
                {"round": index, "order": " ".join(order), "events_start": events_start, "events_end": stack.events()}
            )
    with (output / "samples.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=[*FIELDS, *REQUEST_FIELDS], extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(samples)
    write_csv(output / "rounds.csv", rounds)
    diagnostics.write(output)
    provenance = {
        "commit": commit + ("-dirty" if dirty else ""),
        "project": args.project,
        "host": stack.host(),
        "started_at": started_at,
        "finished_at": now_iso(),
        "seed": args.seed,
        "latin_square": square,
        "conditions": list(CONDITIONS),
        "pages": pages,
        "cached_pages": list(CACHED_PAGES),
        "requests_per_cheap_page": args.requests,
        "requests_dashboard": args.dashboard_requests,
        "untimed_requests_per_page": 2 * WORKERS,
        "burn_in_passes": burn_in,
        "burn_in_visitors": "a fresh anonymous cookie jar per untimed control-product view",
        "workers": WORKERS,
        "data_digest_version": DATA_DIGEST_VERSION,
        "diagnostics": {
            "schema_version": DIAGNOSTICS_SCHEMA_VERSION,
            "signatures": "data-signatures.json: public product ID strings in exact digest order, once per page/digest",
            "warm_up": "warm-up.csv: untimed priming responses joined to request logs, excluded from samples and gates",
            "received_at": "host UTC after the response, before digest/diagnostic work",
            "condition_elapsed_ms": "host monotonic time since before the first untimed request of the condition",
        },
        "pilot": pilot,
        "pilot_note": "sample sizes below the protocol's: set sizes only, not evidence" if pilot else "",
        "cold": "the cached entry is cleared before every timed request of a cached page (round trip inside the web container)",
        "down": "the Redis container is paused after the untimed pass, so the first requests pay the real timeout",
    }
    (output / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    analysis = write_reports(output)
    print(
        json.dumps(
            {"results": str(output), "accepted": analysis["accepted"], "refused": analysis["refused"], "pilot": pilot}
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--source", type=Path, default=ROOT / "data/derived/olist/clean")
    parser.add_argument(
        "--requests", type=int, default=DEFAULT_CHEAP, help="timed requests per cheap page per condition"
    )
    parser.add_argument("--dashboard-requests", type=int, default=DEFAULT_DASHBOARD)
    parser.add_argument("--seed", type=int, default=82)
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args()
    if args.requests < 1 or args.dashboard_requests < 1:
        parser.error("Request counts must be positive")
    try:
        run(args)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        # Exception messages, HTTP bodies and command output may contain secrets.
        safe = isinstance(error, (TimingError, ExperimentError))
        print(f"redis experiment failed: {error if safe else type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
