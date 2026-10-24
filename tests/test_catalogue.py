"""Phase 1A reads use PostgreSQL visibility and MongoDB specifications."""
import os
from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Count, Max, Q
from django.test import Client

from accounts.models import Seller
from catalogue.models import Product
from orders.models import Order

pytestmark=pytest.mark.django_db(transaction=True)


def visible():
    return Product.objects.filter(active=True,taken_down=False,seller__status="approved").order_by("id").first()


def test_minimum_product_list_and_detail_use_their_owning_stores(imported,mongo_db):
    product=visible()
    mongo_db.product_specs.update_one({"_id":product.pk},{"$set":{"description":"Specification lives in MongoDB","attributes":{"material":"cotton"},"price":"0.01","stock":999999,"name":"WRONG STORE"}})
    client=Client()
    listing=client.get("/products/")
    detail=client.get(f"/products/{product.pk}/")
    assert listing.status_code == detail.status_code == 200
    body=detail.content.decode()
    assert product.name in body and product.display_price in body
    assert "Specification lives in MongoDB" in body and "cotton" in body
    assert "WRONG STORE" not in body and "999999" not in body
    assert "generated" in body.lower()
    assert "model-viewer" not in body
    assert client.head(f"/products/{product.pk}/").status_code == 200
    assert client.post(f"/products/{product.pk}/").status_code == 405


@pytest.mark.parametrize("change",[{"active":False},{"taken_down":True}])
def test_hidden_products_are_inaccessible(imported,change):
    product=visible()
    Product.objects.filter(pk=product.pk).update(**change)
    assert Client().get(f"/products/{product.pk}/").status_code == 404


def test_suspended_sellers_products_are_inaccessible(imported):
    product=visible()
    Seller.objects.filter(pk=product.seller_id).update(status="suspended")
    assert Client().get(f"/products/{product.pk}/").status_code == 404


def test_missing_spec_renders_an_explicit_unavailable_state(imported,mongo_db):
    product=visible()
    mongo_db.product_specs.delete_one({"_id":product.pk})
    response=Client().get(f"/products/{product.pk}/")
    assert response.status_code == 200 and "Specifications are temporarily unavailable" in response.content.decode()


def test_real_mongo_outage_is_a_sanitized_retryable_503(imported,monkeypatch):
    product=visible()
    monkeypatch.setenv("MONGO_HOST","127.0.0.1")
    monkeypatch.setenv("MONGO_PORT","1")
    response=Client().get(f"/products/{product.pk}/")
    assert response.status_code == 503 and response["Retry-After"] == "5"
    assert "127.0.0.1" not in response.content.decode()


def test_hostile_page_and_id_parameters_are_not_queries(imported):
    client=Client()
    before=Product.objects.count()
    assert client.get("/products/?page=1%3BDELETE+FROM+catalogue_product").status_code == 200
    assert client.get("/products/%7B%22%24ne%22:null%7D/").status_code == 404
    assert Product.objects.count() == before


def test_future_routes_are_404_even_for_authenticated_roles(imported):
    for role in ("customer","seller","operator"):
        user=get_user_model().objects.filter(role=role).first()
        if user is None:
            user=get_user_model().objects.create_user(username="operator",role="operator")
        client=Client()
        client.force_login(user)
        for route in ("/analytics/","/dashboard/","/products/manage/"):
            assert client.get(route).status_code == 404


def test_demo_accounts_use_only_environment_passwords_and_are_idempotent(imported):
    from catalogue.management.commands.seed_demo import MEMBERS
    # Force the demo's two selected products to need relisting on first seed.
    Product.objects.update(active=False)
    call_command("seed_demo",stdout=StringIO())
    before=get_user_model().objects.count()
    seller=Seller.objects.get(user__username="demo-seller")
    adjusted=seller.products.exclude(demo_adjustment="")
    labels=dict(adjusted.values_list("pk","demo_adjustment"))
    assert all("relisted for demo visibility" in label for label in labels.values())
    assert adjusted.filter(active=True).count() == 2
    call_command("seed_demo",stdout=StringIO())
    assert dict(adjusted.values_list("pk","demo_adjustment")) == labels
    assert get_user_model().objects.count() == before
    for name in ["demo-"+x for x in MEMBERS]+["demo-seller","demo-operator"]:
        user=get_user_model().objects.get(username=name)
        password=os.environ["DEMO_"+user.role.upper()+"_PASSWORD"]
        if not user.check_password(password):
            pytest.fail("Demo password did not match its environment value (secret omitted)",pytrace=False)
        client=Client()
        response=client.post("/login/",{"username":name,"password":password})
        assert response.status_code == 302 and client.session["_auth_user_id"] == str(user.pk)
    seller=Seller.objects.get(user__username="demo-seller")
    assert seller.olist_seller_id and seller.orders.exists()
    assert seller.products.filter(stock=0,demo_adjustment__contains="wishlist").count() == 1
    assert seller.products.filter(stock=1,lead_time_days=30,demo_adjustment__contains="dashboard").count() == 1
    flagged = seller.products.get(stock=1,lead_time_days=30,demo_adjustment__contains="dashboard")
    body=Client().get(f"/products/{flagged.pk}/").content.decode()
    assert body.count("Demo adjustment:") == 1
    assert "relisted for demo visibility" in body
    latest = Order.objects.filter(checkout__olist_order_id__isnull=False).aggregate(latest=Max("placed_at"))["latest"]
    assert flagged.order_lines.filter(order__placed_at__gte=latest-timedelta(days=28)).exclude(order__status="cancelled").exists()
    assert Order.objects.count() == imported["output_counts"]["orders"]


