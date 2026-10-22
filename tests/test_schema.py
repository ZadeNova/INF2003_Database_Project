"""Database constraints on real PostgreSQL, including ported idempotency coverage."""
from datetime import datetime, timezone
from decimal import Decimal
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError

from accounts.models import CustomerProfile, Seller
from catalogue.models import Category, Product, PurchasableProduct
from orders.models import Checkout, Order, OrderLine, Payment, Refund

pytestmark = pytest.mark.django_db
NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)


@pytest.fixture
def graph():
    User = get_user_model()
    customer = User.objects.create_user(username="buyer")
    CustomerProfile.objects.create(user=customer)
    seller = Seller.objects.create(user=User.objects.create_user(username="seller", role="seller"), status="approved", shop_name="Example")
    category = Category.objects.create(slug="example", name_en="Example", name_pt="Exemplo")
    product = Product.objects.create(seller=seller, category=category, name="Example", price="10.00", freight="2.00", stock=2, lead_time_days=5)
    checkout = Checkout.objects.create(customer=customer, placed_at=NOW, total="12.00")
    order = Order.objects.create(checkout=checkout, seller=seller, status="paid", items="10.00", freight="2.00", total="12.00", placed_at=NOW, estimated_delivery=NOW)
    line = OrderLine.objects.create(order=order, seller=seller, product=product, quantity=1, unit_price="10.00", freight="2.00")
    payment = Payment.objects.create(checkout=checkout, sequence=1, method="credit_card", instalments=1, amount="12.00")
    return customer, seller, product, checkout, order, line, payment


@pytest.mark.parametrize("model_index,field,value", [
    (0, "role", "intruder"), (1, "status", "invalid"), (2, "price", "-0.01"), (2, "price", "0"),
    (2, "freight", "-0.01"), (2, "stock", -1), (2, "lead_time_days", -1),
    (4, "status", "unknown"), (4, "total", "-1"), (5, "quantity", 0),
    (6, "method", "not_defined"), (6, "instalments", 0), (6, "amount", "-1"),
])
def test_checks_reject_invalid_values(graph, model_index, field, value):
    obj = graph[model_index]
    with pytest.raises(IntegrityError), transaction.atomic():
        type(obj).objects.filter(pk=obj.pk).update(**{field: value})


def test_bigint_identity_keys_and_payment_has_no_status(graph):
    with connection.cursor() as cursor:
        cursor.execute("SELECT data_type, is_identity FROM information_schema.columns WHERE table_name=%s AND column_name=%s", ["catalogue_product", "id"])
        assert cursor.fetchone() == ("bigint", "YES")
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", ["orders_payment"])
        assert "status" not in {r[0] for r in cursor.fetchall()}


def test_postgresql_rejects_numeric_nan_even_if_an_orm_is_bypassed(graph):
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("UPDATE catalogue_product SET price=%s WHERE id=%s", [Decimal("NaN"), graph[2].pk])


def test_profile_role_checks_prevent_role_confusion(graph):
    customer, seller, *_ = graph
    with pytest.raises(IntegrityError), transaction.atomic():
        Seller.objects.create(user=customer, status="approved", shop_name="Forged")
    with pytest.raises(IntegrityError), transaction.atomic():
        CustomerProfile.objects.create(user=seller.user)
    with pytest.raises(IntegrityError), transaction.atomic():
        get_user_model().objects.filter(pk=customer.pk).update(role="operator")
    with pytest.raises(IntegrityError), transaction.atomic():
        CustomerProfile.objects.create(user=customer)


def test_composite_foreign_keys_reject_another_sellers_product(graph):
    _, seller, product, _, order, line, _ = graph
    other = Seller.objects.create(user=get_user_model().objects.create_user(username="other", role="seller"), status="approved", shop_name="Other")
    other_product = Product.objects.create(seller=other, category=product.category, name="Other", price="1", freight="0", stock=1, lead_time_days=1)
    for change in ({"product": other_product}, {"seller": other}):
        with pytest.raises(IntegrityError), transaction.atomic():
            OrderLine.objects.filter(pk=line.pk).update(**change)


def test_second_order_for_same_seller_in_checkout_is_rejected(graph):
    _, seller, _, checkout, order, *_ = graph
    with pytest.raises(IntegrityError), transaction.atomic():
        Order.objects.create(checkout=checkout, seller=seller, status="paid", items=1, freight=0, total=1, placed_at=NOW, estimated_delivery=NOW)


def test_checkout_idempotency_key_is_unique_per_customer(graph):
    customer, _, _, checkout, *_ = graph
    key = uuid.uuid4()
    Checkout.objects.filter(pk=checkout.pk).update(idempotency_key=key)
    with pytest.raises(IntegrityError), transaction.atomic():
        Checkout.objects.create(customer=customer, placed_at=NOW, total=0, idempotency_key=key)
    other = get_user_model().objects.create_user(username="other-buyer")
    Checkout.objects.create(customer=other, placed_at=NOW, total=0, idempotency_key=key)


def test_refund_is_unique_and_cannot_reference_another_checkout(graph):
    customer, _, _, checkout, order, *_ = graph
    other = Checkout.objects.create(customer=customer, placed_at=NOW, total=0)
    with pytest.raises(IntegrityError), transaction.atomic():
        Refund.objects.create(order=order, checkout=other, amount=12, reason="wrong", refunded_at=NOW, imported=True)
    Refund.objects.create(order=order, checkout=checkout, amount=12, reason="example", refunded_at=NOW, imported=True)
    with pytest.raises(IntegrityError), transaction.atomic():
        Refund.objects.create(order=order, checkout=checkout, amount=12, reason="duplicate", refunded_at=NOW, imported=True)


def test_purchasable_view_has_the_canonical_visibility_rules(graph):
    _, seller, product, *_ = graph
    assert PurchasableProduct.objects.filter(pk=product.pk).exists()
    for field, value in (("active", False), ("taken_down", True)):
        Product.objects.filter(pk=product.pk).update(**{field: value})
        assert not PurchasableProduct.objects.filter(pk=product.pk).exists()
        Product.objects.filter(pk=product.pk).update(active=True, taken_down=False)
    # One seller per status: the status trigger (accounts) forbids moving one seller through all of them.
    for status in ("pending", "rejected", "suspended"):
        other = Seller.objects.create(user=get_user_model().objects.create_user(username="seller-" + status, role="seller"),
                                      status=status, shop_name=status)
        hidden = Product.objects.create(seller=other, category=product.category, name=status, price="1", freight="0", stock=1, lead_time_days=1)
        assert not PurchasableProduct.objects.filter(pk=hidden.pk).exists()


def test_historical_values_survive_price_changes_and_deletion_is_protected(graph):
    customer, seller, product, checkout, order, line, payment = graph
    Product.objects.filter(pk=product.pk).update(price="99.99", active=False)
    line.refresh_from_db()
    assert line.unit_price == Decimal("10.00")
    for obj in (customer, seller, product, checkout, order):
        with pytest.raises(ProtectedError):
            obj.delete()
