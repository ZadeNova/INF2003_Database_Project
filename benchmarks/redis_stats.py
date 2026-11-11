"""Statistics, gates and log parsing for the Redis experiment (docs/plans/redis.md, "Measurement protocol").

Pure functions, standard library only, so the evidence rules are tested without Docker. The protocol in one paragraph:
four conditions (off, cold, warm, down) are measured in four rounds whose order is a seeded Latin square; a sample counts
only when its cache status matches its condition and its data equals the off condition's in the same round; the main
evidence is the per-round paired ratio of medians, because requests within a round are not independent; negative control
pages that Redis never touches set a noise floor, and no effect smaller than it is claimed.
"""

import hashlib
import json
import math
import random
import re
import statistics
from collections import Counter, defaultdict
from urllib.parse import urlsplit

from benchmarks.pooling import summarise

CONDITIONS = ("off", "cold", "warm", "down")
CACHED_PAGES = ("shop", "search", "dashboard")
CONTROL_PAGES = ("product_detail", "category_trending")
EXPECTED_CACHE = {"off": {"off"}, "cold": {"miss"}, "warm": {"hit"}, "down": {"down"}}
# (numerator, denominator, what a ratio above 1 means)
PAIRS = (
    ("off", "warm", "cache benefit (off / warm)"),
    ("cold", "off", "cost of a miss (cold / off)"),
    ("down", "off", "cost of an outage (down / off)"),
)
REQUEST_FIELDS = (
    "duration_ms",
    "db_pg_ms",
    "db_pg_queries",
    "db_mongo_ms",
    "db_mongo_commands",
    "redis_ms",
    "redis_commands",
)
BOOTSTRAP_RESAMPLES = 2000
DATA_DIGEST_VERSION = 2


class ExperimentError(ValueError):
    """A diagnostic written here, safe to display without HTTP or command output."""


# ------------------------------------------------------------------------------------------------ design
def latin_square(seed, conditions=CONDITIONS):
    """One order of the conditions per round; every condition holds every position exactly once.

    With an even number of conditions this is a Williams design: each condition also follows every other condition exactly
    once, so what one condition leaves behind (a warm cache, a paused Redis) is spread evenly over the rest instead of
    always reaching the same successor. The seed only chooses which condition takes which place in the design and the order
    of the rounds, so the balance survives. An odd number falls back to the cyclic square."""
    rng = random.Random(seed)
    size = len(conditions)
    if size % 2:
        first = list(range(size))
    else:
        first, low, high = [0], 1, size - 1
        while len(first) < size:
            first.append(low)
            low += 1
            if len(first) < size:
                first.append(high)
                high -= 1
    labels = list(conditions)
    rng.shuffle(labels)
    rows = [[labels[(place + row) % size] for place in first] for row in range(size)]
    rng.shuffle(rows)
    return rows


# ------------------------------------------------------------------------------------------------ evidence
def product_links(body):
    """Public product IDs in the exact link order hashed for shop/search, retaining duplicates and decimal spelling."""
    return re.findall(r'href="/products/(\d+)/"', body)


def digest(page, body):
    """What 'the same data' means for a page: the product links in order for the shop and search lists, the page without volatile parts
    (the CSRF token and the cache note, which differ by condition by design) for the dashboard. Controls have none."""
    if page in ("shop", "search"):
        text = "|".join(product_links(body))
    elif page == "dashboard":
        text = re.sub(r'name="csrfmiddlewaretoken" value="[^"]*"', "", body)
        # The real template emits a newline/indentation inside the cache-note conditional, before its closing div.
        # Remove that fragment only; global whitespace folding could hide a changed gap between inline values.
        text = re.sub(r'<p class="page__lead">Delivery, category[^<]*</p>(?:\r?\n[ \t]*(?=</div>))?', "", text)
    else:
        return None
    return hashlib.sha256(text.encode()).hexdigest()


def parse_logs(text, request_ids):
    """Request log lines (Compose prefixes allowed) of the selected requests, with the Redis fields of Batch 5."""
    result = {}
    for line in text.splitlines():
        start = line.find("{")
        if start < 0:
            continue
        try:
            row = json.loads(line[start:])
        except ValueError:
            continue
        if not isinstance(row, dict) or row.get("logger") != "mercer.request" or row.get("message") != "request":
            continue
        identity = row.get("request_id")
        if not isinstance(identity, str) or identity not in request_ids:
            continue
        if identity in result:
            raise ExperimentError("Duplicate request log ID")
        result[identity] = {key: row.get(key) for key in ("method", "path", "status", "cache", *REQUEST_FIELDS)}
    return result


