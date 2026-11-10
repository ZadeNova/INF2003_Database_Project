"""The purchasable_product view lists its columns explicitly and keeps its options and privileges (catalogue 0005)."""

import pytest
from account_helpers import runtime_connection
from django.core.management import call_command
from django.db import connection

from catalogue.migration_sql import PRODUCT_COLUMNS

pytestmark = pytest.mark.django_db(transaction=True)


def columns(table):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position",
            [table],
        )
        return [row[0] for row in cursor.fetchall()]


def options():
    with connection.cursor() as cursor:
        cursor.execute("SELECT reloptions FROM pg_class WHERE relname = 'purchasable_product'")
        return cursor.fetchone()[0]


def test_the_view_exposes_exactly_the_listed_columns_and_all_product_columns_are_decided():
    assert columns("purchasable_product") == PRODUCT_COLUMNS.split(", ")
    # A new product column fails here until it is added to the view's list (or this comparison is changed on purpose).
    assert columns("catalogue_product") == PRODUCT_COLUMNS.split(", ")


def test_the_view_is_security_invoker_and_the_runtime_role_can_read_it():
    assert options() == ["security_invoker=true"]
    with runtime_connection() as runtime:
        assert runtime.execute("SELECT count(*) FROM purchasable_product").fetchone()[0] == 0


def test_the_migration_reverses_and_reapplies_keeping_options_and_privileges():
    call_command("migrate", "catalogue", "0004", verbosity=0)
    try:
        assert options() == ["security_invoker=true"]
        with runtime_connection() as runtime:
            runtime.execute("SELECT id FROM purchasable_product")
    finally:
        call_command("migrate", verbosity=0)
    assert columns("purchasable_product") == PRODUCT_COLUMNS.split(", ")
    with runtime_connection() as runtime:
        runtime.execute("SELECT id FROM purchasable_product")
