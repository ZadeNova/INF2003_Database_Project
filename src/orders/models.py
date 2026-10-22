from django.conf import settings
from django.db import models
from django.db.models import Q


def nonnegative(field):
    return Q(**{field + "__gte": 0, field + "__lte": "9999999999.99"})


class Checkout(models.Model):
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="checkouts")
    placed_at = models.DateTimeField()
    total = models.DecimalField(max_digits=12, decimal_places=2)
    idempotency_key = models.UUIDField(null=True, blank=True)
    olist_order_id = models.CharField(max_length=32, unique=True, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["customer", "idempotency_key"], name="checkout_customer_key_unique"),
            models.CheckConstraint(condition=nonnegative("total"), name="checkout_total_valid"),
        ]


class Order(models.Model):
    class Status(models.TextChoices):
        PLACED = "placed"
        PAID = "paid"
        SHIPPED = "shipped"
        DELIVERED = "delivered"
        CANCELLED = "cancelled"

    checkout = models.ForeignKey(Checkout, on_delete=models.PROTECT, related_name="orders")
    seller = models.ForeignKey("accounts.Seller", on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=9, choices=Status.choices)
    items = models.DecimalField(max_digits=12, decimal_places=2)
    freight = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    placed_at = models.DateTimeField()
    paid_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    estimated_delivery = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["checkout", "seller"], name="order_checkout_seller_unique"),
            models.UniqueConstraint(fields=["id", "seller"], name="order_id_seller_unique"),
            models.UniqueConstraint(fields=["id", "checkout"], name="order_id_checkout_unique"),
            models.CheckConstraint(condition=Q(status__in=["placed", "paid", "shipped", "delivered", "cancelled"]), name="order_status_valid"),
            models.CheckConstraint(condition=nonnegative("items") & nonnegative("freight") & nonnegative("total"), name="order_money_valid"),
            models.CheckConstraint(condition=Q(total=models.F("items") + models.F("freight")), name="order_total_parts"),
        ]
        indexes = [models.Index(fields=["seller", "placed_at"], name="order_seller_date")]


class OrderLine(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="lines")
    seller = models.ForeignKey("accounts.Seller", on_delete=models.PROTECT)
    product = models.ForeignKey("catalogue.Product", on_delete=models.PROTECT, related_name="order_lines")
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    freight = models.DecimalField(max_digits=12, decimal_places=2)
    shipping_limit_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="line_quantity_positive"),
            models.CheckConstraint(condition=Q(unit_price__gt=0, unit_price__lte="9999999999.99") & nonnegative("freight"), name="line_money_valid"),
        ]


class Payment(models.Model):
    class Method(models.TextChoices):
        CREDIT_CARD = "credit_card"
        BOLETO = "boleto"
        VOUCHER = "voucher"
        DEBIT_CARD = "debit_card"

    checkout = models.ForeignKey(Checkout, on_delete=models.PROTECT, related_name="payments")
    sequence = models.PositiveIntegerField()
    method = models.CharField(max_length=11, choices=Method.choices)
    instalments = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["checkout", "sequence"], name="payment_checkout_sequence_unique"),
            models.CheckConstraint(condition=Q(method__in=["credit_card", "boleto", "voucher", "debit_card"]), name="payment_method_valid"),
            models.CheckConstraint(condition=Q(instalments__gte=1, sequence__gte=1), name="payment_counts_positive"),
            models.CheckConstraint(condition=nonnegative("amount"), name="payment_amount_valid"),
        ]


class Refund(models.Model):
    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="refund")
    checkout = models.ForeignKey(Checkout, on_delete=models.PROTECT, related_name="refunds")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()
    refunded_at = models.DateTimeField()
    imported = models.BooleanField(default=False)

    class Meta:
        constraints = [models.CheckConstraint(condition=nonnegative("amount"), name="refund_amount_valid")]
