"""Checkout and catalogue together: checkout's stock changes fire catalogue's product audit trigger."""
import uuid

import pytest
from checkout_helpers import customer, product
from django.test import Client

from accounts.audit import change_seller_status
from accounts.models import AuditLog, User
from orders.services import add_to_cart, cart_review, change_order_status, checkout

pytestmark = pytest.mark.django_db(transaction=True)


def product_rows(item):
    return AuditLog.objects.filter(table_name="catalogue_product", row_id=str(item.pk)).order_by("id")


def test_purchase_and_cancellation_stock_changes_are_audited_with_the_buyer():
    buyer, item = customer(), product(stock=20)
    add_to_cart(buyer, item.pk)
    placed = checkout(buyer, uuid.uuid4(), cart_review(buyer)["fingerprint"])
    sold = product_rows(item).get()
    assert sold.actor_id == buyer.pk and sold.reason and sold.reason.strip()
    assert (sold.before["stock"], sold.after["stock"]) == (20, 19)
    change_order_status(buyer, placed.orders.get().pk, "cancel", "Changed my mind")
    restocked = product_rows(item).last()
    assert restocked.pk != sold.pk and restocked.actor_id == buyer.pk and restocked.reason == "Changed my mind"
    assert (restocked.before["stock"], restocked.after["stock"]) == (19, 20)


def test_audit_page_resolves_seller_order_and_product_rows_to_their_own_shops():
    operator = User.objects.create_user(username="ops", role="operator")
    buyer, item = customer(), product("lamp")
    other = product("other-shop")
    change_seller_status(other.seller.pk, "suspend", operator, "Investigation")
    add_to_cart(buyer, item.pk)
    order = checkout(buyer, uuid.uuid4(), cart_review(buyer)["fingerprint"]).orders.get()
    change_order_status(item.seller.user, order.pk, "ship")
    client = Client()
    client.force_login(operator)
    entries = {(e.table_name, e.row_id): e for e in client.get("/operator/audit/").context["entries"]}
    assert entries[("accounts_seller", str(other.seller.pk))].shop == other.seller
    assert entries[("orders_order", str(order.pk))].shop == item.seller
    product_entry = entries[("catalogue_product", str(item.pk))]
    assert product_entry.shop == item.seller and product_entry.product == item