def join_responses(responses, logs):
    """Require an exact, valid log line for every response before any timing is accepted."""
    joined, seen = [], set()
    for response in responses:
        identity = response["request_id"]
        if identity in seen:
            raise ExperimentError("Duplicate response ID")
        seen.add(identity)
        row = logs.get(identity)
        if row is None:
            raise ExperimentError("Missing request log")
        if (row["method"], row["path"], row["status"]) != ("GET", urlsplit(response["path"]).path, response["status"]):
            raise ExperimentError("Response and request log disagree")
        for key in REQUEST_FIELDS:
            value = row[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ExperimentError("Missing or invalid request metric")
        if not isinstance(row["cache"], str):
            raise ExperimentError("Missing cache status")
        joined.append({**response, **{key: row[key] for key in (*REQUEST_FIELDS, "cache")}})
    return joined


def trending_leader(body):
    """The product id on the 'Rank 1' card of the shop page's trending panel, or None when the panel is empty."""
    match = re.search(r'Rank 1 ·.*?href="/products/(\d+)/"', body, re.S)
    return int(match[1]) if match else None


BURN_IN_VIEWS = 20
BURN_IN_LIMIT = 50


def settle(view, ranking, leader=None, views=BURN_IN_VIEWS, limit=BURN_IN_LIMIT):
    """Untimed warm-up of the trending ranking before round 1.

    The product-detail control records a view event on every request, but trending counts distinct visitors. Each `view`
    must therefore use a fresh visitor: repeated views in one session count only once. Bringing the control to the lead,
    then requiring the ranking to hold still for a further pass, keeps later views from moving it: the most viewed product
    stays first however many more visitors it gets. Without `leader` only the second condition applies. Returns the number
    of passes, or raises if the ranking never settles."""
    previous = None
    for attempt in range(1, limit + 1):
        for _ in range(views):
            view()
        current = ranking()
        if current == previous and (leader is None or leader()):
            return attempt
        previous = current
    raise ExperimentError("The trending ranking did not settle during the burn-in")


def gate(sample):
    """The reason a sample is refused by its cache status, or None. The sample carries its page and condition."""
    if sample["status"] != 200:
        return f"status {sample['status']}"
    if sample["page"] in CONTROL_PAGES:
        if sample["redis_commands"] or sample["cache"] not in ("", "off"):
            return "a control page touched Redis"
        return None
    if sample["cache"] not in EXPECTED_CACHE[sample["condition"]]:
        return f"cache status {sample['cache']!r} in a {sample['condition']} condition"
    if sample["condition"] == "off" and sample["redis_commands"]:
        return "Redis commands in the off condition"
    return None


def apply_gates(samples):
    """Split samples into (accepted, refused with a reason). The data gate compares each digest with the most common
    digest of the same page's off samples in the same round."""
    references = {}
    votes = defaultdict(Counter)
    for sample in samples:
        if sample["condition"] == "off" and sample.get("digest") and gate(sample) is None:
            votes[sample["page"], sample["round"]][sample["digest"]] += 1
    for key, counter in votes.items():
        references[key] = counter.most_common(1)[0][0]
    accepted, refused = [], []
    for sample in samples:
        reason = gate(sample)
        reference = references.get((sample["page"], sample["round"]))
        if reason is None and sample.get("digest"):
            if reference is None:
                reason = "no off reference in the same round to compare the data with"
            elif sample["digest"] != reference:
                reason = "data differs from the off condition's in the same round"
        (refused if reason else accepted).append({**sample, "refusal": reason} if reason else sample)
    return accepted, refused


# ------------------------------------------------------------------------------------------------ analysis
def _bootstrap_ratio(numerator, denominator, seed):
    """A 95% percentile interval for the ratio of medians from pooled requests; optimistic, because requests within a
    round are not independent. Fixed seed, so the same data always gives the same interval."""
    rng = random.Random(seed)
    ratios = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        top = statistics.median(rng.choices(numerator, k=len(numerator)))
        bottom = statistics.median(rng.choices(denominator, k=len(denominator)))
        if bottom:
            ratios.append(top / bottom)
    ratios.sort()
    return ratios[int(0.025 * len(ratios))], ratios[min(len(ratios) - 1, int(0.975 * len(ratios)))]


def analyse(samples, *, metric="duration_ms", seed=82):
    accepted, refused = apply_gates(samples)
    pages = [p for p in (*CACHED_PAGES, *CONTROL_PAGES) if any(s["page"] == p for s in samples)]
    by_cell = defaultdict(list)
    by_round = defaultdict(list)
    for sample in accepted:
        by_cell[sample["page"], sample["condition"]].append(sample)
        by_round[sample["page"], sample["round"], sample["condition"]].append(sample[metric])
    round_median = {key: statistics.median(values) for key, values in by_round.items()}

    cells = []
    for page in pages:
        for condition in CONDITIONS:
            group = by_cell.get((page, condition), [])
            if not group:
                continue
            values = [s[metric] for s in group]
            cells.append(
                {
                    "page": page,
                    "condition": condition,
                    **summarise(values),
                    "refused": sum(1 for s in refused if (s["page"], s["condition"]) == (page, condition)),
                    **{
                        f"{field}_median": statistics.median(s[field] for s in group)
                        for field in ("db_pg_ms", "db_mongo_ms", "redis_ms", "redis_commands")
                    },
                }
            )

    ratios = []
    exact = {}  # the unrounded per-round ratios, for the noise floor and the verdicts
    for page in pages:
        for top, bottom, meaning in PAIRS:
            rounds = sorted(
                {r for p, r, c in round_median if p == page and c == top}
                & {r for p, r, c in round_median if p == page and c == bottom}
            )
            values = [
                round_median[page, r, top] / round_median[page, r, bottom]
                for r in rounds
                if round_median[page, r, bottom]
            ]
            if values:
                exact[page, f"{top}/{bottom}"] = values
                ratios.append(
                    {
                        "page": page,
                        "pair": f"{top}/{bottom}",
                        "meaning": meaning,
                        "rounds": len(values),
                        "ratio_median": statistics.median(values),
                        "ratio_min": min(values),
                        "ratio_max": max(values),
                        "per_round": ";".join(f"{v:.4f}" for v in values),
                    }
                )

    deviations = [max(abs(v - 1) for v in values) for (page, _), values in exact.items() if page in CONTROL_PAGES]
    noise_floor = max(deviations) if deviations else None
    verdicts = []
    for row in ratios:
        if row["page"] not in CACHED_PAGES:
            continue
        per_round = exact[row["page"], row["pair"]]
        same_side = all(v > 1 for v in per_round) or all(v < 1 for v in per_round)
        effect = abs(row["ratio_median"] - 1)
        claimable = noise_floor is not None and same_side and effect > noise_floor
        verdicts.append(
            {
                "page": row["page"],
                "pair": row["pair"],
                "effect": effect,
                "noise_floor": noise_floor,
                "same_side_every_round": same_side,
                "claim": "yes" if claimable else "no: not distinguishable from the noise floor",
            }
        )

    bootstrap = []
    for page in CACHED_PAGES:
        top = [s[metric] for s in by_cell.get((page, "off"), [])]
        bottom = [s[metric] for s in by_cell.get((page, "warm"), [])]
        if top and bottom:
            low, high = _bootstrap_ratio(top, bottom, seed)
            bootstrap.append({"page": page, "pair": "off/warm", "ci_low": low, "ci_high": high, "label": "optimistic"})

    reasons = Counter((s["page"], s["condition"], s["refusal"]) for s in refused)
    refusals = [
        {"page": page, "condition": condition, "reason": reason, "samples": count}
        for (page, condition, reason), count in sorted(reasons.items())
    ]
    return {
        "cells": cells,
        "ratios": ratios,
        "verdicts": verdicts,
        "bootstrap": bootstrap,
        "refusals": refusals,
        "noise_floor": noise_floor,
        "accepted": len(accepted),
        "refused": len(refused),
    }


# ------------------------------------------------------------------------------------------------ stampede
def stampede_outcome(samples):
    """How many of N simultaneous cold dashboard requests ran the expensive history computation. A miss computes (under
    the lock); a wait or a hit does not; with Redis off every request computes."""
    statuses = Counter(s["cache"] for s in samples)
    durations = [s["duration_ms"] for s in samples]
    return {
        "requests": len(samples),
        "computed": statuses["miss"] + statuses["off"] + statuses["down"],
        "waited": statuses["wait"],
        "hit": statuses["hit"],
        "median_ms": statistics.median(durations),
        "max_ms": max(durations),
    }
