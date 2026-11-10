"""Seller status transitions and their trigger-written audit rows, on real PostgreSQL (accounts plan, P2/P4)."""

import itertools
import threading

import pytest
from account_helpers import make_operator, make_seller
from db_helpers import wait_until_blocked
from django.db import DataError, IntegrityError, connection, transaction

from accounts.audit import StaleAction, change_seller_status, set_audit_context
from accounts.models import AuditLog, Seller
from catalogue.models import Category, Product, PurchasableProduct

STATUSES = ("pending", "approved", "rejected", "suspended")
LEGAL = {
    ("pending", "approved"): "approve",
    ("pending", "rejected"): "reject",
    ("approved", "suspended"): "suspend",
    ("suspended", "approved"): "reinstate",
}
ILLEGAL = [pair for pair in itertools.permutations(STATUSES, 2) if pair not in LEGAL]


def update_status(seller, status):
    Seller.objects.filter(pk=seller.pk).update(status=status)


@pytest.mark.django_db
@pytest.mark.parametrize("old, new", list(LEGAL))
def test_legal_transitions_write_one_system_audit_row(old, new):
    seller = make_seller(status=old)
    update_status(seller, new)
    entry = AuditLog.objects.get()
    assert (entry.table_name, entry.row_id, entry.action) == (
        "accounts_seller",
        str(seller.pk),
        "seller." + LEGAL[old, new],
    )
    assert entry.actor is None and entry.reason is None  # no context: a system change
    assert entry.before == {"id": seller.pk, "user_id": seller.user_id, "status": old, "shop_name": seller.shop_name}
    assert entry.after == {**entry.before, "status": new}
    assert entry.created_at is not None


@pytest.mark.django_db
@pytest.mark.parametrize("old, new", ILLEGAL)
def test_illegal_transitions_are_refused_by_the_database(old, new):
    seller = make_seller(status=old)
    with pytest.raises(IntegrityError, match=f"cannot change from {old} to {new}"), transaction.atomic():
        update_status(seller, new)
    seller.refresh_from_db()
    assert seller.status == old and not AuditLog.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("status", STATUSES)
def test_unchanged_status_and_shop_name_edits_are_not_audited(status):
    seller = make_seller(status=status)
    update_status(seller, status)
    Seller.objects.filter(pk=seller.pk).update(shop_name="Renamed shop")
    assert Seller.objects.get(pk=seller.pk).shop_name == "Renamed shop"
    assert not AuditLog.objects.exists()


@pytest.mark.django_db
def test_operator_action_records_exact_actor_reason_and_snapshots():
    operator, seller = make_operator(), make_seller(status="pending")
    change_seller_status(seller.pk, "approve", operator, "  Documents verified  ")
    entry = AuditLog.objects.get()
    assert entry.actor == operator and entry.reason == "Documents verified" and entry.action == "seller.approve"
    assert (entry.before["status"], entry.after["status"]) == ("pending", "approved")
    assert set(entry.after) == {"id", "user_id", "status", "shop_name"}  # no secrets or unlisted columns


@pytest.mark.django_db
def test_an_actor_without_a_reason_is_refused_by_the_database():
    seller = make_seller(status="pending")
    with pytest.raises(IntegrityError, match="audit_log_actor_reason"), transaction.atomic():
        set_audit_context(make_operator().pk, "   ")
        update_status(seller, "approved")
    seller.refresh_from_db()
    assert seller.status == "pending" and not AuditLog.objects.exists()


@pytest.mark.django_db
def test_hostile_reason_is_stored_as_data():
    payload = "x'); DELETE FROM audit_log; DROP TABLE accounts_seller; --"
    seller = make_seller(status="pending")
    change_seller_status(seller.pk, "reject", make_operator(), payload)
    assert AuditLog.objects.get().reason == payload
    assert Seller.objects.filter(pk=seller.pk, status="rejected").exists()


