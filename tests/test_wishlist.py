"""Composite wishlist keys, trigger-created alerts and scoped UI against real databases."""
import uuid
import json

from django.db import IntegrityError, connection, transaction
from django.http import Http404
from django.test import Client
import pytest

from accounts.models import AuditLog
from catalogue.models import Product
from orders.services import add_to_cart, cart_review, checkout, change_order_status
from wishlist.models import RestockAlert, WishlistItem
from wishlist.services import set_saved, unseen_count
from account_helpers import runtime_connection
from checkout_helpers import customer, product

pytestmark = pytest.mark.django_db(transaction=True)


def restock(item, stock):
    Product.objects.filter(pk=item.pk).update(stock=stock)


def test_zero_to_positive_trigger_each_customer_and_no_duplicate_unseen():
    item = product(stock=0)
    buyers = [customer("one"), customer("two")]
    for buyer in buyers:
        set_saved(buyer, item.pk, True)
        set_saved(buyer, item.pk, True)
    assert WishlistItem.objects.count() == 2
    for stock in [5, 6, 0, 5]:
        restock(item, stock)
    assert RestockAlert.objects.count() == 2
    assert all(unseen_count(buyer) == 1 for buyer in buyers)
    assert AuditLog.objects.filter(table_name="catalogue_product").count() == 4
    assert not AuditLog.objects.filter(table_name="catalogue_product", actor__isnull=False).exists()


def test_raw_runtime_update_fires_trigger_and_keeps_product_audit():
    item = product(name="x'); DROP TABLE wishlist_item; --", stock=0)
    buyer = customer()
    set_saved(buyer, item.pk, True)
    with runtime_connection() as runtime:
        runtime.execute("UPDATE catalogue_product SET stock=%s WHERE id=%s", [5, item.pk])
    alert = RestockAlert.objects.get()
    assert alert.customer_id == buyer.pk and alert.product_id == item.pk
    audit = AuditLog.objects.get(table_name="catalogue_product")
    assert audit.before["stock"] == 0 and audit.after["stock"] == 5
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='wishlist_item'::regclass AND contype='p'")
        assert cursor.fetchone()[0] == "PRIMARY KEY (customer_id, product_id)"
        cursor.execute("SELECT indexdef FROM pg_indexes WHERE indexname=%s", ["restock_one_unseen"])
        assert "WHERE (seen_at IS NULL)" in cursor.fetchone()[0]


def test_positive_to_positive_and_nonwishlisted_restock_create_no_alerts():
    item = product(stock=5)
    set_saved(customer(), item.pk, True)
    restock(item, 6)
    restock(product("unsaved", stock=0), 3)
    assert not RestockAlert.objects.exists()


def test_checkout_cancellation_restock_creates_alert():
    buyer, item = customer(), product(stock=1)
    watcher = customer("watcher")
    add_to_cart(buyer, item.pk)
    placed = checkout(buyer, uuid.uuid4(), cart_review(buyer)["fingerprint"])
    item.refresh_from_db(); assert item.stock == 0
    set_saved(watcher, item.pk, True)
    change_order_status(buyer, placed.orders.get().pk, "cancel", "Restock trigger exit check")
    item.refresh_from_db(); assert item.stock == 1
    assert RestockAlert.objects.get().customer_id == watcher.pk
    assert AuditLog.objects.filter(action="order.cancelled").exists()
    assert AuditLog.objects.filter(table_name="catalogue_product", after__stock=1).exists()


def test_customer_scoping_badge_and_seen_alert_allow_next_restock():
    buyer, other = customer(), customer("other")
    item, private = product(stock=0), product("private", stock=0)
    set_saved(buyer, item.pk, True); set_saved(other, item.pk, True); set_saved(other, private.pk, True)
    restock(item, 4); restock(private, 2)
    client = Client(); client.force_login(buyer)
    page = client.get("/wishlist/?customer_id=" + str(other.pk))
    assert page.status_code == 200
    assert list(page.context["page_obj"].object_list)[0].pk == item.pk
    assert len(page.context["page_obj"].object_list) == 1
    assert page.context["restock_unseen"] == 1 and b"1 unseen restock alerts" in page.content
    # HEAD neither consumes an alert nor changes another customer's state.
    assert client.head("/alerts/").status_code == 200
    assert unseen_count(buyer) == 1
    alerts = client.get("/alerts/?customer_id=" + str(other.pk))
    assert alerts.status_code == 200 and [a.product_id for a in alerts.context["page_obj"]] == [item.pk]
    assert unseen_count(buyer) == 0 and unseen_count(other) == 2
    restock(item, 0); restock(item, 7)
    assert RestockAlert.objects.filter(customer=buyer, product=item).count() == 2
    assert unseen_count(buyer) == 1 and unseen_count(other) == 2
    client.post(f"/wishlist/{item.pk}/remove/")
    assert not WishlistItem.objects.filter(customer=buyer).exists()
    assert WishlistItem.objects.filter(customer=other).count() == 2


