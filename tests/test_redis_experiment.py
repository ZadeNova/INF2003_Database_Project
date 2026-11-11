"""The evidence rules of the Redis experiment, without Docker (benchmarks/redis_stats.py and redis_report.py).

Run on the host, like test_request_timing:
    python -m pytest --noconftest -q -p no:cacheprovider tests/test_redis_experiment.py
"""

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.request import HTTPCookieProcessor

import pytest
from django.template import Context, Engine

pytest.importorskip("benchmarks.redis_stats")  # the benchmarks package is on the host, not in the test container

from benchmarks import redis_experiment  # noqa: E402
from benchmarks.redis_report import write_reports  # noqa: E402
from benchmarks.redis_stack import Stack, redis_restored  # noqa: E402
from benchmarks.redis_stats import (  # noqa: E402
    BURN_IN_VIEWS,
    CONDITIONS,
    ExperimentError,
    analyse,
    apply_gates,
    digest,
    gate,
    join_responses,
    latin_square,
    parse_logs,
    settle,
    stampede_outcome,
    trending_leader,
)

CACHE_FOR = {"off": "off", "cold": "miss", "warm": "hit", "down": "down"}


# ------------------------------------------------------------------------------------------------ design
@pytest.mark.parametrize("seed", [1, 82, 2026])
def test_the_latin_square_gives_every_condition_every_position_once(seed):
    square = latin_square(seed)
    assert len(square) == 4 and all(sorted(row) == sorted(CONDITIONS) for row in square)
    for position in range(4):
        assert sorted(row[position] for row in square) == sorted(CONDITIONS)


@pytest.mark.parametrize("seed", [1, 82, 2026])
def test_every_condition_follows_every_other_exactly_once(seed):
    """Carryover is balanced: the ordered pairs of neighbouring conditions are all different."""
    pairs = [(row[i], row[i + 1]) for row in latin_square(seed) for i in range(3)]
    assert len(pairs) == len(set(pairs)) == 12 and all(a != b for a, b in pairs)


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
        sample("shop", "warm", 2, digest_="B"),  # round 2 has no off sample to compare with
    ]
    accepted, refused = apply_gates(samples)
    assert len(accepted) == 3 and len(refused) == 2
    assert refused[0]["refusal"].startswith("data differs") and refused[0]["digest"] == "B"
    assert refused[1]["refusal"].startswith("no off reference")  # nothing to compare with is a refusal, not a pass


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


@pytest.fixture
def dashboard_header():
    """Render the real conditional, including the indentation inside it; no settings or databases are needed."""
    source = (Path(__file__).parents[1] / "src/templates/dashboard/dashboard.html").read_text(encoding="utf-8")
    header = source[source.index('<div class="page__header">') : source.index('<form method="post"')]
    template = Engine().from_string(header)

    def render(status):
        return template.render(Context({"cache_status": status, "computed_at": ""}, use_l10n=False, use_tz=False))

    return render


@pytest.mark.parametrize("status", ["hit", "wait"])
def test_the_real_dashboard_conditional_has_the_same_digest_as_off(dashboard_header, status):
    off, cached = dashboard_header("off"), dashboard_header(status)
    assert "served from cache" not in off and "served from cache" in cached
    assert digest("dashboard", off) == digest("dashboard", cached)


@pytest.mark.parametrize(
    "changed",
    [
        '<tr><td><a href="/products/17/">Soft</a> <span>white</span></td><td>12.31</td></tr>',
        '<tr><td><a href="/products/18/">Soft</a> <span>white</span></td><td>12.30</td></tr>',
        '<tr><td><a href="/products/17/">Soft</a><span>white</span></td><td>12.30</td></tr>',
        "",
    ],
    ids=["value", "link", "inline-space", "missing-row"],
)
def test_dashboard_normalisation_still_rejects_business_data_changes(dashboard_header, changed):
    row = '<tr><td><a href="/products/17/">Soft</a> <span>white</span></td><td>12.30</td></tr>'
    plain = dashboard_header("off") + f"<table>{row}</table>"
    cached = dashboard_header("hit") + f"<table>{changed}</table>"
    assert digest("dashboard", plain) != digest("dashboard", cached)


def test_dashboard_normalisation_preserves_row_order_and_other_inter_tag_whitespace(dashboard_header):
    first, second = "<tr><td>first</td></tr>", "<tr><td>second</td></tr>"
    plain = dashboard_header("off") + f"<table>{first}\n{second}</table>"
    assert digest("dashboard", plain) != digest(
        "dashboard", plain.replace(first + "\n" + second, second + "\n" + first)
    )
    assert digest("dashboard", plain) != digest("dashboard", plain.replace("</tr>\n<tr>", "</tr><tr>"))


