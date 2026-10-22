"""Small builders for the accounts tests: one user per role, sellers in any status, real database rows."""
import os

import psycopg
from django.contrib.auth import get_user_model
from django.db import connection

from accounts.models import CustomerProfile, Seller

PASSWORD = "Str0ngPass!2026"


def make_customer(username="customer"):
    user = get_user_model().objects.create_user(username=username, password=PASSWORD)
    CustomerProfile.objects.create(user=user)
    return user


def make_seller(username="seller", status="approved", shop_name=None):
    # Created directly in the wanted status: the status trigger checks updates, not inserts.
    user = get_user_model().objects.create_user(username=username, password=PASSWORD, role="seller")
    return Seller.objects.create(user=user, status=status, shop_name=shop_name or f"{username} shop",
                                 city="sao paulo", state="SP", zip_prefix="01310")


def make_operator(username="operator"):
    return get_user_model().objects.create_user(username=username, password=PASSWORD, role="operator")


def runtime_connection():
    """A real connection as the web service's runtime role, to the database the tests are using."""
    return psycopg.connect(dbname=connection.settings_dict["NAME"], host=os.environ["POSTGRES_HOST"],
                           port=os.environ["POSTGRES_PORT"], user=os.environ["POSTGRES_RUNTIME_USER"],
                           password=os.environ["POSTGRES_RUNTIME_PASSWORD"], autocommit=True)
