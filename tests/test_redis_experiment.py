"""The evidence rules of the Redis experiment, without Docker (benchmarks/redis_stats.py and redis_report.py).

Run on the host, like test_request_timing:
    python -m pytest --noconftest -q -p no:cacheprovider tests/test_redis_experiment.py
"""

import csv
import json

import pytest

pytest.importorskip("benchmarks.redis_stats")  # the benchmarks package is on the host, not in the test container

from benchmarks.redis_report import write_reports  # noqa: E402
from benchmarks.redis_stats import (  # noqa: E402
    CONDITIONS,
    ExperimentError,
    analyse,
    apply_gates,
    digest,
    gate,
    join_responses,
    latin_square,
    parse_logs,
    stampede_outcome,
)

CACHE_FOR = {"off": "off", "cold": "miss", "warm": "hit", "down": "down"}


# ------------------------------------------------------------------------------------------------ design
@pytest.mark.parametrize("seed", [1, 82, 2026])
def test_the_latin_square_gives_every_condition_every_position_once(seed):
    square = latin_square(seed)
    assert len(square) == 4 and all(sorted(row) == sorted(CONDITIONS) for row in square)
    for position in range(4):
        assert sorted(row[position] for row in square) == sorted(CONDITIONS)


def test_the_latin_square_is_reproducible_from_its_seed():
    assert latin_square(82) == latin_square(82)
    assert any(latin_square(seed) != latin_square(82) for seed in range(1, 20))


# ------------------------------------------------------------------------------------------------ gates
def sample(
    page="shop", condition="warm", round_=1, *, duration=10.0, cache=None, status=200, commands=None, digest_="d"
):
    cache = CACHE_FOR[condition] if cache is None else cache
    if page in ("product_detail", "category_trending"):
        cache = ""
        commands = 0 if commands is None else commands
    elif commands is None:
        commands = 0 if condition == "off" else 2
    return {
        "page": page,
        "condition": condition,
        "round": round_,
        "status": status,
        "duration_ms": duration,
        "db_pg_ms": 1.0,
        "db_mongo_ms": 2.0,
        "redis_ms": 0.5,
        "redis_commands": commands,
        "cache": cache,
        "digest": digest_ if page in ("shop", "search", "dashboard") else "",
    }


def test_a_sample_counts_only_when_its_cache_status_matches_its_condition():
    assert gate(sample(condition="warm")) is None
    assert "cache status" in gate(sample(condition="warm", cache="miss"))  # the entry expired in a warm condition
    assert "cache status" in gate(sample(condition="cold", cache="hit"))
    assert "cache status" in gate(sample(condition="down", cache="miss"))
    assert "Redis commands" in gate(sample(condition="off", commands=3))
    assert gate(sample(condition="warm", status=500)) == "status 500"


def test_a_control_page_that_touches_redis_is_refused():
    assert gate(sample("product_detail", "warm")) is None
    assert "control" in gate(sample("product_detail", "warm", commands=1))


def test_the_data_gate_compares_each_sample_with_the_off_condition_of_the_same_round():
    samples = [
        sample("shop", "off", 1, digest_="A"),
        sample("shop", "off", 1, digest_="A"),
        sample("shop", "warm", 1, digest_="A"),
        sample("shop", "warm", 1, digest_="B"),  # different data than the off condition served
        sample("shop", "warm", 2, digest_="B"),  # round 2 has no off sample to compare with: not refused for data
    ]
    accepted, refused = apply_gates(samples)
    assert len(accepted) == 4 and len(refused) == 1
    assert refused[0]["refusal"].startswith("data differs") and refused[0]["digest"] == "B"


# ------------------------------------------------------------------------------------------------ analysis
def experiment(off=20.0, warm=5.0, cold=22.0, down=21.0, control=10.0, noise=0.0, cheap=150, dashboard=15):
    """Four rounds of every condition on every page; the controls are the same under every condition up to `noise`."""
    durations = {"off": off, "warm": warm, "cold": cold, "down": down}
    samples = []
    for round_ in range(1, 5):
        for condition in CONDITIONS:
            for page, count in (("shop", cheap), ("search", cheap), ("dashboard", dashboard)):
                samples += [sample(page, condition, round_, duration=durations[condition]) for _ in range(count)]
            bump = noise * (1 if condition == "warm" else 0)
            for page in ("product_detail", "category_trending"):
                samples += [sample(page, condition, round_, duration=control + bump) for _ in range(cheap)]
    return samples