# ------------------------------------------------------------------------------------------------ diagnostics
@pytest.mark.parametrize("warm_up_logs", ["complete", "missing", "duplicate"])
def test_diagnostics_preserve_exact_hashed_links_and_priming_without_changing_samples(tmp_path, warm_up_logs):
    """Only HTTP/Docker transport is replaced; exercise collection, log joins, files and gates together."""
    pages = {
        "shop": "/products/",
        "search": "/products/?q=Soft",
        "dashboard": "/operator/dashboard/",
        "product_detail": "/products/17/",
        "category_trending": "/products/category/soft/",
    }
    links = '<a href="/products/001/">one</a><a href="/products/2/">two</a><a href="/products/001/">one</a>'
    changed = '<a href="/products/2/">two</a><a href="/products/001/">one</a>'
    private = "private-cookie-csrf-username"

    class Transport:
        def __init__(self):
            self.calls, self.log_lines, self.recreated = [], [], []
            self.anonymous, self.operator = object(), object()

        def recreate_web(self, enabled):
            self.recreated.append(enabled)

        def openers(self):
            return self.anonymous, self.operator

        def timed_get(self, opener, page, path):
            assert opener is (self.operator if page == "dashboard" else self.anonymous)
            self.calls.append(page)
            count = self.calls.count(page)
            identity = f"request-{len(self.calls)}"
            cache = "miss" if len(self.calls) == 1 or (page == "search" and count == 5) else "hit"
            commands = 2
            if page not in ("shop", "search", "dashboard"):
                cache, commands = "", 0
            self.log_lines.append(log_line(identity, path=path.split("?")[0], cache=cache, redis_commands=commands))
            body = (changed if page == "shop" and count == 6 else links) + f"<p>{private}</p>"
            return {"request_id": identity, "path": path, "status": 200}, body, {"Set-Cookie": private}, 17.0

        def logs(self, since, identities):
            assert len(identities) == len(self.calls)
            lines = self.log_lines if warm_up_logs != "missing" else self.log_lines[1:]
            if warm_up_logs == "duplicate":
                lines = [*lines, self.log_lines[0]]
            return parse_logs("\n".join(lines), identities)

    stack, diagnostics = Transport(), redis_experiment.Diagnostics()
    if warm_up_logs != "complete":
        error = "Missing request log" if warm_up_logs == "missing" else "Duplicate request log ID"
        with pytest.raises(ExperimentError, match=error):
            redis_experiment.measure(stack, "warm", 2, pages, cheap=2, dashboard=1, diagnostics=diagnostics)
        return
    samples = redis_experiment.measure(stack, "warm", 2, pages, cheap=2, dashboard=1, diagnostics=diagnostics)
    assert stack.recreated == [True]
    assert stack.calls == list(redis_experiment.PAGE_ORDER) * 4 + [
        "shop", "shop", "search", "search", "dashboard", "product_detail", "product_detail",
        "category_trending", "category_trending",
    ]  # fmt: skip
    assert len(samples) == 9 and len(diagnostics.warm_up) == 20
    assert diagnostics.warm_up[0]["cache"] == "miss"  # the untimed cache prime is explainable
    assert all(s["client_ms"] == 17.0 and s["round"] == 2 and s["condition"] == "warm" for s in samples)
    elapsed = [s["condition_elapsed_ms"] for s in [*diagnostics.warm_up, *samples]]
    assert elapsed == sorted(elapsed) and elapsed[0] > 0
    assert all(datetime.fromisoformat(s["received_at"]).utcoffset().total_seconds() == 0 for s in samples)

    diagnostics.write(tmp_path)
    payload = json.loads((tmp_path / "data-signatures.json").read_text())
    assert payload["schema_version"] == redis_experiment.DIAGNOSTICS_SCHEMA_VERSION == 1
    assert len(payload["signatures"]) == 3  # one per page/digest, including the changed shop order
    for signature in payload["signatures"]:
        assert hashlib.sha256("|".join(signature["product_ids"]).encode()).hexdigest() == signature["digest"]
        assert signature["digest"] in {s["digest"] for s in [*samples, *diagnostics.warm_up]}
    assert any(s["product_ids"] == ["001", "2", "001"] for s in payload["signatures"])
    with (tmp_path / "warm-up.csv").open(newline="", encoding="utf-8") as stream:
        assert len(list(csv.DictReader(stream))) == 20
    assert private not in "".join(path.read_text() for path in tmp_path.iterdir())

    off = [{**s, "condition": "off", "cache": "off", "redis_commands": 0} for s in samples if s["page"] != "shop"]
    off.append({**samples[0], "condition": "off", "cache": "off", "redis_commands": 0})
    _, refused = apply_gates([*off, *samples])
    assert len(refused) == 2
    assert {r["refusal"] for r in refused} == {
        "data differs from the off condition's in the same round",
        "cache status 'miss' in a warm condition",
    }


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


