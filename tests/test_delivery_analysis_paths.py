"""The delivery analysis reads the maintained summaries when they can be trusted and computes from the source otherwise."""

import pytest
from account_helpers import make_operator
from django.db import connection

from dashboard import services
from dashboard.services import (
    ORDER_SCORES,
    as_of_date,
    dashboard_data,
    delivery_analysis,
    history_blocks,
    refresh_sales,
)
from reviews.services import moderate_review

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def live_calls(monkeypatch):
    """The reporting-date-by-source calls: every time the analysis had to compute from the reviews and orders."""
    calls = []
    original = services.live_inputs

    def spy(as_of, database):
        calls.append(as_of)
        return original(as_of, database)

    monkeypatch.setattr(services, "live_inputs", spy)
    return calls


def test_the_summary_path_gives_exactly_the_live_result_and_does_not_compute_from_the_source(
    imported, mongo_db, live_calls
):
    as_of = as_of_date()
    from_summaries = delivery_analysis(as_of, mongo_db)
    assert live_calls == []
    assert from_summaries == delivery_analysis(as_of, mongo_db, use_summaries=False)
    assert live_calls == [as_of]  # asked for explicitly


def test_the_cached_history_blocks_are_the_same_whichever_path_computed_them(imported, mongo_db, monkeypatch):
    as_of = as_of_date()
    with_summaries = history_blocks(as_of)
    original = services.summary_inputs
    monkeypatch.setattr(services, "summary_inputs", lambda *args: None)
    assert history_blocks(as_of) == with_summaries
    monkeypatch.setattr(services, "summary_inputs", original)
    assert dashboard_data(as_of)["delay_rows"] == with_summaries["delay_rows"]


def test_after_a_takedown_the_analysis_from_summaries_still_equals_the_live_one(imported, mongo_db):
    as_of = as_of_date()
    review = mongo_db.reviews.find_one({"taken_down": {"$ne": True}})
    moderate_review(make_operator(), review["order_line_id"], "takedown", "Test reason")
    assert delivery_analysis(as_of, mongo_db) == delivery_analysis(as_of, mongo_db, use_summaries=False)


def unpopulate_delivery_view():
    with connection.cursor() as cursor:
        cursor.execute("REFRESH MATERIALIZED VIEW public.order_delivery_summary WITH NO DATA")


def empty_scores(mongo_db):
    mongo_db[ORDER_SCORES].delete_many({})


def scores_for_another_date(mongo_db):
    mongo_db[ORDER_SCORES].update_many({}, {"$set": {"as_of": "2000-01-01"}})


@pytest.mark.parametrize(
    "damage",
    [
        pytest.param(lambda mongo_db, monkeypatch: unpopulate_delivery_view(), id="delivery view not populated"),
        pytest.param(lambda mongo_db, monkeypatch: empty_scores(mongo_db), id="score summary empty"),
        pytest.param(lambda mongo_db, monkeypatch: scores_for_another_date(mongo_db), id="score summary other date"),
        pytest.param(
            lambda mongo_db, monkeypatch: monkeypatch.setattr(
                services,
                "DELIVERY_SUMMARY",
                "SELECT order_id, seller_id, delay_days, distance_km, bucket, DATE '2000-01-01' AS as_of "
                "FROM public.order_delivery_summary ORDER BY order_id",
            ),
            id="delivery view other date",
        ),
    ],
)
def test_a_missing_or_mismatched_summary_falls_back_to_the_source_with_the_same_answer(
    imported, mongo_db, monkeypatch, live_calls, damage
):
    as_of = as_of_date()
    expected = delivery_analysis(as_of, mongo_db, use_summaries=False)
    live_calls.clear()
    damage(mongo_db, monkeypatch)
    assert delivery_analysis(as_of, mongo_db) == expected
    assert live_calls == [as_of]  # it did not trust the damaged summary


def test_a_refresh_repairs_a_damaged_summary_and_the_fast_path_returns(imported, mongo_db, live_calls):
    as_of = as_of_date()
    empty_scores(mongo_db)
    unpopulate_delivery_view()
    delivery_analysis(as_of, mongo_db)
    assert live_calls == [as_of]
    refresh_sales()
    live_calls.clear()
    delivery_analysis(as_of, mongo_db)
    assert live_calls == []
