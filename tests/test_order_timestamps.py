"""The delay analysis is computed from order timestamps, so the database refuses to let the web role rewrite them."""

from datetime import datetime, timezone

import pytest
from account_helpers import runtime_connection
from checkout_helpers import customer, paid_order, product
from psycopg import errors

pytestmark = pytest.mark.django_db(transaction=True)
PAST = datetime(2001, 1, 1, tzinfo=timezone.utc)
COLUMNS = ["placed_at", "estimated_delivery", "paid_at", "shipped_at", "delivered_at", "cancelled_at"]


def new_order():
    return paid_order(customer(), product())[1]


@pytest.mark.parametrize("column", COLUMNS)
def test_runtime_cannot_rewrite_a_lifecycle_timestamp_without_a_status_change(column):
    order = new_order()
    with runtime_connection() as runtime:
        with pytest.raises(errors.CheckViolation, match="cannot be changed directly"):
            with runtime.transaction():
                runtime.execute(f"UPDATE orders_order SET {column} = %s WHERE id = %s", [PAST, order.pk])


@pytest.mark.parametrize("column", ["placed_at", "estimated_delivery", "delivered_at", "cancelled_at", "paid_at"])
def test_a_status_change_cannot_carry_a_rewrite_of_any_other_timestamp(column):
    order = new_order()
    with runtime_connection() as runtime:
        with pytest.raises(errors.CheckViolation, match="cannot be changed directly"):
            with runtime.transaction():
                runtime.execute(
                    f"UPDATE orders_order SET status = 'shipped', {column} = %s WHERE id = %s", [PAST, order.pk]
                )
        assert runtime.execute("SELECT status FROM orders_order WHERE id = %s", [order.pk]).fetchone() == ("paid",)


def test_a_legitimate_status_change_still_stamps_its_own_timestamp_whatever_the_statement_said():
    order = new_order()
    with runtime_connection() as runtime:
        with runtime.transaction():
            runtime.execute(
                "UPDATE orders_order SET status = 'shipped', shipped_at = %s WHERE id = %s", [PAST, order.pk]
            )
        status, shipped_at = runtime.execute(
            "SELECT status, shipped_at FROM orders_order WHERE id = %s", [order.pk]
        ).fetchone()
    assert status == "shipped" and shipped_at > datetime(2020, 1, 1, tzinfo=timezone.utc)


def test_untouched_timestamps_do_not_block_other_updates():
    order = new_order()
    with runtime_connection() as runtime:
        with runtime.transaction():
            runtime.execute("UPDATE orders_order SET placed_at = placed_at WHERE id = %s", [order.pk])