@pytest.mark.django_db
def test_a_non_numeric_actor_setting_cannot_be_injected():
    seller = make_seller(status="pending")
    with pytest.raises(ValueError):
        set_audit_context("1; DROP TABLE audit_log")
    with pytest.raises(DataError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SELECT set_config('mercer.actor_id', %s, true)", ["1 OR 1=1"])
        update_status(seller, "approved")
    seller.refresh_from_db()
    assert seller.status == "pending" and not AuditLog.objects.exists()


@pytest.mark.django_db
def test_stale_or_repeated_actions_fail_without_another_audit_row():
    operator, seller = make_operator(), make_seller(status="pending")
    change_seller_status(seller.pk, "approve", operator, "First decision")
    for action in ("approve", "reject"):
        with pytest.raises(StaleAction):
            change_seller_status(seller.pk, action, operator, "Too late")
    assert AuditLog.objects.count() == 1 and Seller.objects.get(pk=seller.pk).status == "approved"


@pytest.mark.django_db
def test_customers_and_sellers_cannot_use_the_status_service():
    from django.core.exceptions import PermissionDenied

    seller = make_seller(status="pending")
    with pytest.raises(PermissionDenied):
        change_seller_status(seller.pk, "approve", seller.user, "Self approval")
    assert Seller.objects.get(pk=seller.pk).status == "pending"


@pytest.mark.django_db
def test_suspension_hides_products_and_reinstatement_restores_them():
    operator, seller = make_operator(), make_seller(status="approved")
    category = Category.objects.create(slug="example", name_en="Example", name_pt="Exemplo")
    product = Product.objects.create(
        seller=seller, category=category, name="Lamp", price="10.00", freight="1.00", stock=3, lead_time_days=2
    )

    def visible():
        return PurchasableProduct.objects.filter(pk=product.pk).exists()

    assert visible()
    change_seller_status(seller.pk, "suspend", operator, "Investigation")
    assert not visible()
    change_seller_status(seller.pk, "reinstate", operator, "Cleared")
    assert visible()
    # Creating the product wrote its own product.create row; the seller decisions are the two after it.
    assert list(AuditLog.objects.order_by("id").values_list("action", flat=True)) == [
        "product.create",
        "seller.suspend",
        "seller.reinstate",
    ]


# Transaction-local context needs real commits, so these tests use transactional_db on Django's own connection.


@pytest.mark.django_db(transaction=True)
def test_context_requires_an_open_transaction():
    with pytest.raises(RuntimeError):
        set_audit_context(None, "")


@pytest.mark.django_db(transaction=True)
def test_context_clears_after_commit_on_a_reused_connection():
    operator, seller = make_operator(), make_seller(status="pending")
    change_seller_status(seller.pk, "approve", operator, "Approved")
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('mercer.actor_id', true), current_setting('mercer.audit_reason', true)")
        assert cursor.fetchone() in ((None, None), ("", ""))
    update_status(seller, "suspended")  # same connection, no context: a system change
    latest = AuditLog.objects.order_by("-id").first()
    assert latest.action == "seller.suspend" and latest.actor is None and latest.reason is None


@pytest.mark.django_db(transaction=True)
def test_context_clears_after_rollback_on_a_reused_connection():
    operator, seller = make_operator(), make_seller(status="pending")
    with pytest.raises(ZeroDivisionError), transaction.atomic():
        set_audit_context(operator.pk, "Rolled back")
        update_status(seller, "approved")
        raise ZeroDivisionError("force a rollback")
    assert Seller.objects.get(pk=seller.pk).status == "pending" and not AuditLog.objects.exists()
    update_status(seller, "rejected")
    entry = AuditLog.objects.get()
    assert entry.actor is None and entry.reason is None


@pytest.mark.django_db(transaction=True)
def test_concurrent_operators_one_wins_and_the_other_fails_cleanly():
    operator, other_operator, seller = make_operator(), make_operator("operator-2"), make_seller(status="pending")
    outcome = {}

    def second_operator():
        try:
            change_seller_status(seller.pk, "reject", other_operator, "Rejected concurrently")
            outcome["result"] = "changed"
        except StaleAction:
            outcome["result"] = "stale"
        finally:
            connection.close()

    with transaction.atomic():
        Seller.objects.select_for_update().get(pk=seller.pk)  # first operator holds the row lock
        thread = threading.Thread(target=second_operator)
        thread.start()
        wait_until_blocked()  # the second operator waits on that lock
        change_seller_status(seller.pk, "approve", operator, "Approved first")
    thread.join(10)
    assert outcome == {"result": "stale"}
    assert Seller.objects.get(pk=seller.pk).status == "approved"
    assert list(AuditLog.objects.values_list("action", "actor_id")) == [("seller.approve", operator.pk)]
