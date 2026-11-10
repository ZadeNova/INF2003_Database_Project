"""Customer, seller and operator pages, CSRF and object ownership using real PostgreSQL."""

import uuid

import pytest
from checkout_helpers import customer, product
from django.test import Client
from django.urls import reverse

from accounts.models import Seller, User
from catalogue.models import Product
from orders.models import Checkout, Order, Payment, Refund
from orders.services import add_to_cart, cart_review, checkout

pytestmark = pytest.mark.django_db(transaction=True)


def signed_in(user):
    client = Client()
    client.force_login(user)
    return client


def order_for(buyer, item):
    add_to_cart(buyer, item.pk)
    return checkout(buyer, uuid.uuid4(), cart_review(buyer)["fingerprint"]).orders.get()


def test_cart_add_update_remove_htmx_and_plain_fallback():
    buyer, item = customer(), product()
    client = signed_in(buyer)
    response = client.post(reverse("orders:cart_add", args=[item.pk]), {"quantity": 2}, HTTP_HX_REQUEST="true")
    assert response.status_code == 200 and b"Added to your cart" in response.content
    assert response.templates[0].name == "orders/_cart_added.html"
    response = client.get(reverse("orders:cart"))
    assert response.status_code == 200 and b"example shop" in response.content and b"S$24.00" in response.content
    line = buyer.cart.lines.get()
    response = client.post(reverse("orders:cart_quantity", args=[line.pk]), {"quantity": 3}, HTTP_HX_REQUEST="true")
    assert (
        response.status_code == 200
        and b"S$36.00" in response.content
        and b'<div id="cart-content">' in response.content
    )
    assert b"<html" not in response.content
    response = client.post(reverse("orders:cart_quantity", args=[line.pk]), {"quantity": "0"}, HTTP_HX_REQUEST="true")
    assert response.status_code == 200 and b'role="alert"' in response.content
    response = client.post(reverse("orders:cart_remove", args=[line.pk]), HTTP_HX_REQUEST="true")
    assert response.status_code == 200 and b"Your cart is empty" in response.content
    response = client.post(reverse("orders:cart_add", args=[item.pk]), {"quantity": 1})
    assert response.status_code == 302 and response.url == reverse("orders:cart")


def test_review_creates_fresh_key_and_submit_replays_same_form():
    buyer, item = customer(), product()
    client = signed_in(buyer)
    add_to_cart(buyer, item.pk, 2)
    first = client.get(reverse("orders:review"))
    second = client.get(reverse("orders:review"))
    assert first.context["form"]["idempotency_key"].value() != second.context["form"]["idempotency_key"].value()
    assert "no-store" in first.headers["Cache-Control"]
    data = {
        "idempotency_key": first.context["form"]["idempotency_key"].value(),
        "fingerprint": first.context["fingerprint"],
        "method": "credit_card",
        "instalments": 12,
    }
    response = client.post(reverse("orders:review"), data)
    assert response.status_code == 302 and Checkout.objects.count() == 1
    destination = response.url
    replay = client.post(reverse("orders:review"), data)
    assert replay.url == destination and Checkout.objects.count() == 1
    assert Payment.objects.get().instalments == 12
    detail = client.get(destination)
    assert detail.status_code == 200 and b"Your shop orders" in detail.content and b"Payment received" in detail.content


def test_price_change_forces_rereview_without_any_payment():
    buyer, item = customer(), product()
    client = signed_in(buyer)
    add_to_cart(buyer, item.pk)
    response = client.get(reverse("orders:review"))
    data = {
        "idempotency_key": response.context["form"]["idempotency_key"].value(),
        "fingerprint": response.context["fingerprint"],
        "method": "boleto",
        "instalments": 1,
    }
    Product.objects.filter(pk=item.pk).update(price="15.00")
    result = client.post(reverse("orders:review"), data, follow=True)
    assert b"prices changed" in result.content and b"S$17.00" in result.content
    assert not Checkout.objects.exists() and not Payment.objects.exists()


