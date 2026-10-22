"""Real PostgreSQL graph builders shared by checkout tests."""
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from accounts.audit import set_audit_context
from accounts.models import User, Seller, CustomerProfile
from catalogue.models import Category, Product
from orders.models import Checkout, Order, Payment, Refund


def customer(name="buyer"):
    user = User.objects.create_user(username=name)
    CustomerProfile.objects.create(user=user)
    return user


def product(name="example", stock=20, price="10.00", freight="2.00", lead=5):
    category, _ = Category.objects.get_or_create(slug="example", defaults={"name_en": "Example", "name_pt": "Exemplo"})
    user = User.objects.create_user(username="seller-" + name, role="seller")
    seller = Seller.objects.create(user=user, shop_name=name + " shop", status="approved")
    return Product.objects.create(seller=seller, category=category, name=name, stock=stock,
                                  price=Decimal(price), freight=Decimal(freight), lead_time_days=lead)


def paid_order(buyer, item, status="paid"):
    now = timezone.now()
    with transaction.atomic():
        set_audit_context()
        checkout = Checkout.objects.create(customer=buyer, total=12, placed_at=now)
        order = Order.objects.create(checkout=checkout, seller=item.seller, status=status, items=10,
                                     freight=2, total=12, placed_at=now, estimated_delivery=now)
        Payment.objects.create(checkout=checkout, sequence=1, method="boleto", instalments=1, amount=12)
        if status == "cancelled":
            Refund.objects.create(order=order, checkout=checkout, amount=12, reason="Example", refunded_at=now)
    return checkout, order