def cell(analysis, page, condition):
    return next(c for c in analysis["cells"] if (c["page"], c["condition"]) == (page, condition))


def ratio(analysis, page, pair):
    return next(r for r in analysis["ratios"] if (r["page"], r["pair"]) == (page, pair))


def test_the_paired_ratios_are_per_round_and_the_effect_above_the_noise_floor_is_claimed():
    analysis = analyse(experiment())
    off_over_warm = ratio(analysis, "shop", "off/warm")
    assert off_over_warm["rounds"] == 4 and off_over_warm["ratio_median"] == pytest.approx(4.0)
    assert off_over_warm["ratio_min"] == off_over_warm["ratio_max"] == pytest.approx(4.0)
    assert ratio(analysis, "shop", "cold/off")["ratio_median"] == pytest.approx(1.1)
    assert ratio(analysis, "shop", "down/off")["ratio_median"] == pytest.approx(1.05)
    assert analysis["noise_floor"] == pytest.approx(0.0)  # identical controls
    verdict = next(v for v in analysis["verdicts"] if (v["page"], v["pair"]) == ("shop", "off/warm"))
    assert verdict["claim"] == "yes" and verdict["same_side_every_round"]


def test_an_effect_smaller_than_the_noise_floor_is_not_claimed():
    # The controls differ by about 9% between conditions, so a 5% outage cost cannot be told from noise.
    analysis = analyse(experiment(control=10.0, noise=1.0))
    assert analysis["noise_floor"] == pytest.approx(1 - 10 / 11)  # a control at 10 ms off and 11 ms warm: ratio 0.909
    outage = next(v for v in analysis["verdicts"] if (v["page"], v["pair"]) == ("shop", "down/off"))
    assert outage["claim"].startswith("no")
    benefit = next(v for v in analysis["verdicts"] if (v["page"], v["pair"]) == ("shop", "off/warm"))
    assert benefit["claim"] == "yes"


def test_tail_percentiles_appear_only_where_the_pooled_sample_is_large_enough():
    analysis = analyse(experiment())
    home = cell(analysis, "shop", "off")  # 150 requests x 4 rounds
    dashboard = cell(analysis, "dashboard", "off")  # 15 requests x 4 rounds
    assert home["samples"] == 600 and home["p95_ms"] is not None and home["p99_ms"] is not None
    assert dashboard["samples"] == 60 and dashboard["p95_ms"] is None and dashboard["p95_label"] == "not enough data"


def test_refused_samples_are_counted_and_never_enter_a_median():
    samples = experiment()
    samples += [sample("shop", "warm", 1, duration=9999.0, cache="miss") for _ in range(3)]
    analysis = analyse(samples)
    warm = cell(analysis, "shop", "warm")
    assert warm["refused"] == 3 and warm["max_ms"] == 5.0
    assert any(
        r["page"] == "shop" and r["samples"] == 3 and "cache status" in r["reason"] for r in analysis["refusals"]
    )


def test_the_bootstrap_interval_is_reproducible_labelled_and_contains_the_ratio():
    first, second = analyse(experiment()), analyse(experiment())
    assert first["bootstrap"] == second["bootstrap"]
    interval = next(b for b in first["bootstrap"] if b["page"] == "shop")
    assert interval["label"] == "optimistic" and interval["ci_low"] <= 4.0 <= interval["ci_high"]


# ------------------------------------------------------------------------------------------------ digest
def test_the_lists_are_compared_by_their_product_links_in_order():
    one = '<a href="/products/1/">x</a><a href="/products/2/">y</a>'
    other = '<a href="/products/2/">y</a><a href="/products/1/">x</a>'
    assert digest("shop", one) == digest("search", one) != digest("shop", other)
    assert digest("shop", one + "<p>different chrome</p>") == digest("shop", one)