def test_bad_payment_form_is_recoverable_and_never_collects_card_details():
    buyer, item = customer(), product()
    client = signed_in(buyer)
    add_to_cart(buyer, item.pk)
    response = client.get(reverse("orders:review"))
    data = {
        "idempotency_key": response.context["form"]["idempotency_key"].value(),
        "fingerprint": response.context["fingerprint"],
        "method": "boleto",
        "instalments": 2,
        "card_number": "discard this unrecognised field",
    }
    result = client.post(reverse("orders:review"), data)
    assert result.status_code == 400 and b"Choose 1 for this payment method" in result.content
    assert b'"card_number"' not in result.content and not Payment.objects.exists()
    data["instalments"] = 1
    assert client.post(reverse("orders:review"), data).status_code == 302
    assert set(f.name for f in Payment._meta.fields) == {
        "id",
        "checkout",
        "sequence",
        "method",
        "instalments",
        "amount",
    }


def test_unavailable_review_flags_line_and_hides_pay_action():
    buyer, item = customer(), product()
    client = signed_in(buyer)
    add_to_cart(buyer, item.pk)
    Product.objects.filter(pk=item.pk).update(taken_down=True)
    response = client.get(reverse("orders:review"))
    assert b"No longer available" in response.content and b"Place order and pay" not in response.content
    assert b"No longer available" in client.get(reverse("orders:cart")).content


def test_customer_history_detail_cancel_and_visible_status_changes():
    buyer, item = customer(), product()
    order = order_for(buyer, item)
    client = signed_in(buyer)
    assert b"Paid" in client.get(reverse("orders:history")).content
    response = client.get(reverse("orders:order_detail", args=[order.pk]))
    assert response.status_code == 200 and b"Cancel this order" in response.content
    response = client.post(reverse("orders:cancel", args=[order.pk]), {"reason": "Changed my mind"}, follow=True)
    assert response.status_code == 200 and b"Refunded S$12.00" in response.content and b"Cancelled" in response.content
    assert Refund.objects.get().reason == "Changed my mind"
    item.refresh_from_db()
    assert item.stock == 20


def test_seller_ship_operator_deliver_then_customer_sees_timestamps():
    buyer, item = customer(), product()
    order = order_for(buyer, item)
    seller = signed_in(item.seller.user)
    assert b"Mark shipped" in seller.get(reverse("orders:seller_orders")).content
    assert seller.post(reverse("orders:ship", args=[order.pk])).status_code == 302
    operator = User.objects.create_user(username="operator", role="operator")
    ops = signed_in(operator)
    assert b"Mark delivered" in ops.get(reverse("orders:operator_orders")).content
    assert ops.post(reverse("orders:deliver", args=[order.pk])).status_code == 302
    response = signed_in(buyer).get(reverse("orders:order_detail", args=[order.pk]))
    assert b"Delivered" in response.content and b"Cancel this order" not in response.content
    order.refresh_from_db()
    assert order.shipped_at and order.delivered_at


def test_foreign_objects_are_hidden_and_mutations_cannot_cross_owners():
    buyer, other, item, foreign = customer(), customer("other"), product(), product("foreign")
    order = order_for(buyer, item)
    client = signed_in(other)
    for route in (
        reverse("orders:order_detail", args=[order.pk]),
        reverse("orders:checkout_detail", args=[order.checkout_id]),
    ):
        assert client.get(route).status_code == 404
    assert client.post(reverse("orders:cancel", args=[order.pk])).status_code == 404
    assert b"example shop" not in client.get(reverse("orders:history")).content
    line = add_to_cart(buyer, item.pk)
    assert client.post(reverse("orders:cart_quantity", args=[line.pk]), {"quantity": 2}).status_code == 404
    assert client.post(reverse("orders:cart_remove", args=[line.pk])).status_code == 404
    seller = signed_in(foreign.seller.user)
    assert str(order.pk) not in [str(o.pk) for o in seller.get(reverse("orders:seller_orders")).context["page_obj"]]
    assert seller.post(reverse("orders:ship", args=[order.pk])).status_code == 404
    order.refresh_from_db()
    assert order.status == "paid" and not Refund.objects.exists()


@pytest.mark.parametrize(
    "name,role",
    [
        ("cart", "customer"),
        ("review", "customer"),
        ("history", "customer"),
        ("seller_orders", "seller"),
        ("operator_orders", "operator"),
    ],
)
def test_pages_require_the_expected_role(name, role):
    people = {
        "customer": customer(),
        "seller": product().seller.user,
        "operator": User.objects.create_user(username="operator", role="operator"),
    }
    route = reverse("orders:" + name)
    assert Client().get(route).status_code == 302
    for actual, user in people.items():
        response = signed_in(user).get(route)
        assert response.status_code == (200 if actual == role else 403)


