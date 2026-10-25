"""Product updates use the same real owner/runtime boundary as seller decisions."""
import os

import pytest
from account_helpers import make_seller, runtime_connection
from django.db import connection, transaction
from psycopg import errors

from accounts.audit import set_audit_context
from accounts.models import AuditLog
from catalogue.models import Category, Product

pytestmark = pytest.mark.django_db(transaction=True)


def product_audits():
    return AuditLog.objects.filter(table_name="catalogue_product")


def product():
    seller = make_seller()
    category = Category.objects.create(slug="test", name_en="Test", name_pt="Test")
    return Product.objects.create(seller=seller, category=category, name="Test", price="10.00",
                                  freight="1.00", stock=10, lead_time_days=3)


def test_product_updates_record_actor_reason_and_only_watched_fields():
    item = product()
    with transaction.atomic():
        set_audit_context(item.seller.user_id, "Seller saved product")
        Product.objects.filter(pk=item.pk).update(price="12.00", stock=4)
    row = product_audits().get(table_name="catalogue_product")
    assert row.actor_id == item.seller.user_id and row.reason == "Seller saved product"
    assert row.before["price"] == 10 and row.after["price"] == 12
    assert row.before["stock"] == 10 and row.after["stock"] == 4
    Product.objects.filter(pk=item.pk).update(name="New name")
    assert product_audits().count() == 1
    Product.objects.filter(pk=item.pk).update(active=False)
    row = product_audits().latest("id")
    assert row.action == "product.deactivate" and row.actor_id is None and row.reason is None


def test_product_audit_rolls_back_with_the_product():
    item = product()
    with pytest.raises(ValueError):
        with transaction.atomic():
            set_audit_context(item.seller.user_id, "Cancelled save")
            Product.objects.filter(pk=item.pk).update(stock=1)
            raise ValueError("rollback")
    item.refresh_from_db()
    assert item.stock == 10 and not product_audits().exists()


def test_runtime_product_trigger_works_and_cannot_be_tampered_with():
    item = product()
    with runtime_connection() as runtime:
        with runtime.transaction():
            runtime.execute("SELECT set_config('mercer.actor_id', %s, true), set_config('mercer.audit_reason', %s, true)",
                            [str(item.seller.user_id), "Runtime product edit"])
            runtime.execute("UPDATE catalogue_product SET stock = %s WHERE id = %s", [3, item.pk])
        assert runtime.execute("SELECT actor_id, reason FROM audit_log WHERE table_name = %s",
                               ["catalogue_product"]).fetchall() == [(item.seller.user_id, "Runtime product edit")]
        for statement in (
            "ALTER TABLE catalogue_product DISABLE TRIGGER product_update_audit",
            "ALTER FUNCTION public.audit_product_update() SET search_path = pg_temp, public",
            "CREATE OR REPLACE FUNCTION public.audit_product_update() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END $$",
            "INSERT INTO audit_log (table_name,row_id,action,created_at) VALUES ('catalogue_product','1','forged',now())",
        ):
            with pytest.raises(errors.InsufficientPrivilege):
                runtime.execute(statement)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_get_userbyid(proowner), prosecdef, proconfig, has_function_privilege(%s, oid, 'EXECUTE') "
                       "FROM pg_proc WHERE oid='public.audit_product_update()'::regprocedure", [os.environ["POSTGRES_RUNTIME_USER"]])
        assert cursor.fetchone() == (os.environ["POSTGRES_USER"], True, ["search_path=public, pg_temp"], False)


def test_audit_context_injection_remains_a_literal_reason():
    item = product()
    reason = "'; DELETE FROM catalogue_product; --"
    with transaction.atomic():
        set_audit_context(item.seller.user_id, reason)
        Product.objects.filter(pk=item.pk).update(stock=2)
    assert product_audits().get().reason == reason and Product.objects.filter(pk=item.pk).exists()


def test_shared_mongo_client_is_reused_without_losing_test_routing(mongo_db):
    from config import mongo
    with mongo.client() as first:
        first.admin.command("ping")
    with mongo.client() as second:
        assert first is second
        assert mongo.database_name() == mongo_db.name
        assert second[mongo.database_name()].product_specs.count_documents({}) == 0
