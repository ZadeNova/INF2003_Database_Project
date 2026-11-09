"""Pure-Python checks of the benchmark tooling (pooling, drift, sessions, container events). No database needed.

Run on the host, like test_request_timing:
    python -m pytest --noconftest -q -p no:cacheprovider tests/test_benchmark_tooling.py
"""

import csv
import gzip
import json

import pytest

pytest.importorskip("benchmarks.pooling")  # the benchmarks package is on the host, not inside the test container

from benchmarks.pooling import NOT_ENOUGH, operations, pooled, summarise  # noqa: E402
from benchmarks.report import baseline_drift  # noqa: E402
from benchmarks.run import container_events  # noqa: E402
from benchmarks.sessions import aggregate, load_session  # noqa: E402


# ----------------------------------------------------------------------------------------------- pooled percentiles
@pytest.mark.parametrize(
    "count,p95,p99",
    [(99, False, False), (100, True, False), (499, True, False), (500, True, True)],
)
def test_a_tail_percentile_appears_only_with_enough_pooled_samples(count, p95, p99):
    summary = summarise([float(n) for n in range(1, count + 1)])
    assert (summary["p95_ms"] is not None, summary["p99_ms"] is not None) == (p95, p99)
    assert (summary["p95_label"], summary["p99_label"]) == (
        "" if p95 else NOT_ENOUGH,
        "" if p99 else NOT_ENOUGH,
    )
    assert summary["p50_ms"] and summary["min_ms"] == 1.0 and summary["max_ms"] == float(count)


def test_percentiles_use_nearest_rank():
    summary = summarise([float(n) for n in range(1, 501)])
    assert (summary["p50_ms"], summary["p95_ms"], summary["p99_ms"]) == (250.0, 475.0, 495.0)


def write_raw(directory, rows, *, packed=False):
    directory.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row) + "\n" for row in rows)
    if packed:
        with gzip.open(directory / "raw.jsonl.gz", "wt", encoding="utf-8") as stream:
            stream.write(text)
    else:
        (directory / "raw.jsonl").write_text(text, encoding="utf-8")


def operation(latency_ms, *, accepted=True, output="B1_x", engine="mongo", variant="documents", clients=1):
    return {
        "kind": "operation",
        "output": output,
        "engine": engine,
        "variant": variant,
        "clients": clients,
        "accepted": accepted,
        "accepted_latency_ns": int(latency_ms * 1e6) if accepted else None,
    }


def test_only_accepted_operations_are_pooled_across_directories_and_formats(tmp_path):
    write_raw(tmp_path / "a", [operation(1), operation(2), operation(99, accepted=False), {"kind": "check"}])
    write_raw(tmp_path / "b", [operation(3), operation(4, clients=10)], packed=True)
    result = pooled([tmp_path / "a", tmp_path / "b"])
    assert result[("B1_x", "mongo", "documents", "1")]["samples"] == 3
    assert result[("B1_x", "mongo", "documents", "10")]["samples"] == 1
    assert list(operations(tmp_path / "missing")) == []


# ----------------------------------------------------------------------------------------------- baseline drift
def baseline(output, engine, p50, p95):
    return {"output": output, "engine": engine, "clients": "1", "status": "passed", "p50_ms": p50, "p95_ms": p95}


def test_a_baseline_that_moved_beyond_its_noise_band_is_flagged():
    rows = [
        baseline("baseline_roundtrip", "postgres", "1.00", "1.20"),
        baseline("baseline_roundtrip_end", "postgres", "1.10", "1.25"),  # moved 0.10, band 0.20: inside
        baseline("baseline_roundtrip", "mongo", "1.00", "1.10"),
        baseline("baseline_roundtrip_end", "mongo", "1.50", "1.60"),  # moved 0.50, band 0.10: drift
    ]
    result = {r["engine"]: r for r in baseline_drift(rows)}
    assert result["postgres"]["drift"] == "no" and result["mongo"]["drift"] == "yes"
    assert result["mongo"]["noise_band_ms"] == pytest.approx(0.10)


def test_a_baseline_without_an_end_measurement_is_not_compared():
    assert baseline_drift([baseline("baseline", "python", "0.01", "0.02")]) == []


# ----------------------------------------------------------------------------------------------- container events
def state(*, oom=False, restarts=0, status="running"):
    return {"oom_killed": oom, "restarts": restarts, "status": status, "exit_code": 137 if oom else 0}


def test_no_container_event_when_nothing_happened():
    states = {"p-bench-db-1": state(), "p-bench-mongo-1": state()}
    assert container_events(states, dict(states)) == []


def test_an_out_of_memory_kill_a_restart_and_a_stopped_container_are_all_events():
    before = {"db": state(), "mongo": state(), "extra": state()}
    after = {"db": state(), "mongo": state(oom=True, restarts=2), "extra": state(status="exited")}
    events = container_events(before, after)
    assert any("memory" in e and "mongo" in e for e in events)
    assert any("restarted 2" in e for e in events)
    assert any("extra is exited" in e for e in events)
    assert container_events({"gone": state()}, {}) == ["gone disappeared"]


