"""Step 3 of docs/plans/seller-rls.md: every seller-centre view is confined, and shipping races a cancel under the policies.

The sweep fails when a new view is built on AnySellerMixin without being listed here, so a seller page cannot quietly be
added outside the test. The concurrency tests run as the runtime role in separate connections, because the owner would
bypass the policies and a single connection cannot show a lock wait.
"""

import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from account_helpers import make_seller
from checkout_helpers import customer, paid_order, product
from django.db import connection, connections, transaction
from django.test import Client
from django.urls import get_resolver, reverse
from django.utils import timezone

from accounts import rowsecurity
from accounts.audit import set_audit_context
from accounts.mixins import AnySellerMixin
from orders.models import Checkout, Order, OrderLine, Payment, Refund
from orders.services import CheckoutError, change_order_status

pytestmark = pytest.mark.django_db(transaction=True)


def current_setting():
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('mercer.seller_id', true)")
        return cursor.fetchone()[0]


def seller_views():
    """Every class that confines its session to a seller, found by walking the subclasses once all URLs are loaded."""
    get_resolver().url_patterns  # noqa: B018 - importing the URL configuration imports every view module
    found, pending = set(), [AnySellerMixin]
    while pending:
        for subclass in pending.pop().__subclasses__():
            if subclass.__name__ not in found:
                if not subclass.__name__.endswith("Mixin") and not subclass.__module__.startswith("test"):  # a page
                    found.add(subclass.__name__)
                pending.append(subclass)
    return found


# Class name -> (method, URL name, arguments, key of the world dictionary that supplies the argument or None).
SWEEP = {
    "SellerHomeView": ("get", "accounts:seller_home", None),
    "SellerStatusView": ("get", "accounts:seller_status", None),
    "SellerOrdersView": ("get", "orders:seller_orders", None),
    "ShipView": ("post", "orders:ship", "order"),
    "InsightsView": ("get", "activity:insights", None),
    "SellerReviewsView": ("get", "reviews:seller_reviews", None),
    "SellerProductListView": ("get", "catalogue:seller_products", None),
    "SellerProductEditView": ("get", "catalogue:product_edit", "product"),
    "SellerProductDeactivateView": ("post", "catalogue:product_deactivate", "product"),
}


def test_the_sweep_lists_every_seller_view():
    assert seller_views() == set(SWEEP)


@pytest.fixture
def shop():
    item = product("sweep")
    _, order = paid_order_for(item)
    client = Client()
    client.force_login(item.seller.user)
    return {"item": item, "seller": item.seller, "order": order, "client": client}


def paid_order_for(item):
    checkout, order = paid_order(customer("sweep-buyer"), item)
    OrderLine.objects.create(order=order, seller=item.seller, product=item, quantity=1, unit_price=10, freight=2)
    return checkout, order


@pytest.mark.parametrize("name", sorted(SWEEP))
def test_every_seller_view_runs_confined_to_its_seller_and_releases(name, shop, runtime_role, monkeypatch):
    method, url_name, argument = SWEEP[name]
    seen = []
    release = rowsecurity.release

    def spy():
        seen.append(current_setting())  # the last moment of the view, before the setting is cleared
        release()

    monkeypatch.setattr(rowsecurity, "release", spy)
    args = [] if argument is None else [shop["order"].pk if argument == "order" else shop["item"].pk]
    with runtime_role():
        response = getattr(shop["client"], method)(reverse(url_name, args=args))
        assert response.status_code < 400, f"{name} answered {response.status_code}"
        assert seen == [str(shop["seller"].pk)], f"{name} was not confined to its seller while it ran"
        assert current_setting() in ("", None)