# ------------------------------------------------------------------------------------------------ burn-in
def test_the_collector_uses_a_fresh_cookie_jar_per_burn_in_view_and_keeps_the_ranking_session(monkeypatch):
    """Exercise the real opener factory; a reused visitor cannot overtake the pre-existing leader."""
    views, probes, clears = [], [], []
    closed = []

    class Helper:
        def __init__(self, stack):
            pass

        def clear(self, kind):
            clears.append(kind)

        def close(self):
            closed.append(True)

    class VisitorStack:
        anonymous_opener = staticmethod(Stack.anonymous_opener)

        def timed_get(self, opener, page, path):
            if page == "product_detail":
                views.append(opener)
                return {}, "", {}, 0
            assert page == "shop"
            probes.append(opener)
            ids = (17, 12) if len({id(visitor) for visitor in views}) > 36 else (12, 17)
            body = f'<p>Rank 1 · views</p><a href="/products/{ids[0]}/">lead</a><a href="/products/{ids[1]}/">other</a>'
            return {}, body, {}, 0

    monkeypatch.setattr(redis_experiment, "ColdHelper", Helper)  # Docker cache control only; no database is replaced.
    stack = VisitorStack()
    anonymous = stack.anonymous_opener()
    passes = redis_experiment.settle_ranking(
        stack, {"product_detail": "/products/17/", "shop": "/products/"}, anonymous
    )
    jars = [
        next(handler.cookiejar for handler in opener.handlers if isinstance(handler, HTTPCookieProcessor))
        for opener in views
    ]
    assert passes == 3 and len(views) == passes * BURN_IN_VIEWS
    assert len({id(jar) for jar in jars}) == len(jars)
    assert all(probe is anonymous for probe in probes) and anonymous not in views
    assert clears == ["trending"] * passes and closed == [True]


def test_the_burn_in_stops_once_the_ranking_holds_still():
    views, rankings = [], iter(["A", "B", "C", "C", "C"])
    passes = settle(lambda: views.append(1), lambda: next(rankings), views=3)
    assert passes == 4 and len(views) == 12  # three passes of views before the ranking repeated its predecessor


def test_the_burn_in_also_waits_for_the_control_product_to_lead():
    """A ranking that holds still with the control product below the panel could still be changed by the timed views."""
    leads = iter([False, True])  # asked from pass 2, once the ranking has repeated
    passes = settle(lambda: None, lambda: "same", leader=lambda: next(leads), views=1)
    assert passes == 3  # the ranking held still from pass 2, but the control product only led from pass 3


def test_the_trending_leader_is_the_product_on_the_rank_one_card():
    body = (
        '<a href="/products/9/">x</a><p class="panel__note">Rank 1 · 40 views</p><a href="/products/7/">y</a>'
        '<p class="panel__note">Rank 10 · 2 views</p><a href="/products/3/">z</a>'
    )
    assert trending_leader(body) == 7 and trending_leader("<p>No recent views yet.</p>") is None


def test_a_ranking_that_never_settles_fails_the_experiment_instead_of_starting():
    counter = iter(range(1000))
    with pytest.raises(ExperimentError, match="did not settle"):
        settle(lambda: None, lambda: next(counter), views=1, limit=5)


# ------------------------------------------------------------------------------------------------ restoring the stack
class RecordingStack:
    def __init__(self, fail_unpause=False):
        self.calls, self.fail_unpause = [], fail_unpause

    def unpause_redis(self):
        self.calls.append("unpause")
        if self.fail_unpause:
            raise RuntimeError("docker unavailable")

    def recreate_web(self, redis_enabled):
        self.calls.append(f"web redis={redis_enabled}")


def test_however_an_experiment_ends_redis_runs_again_and_web_goes_back_to_redis_enabled():
    stack = RecordingStack()
    with pytest.raises(KeyboardInterrupt), redis_restored(stack):
        raise KeyboardInterrupt
    assert stack.calls == ["unpause", "web redis=True"]


def test_the_web_container_is_restored_even_when_unpausing_fails():
    stack = RecordingStack(fail_unpause=True)
    with pytest.raises(RuntimeError), redis_restored(stack):
        pass
    assert stack.calls == ["unpause", "web redis=True"]
