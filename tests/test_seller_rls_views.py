"""The real seller views and the shipping service under the row-level policies (docs/plans/seller-rls.md), as the runtime role.

test_seller_rls.py proves the policies with raw SQL. These tests prove the application still works under them, that the
setting is applied only while a seller-centre view runs, and that it never survives a request.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from checkout_helpers import customer, paid_order, product
from django.db import DatabaseError, connection
from django.http import Http404
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts import rowsecurity
from orders.models import Order, OrderLine
from orders.services import change_order_status

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def world():
    buyer = customer()
    first, second = product("first"), product("second")
    _, first_order = paid_order(buyer, first)
    _, second_order = paid_order(buyer, second)
    for order, item in ((first_order, first), (second_order, second)):
        OrderLine.objects.create(order=order, seller=item.seller, product=item, quantity=1, unit_price=10, freight=2)
    client = Client()
    client.force_login(first.seller.user)
    return {
        "buyer": buyer,
        "first": first,
        "second": second,
        "first_order": first_order,
        "second_order": second_order,
        "client": client,
    }


def current_setting():
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('mercer.seller_id', true)")
        return cursor.fetchone()[0]


# ----------------------------------------------------------------------------------------------- the real views
def test_the_seller_pages_work_under_the_policies(world, runtime_role):
    with runtime_role():
        orders = world["client"].get(reverse("orders:seller_orders"))
        assert orders.status_code == 200
        assert [o.pk for o in orders.context["page_obj"]] == [world["first_order"].pk]
        assert world["client"].get(reverse("catalogue:seller_products")).status_code == 200
        assert world["client"].get(reverse("accounts:seller_home")).status_code == 200
        assert world["client"].get(reverse("accounts:seller_status")).status_code == 200


def test_the_database_alone_keeps_a_seller_to_its_own_orders_when_the_view_forgets_its_filter(
    world, runtime_role, monkeypatch
):
    """The point of row-level security: the application's `filter(seller=...)` is removed and the page still shows only
    this seller's orders."""
    monkeypatch.setattr(
        "orders.views.Order", SimpleNamespace(objects=SimpleNamespace(filter=lambda **kwargs: Order.objects.all()))
    )
    with runtime_role():
        page = world["client"].get(reverse("orders:seller_orders")).context["page_obj"]
        assert [o.pk for o in page] == [world["first_order"].pk]


def test_a_seller_ships_its_own_order_through_the_real_view_and_not_another_sellers(world, runtime_role):
    with runtime_role():
        shipped = world["client"].post(reverse("orders:ship", args=[world["first_order"].pk]))
        refused = world["client"].post(reverse("orders:ship", args=[world["second_order"].pk]))
    assert shipped.status_code == 302 and refused.status_code == 404
    assert Order.objects.get(pk=world["first_order"].pk).status == "shipped"
    assert Order.objects.get(pk=world["second_order"].pk).status == "paid"


def test_a_customer_still_cancels_an_order_under_the_runtime_role(world, runtime_role):
    """The customer path never sets the setting: the lock function, the money checks and the refund behave as before."""
    with runtime_role():
        change_order_status(world["buyer"], world["first_order"].pk, "cancel")
    assert Order.objects.get(pk=world["first_order"].pk).status == "cancelled"


def test_the_lock_function_refuses_an_order_that_does_not_exist(world, runtime_role):
    with runtime_role(), pytest.raises(Http404):
        change_order_status(world["buyer"], 10**9, "cancel")


# ----------------------------------------------------------------------------------------------- the setting's life
def test_the_setting_exists_only_while_a_seller_view_runs(world, runtime_role):
    with runtime_role():
        with CaptureQueriesContext(connection) as seller_page:
            world["client"].get(reverse("orders:seller_orders"))
        assert any("mercer.seller_id" in q["sql"] for q in seller_page)
        assert current_setting() in ("", None)  # released when the request ended
        with CaptureQueriesContext(connection) as public_page:
            world["client"].get(reverse("catalogue:product_list"))
        assert not any("mercer.seller_id" in q["sql"] for q in public_page)  # public pages are never confined


def test_the_setting_is_released_when_the_view_fails(world, runtime_role):
    with runtime_role():
        missing = world["client"].get(reverse("catalogue:product_edit", args=[10**9]))
        assert missing.status_code == 404
        assert current_setting() in ("", None)
        forbidden = Client()
        forbidden.force_login(world["buyer"])  # a customer is refused before any seller is found
        assert forbidden.get(reverse("orders:seller_orders")).status_code == 403
        assert current_setting() in ("", None)


def test_a_failed_release_drops_the_connection_instead_of_leaving_the_setting(monkeypatch):
    fake = MagicMock()
    fake.cursor.side_effect = DatabaseError("the database has gone")
    monkeypatch.setattr(rowsecurity, "connection", fake)
    rowsecurity.release()  # must not raise: the request's own outcome is not replaced by this failure
    fake.close.assert_called_once_with()
