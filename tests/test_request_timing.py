"""Pure host-side timing checks: no Django, database drivers or running services required."""

import json

import pytest

from benchmarks.request_timing import aggregate, join_requests, pages_for_product, parse_request_logs


def log_row(**overrides):
    return {
        "logger": "mercer.request",
        "message": "request",
        "request_id": "k2-test-0001",
        "method": "GET",
        "path": "/products/",
        "status": 200,
        "user_id": None,
        "duration_ms": 10,
        "db_pg_ms": 2,
        "db_pg_queries": 3,
        "db_mongo_ms": 1,
        "db_mongo_commands": 2,
        **overrides,
    }


def response(**overrides):
    return {
        "page": "faceted_search",
        "request_id": "k2-test-0001",
        "path": "/products/?category=45&attr_wireless=true",
        "status": 200,
        **overrides,
    }


def test_compose_logs_ignore_other_traffic_and_strip_unneeded_fields():
    row = log_row(cookie="private", username="private", password="private")
    text = "\n".join(
        [
            "web-1 | not JSON",
            "web-1 | {incomplete",
            "[]",
            json.dumps(log_row(logger="mercer.errors")),
            json.dumps(log_row(request_id="unrelated")),
            "web-1 | " + json.dumps(row),
        ]
    )
    logs = parse_request_logs(text, {"k2-test-0001"})
    assert set(logs) == {"k2-test-0001"}
    joined = join_requests([response()], logs)
    assert joined[0]["db_share_percent"] == 30
    assert not {"cookie", "username", "password", "user_id", "logger"} & joined[0].keys()


def test_duplicate_selected_logs_and_duplicate_responses_are_rejected():
    text = json.dumps(log_row())
    with pytest.raises(ValueError, match="Duplicate request log ID"):
        parse_request_logs(text + "\n" + text, {"k2-test-0001"})
    with pytest.raises(ValueError, match="Duplicate response ID"):
        join_requests([response(), response()], {"k2-test-0001": log_row()})


@pytest.mark.parametrize("overrides", [{"path": "/login/"}, {"status": 302}, {"method": "POST"}])
def test_join_rejects_mismatched_log(overrides):
    with pytest.raises(ValueError, match="disagree"):
        join_requests([response()], {"k2-test-0001": log_row(**overrides)})


def test_join_rejects_missing_log_and_unauthenticated_dashboard():
    with pytest.raises(ValueError, match="Missing request log"):
        join_requests([response()], {})
    dashboard = response(page="operator_dashboard", path="/operator/dashboard/")
    row = log_row(path="/operator/dashboard/")
    with pytest.raises(ValueError, match="not authenticated"):
        join_requests([dashboard], {"k2-test-0001": row})
    joined = join_requests([dashboard], {"k2-test-0001": {**row, "user_id": 7}})
    assert "user_id" not in joined[0]


@pytest.mark.parametrize(
    "overrides",
    [
        {"duration_ms": None},
        {"db_pg_ms": -1},
        {"db_mongo_ms": float("nan")},
        {"db_pg_ms": float("inf")},
        {"db_pg_queries": True},
        {"db_mongo_commands": 1.5},
        {"duration_ms": 0},
    ],
)
def test_join_rejects_invalid_metrics(overrides):
    with pytest.raises(ValueError):
        join_requests([response()], {"k2-test-0001": log_row(**overrides)})


def test_twenty_sample_aggregation_uses_median_and_nearest_rank_p95():
    samples = [
        {
            "duration_ms": i * 10,
            "db_pg_ms": i * 2,
            "db_mongo_ms": i,
            "db_pg_queries": 3,
            "db_mongo_commands": 2,
            "db_share_percent": 30,
        }
        for i in range(1, 21)
    ]
    result = aggregate(samples)
    assert result["requests"] == 20
    assert result["duration_ms_median"] == 105
    assert result["duration_ms_p95"] == 190
    assert result["db_pg_ms_median"] == 21 and result["db_pg_ms_p95"] == 38
    assert result["db_mongo_ms_median"] == 10.5 and result["db_mongo_ms_p95"] == 19
    assert result["db_pg_queries_total"] == 60 and result["db_mongo_commands_total"] == 40
    assert result["db_share_percent_median"] == result["db_share_percent_p95"] == result["db_share_percent_total"] == 30


def test_share_of_totals_is_duration_weighted_and_zero_durations_are_supported():
    first = join_requests([response()], {"k2-test-0001": log_row(duration_ms=10, db_pg_ms=9, db_mongo_ms=0)})[0]
    second = {**first, "duration_ms": 90, "db_pg_ms": 0, "db_share_percent": 0}
    result = aggregate([first, second])
    assert result["db_share_percent_median"] == 45 and result["db_share_percent_total"] == 9
    row = log_row(duration_ms=0, db_pg_ms=0, db_mongo_ms=0, db_pg_queries=0, db_mongo_commands=0)
    assert aggregate(join_requests([response()], {"k2-test-0001": row}))["db_share_percent_total"] == 0
    with pytest.raises(ValueError, match="No request samples"):
        aggregate([])


def test_pages_use_a_visible_product_its_category_and_a_real_attribute_facet(tmp_path):
    (tmp_path / "product_specs.ndjson").write_text(
        json.dumps({"_id": 12, "category_id": 45, "attributes": {"wireless": True}})
    )
    (tmp_path / "categories.csv").write_text("id,slug\n44,electronics\n45,computers-accessories\n")
    pages = pages_for_product('<a href="/products/12/">Item</a>', tmp_path)
    assert pages == {
        "category": "/products/category/computers-accessories/",
        "product_list": "/products/",
        "faceted_search": "/products/?category=45&attr_wireless=true",
        "product_detail": "/products/12/",
        "operator_dashboard": "/operator/dashboard/",
    }
    with pytest.raises(ValueError, match="no visible product"):
        pages_for_product("No products", tmp_path)
    (tmp_path / "categories.csv").write_text("id,slug\n44,electronics\n")
    with pytest.raises(ValueError, match="source category"):
        pages_for_product('<a href="/products/12/">Item</a>', tmp_path)
