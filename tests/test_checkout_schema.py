"""Lifecycle, deferred money and audit protections exercised on real PostgreSQL."""

import os
import uuid

import pytest
from account_helpers import runtime_connection
from checkout_helpers import customer, paid_order, product
from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from psycopg import errors, sql

from accounts.audit import set_audit_context
from accounts.models import AuditLog
from config.privileges import grant_runtime
from orders.models import Cart, CartLine, Checkout, Order, Payment, Refund
from orders.services import add_to_cart, cart_review, change_order_status, checkout

pytestmark = pytest.mark.django_db(transaction=True)
STATUSES = list(Order.Status.values)
ALLOWED = {
    ("placed", "paid"),
    ("placed", "cancelled"),
    ("paid", "shipped"),
    ("paid", "cancelled"),
    ("shipped", "delivered"),
}


@pytest.mark.parametrize("old,new", [(a, b) for a in STATUSES for b in STATUSES if a != b and (a, b) not in ALLOWED])
def test_every_illegal_transition_is_rejected(old, new):
    _, order = paid_order(customer(), product(), status=old)
    with pytest.raises(IntegrityError), transaction.atomic():
        set_audit_context()
        Order.objects.filter(pk=order.pk).update(status=new)
    order.refresh_from_db()
    assert order.status == old
    assert not AuditLog.objects.filter(table_name="orders_order").exists()


@pytest.mark.parametrize("old,new", sorted(ALLOWED))
def test_allowed_transitions_stamp_time_and_audit_actor(old, new):
    buyer = customer()
    checkout, order = paid_order(buyer, product(), status=old)
    with transaction.atomic():
        set_audit_context(buyer.pk, "Order update")
        Order.objects.filter(pk=order.pk).update(status=new)
        if new == "cancelled":
            Refund.objects.create(
                order=order, checkout=checkout, amount=12, reason="Order update", refunded_at=timezone.now()
            )
    order.refresh_from_db()
    assert getattr(order, new + "_at") is not None
    audit = AuditLog.objects.get(table_name="orders_order")
    assert (audit.action, audit.actor_id, audit.reason, audit.before["status"], audit.after["status"]) == (
        "order." + new,
        buyer.pk,
        "Order update",
        old,
        new,
    )
    # A no-op status update does not change a timestamp or add an audit row.
    at = getattr(order, new + "_at")
    Order.objects.filter(pk=order.pk).update(status=new)
    order.refresh_from_db()
    assert getattr(order, new + "_at") == at and AuditLog.objects.filter(table_name="orders_order").count() == 1


@pytest.mark.parametrize("bad", ["checkout", "order", "payment", "payment-delete", "refund"])
def test_money_changes_are_rejected_at_commit(bad):
    checkout, order = paid_order(customer(), product())
    with pytest.raises(IntegrityError), transaction.atomic():
        set_audit_context()
        if bad == "checkout":
            Checkout.objects.filter(pk=checkout.pk).update(total=13)
        elif bad == "order":
            Order.objects.filter(pk=order.pk).update(items=11, total=13)
        elif bad == "payment":
            Payment.objects.filter(checkout=checkout).update(amount=11)
        elif bad == "payment-delete":
            Payment.objects.filter(checkout=checkout).delete()
        else:
            Refund.objects.create(order=order, checkout=checkout, amount=12, reason="Wrong", refunded_at=timezone.now())
        # The constraints are genuinely deferred: the inconsistent write itself reached this point.
        assert connection.in_atomic_block
    checkout.refresh_from_db()
    assert checkout.total == 12 and checkout.payments.get().amount == 12


def test_cancelled_order_requires_matching_refund_at_commit():
    checkout, order = paid_order(customer(), product())
    with pytest.raises(IntegrityError), transaction.atomic():
        set_audit_context()
        Order.objects.filter(pk=order.pk).update(status="cancelled")
    checkout, order = paid_order(checkout.customer, order.seller.products.get(), status="cancelled")
    with pytest.raises(IntegrityError), transaction.atomic():
        set_audit_context()
        Refund.objects.filter(order=order).delete()
    with pytest.raises(IntegrityError), transaction.atomic():
        set_audit_context()
        Refund.objects.filter(order=order).update(amount=11)


