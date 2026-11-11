import collections, csv, difflib, hashlib, json, math, re, shutil, sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from benchmarks.redis_report import read_samples, write_reports, INTEGER_FIELDS, FLOAT_FIELDS
from benchmarks.redis_stats import apply_gates, analyse, latin_square, CACHED_PAGES, CONTROL_PAGES, DATA_DIGEST_VERSION
from benchmarks.report import table

ROOT = Path.cwd()
OUT = ROOT / "benchmarks/results/redis-v2-2026-11-11"
result = next((ROOT / "benchmarks/results").glob("*_b82ac876_redis"))
p = json.loads((result / "provenance.json").read_text())
samples = read_samples(result)
with (result / "warm-up.csv").open(newline="") as f:
    priming = list(csv.DictReader(f))
for row in priming:
    for key in INTEGER_FIELDS:
        row[key] = int(float(row[key]))
    for key in FLOAT_FIELDS:
        row[key] = float(row[key])
assert (
    p["commit"] == "b82ac876e9ff0fa4d3f530d81d70fa2b434c8e43"
    and not p["pilot"]
    and p["seed"] == 82
    and p["data_digest_version"] == DATA_DIGEST_VERSION == 2
    and p["diagnostics"]["schema_version"] == 1
)
assert (
    p["requests_dashboard"] == 15
    and p["requests_per_cheap_page"] == 150
    and p["untimed_requests_per_page"] == 4
    and 2 <= p["burn_in_passes"] <= 50
    and p["latin_square"] == latin_square(82)
)
assert len(samples) == 9840 and len(priming) == 320
measured_ids = {r["request_id"] for r in samples}
priming_ids = {r["request_id"] for r in priming}
assert len(measured_ids) == 9840 and len(priming_ids) == 320 and not measured_ids & priming_ids
counts = collections.Counter((r["round"], r["condition"], r["page"]) for r in samples)
warm_counts = collections.Counter((r["round"], r["condition"], r["page"]) for r in priming)
assert (
    len(counts) == 80
    and all(n == (15 if key[2] == "dashboard" else 150) for key, n in counts.items())
    and set(warm_counts) == set(counts)
    and all(n == 4 for n in warm_counts.values())
)
for index, order in enumerate(p["latin_square"], 1):
    seen = []
    for row in samples:
        if row["round"] == index and (not seen or seen[-1] != row["condition"]):
            seen.append(row["condition"])
    assert seen == order
allrows = priming + samples
for row in allrows:
    assert row["status"] == 200
    assert all(math.isfinite(row[key]) and row[key] >= 0 for key in FLOAT_FIELDS)
    assert datetime.fromisoformat(row["received_at"]).utcoffset() == timedelta(0)
    row["condition_elapsed_ms"] = float(row["condition_elapsed_ms"])
    assert math.isfinite(row["condition_elapsed_ms"]) and row["condition_elapsed_ms"] >= 0
clock = []
for round_index, order in enumerate(p["latin_square"], 1):
    for condition in order:
        warm = [r for r in priming if (r["round"], r["condition"]) == (round_index, condition)]
        timed = [r for r in samples if (r["round"], r["condition"]) == (round_index, condition)]
        group = warm + timed
        assert max(r["condition_elapsed_ms"] for r in warm) < min(r["condition_elapsed_ms"] for r in timed)
        assert all(b["condition_elapsed_ms"] > a["condition_elapsed_ms"] for a, b in zip(group, group[1:]))
        dates = [datetime.fromisoformat(r["received_at"]) for r in group]
        assert all(b >= a for a, b in zip(dates, dates[1:]))
        offsets = [
            date.timestamp() * 1000 - row["condition_elapsed_ms"] for date, row in zip(dates, group, strict=True)
        ]
        clock.append(
            {
                "round": round_index,
                "condition": condition,
                "priming_records": len(warm),
                "measured_records": len(timed),
                "UTC_backsteps": 0,
                "UTC_minus_monotonic_base_spread_ms": max(offsets) - min(offsets),
                "last_priming_elapsed_ms": max(r["condition_elapsed_ms"] for r in warm),
                "first_measured_elapsed_ms": min(r["condition_elapsed_ms"] for r in timed),
            }
        )