def test_a_seller_awaiting_approval_is_confined_too_and_released(runtime_role, monkeypatch):
    waiting = make_seller("waiting", status="pending")
    client = Client()
    client.force_login(waiting.user)
    seen = []
    release = rowsecurity.release
    monkeypatch.setattr(rowsecurity, "release", lambda: (seen.append(current_setting()), release()))
    with runtime_role():
        response = client.get(reverse("orders:seller_orders"))  # sent on to the status page
        assert response.status_code == 302
        assert seen == [str(waiting.pk)] and current_setting() in ("", None)


# ----------------------------------------------------------------------------------------------- shipping against a cancel
def as_runtime_in_this_thread():
    """A thread opens its own Django connection from the settings (the owner); point it at the runtime role."""
    connections.close_all()
    connection.settings_dict = {
        **connection.settings_dict,
        "USER": os.environ["POSTGRES_RUNTIME_USER"],
        "PASSWORD": os.environ["POSTGRES_RUNTIME_PASSWORD"],
    }
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user")
        assert cursor.fetchone()[0] == os.environ["POSTGRES_RUNTIME_USER"]


def one_checkout_of_two_sellers():
    """One basket, two sellers, two paid orders sharing the checkout that every cancel and shipment locks."""
    buyer, first, second = customer("race-buyer"), product("race-first"), product("race-second")
    now = timezone.now()
    with transaction.atomic():
        set_audit_context()
        checkout = Checkout.objects.create(customer=buyer, total=24, placed_at=now)
        orders = [
            Order.objects.create(
                checkout=checkout,
                seller=item.seller,
                status="paid",
                items=10,
                freight=2,
                total=12,
                placed_at=now,
                estimated_delivery=now,
            )
            for item in (first, second)
        ]
        Payment.objects.create(checkout=checkout, sequence=1, method="boleto", instalments=1, amount=24)
    for order, item in zip(orders, (first, second), strict=True):
        OrderLine.objects.create(order=order, seller=item.seller, product=item, quantity=1, unit_price=10, freight=2)
    return buyer, (first, second), orders


def ship(item, order):
    as_runtime_in_this_thread()
    try:
        rowsecurity.confine_to_seller(item.seller.pk)
        try:
            return change_order_status(item.seller.user, order.pk, "ship")
        finally:
            rowsecurity.release()
    finally:
        connections.close_all()


def cancel(buyer, order):
    as_runtime_in_this_thread()
    try:
        return change_order_status(buyer, order.pk, "cancel")
    finally:
        connections.close_all()


def run_together(first, second):
    barrier = threading.Barrier(2)

    def start(action):
        barrier.wait(timeout=30)
        try:
            return ("done", action())
        except CheckoutError as error:
            return ("refused", str(error))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(start, first), pool.submit(start, second)]
        return [future.result(timeout=60) for future in futures]


@pytest.mark.parametrize("run", range(5))
def test_a_seller_ships_one_order_while_the_customer_cancels_its_sibling(run):
    buyer, (first, second), (first_order, second_order) = one_checkout_of_two_sellers()
    results = run_together(lambda: ship(first, first_order), lambda: cancel(buyer, second_order))
    assert [kind for kind, _ in results] == ["done", "done"]
    assert Order.objects.get(pk=first_order.pk).status == "shipped"
    assert Order.objects.get(pk=second_order.pk).status == "cancelled"
    assert (
        Refund.objects.filter(order=second_order).count() == 1 and not Refund.objects.filter(order=first_order).exists()
    )


@pytest.mark.parametrize("run", range(5))
def test_a_seller_ships_while_the_customer_cancels_the_same_order_and_exactly_one_wins(run):
    buyer, (first, _), (order, _) = one_checkout_of_two_sellers()
    results = run_together(lambda: ship(first, order), lambda: cancel(buyer, order))
    assert sorted(kind for kind, _ in results) == ["done", "refused"]
    refused = next(detail for kind, detail in results if kind == "refused")
    assert "already changed" in refused
    status = Order.objects.get(pk=order.pk).status
    refunds = Refund.objects.filter(order=order).count()
    assert (status, refunds) in {("shipped", 0), ("cancelled", 1)}