@pytest.mark.parametrize("name", ["cart_add", "cart_quantity", "cart_remove", "cancel", "ship", "deliver"])
def test_mutations_are_post_only_and_need_csrf(name):
    buyer, item = customer(), product()
    actor = (
        item.seller.user
        if name == "ship"
        else User.objects.create_user(username="operator", role="operator")
        if name == "deliver"
        else buyer
    )
    client = signed_in(actor)
    route = reverse("orders:" + name, args=[item.pk])
    assert client.get(route).status_code == 405
    csrf = Client(enforce_csrf_checks=True)
    csrf.force_login(actor)
    assert csrf.post(route, {"quantity": 1}).status_code == 403


def test_review_payment_needs_csrf_and_anonymous_htmx_gets_login_redirect():
    buyer = customer()
    client = Client(enforce_csrf_checks=True)
    client.force_login(buyer)
    assert client.post(reverse("orders:review"), {}).status_code == 403
    response = Client().post(reverse("orders:cart_add", args=[1]), HTTP_HX_REQUEST="true")
    assert response.status_code == 200 and response.headers["HX-Redirect"] == reverse("accounts:login")


def test_role_navigation_adds_only_relevant_checkout_links():
    buyer, item = customer(), product()
    assert b">Cart</a>" in signed_in(buyer).get(reverse("orders:cart")).content
    assert b">Orders</a>" in signed_in(buyer).get(reverse("orders:history")).content
    seller = signed_in(item.seller.user).get(reverse("accounts:seller_home"))
    assert b"My orders" in seller.content and b">Cart</a>" not in seller.content
    Seller.objects.filter(pk=item.seller_id).update(status="suspended")
    client = signed_in(item.seller.user)
    assert client.get(reverse("orders:seller_orders")).status_code == 302
    assert client.post(reverse("orders:ship", args=[1])).status_code == 403


def test_operator_audit_labels_and_resolves_order_shop():
    from orders.services import change_order_status

    buyer, item = customer(), product()
    order = order_for(buyer, item)
    change_order_status(item.seller.user, order.pk, "ship")
    operator = User.objects.create_user(username="operator", role="operator")
    response = signed_in(operator).get(reverse("accounts:operator_audit"))
    assert response.status_code == 200 and b"Shipped" in response.content and b"example shop" in response.content
    assert b"order.shipped" not in response.content.split(b'<div class="surface-card optable')[1]
    assert b"Shop unavailable" not in response.content


def test_order_filters_find_full_data_actions_without_widening_seller_scope():
    buyer, item, foreign = customer(), product(), product("foreign")
    own = order_for(buyer, item)
    other = order_for(buyer, foreign)
    seller = signed_in(item.seller.user)
    response = seller.get(reverse("orders:seller_orders"), {"order_id": own.pk, "status": "paid"})
    assert list(response.context["page_obj"]) == [own]
    assert str(own.pk) in response.context["query"]
    response = seller.get(reverse("orders:seller_orders"), {"order_id": other.pk})
    assert list(response.context["page_obj"]) == []
    operator = User.objects.create_user(username="operator", role="operator")
    response = signed_in(operator).get(reverse("orders:operator_orders"), {"order_id": other.pk, "status": "paid"})
    assert list(response.context["page_obj"]) == [other]


@pytest.mark.parametrize(
    "query",
    [
        {"order_id": "1; DROP TABLE orders_order"},
        {"order_id": "9223372036854775808"},
        {"order_id": "0"},
        {"status": "paid' OR 1=1 --"},
    ],
)
def test_invalid_order_filters_are_errors_and_never_broaden_the_list(query):
    buyer, item = customer(), product()
    order_for(buyer, item)
    response = signed_in(item.seller.user).get(reverse("orders:seller_orders"), query)
    assert response.status_code == 200 and response.context["filters"].errors
    assert not list(response.context["page_obj"]) and Order.objects.count() == 1


def test_the_purchase_page_shows_a_cancelled_orders_refund_and_no_arrival_estimate():
    buyer = customer()
    order = order_for(buyer, product("lamp"))
    client = signed_in(buyer)
    assert client.post(reverse("orders:cancel", args=[order.pk]), {"reason": "Changed my mind"}).status_code == 302
    body = client.get(reverse("orders:checkout_detail", args=[order.checkout_id])).content.decode()
    refund = Refund.objects.get(order=order)
    assert f"Refunded S${refund.amount}" in body
    assert "Estimated arrival" not in body