table(OUT / "timing-and-priming.csv", clock)
sig = json.loads((result / "data-signatures.json").read_text())
assert sig["schema_version"] == 1
mapping = {}
for row in sig["signatures"]:
    assert row["page"] in ("shop", "search") and all(
        isinstance(v, str) and re.fullmatch(r"\d+", v) for v in row["product_ids"]
    )
    assert hashlib.sha256("|".join(row["product_ids"]).encode()).hexdigest() == row["digest"]
    assert (row["page"], row["digest"]) not in mapping
    mapping[row["page"], row["digest"]] = row["product_ids"]
assert set(mapping) == {(r["page"], r["digest"]) for r in allrows if r["page"] in ("shop", "search")}
accepted, refused = apply_gates(samples)
a = analyse(samples)
assert a["accepted"] + a["refused"] == len(samples)
cellcounts = collections.Counter((r["round"], r["condition"], r["page"]) for r in accepted)
table(
    OUT / "condition-coverage.csv",
    [
        {
            "round": key[0],
            "condition": key[1],
            "page": key[2],
            "requested": n,
            "accepted": cellcounts[key],
            "refused": n - cellcounts[key],
        }
        for key, n in sorted(counts.items())
    ],
)
reasons = collections.Counter((r["round"], r["condition"], r["page"], r["refusal"]) for r in refused)
table(
    OUT / "refusals-by-round.csv",
    [
        {"round": key[0], "condition": key[1], "page": key[2], "reason": key[3], "samples": n}
        for key, n in sorted(reasons.items())
    ],
)
comparisons = []
for page in (*CACHED_PAGES, *CONTROL_PAGES):
    for top, bottom in [("off", "warm"), ("cold", "off"), ("down", "off")]:
        usable = [n for n in range(1, 5) if cellcounts[n, top, page] and cellcounts[n, bottom, page]]
        row = next((r for r in a["ratios"] if r["page"] == page and r["pair"] == top + "/" + bottom), None)
        verdict = next((r for r in a["verdicts"] if r["page"] == page and r["pair"] == top + "/" + bottom), None)
        comparisons.append(
            {
                "page": page,
                "pair": top + "/" + bottom,
                "usable_rounds": ";".join(map(str, usable)),
                "usable_paired_rounds": len(usable),
                "four_paired_rounds": len(usable) == 4,
                "min_accepted_samples_in_paired_cell": min(
                    (cellcounts[n, c, page] for n in usable for c in (top, bottom)), default=0
                ),
                "ratio_median": row["ratio_median"] if row else "",
                "claim": verdict["claim"] if verdict else "negative control" if row else "unavailable",
                "protocol_status": "available; reduced paired coverage disclosed"
                if row and len(usable) < 4
                else "available"
                if row
                else "unavailable",
            }
        )
table(OUT / "comparison-usability.csv", comparisons)
# Diagnose refused data directly from the new ordered public signatures, not from historical hashes or hypotheses.
references = {}
for row in samples:
    if row["condition"] == "off":
        references.setdefault((row["round"], row["page"]), collections.Counter())[row["digest"]] += 1
