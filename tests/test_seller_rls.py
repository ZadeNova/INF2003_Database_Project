"""Seller row-level security (docs/plans/seller-rls.md), proved as the real runtime role.

The owner role bypasses row security and the ordinary tests run as the owner, so none of them says anything about the
policies. Every test here opens a raw connection as the web service's runtime role (the data is committed first, hence
transaction=True) and declares a seller the way the seller mixin does, with the session setting `mercer.seller_id`.
"""

import os
from contextlib import contextmanager

import psycopg
import pytest
from account_helpers import make_operator, runtime_connection
from checkout_helpers import customer, paid_order, product
from django.db import connection
from psycopg import errors

from accounts.audit import change_seller_status
from orders.models import OrderLine

pytestmark = pytest.mark.django_db(transaction=True)


@contextmanager
def session(seller_id=None):
    """A runtime-role connection that has declared a seller (or none, as a customer or operator session does)."""
    with runtime_connection() as conn:
        if seller_id is not None:
            conn.execute("SELECT set_config('mercer.seller_id', %s, false)", [str(seller_id)])
        yield conn


@pytest.fixture
def world():
    """Two sellers, each with a product and a paid order in a checkout of its own."""
    buyer = customer()
    first, second = product("first"), product("second")
    first_checkout, first_order = paid_order(buyer, first)
    second_checkout, second_order = paid_order(buyer, second)
    for order, item in ((first_order, first), (second_order, second)):
        OrderLine.objects.create(order=order, seller=item.seller, product=item, quantity=1, unit_price=10, freight=2)
    return {
        "first": first,
        "second": second,
        "first_order": first_order,
        "second_order": second_order,
        "first_checkout": first_checkout,
        "second_checkout": second_checkout,
    }


def ids(conn, query, *params):
    return sorted(row[0] for row in conn.execute(query, params).fetchall())


# ----------------------------------------------------------------------------------------------- reading
def test_a_seller_session_reads_only_its_own_orders_and_lines(world):
    with session(world["first"].seller_id) as conn:
        assert ids(conn, "SELECT id FROM orders_order") == [world["first_order"].pk]
        assert ids(conn, "SELECT order_id FROM orders_orderline") == [world["first_order"].pk]


def test_a_seller_session_sees_every_product_but_no_checkout_or_payment(world):
    with session(world["first"].seller_id) as conn:
        assert len(ids(conn, "SELECT id FROM catalogue_product")) == 2  # the shop is public
        assert ids(conn, "SELECT id FROM orders_checkout") == []
        assert ids(conn, "SELECT id FROM orders_payment") == []


def test_a_session_without_a_seller_sees_everything_as_before(world):
    """Documents the fail-open default: no setting means no restriction (customers, operators, public pages)."""
    with session() as conn:
        assert len(ids(conn, "SELECT id FROM orders_order")) == 2
        assert len(ids(conn, "SELECT id FROM orders_checkout")) == 2
        assert len(ids(conn, "SELECT id FROM orders_payment")) == 2


def test_an_empty_or_reset_setting_is_the_same_as_none(world):
    with session(world["first"].seller_id) as conn:
        conn.execute("SELECT set_config('mercer.seller_id', '', false)")
        assert len(ids(conn, "SELECT id FROM orders_order")) == 2


def test_a_seller_reads_the_refunds_of_its_own_orders_only(world):
    buyer = customer("second-buyer")
    _, cancelled_first = paid_order(buyer, world["first"], status="cancelled")
    _, cancelled_second = paid_order(buyer, world["second"], status="cancelled")
    with session(world["first"].seller_id) as conn:
        assert ids(conn, "SELECT order_id FROM orders_refund") == [cancelled_first.pk]
    with session() as conn:
        assert ids(conn, "SELECT order_id FROM orders_refund") == sorted([cancelled_first.pk, cancelled_second.pk])


# ----------------------------------------------------------------------------------------------- writing
def test_an_unfiltered_update_changes_only_the_sellers_own_rows(world):
    with session(world["first"].seller_id) as conn:
        assert conn.execute("UPDATE catalogue_product SET stock = stock + 1").rowcount == 1
        assert conn.execute("UPDATE orders_order SET freight = freight").rowcount == 1
    with session() as conn:
        stocks = dict(conn.execute("SELECT id, stock FROM catalogue_product").fetchall())
    assert stocks[world["first"].pk] == 21 and stocks[world["second"].pk] == 20


