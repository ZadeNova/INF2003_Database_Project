"""The PostgreSQL delivery summary: the same rows as the live query, the refresh, and the runtime boundary."""

from datetime import timedelta

import psycopg
import pytest
from account_helpers import runtime_connection
from checkout_helpers import customer, paid_order, product
from db_helpers import timestamp_guard_off
from django.core.management import call_command
from django.db import connection
from django.db.models import F
from django.utils import timezone

from dashboard.queries import DELAY_BUCKETS
from dashboard.services import as_of_date, delivery_summary_populated, end_of_day, query_rows, refresh_sales
from orders.models import Order

pytestmark = pytest.mark.django_db(transaction=True)

COLUMNS = ("order_id", "seller_id", "delay_days", "distance_km", "bucket")
SUMMARY = "SELECT order_id, seller_id, delay_days, distance_km, bucket FROM order_delivery_summary ORDER BY order_id"


def live_rows(as_of):
    """The live query's rows without the shop name, which the summary leaves out on purpose."""
    rows = query_rows(DELAY_BUCKETS, {"end": end_of_day(as_of)})
    return sorted(({column: row[column] for column in COLUMNS} for row in rows), key=lambda row: row["order_id"])


def test_the_summary_holds_exactly_the_rows_of_the_live_query(imported):
    as_of = as_of_date()
    rows = query_rows(SUMMARY, {})
    assert rows and rows == live_rows(as_of)
    assert {row["bucket"] for row in rows} <= {
        "early_over_7",
        "early_up_to_7_or_on_time",
        "late_1_to_7",
        "late_8_to_14",
        "late_over_14",
    }
    assert {row["as_of"] for row in query_rows("SELECT DISTINCT as_of FROM order_delivery_summary", {})} == {as_of}


def test_a_delivery_after_the_reporting_date_is_not_in_the_summary(imported):
    as_of = as_of_date()
    before = query_rows(SUMMARY, {})
    _, order = paid_order(customer("late"), product("late"), status="delivered")
    with timestamp_guard_off():
        Order.objects.filter(pk=order.pk).update(delivered_at=timezone.now())  # placed and delivered after the cut-off
    refresh_sales()
    assert query_rows(SUMMARY, {}) == before == live_rows(as_of)


def test_the_summary_is_stale_until_the_refresh_and_then_matches_the_live_query_again(imported):
    as_of = as_of_date()
    chosen = query_rows(SUMMARY, {})[0]
    with timestamp_guard_off():
        Order.objects.filter(pk=chosen["order_id"]).update(
            estimated_delivery=F("estimated_delivery") - timedelta(days=10)
        )
    assert query_rows(SUMMARY, {})[0] == chosen  # a materialized view does not follow its tables by itself
    refresh_sales()
    refreshed = query_rows(SUMMARY, {})
    assert refreshed == live_rows(as_of)
    assert refreshed[0]["delay_days"] == chosen["delay_days"] + 10


def test_the_first_population_and_a_later_refresh_both_work_and_the_flag_follows(imported):
    assert delivery_summary_populated() is True
    with connection.cursor() as cursor:
        cursor.execute("REFRESH MATERIALIZED VIEW public.order_delivery_summary WITH NO DATA")
    assert delivery_summary_populated() is False
    refresh_sales()  # not populated: the plain refresh
    assert delivery_summary_populated() is True
    assert query_rows(SUMMARY, {}) == live_rows(as_of_date())
    refresh_sales()  # populated: the concurrent refresh keeps readers on the old snapshot
    assert query_rows(SUMMARY, {}) == live_rows(as_of_date())


def test_runtime_can_read_and_refresh_through_the_function_only(imported):
    with runtime_connection() as runtime:
        assert runtime.execute("SELECT count(*) FROM public.order_delivery_summary").fetchone()[0] > 0
        for _ in range(2):
            runtime.execute("SELECT public.refresh_order_delivery_summary()")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            runtime.execute("REFRESH MATERIALIZED VIEW public.order_delivery_summary")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            runtime.execute("DROP MATERIALIZED VIEW public.order_delivery_summary")
        row = runtime.execute(
            "SELECT prosecdef,proconfig,pg_get_userbyid(proowner)=current_user FROM pg_proc WHERE proname=%s",
            ["refresh_order_delivery_summary"],
        ).fetchone()
        assert row == (True, ["search_path=public, pg_temp"], False)
        acl = runtime.execute(
            "SELECT acl.grantee FROM pg_proc p CROSS JOIN LATERAL aclexplode(p.proacl) acl "
            "WHERE p.proname=%s AND acl.privilege_type='EXECUTE'",
            ["refresh_order_delivery_summary"],
        ).fetchall()
        assert (0,) not in acl  # PUBLIC has no EXECUTE


def test_the_migration_reverses_and_applies_again_with_the_runtime_grants(imported):
    try:
        call_command("migrate", "dashboard", "0001", verbosity=0)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass('public.order_delivery_summary'), "
                "to_regproc('public.refresh_order_delivery_summary'), to_regclass('public.daily_product_sales')"
            )
            view, function, sales = cursor.fetchone()
        assert (view, function) == (None, None) and sales is not None  # only this migration's objects went
    finally:
        call_command("migrate", "dashboard", verbosity=0)
    with runtime_connection() as runtime:  # applied again: unpopulated until the first refresh, grants restored
        runtime.execute("SELECT public.refresh_order_delivery_summary()")
        assert runtime.execute("SELECT count(*) FROM public.order_delivery_summary").fetchone()[0] > 0