diagnoses = []
for key, n in sorted(reasons.items()):
    round_index, condition, page, reason = key
    group = [r for r in refused if (r["round"], r["condition"], r["page"], r["refusal"]) == key]
    first = group[0]
    entry = {
        "round": round_index,
        "condition": condition,
        "page": page,
        "reason": reason,
        "samples": n,
        "first_received_at": first["received_at"],
        "first_condition_elapsed_ms": first["condition_elapsed_ms"],
        "confirmed_observation": "cache miss in measured warm request"
        if "cache status" in reason
        else "ordered public product links differ from same-round off reference",
        "mechanism_status": "TTL expiry is consistent with timing; key creation/TTL/eviction was not directly recorded"
        if "cache status" in reason
        else "link reordering confirmed; rolling-window event expiry is a hypothesis, not directly established",
    }
    if page in ("shop", "search") and "data differs" in reason:
        expected = mapping[page, references[round_index, page].most_common(1)[0][0]]
        actual = mapping[page, first["digest"]]
        entry["link_differences"] = [
            {
                "operation": op,
                "expected_ids": expected[i:j],
                "observed_ids": actual[k:l],
                "expected_positions": [i, j],
                "observed_positions": [k, l],
            }
            for op, i, j, k, l in difflib.SequenceMatcher(a=expected, b=actual, autojunk=False).get_opcodes()
            if op != "equal"
        ]
        entry["same_multiset_of_ids"] = collections.Counter(expected) == collections.Counter(actual)
    else:
        prior_cold = [
            r
            for r in samples
            if r["condition"] == "cold"
            and r["page"] == "search"
            and datetime.fromisoformat(r["received_at"]) < datetime.fromisoformat(first["received_at"])
        ]
        if prior_cold:
            last = max(prior_cold, key=lambda r: r["received_at"])
            entry["seconds_since_latest_cold_search_response"] = (
                datetime.fromisoformat(first["received_at"]) - datetime.fromisoformat(last["received_at"])
            ).total_seconds()
        entry["priming_cache_states"] = [
            {"received_at": r["received_at"], "cache": r["cache"], "condition_elapsed_ms": r["condition_elapsed_ms"]}
            for r in priming
            if (r["round"], r["condition"], r["page"]) == (round_index, condition, page)
        ]
    diagnoses.append(entry)
(OUT / "refusal-diagnosis.json").write_text(
    json.dumps(
        {"diagnostic_schema": 1, "digest_version": 2, "groups": diagnoses, "no_old_sample_reinterpretation": True},
        indent=2,
    )
    + "\n"
)
reports = ["summary.csv", "ratios.csv", "verdicts.csv", "bootstrap.csv", "refusals.csv", "chart.svg", "analysis.json"]
scratch = OUT / "regeneration.local"
shutil.copytree(result, scratch, dirs_exist_ok=True)
write_reports(scratch)
assert all((scratch / name).read_bytes() == (result / name).read_bytes() for name in reports)
commands = [json.loads(l) for l in (OUT / "commands.jsonl").read_text().splitlines()]
assert next(r["exit_code"] for r in commands if r["step"] == "redis-measurement") == 0
containers = json.loads((OUT / "containers-after.json").read_text())
assert all(
    not row["state"]["oom"] and not row["state"]["paused"] and row["state"]["restarts"] == 0 for row in containers
)
available = all(r["usable_paired_rounds"] > 0 for r in comparisons)
validation = {
    "source_commit": p["commit"],
    "execution_exit_zero": True,
    "full_default_matrix": True,
    "pilot": False,
    "seed": 82,
    "burn_in_passes": p["burn_in_passes"],
    "leader_and_stability_checks_passed": True,
    "digest_version": 2,
    "diagnostic_schema": 1,
    "measured_samples": len(samples),
    "untimed_priming_records": len(priming),
    "priming_and_measured_ids_unique_disjoint": True,
    "priming_counts_complete": True,
    "priming_log_joins": "existing strict join_responses completed for every condition before files were written",
    "timing_metadata_consistent": True,
    "all_public_signatures_rehash_exactly": True,
    "distinct_public_signatures": len(mapping),
    "accepted": a["accepted"],
    "refused": a["refused"],
    "warm_dashboard_accepted": sum(r["page"] == "dashboard" and r["condition"] == "warm" for r in accepted),
    "reports_reproduce_byte_identically": True,
    "all_required_comparisons_available": available,
    "all_comparisons_have_four_usable_pairs": all(r["four_paired_rounds"] for r in comparisons),
    "measurement_acceptance": "valid with disclosed refusals and reduced coverage; existing protocol has no zero-refusal or new minimum-paired-round rule"
    if available
    else "incomplete: unavailable comparison",
    "independent_evidence_review": "pending",
    "repository_delivery": "pending review/CI/merge",
}
(OUT / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
table(
    OUT / "command-outcomes.csv",
    [{"step": r["step"], "exit_code": r["exit_code"], "duration_seconds": r["duration_seconds"]} for r in commands],
)
print(json.dumps(validation))