def test_a_seller_cannot_delete_another_sellers_product(world):
    with session(world["first"].seller_id) as conn:
        assert conn.execute("DELETE FROM catalogue_product WHERE id = %s", [world["second"].pk]).rowcount == 0


def test_a_seller_cannot_hand_a_row_to_another_seller_or_create_one_for_another(world):
    with session(world["first"].seller_id) as conn:
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute(
                "UPDATE catalogue_product SET seller_id = %s WHERE id = %s",
                [world["second"].seller_id, world["first"].pk],
            )
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute(
                "INSERT INTO catalogue_product (seller_id, category_id, name, price, stock, freight, lead_time_days, active, "
                "taken_down, has_generated_content) SELECT %s, category_id, 'planted', 1, 1, 1, 1, true, false, false "
                "FROM catalogue_product WHERE id = %s",
                [world["second"].seller_id, world["first"].pk],
            )
        with pytest.raises(
            errors.InsufficientPrivilege
        ):  # an order too (here the SELECT policy refuses the new row as well)
            conn.execute(
                "UPDATE orders_order SET seller_id = %s WHERE id = %s",
                [world["second"].seller_id, world["first_order"].pk],
            )


def test_a_seller_cannot_insert_or_delete_orders(world):
    with session(world["first"].seller_id) as conn:
        with pytest.raises(
            errors.InsufficientPrivilege
        ):  # money tables are never deleted from: the grant refuses first
            conn.execute("DELETE FROM orders_order WHERE id = %s", [world["first_order"].pk])
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute(
                "INSERT INTO orders_order (checkout_id, seller_id, status, items, freight, total, placed_at, estimated_delivery) "
                "SELECT checkout_id, seller_id, status, items, freight, total, placed_at, estimated_delivery "
                "FROM orders_order WHERE id = %s",
                [world["first_order"].pk],
            )


def test_a_seller_cannot_rewrite_its_own_order_lines(world):
    """The runtime role holds UPDATE on order lines; only the policy (a seller may read them, nothing else) stops this."""
    with session(world["first"].seller_id) as conn:
        assert conn.execute("UPDATE orders_orderline SET quantity = quantity + 1").rowcount == 0
    with session() as conn:
        assert conn.execute(
            "SELECT quantity FROM orders_orderline WHERE order_id = %s", [world["first_order"].pk]
        ).fetchone() == (1,)


# ----------------------------------------------------------------------------------------------- the money checks
def test_a_seller_session_cannot_break_the_checkout_money_invariant(world):
    """The deferred money check reads the whole checkout. As the caller, a seller session would not see the checkout,
    the check would skip it and the write would commit; as SECURITY DEFINER it is rejected at commit."""
    with session(world["first"].seller_id) as conn, pytest.raises(errors.CheckViolation), conn.transaction():
        # items and total move together, so the row's own check (total = items + freight) holds and only the
        # checkout-wide rule (orders add up to the checkout total) is broken
        conn.execute(
            "UPDATE orders_order SET items = items + 987, total = total + 987 WHERE id = %s",
            [world["first_order"].pk],
        )
    with session() as conn:
        assert (
            conn.execute("SELECT total FROM orders_order WHERE id = %s", [world["first_order"].pk]).fetchone()[0] == 12
        )


def test_the_checkout_lock_is_taken_only_for_an_order_the_session_may_see(world):
    with session(world["first"].seller_id) as conn, conn.transaction():
        own = conn.execute("SELECT lock_checkout_of_order(%s)", [world["first_order"].pk]).fetchone()[0]
        other = conn.execute("SELECT lock_checkout_of_order(%s)", [world["second_order"].pk]).fetchone()[0]
    assert own == world["first_checkout"].pk and other is None
    with session(world["first"].seller_id) as conn, conn.transaction():
        assert conn.execute("SELECT lock_checkout_of_order(%s)", [10**9]).fetchone()[0] is None
    with session() as conn, conn.transaction():
        assert (
            conn.execute("SELECT lock_checkout_of_order(%s)", [world["second_order"].pk]).fetchone()[0]
            == world["second_checkout"].pk
        )


