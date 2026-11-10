"""A MongoDB that is down or hung must cost one short wait, not every request; pages that only decorate with it still work."""

import os
import time

import pytest
from checkout_helpers import product
from django.test import Client
from django.urls import reverse
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from config import mongo

pytestmark = pytest.mark.django_db


def test_the_client_has_bounded_connection_and_selection_waits_and_an_operation_bound_only_when_asked():
    options = mongo.connection_options(environ=os.environ)
    assert options["connectTimeoutMS"] == 3000 and options["serverSelectionTimeoutMS"] == 3000
    assert "socketTimeoutMS" not in options  # the importer and offline tools run long operations on purpose
    web = mongo.connection_options(environ={**os.environ, "MONGO_SOCKET_TIMEOUT_MS": "10000"})
    assert web["socketTimeoutMS"] == 10000


def test_a_connection_failure_makes_the_next_calls_fail_fast_until_the_back_off_ends():
    refused = {**os.environ, "MONGO_PORT": "1"}
    with pytest.raises(ConnectionFailure), mongo.client(environ=refused):
        raise ConnectionFailure("the server went away")  # what a request sees when MongoDB is unreachable
    started = time.monotonic()
    for _ in range(20):
        with pytest.raises(ServerSelectionTimeoutError), mongo.client(environ=refused):
            raise AssertionError("no operation may be attempted during the back-off")
    assert time.monotonic() - started < 0.5  # not 3 s x 20
    with mongo.client() as healthy:  # a different client (the working MongoDB) is unaffected
        assert healthy.admin.command("ping")["ok"] == 1
    mongo._down_until.clear()  # the back-off ends
    with mongo.client(environ=refused):
        pass  # the client is handed out again (it would try to connect on first use)


def test_an_error_that_is_not_a_lost_connection_does_not_start_a_back_off():
    with pytest.raises(ValueError), mongo.client():
        raise ValueError("a bug, not an outage")
    assert not mongo._down_until


@pytest.fixture
def mongo_down(monkeypatch):
    """Point the application at a MongoDB that refuses connections, with the back-off already running (no 3 s wait)."""
    monkeypatch.setenv("MONGO_PORT", "1")
    with pytest.raises(ConnectionFailure), mongo.client():
        raise ConnectionFailure("down")
    yield
    mongo._down_until.clear()


def test_the_shop_listing_and_a_shop_page_still_work_without_mongodb(mongo_down):
    item = product("lamp")
    client = Client()
    listing = client.get("/products/")
    assert listing.status_code == 200 and b"lamp" in listing.content  # icon cards instead of photos
    shop = client.get(reverse("catalogue:seller_shop", args=[item.seller.pk]))
    assert shop.status_code == 200 and b"lamp" in shop.content
    assert b"Bayesian shop rating" not in shop.content  # the rating comes from MongoDB, so the line is left out


def test_the_wishlist_still_works_without_mongodb(mongo_down):
    from checkout_helpers import customer

    from wishlist.models import WishlistItem

    buyer, item = customer(), product("teapot")
    WishlistItem.objects.create(customer=buyer, product=item)
    client = Client()
    client.force_login(buyer)
    response = client.get(reverse("wishlist:list"))
    assert response.status_code == 200 and b"teapot" in response.content  # an icon card instead of the photo