def test_a_container_created_for_the_run_is_not_compared():
    assert container_events({"db": state()}, {"db": state(), "load-client": state(status="exited")}) == []


# ----------------------------------------------------------------------------------------------- sessions
FIELDS = ["output", "engine", "variant", "clients", "status", "p50_ms", "p95_ms", "throughput_ops_s", "headline"]


def write_session(directory, p50, *, status="passed", exit_code=0, events=(), commit="abc", headline="True"):
    directory.mkdir(parents=True)
    with (directory / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for output, engine, variant in (("B2a", "postgres", "live"), ("B2a", "mongo", "idiomatic")):
            writer.writerow(
                {
                    "output": output,
                    "engine": engine,
                    "variant": variant,
                    "clients": "1",
                    "status": status,
                    "p50_ms": p50 * (3 if engine == "mongo" else 1),
                    "p95_ms": p50 * 2,
                    "throughput_ops_s": 100 / p50,
                    "headline": headline,
                }
            )
    (directory / "host.json").write_text(
        json.dumps({"exit_code": exit_code, "container_events": list(events), "commit": commit}), encoding="utf-8"
    )


def read(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def test_the_headline_is_the_median_of_the_session_medians_and_every_session_is_kept(tmp_path):
    for number, p50 in enumerate((10, 30, 20), start=1):
        write_session(tmp_path / f"s{number}", p50)
    summary = aggregate([tmp_path / f"s{n}" for n in (1, 2, 3)], tmp_path / "out")
    assert summary == {"sessions": 3, "usable": 3, "excluded": 0, "notes": []}
    headline = {(r["engine"], r["variant"]): r for r in read(tmp_path / "out" / "headline.csv")}
    postgres = headline[("postgres", "live")]
    assert float(postgres["p50_ms"]) == 20.0  # the median of 10, 30 and 20, not their mean and not the best
    assert (float(postgres["p50_session_min_ms"]), float(postgres["p50_session_max_ms"])) == (10.0, 30.0)
    assert float(postgres["session_spread_percent"]) == pytest.approx(100.0)
    assert len(read(tmp_path / "out" / "sessions.csv")) == 6  # two measures from each of three sessions
    pair = read(tmp_path / "out" / "b2-headline.csv")[0]
    assert float(pair["mongo_over_postgres"]) == 3.0


@pytest.mark.parametrize(
    "damage,reason",
    [
        ({"status": "failed"}, "failed checks"),
        ({"exit_code": 1}, "exit code"),
        ({"events": ["db was killed for exceeding its memory limit"]}, "memory limit"),
    ],
)
def test_a_damaged_session_is_excluded_with_its_number_and_reason_not_for_being_slow(tmp_path, damage, reason):
    write_session(tmp_path / "s1", 10)
    write_session(tmp_path / "s2", 1000, **damage)
    write_session(tmp_path / "s3", 12)
    summary = aggregate([tmp_path / "s1", tmp_path / "s2", tmp_path / "s3"], tmp_path / "out")
    assert (summary["usable"], summary["excluded"]) == (2, 1)
    excluded = read(tmp_path / "out" / "excluded.csv")
    assert [row["session"] for row in excluded] == ["2"] and reason in excluded[0]["reason"]
    assert any("only 2 usable" in note for note in summary["notes"])
    headline = {(r["engine"], r["variant"]): r for r in read(tmp_path / "out" / "headline.csv")}
    assert float(headline[("postgres", "live")]["p50_ms"]) == 11.0  # sessions 1 and 3 only


def test_a_slow_but_healthy_session_stays_in_the_headline(tmp_path):
    write_session(tmp_path / "s1", 10)
    write_session(tmp_path / "s2", 1000)
    write_session(tmp_path / "s3", 12)
    summary = aggregate([tmp_path / "s1", tmp_path / "s2", tmp_path / "s3"], tmp_path / "out")
    assert summary["excluded"] == 0
    headline = {(r["engine"], r["variant"]): r for r in read(tmp_path / "out" / "headline.csv")}
    assert float(headline[("postgres", "live")]["p50_ms"]) == 12.0


def test_sessions_from_different_commits_are_reported(tmp_path):
    for number, commit in enumerate(("aaa", "bbb", "aaa"), start=1):
        write_session(tmp_path / f"s{number}", 10, commit=commit)
    summary = aggregate([tmp_path / f"s{n}" for n in (1, 2, 3)], tmp_path / "out")
    assert any("different commits" in note for note in summary["notes"])


def test_a_session_flagged_for_baseline_drift_is_still_listed(tmp_path):
    write_session(tmp_path / "s1", 10)
    (tmp_path / "s1" / "report").mkdir()
    (tmp_path / "s1" / "report" / "drift.csv").write_text("baseline,engine,clients,drift\nbaseline,python,1,yes\n")
    assert load_session(tmp_path / "s1", 1)["drift_flagged"] is True