# ----------------------------------------------------------------------------------------------- the audit log
def test_a_seller_reads_only_the_audit_rows_of_its_own_shop(world):
    with session(world["first"].seller_id) as conn:
        rows = conn.execute(
            "SELECT table_name, row_id, COALESCE(after, before) ->> 'seller_id' FROM audit_log"
        ).fetchall()
    assert rows, "the product inserts left audit rows"
    for table_name, row_id, seller_id in rows:
        assert seller_id == str(world["first"].seller_id) or (
            table_name == "accounts_seller" and row_id == str(world["first"].seller_id)
        )
    with session() as conn:
        assert conn.execute("SELECT count(*) FROM audit_log").fetchone()[0] > len(rows)


def test_a_seller_reads_its_own_status_history_and_no_other_sellers(world):
    operator = make_operator()
    for item in (world["first"], world["second"]):  # one status change each: an audit row about the seller itself
        change_seller_status(item.seller_id, "suspend", operator, "Policy test")
    with session(world["first"].seller_id) as conn:
        seen = conn.execute("SELECT row_id FROM audit_log WHERE table_name = 'accounts_seller'").fetchall()
    assert seen == [(str(world["first"].seller_id),)]


# ----------------------------------------------------------------------------------------------- the safety nets
TABLES = {
    "orders_order": {"SELECT", "INSERT", "UPDATE", "DELETE"},
    "orders_orderline": {"SELECT", "INSERT", "UPDATE", "DELETE"},
    "orders_refund": {"SELECT", "INSERT", "UPDATE", "DELETE"},
    "orders_checkout": {"ALL"},
    "orders_payment": {"ALL"},
    "catalogue_product": {"SELECT", "INSERT", "UPDATE", "DELETE"},
    "audit_log": {"SELECT"},
}


def owner_rows(query, *params):
    with psycopg.connect(
        dbname=connection.settings_dict["NAME"],
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        autocommit=True,
    ) as owner:
        return owner.execute(query, params).fetchall()


def test_every_table_with_policies_is_in_the_expected_map_and_row_security_is_never_forced():
    found = {}
    for table, command in owner_rows("SELECT tablename, cmd FROM pg_policies WHERE schemaname = 'public'"):
        found.setdefault(table, set()).add(command)
    assert found == TABLES
    flags = dict(
        (name, (enabled, forced))
        for name, enabled, forced in owner_rows(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = ANY(%s)", list(TABLES)
        )
    )
    assert flags == {table: (True, False) for table in TABLES}


def test_a_new_table_with_a_seller_column_cannot_be_forgotten():
    """Any ordinary table with a seller_id column must be one of the protected tables (add a policy and extend the map)."""
    with_seller = {
        row[0]
        for row in owner_rows(
            "SELECT c.relname FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND a.attname = 'seller_id' AND NOT a.attisdropped AND c.relkind IN ('r', 'p')"
        )
    }
    assert with_seller <= set(TABLES), with_seller - set(TABLES)


def test_the_runtime_role_is_not_the_owner_and_cannot_bypass_row_security():
    role, owner = os.environ["POSTGRES_RUNTIME_USER"], os.environ["POSTGRES_USER"]
    assert role != owner
    assert owner_rows("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = %s", role) == [(False, False)]
    owners = {row[0] for row in owner_rows("SELECT tableowner FROM pg_tables WHERE tablename = ANY(%s)", list(TABLES))}
    assert owners == {owner}


def test_the_migration_reverses_cleanly_and_reapplies(world):
    from django.core.management import call_command

    call_command("migrate", "orders", "0004", verbosity=0)
    try:
        assert owner_rows("SELECT count(*) FROM pg_policies WHERE schemaname = 'public'") == [(0,)]
        assert owner_rows(
            "SELECT proname, prosecdef FROM pg_proc WHERE proname IN ('check_checkout_money', 'check_checkout_refunds') ORDER BY proname"
        ) == [("check_checkout_money", False), ("check_checkout_refunds", False)]
        assert owner_rows(
            "SELECT count(*) FROM pg_proc WHERE proname IN ('mercer_seller', 'lock_checkout_of_order')"
        ) == [(0,)]
    finally:
        call_command("migrate", verbosity=0)
    assert owner_rows("SELECT count(*) FROM pg_policies WHERE schemaname = 'public'")[0][0] > 0
    assert owner_rows(
        "SELECT proname, prosecdef FROM pg_proc WHERE proname IN ('check_checkout_money', 'check_checkout_refunds') ORDER BY proname"
    ) == [("check_checkout_money", True), ("check_checkout_refunds", True)]