def test_the_dashboard_digest_ignores_the_csrf_token_and_the_cache_note():
    page = '<input name="csrfmiddlewaretoken" value="{token}"><p class="page__lead">{note}</p><table>numbers</table>'
    plain = page.format(token="aaa", note="Delivery, category and review panels computed live.")
    cached = page.format(
        token="bbb", note="Delivery, category and review panels served from cache, computed 3 minutes ago."
    )
    assert digest("dashboard", plain) == digest("dashboard", cached)
    assert digest("dashboard", plain) != digest("dashboard", plain.replace("numbers", "other numbers"))
    assert digest("product_detail", plain) is None


# ------------------------------------------------------------------------------------------------ logs
def log_line(identity, **fields):
    row = {
        "logger": "mercer.request",
        "message": "request",
        "request_id": identity,
        "method": "GET",
        "path": "/",
        "status": 200,
        "cache": "hit",
        **{key: 1.5 for key in ("duration_ms", "db_pg_ms", "db_mongo_ms", "redis_ms")},
        "db_pg_queries": 2,
        "db_mongo_commands": 1,
        "redis_commands": 2,
    }
    row.update(fields)
    return "web-1  | " + json.dumps(row)


def response(identity, path="/", status=200):
    return {"request_id": identity, "path": path, "status": status, "page": "shop"}


def test_a_response_joins_its_log_line_with_the_cache_status_and_redis_fields():
    logs = parse_logs(log_line("a") + "\nnoise\n" + log_line("b", path="/other"), {"a"})
    joined = join_responses([response("a")], logs)
    assert joined[0]["cache"] == "hit" and joined[0]["redis_commands"] == 2


@pytest.mark.parametrize(
    "responses,logs_text",
    [
        ([response("a")], ""),  # no log line
        ([response("a"), response("a")], log_line("a")),  # the same response twice
        ([response("a", status=500)], log_line("a")),  # response and log disagree
        ([response("a")], log_line("a", duration_ms=-1)),  # an invalid metric
        ([response("a")], log_line("a", redis_ms=None)),  # a missing Redis field
        ([response("a")], log_line("a", cache=None)),  # no cache status
    ],
)
def test_nothing_is_accepted_without_an_exact_valid_log_line(responses, logs_text):
    with pytest.raises(ExperimentError):
        join_responses(responses, parse_logs(logs_text, {"a"}))


def test_a_duplicate_log_line_is_refused():
    with pytest.raises(ExperimentError):
        parse_logs(log_line("a") + "\n" + log_line("a"), {"a"})


# ------------------------------------------------------------------------------------------------ stampede
def test_the_stampede_outcome_counts_who_ran_the_computation():
    def one(cache, duration):
        return {"cache": cache, "duration_ms": duration}

    with_lock = stampede_outcome([one("miss", 900)] + [one("wait", 950)] * 6 + [one("hit", 5)])
    assert (with_lock["computed"], with_lock["waited"], with_lock["hit"], with_lock["max_ms"]) == (1, 6, 1, 950)
    without_redis = stampede_outcome([one("off", 900)] * 8)
    assert without_redis["computed"] == 8 and without_redis["waited"] == 0


# ------------------------------------------------------------------------------------------------ report
def test_the_report_writes_every_table_and_the_chart(tmp_path):
    fields = [
        "round", "condition", "page", "request_id", "path", "status", "client_ms", "x_cache", "digest", "cache",
        "duration_ms", "db_pg_ms", "db_pg_queries", "db_mongo_ms", "db_mongo_commands", "redis_ms", "redis_commands",
    ]  # fmt: skip
    with (tmp_path / "samples.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for s in experiment(cheap=6, dashboard=3):
            writer.writerow(
                {
                    **s,
                    "request_id": "r",
                    "path": "/",
                    "client_ms": 1.0,
                    "x_cache": "",
                    "db_pg_queries": 1,
                    "db_mongo_commands": 1,
                }
            )
    analysis = write_reports(tmp_path)
    for name in (
        "summary.csv",
        "ratios.csv",
        "verdicts.csv",
        "bootstrap.csv",
        "refusals.csv",
        "chart.svg",
        "analysis.json",
    ):
        assert (tmp_path / name).exists(), name
    assert analysis["refused"] == 0 and "shop / warm" in (tmp_path / "chart.svg").read_text()