@pytest.mark.parametrize("variable",["DEMO_CUSTOMER_PASSWORD","DEMO_SELLER_PASSWORD","DEMO_OPERATOR_PASSWORD"])
def test_demo_passwords_have_no_fallback(imported,monkeypatch,variable):
    monkeypatch.delenv(variable,raising=False)
    with pytest.raises(CommandError,match="no fallback passwords"):
        call_command("seed_demo",stdout=StringIO())
    assert not get_user_model().objects.filter(username__startswith="demo-").exists()


def test_seed_demo_repairs_a_previously_seeded_relisting_label_from_imported_history(imported):
    eligible = (Seller.objects.annotate(product_count=Count("products"))
                .filter(status="approved",product_count__gte=2).values("pk"))
    latest = Order.objects.aggregate(latest=Max("placed_at"))["latest"]
    product = (Product.objects.filter(seller_id__in=eligible)
               .annotate(imported_orders=Count("order_lines__order",distinct=True,
                         filter=Q(order_lines__order__checkout__olist_order_id__isnull=False)))
               .filter(imported_orders=1,order_lines__order__placed_at__gte=latest-timedelta(days=27))
               .exclude(order_lines__order__status="cancelled").order_by("id").first())
    assert product is not None
    seller = product.seller
    seller.user.username = "demo-seller"
    seller.user.save(update_fields=["username"])
    other = seller.products.exclude(pk=product.pk).first()
    seller.products.exclude(pk__in=[product.pk,other.pk]).update(taken_down=True)
    # This is the state left by the older seeder: visible, with no relisting label.
    product.active = True
    product.demo_adjustment = "Demo adjustment: seeded before relisting labels"
    product.save(update_fields=["active","demo_adjustment"])
    call_command("seed_demo",stdout=StringIO())
    product.refresh_from_db()
    assert product.active and product.demo_adjustment.count("relisted for demo visibility") == 1
    label = product.demo_adjustment
    call_command("seed_demo",stdout=StringIO())
    product.refresh_from_db()
    assert product.demo_adjustment == label


def test_seed_demo_refuses_to_promote_an_existing_customer(imported):
    get_user_model().objects.create_user(username="demo-operator",role="customer")
    before=get_user_model().objects.count()
    with pytest.raises(CommandError,match="belongs to another role"):
        call_command("seed_demo",stdout=StringIO())
    assert get_user_model().objects.count() == before
    assert get_user_model().objects.get(username="demo-operator").role == "customer"


def test_seed_demo_adds_a_pending_applicant_and_keeps_decided_statuses(imported):
    from accounts.audit import change_seller_status
    call_command("seed_demo",stdout=StringIO())
    applicant=Seller.objects.select_related("user").get(user__username="demo-applicant")
    assert applicant.status == "pending" and applicant.has_generated_content and "generated" in applicant.shop_name
    assert applicant.olist_seller_id is None and applicant.user.role == "seller"
    if not applicant.user.check_password(os.environ["DEMO_SELLER_PASSWORD"]):
        pytest.fail("Applicant password did not match DEMO_SELLER_PASSWORD (secret omitted)",pytrace=False)
    client=Client()
    assert client.post("/login/",{"username":"demo-applicant","password":os.environ["DEMO_SELLER_PASSWORD"]}).url == "/seller/status/"
    demo_seller=Seller.objects.get(user__username="demo-seller")
    labels=dict(demo_seller.products.exclude(demo_adjustment="").values_list("pk","demo_adjustment"))
    operator=get_user_model().objects.get(username="demo-operator")
    change_seller_status(applicant.pk,"approve",operator,"Demo approval")
    change_seller_status(demo_seller.pk,"suspend",operator,"Demo suspension")
    users=get_user_model().objects.count()
    call_command("seed_demo",stdout=StringIO())
    assert Seller.objects.get(pk=applicant.pk).status == "approved"
    assert Seller.objects.get(pk=demo_seller.pk).status == "suspended"
    assert dict(demo_seller.products.exclude(demo_adjustment="").values_list("pk","demo_adjustment")) == labels
    assert get_user_model().objects.count() == users


def test_seed_demo_writes_system_audit_rows_even_inside_a_callers_actor_context(imported):
    # seed_demo resets the audit context itself, so a caller's actor and reason never leak into its product changes.
    from django.db import transaction

    from accounts.audit import set_audit_context
    from accounts.models import AuditLog
    operator=get_user_model().objects.create_user(username="ctx-operator",role="operator")
    before=set(AuditLog.objects.filter(table_name="catalogue_product").values_list("pk",flat=True))
    with transaction.atomic():
        set_audit_context(operator.pk,"Caller context that must not leak")
        call_command("seed_demo",stdout=StringIO())
    rows=AuditLog.objects.filter(table_name="catalogue_product").exclude(pk__in=before)
    assert rows.exists()
    assert set(rows.values_list("actor_id","reason")) == {(None,None)}