def test_cart_quantity_and_unique_product_constraints():
    cart = Cart.objects.create(customer=customer())
    item = product()
    CartLine.objects.create(cart=cart, product=item, quantity=1)
    for quantity in (0, 1000):
        with pytest.raises(IntegrityError), transaction.atomic():
            CartLine.objects.filter(cart=cart).update(quantity=quantity)
    with pytest.raises(IntegrityError), transaction.atomic():
        CartLine.objects.create(cart=cart, product=item, quantity=1)


def test_order_audit_trigger_works_as_runtime_and_cannot_be_tampered_with():
    buyer = customer()
    _, order = paid_order(buyer, product())
    with runtime_connection() as runtime:
        with runtime.transaction():
            runtime.execute(
                "SELECT set_config('mercer.actor_id', %s, true), set_config('mercer.audit_reason', %s, true)",
                [str(buyer.pk), "Ship order"],
            )
            runtime.execute("UPDATE orders_order SET status=%s WHERE id=%s", ["shipped", order.pk])
        assert runtime.execute(
            "SELECT action, actor_id FROM audit_log WHERE table_name=%s", ["orders_order"]
        ).fetchall() == [("order.shipped", buyer.pk)]
        for statement in (
            "ALTER TABLE orders_order DISABLE TRIGGER order_status_audit",
            "DROP FUNCTION public.audit_order_status() CASCADE",
            "ALTER FUNCTION public.audit_order_status() SET search_path=pg_temp, public",
            "UPDATE audit_log SET reason='forged'",
        ):
            with pytest.raises(errors.InsufficientPrivilege):
                runtime.execute(statement)
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT p.proname, pg_get_userbyid(p.proowner), p.prosecdef, p.proconfig,
                         has_function_privilege(%s, p.oid, 'EXECUTE') FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                         WHERE n.nspname='public' AND p.proname IN ('audit_order_status','check_order_status_transition',
                         'check_checkout_money','check_checkout_refunds') ORDER BY p.proname""",
            [os.environ["POSTGRES_RUNTIME_USER"]],
        )
        rows = cursor.fetchall()
    assert len(rows) == 4
    for name, owner, definer, config, execute in rows:
        assert owner == os.environ["POSTGRES_USER"] and config == ["search_path=public, pg_temp"] and not execute
        # The audit function writes a table runtime cannot; the two money checks read every payment, order and refund of a
        # checkout, which a seller session's row policies would otherwise hide (docs/plans/seller-rls.md). The status
        # check only looks at OLD and NEW and keeps the caller's rights.
        assert definer == (name != "check_order_status_transition")


@pytest.mark.parametrize("bad", ["checkout-insert", "order-insert", "order-delete", "payment-insert", "payment-move"])
def test_deferred_checks_cover_inserts_deletes_and_both_moved_parents(bad):
    buyer, item = customer(), product()
    checkout, order = paid_order(buyer, item)
    other = Checkout.objects.create(customer=buyer, total=0, placed_at=timezone.now())
    with pytest.raises(IntegrityError), transaction.atomic():
        set_audit_context()
        if bad == "checkout-insert":
            Checkout.objects.create(customer=buyer, total=1, placed_at=timezone.now())
        elif bad == "order-insert":
            extra = product("extra")
            Order.objects.create(
                checkout=checkout,
                seller=extra.seller,
                status="paid",
                items=1,
                freight=0,
                total=1,
                placed_at=timezone.now(),
                estimated_delivery=timezone.now(),
            )
        elif bad == "order-delete":
            order.delete()
        elif bad == "payment-insert":
            Payment.objects.create(checkout=checkout, sequence=2, method="voucher", instalments=1, amount=1)
        else:
            Payment.objects.filter(checkout=checkout).update(checkout=other)
        assert connection.in_atomic_block
    assert Checkout.objects.get(pk=checkout.pk).payments.get().amount == 12
    assert not other.payments.exists()


MONEY_TABLES = ("orders_checkout", "orders_order", "orders_orderline", "orders_payment", "orders_refund")


def _purchase():
    buyer, item = customer(), product()
    add_to_cart(buyer, item.pk, 2)
    record = checkout(buyer, uuid.uuid4(), cart_review(buyer)["fingerprint"])
    return buyer, item, record, record.orders.get()


@pytest.mark.parametrize("table", MONEY_TABLES)
@pytest.mark.parametrize("regrant", [False, True])
def test_runtime_cannot_delete_money_rows_even_after_regrant(table, regrant):
    buyer, _, record, order = _purchase()
    change_order_status(buyer, order.pk, "cancel")
    if regrant:
        with connection.schema_editor() as editor:
            grant_runtime(None, editor)
    with runtime_connection() as runtime:
        privileges = runtime.execute(
            """SELECT has_table_privilege(current_user, %s, privilege)
                                       FROM unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE']) privilege""",
            [table],
        ).fetchall()
        assert privileges == [(True,), (True,), (True,), (False,)]
        with pytest.raises(errors.InsufficientPrivilege):
            runtime.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier(table)))
    with connection.cursor() as cursor:
        cursor.execute("SELECT has_table_privilege(current_user, %s, 'DELETE')", [table])
        assert cursor.fetchone()[0]  # the owner's privileges are unchanged
    assert Checkout.objects.filter(pk=record.pk).exists() and Refund.objects.filter(order=order).exists()


