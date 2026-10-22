"""Customer registration with an optional location, and atomic seller applications."""
import pytest
from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.test import Client

from accounts.models import CustomerProfile, Seller
from account_helpers import PASSWORD, make_customer

pytestmark = pytest.mark.django_db

APPLICATION = {"username": "new-shop", "shop_name": "New Shop", "city": "campinas", "state": "sp",
               "zip_prefix": "13010", "password1": PASSWORD, "password2": PASSWORD}


def test_registration_stores_an_optional_location():
    response = Client().post("/register/", {"username": "located", "password1": PASSWORD, "password2": PASSWORD,
                                            "zip_prefix": "01310", "city": " sao paulo ", "state": "sp"})
    assert response.status_code == 302
    profile = CustomerProfile.objects.get(user__username="located")
    assert (profile.zip_prefix, profile.city, profile.state) == ("01310", "sao paulo", "SP")


@pytest.mark.parametrize("field, value", [("zip_prefix", "1234"), ("zip_prefix", "12a45"), ("state", "S1"),
                                          ("state", "SPX")])
def test_registration_rejects_a_malformed_location(field, value):
    response = Client().post("/register/", {"username": "bad", "password1": PASSWORD, "password2": PASSWORD, field: value})
    assert response.status_code == 200
    assert not get_user_model().objects.filter(username="bad").exists()


def test_seller_application_creates_a_pending_seller_atomically():
    response = Client().post("/sell/apply/", APPLICATION)
    assert response.status_code == 302 and response.url == "/login/"
    seller = Seller.objects.select_related("user").get(user__username="new-shop")
    assert seller.user.role == "seller" and seller.status == "pending"
    assert (seller.shop_name, seller.city, seller.state, seller.zip_prefix) == ("New Shop", "campinas", "SP", "13010")
    assert seller.olist_seller_id is None and not seller.has_generated_content
    assert not CustomerProfile.objects.filter(user=seller.user).exists()
    client = Client()
    assert client.post("/login/", {"username": "new-shop", "password": PASSWORD}).url == "/seller/status/"
    assert "waiting for an operator" in client.get("/seller/status/").content.decode()


@pytest.mark.parametrize("missing", ["shop_name", "city", "state", "zip_prefix"])
def test_seller_application_requires_shop_and_location(missing):
    response = Client().post("/sell/apply/", {**APPLICATION, missing: ""})
    assert response.status_code == 200
    assert not get_user_model().objects.filter(username="new-shop").exists()


def test_seller_application_ignores_forged_role_status_and_staff_fields():
    forged = {**APPLICATION, "role": "operator", "status": "approved", "is_staff": "true", "is_superuser": "true",
              "olist_seller_id": "x" * 32, "has_generated_content": "true", "user": "1"}
    assert Client().post("/sell/apply/", forged).status_code == 302
    seller = Seller.objects.select_related("user").get(user__username="new-shop")
    assert seller.status == "pending" and seller.olist_seller_id is None and not seller.has_generated_content
    assert seller.user.role == "seller" and not seller.user.is_staff and not seller.user.is_superuser


def test_a_failed_seller_insert_rolls_back_the_new_user(monkeypatch):
    # The database is real; only the second insert is made to fail, to prove both share one transaction.
    def fail(*args, **kwargs):
        raise DatabaseError("simulated failure after the user insert")
    monkeypatch.setattr(Seller.objects, "create", fail)
    with pytest.raises(DatabaseError):
        Client().post("/sell/apply/", APPLICATION)
    assert not get_user_model().objects.filter(username="new-shop").exists()


@pytest.mark.parametrize("route", ["/register/", "/sell/apply/"])
def test_registration_forms_require_csrf(route):
    response = Client(enforce_csrf_checks=True).post(route, APPLICATION)
    assert response.status_code == 403 and not get_user_model().objects.exists()


@pytest.mark.parametrize("route", ["/register/", "/sell/apply/"])
def test_logged_in_users_are_sent_to_their_home_instead_of_registering(route):
    client = Client()
    client.force_login(make_customer())
    response = client.get(route)
    assert response.status_code == 302 and response.url == "/products/"


def test_hostile_shop_name_is_stored_as_text_and_escaped():
    payload = "<script>alert(1)</script>'); DROP TABLE accounts_seller; --"
    Client().post("/sell/apply/", {**APPLICATION, "shop_name": payload})
    seller = Seller.objects.get(user__username="new-shop")
    assert seller.shop_name == payload
    client = Client()
    client.force_login(seller.user)
    body = client.get("/seller/status/").content.decode()
    assert "<script>alert(1)</script>" not in body and "&lt;script&gt;" in body