@pytest.mark.parametrize("hidden", ["taken_down", "inactive", "suspended"])
def test_alerts_and_badge_hide_products_outside_purchasable_view(hidden):
    buyer, item = customer(), product(stock=0)
    set_saved(buyer, item.pk, True); restock(item, 1)
    if hidden == "suspended":
        from accounts.models import Seller
        Seller.objects.filter(pk=item.seller_id).update(status="suspended")
    else:
        Product.objects.filter(pk=item.pk).update(**({"taken_down": True} if hidden == "taken_down" else {"active": False}))
    client = Client(); client.force_login(buyer)
    assert unseen_count(buyer) == 0
    page = client.get("/alerts/")
    assert len(page.context["page_obj"].object_list) == 0
    assert RestockAlert.objects.get().seen_at is None
    assert client.post(f"/wishlist/{item.pk}/add/").status_code == 404


def test_composite_key_and_partial_unique_index_enforce_database_invariants():
    buyer, item = customer(), product(stock=0)
    set_saved(buyer, item.pk, True)
    with pytest.raises(IntegrityError), transaction.atomic():
        WishlistItem.objects.create(customer=buyer, product=item)
    restock(item, 1)
    with pytest.raises(IntegrityError), transaction.atomic():
        RestockAlert.objects.create(customer=buyer, product=item)


@pytest.mark.parametrize("saved", [True, False])
def test_insert_and_delete_injection_parameters_cannot_reach_other_rows(saved):
    buyer, other, item = customer(), customer("other"), product()
    set_saved(other, item.pk, True)
    for payload in ["1 OR 1=1", "1; DELETE FROM wishlist_item; --", {"$ne": None}]:
        with pytest.raises(Http404):
            set_saved(buyer, payload, saved)
    assert WishlistItem.objects.get().customer_id == other.pk


def test_htmx_buttons_post_only_csrf_roles_and_safe_redirect():
    buyer, item = customer(), product(stock=0)
    client = Client(); client.force_login(buyer)
    for path in [f"/wishlist/{item.pk}/add/", f"/wishlist/{item.pk}/remove/"]:
        assert client.get(path).status_code == 405
    page = client.post(f"/wishlist/{item.pk}/add/", {"next": "https://evil.example/"}, HTTP_HX_REQUEST="true")
    assert page.status_code == 200 and b"Remove from wishlist" in page.content
    assert json.loads(page["HX-Trigger"]) == {"wishlistChanged":{"product_id":item.pk,"saved":True}}
    page = client.post(f"/wishlist/{item.pk}/remove/", HTTP_HX_REQUEST="true")
    assert json.loads(page["HX-Trigger"]) == {"wishlistChanged":{"product_id":item.pk,"saved":False}}
    assert b"Save to wishlist" in page.content
    assert Client().post(f"/wishlist/{item.pk}/add/", HTTP_HX_REQUEST="true")["HX-Redirect"] == "/login/"
    secure = Client(enforce_csrf_checks=True); secure.force_login(buyer)
    assert secure.post(f"/wishlist/{item.pk}/remove/").status_code == 403
    seller = Client(); seller.force_login(item.seller.user)
    assert seller.get("/wishlist/").status_code == 403 and seller.get("/alerts/").status_code == 403
    assert seller.post(f"/wishlist/{item.pk}/add/").status_code == 403
    response = client.post(f"/wishlist/{item.pk}/remove/", {"next": "//evil.example/"})
    assert response.status_code == 302 and response.url == "/wishlist/"