def test_runtime_cannot_rewrite_shipped_order_by_delete_and_insert():
    buyer, item, record, order = _purchase()
    change_order_status(item.seller.user, order.pk, "ship")
    order.refresh_from_db()
    audit_before = AuditLog.objects.filter(table_name="orders_order").count()
    with runtime_connection() as runtime, pytest.raises(errors.InsufficientPrivilege), runtime.transaction():
        runtime.execute("SELECT set_config('mercer.actor_id', %s, true)", [str(buyer.pk)])
        line = runtime.execute(
            """SELECT seller_id,product_id,quantity,unit_price,freight,shipping_limit_at
                                      FROM orders_orderline WHERE order_id=%s""",
            [order.pk],
        ).fetchone()
        runtime.execute("DELETE FROM orders_orderline WHERE order_id=%s", [order.pk])
        runtime.execute("DELETE FROM orders_order WHERE id=%s", [order.pk])
        new_id = runtime.execute(
            """INSERT INTO orders_order (checkout_id,seller_id,status,items,freight,total,placed_at,
                                         paid_at,shipped_at,cancelled_at,estimated_delivery)
                                         VALUES (%s,%s,'cancelled',%s,%s,%s,%s,%s,%s,now(),%s) RETURNING id""",
            [
                record.pk,
                order.seller_id,
                order.items,
                order.freight,
                order.total,
                order.placed_at,
                order.paid_at,
                order.shipped_at,
                order.estimated_delivery,
            ],
        ).fetchone()[0]
        runtime.execute(
            """INSERT INTO orders_orderline (order_id,seller_id,product_id,quantity,unit_price,freight,shipping_limit_at)
                               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            [new_id, *line],
        )
        runtime.execute(
            """INSERT INTO orders_refund (order_id,checkout_id,amount,reason,refunded_at,imported)
                               VALUES (%s,%s,%s,'forged',now(),false)""",
            [new_id, record.pk, order.total],
        )
    order.refresh_from_db()
    assert order.status == "shipped" and order.lines.count() == 1
    assert Order.objects.count() == 1 and not Refund.objects.exists()
    assert AuditLog.objects.filter(table_name="orders_order").count() == audit_before


def test_runtime_cannot_delete_a_whole_paid_checkout():
    _, _, record, order = _purchase()
    with runtime_connection() as runtime, pytest.raises(errors.InsufficientPrivilege), runtime.transaction():
        for statement in (
            "DELETE FROM orders_payment WHERE checkout_id=%s",
            "DELETE FROM orders_orderline WHERE order_id IN (SELECT id FROM orders_order WHERE checkout_id=%s)",
            "DELETE FROM orders_order WHERE checkout_id=%s",
            "DELETE FROM orders_checkout WHERE id=%s",
        ):
            runtime.execute(statement, [record.pk])
    assert Checkout.objects.get(pk=record.pk).payments.get().amount == record.total
    assert Order.objects.get(pk=order.pk).lines.count() == 1
