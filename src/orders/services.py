"""Cart CRUD uses the ORM; checkout and lifecycle writes demonstrate explicit PostgreSQL locking.

All purchase amounts come from locked PostgreSQL products. No payment details are retained beyond
method, instalments and amount. Every order/product write starts with transaction-local audit context.
"""
from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import re
import uuid

from django.core.exceptions import PermissionDenied
from django.db import connection, transaction
from django.http import Http404
from django.utils import timezone

from accounts.audit import set_audit_context
from accounts.models import User
from catalogue.models import Product, PurchasableProduct
from .models import Cart, CartLine, Checkout, MAX_CART_QUANTITY, Payment

ZERO = Decimal("0.00")
MAX_MONEY = Decimal("9999999999.99")
MAX_REASON_LENGTH = 1000  # matches the cancel form's maxlength; enforced here for hand-made requests


class CheckoutError(Exception):
    pass


class CartChangedError(CheckoutError):
    def __init__(self):
        super().__init__("Your cart or its prices changed. Please review it again.")


class InsufficientStockError(CheckoutError):
    pass


def require_customer(user):
    if not User.objects.filter(pk=user.pk, role=User.Role.CUSTOMER, is_active=True).exists():
        raise PermissionDenied


def quantity_value(value):
    try:
        quantity = int(value)
    except (ValueError, TypeError, OverflowError):
        raise CheckoutError("Choose a whole quantity from 1 to 999.") from None
    if str(quantity) != str(value) or not 1 <= quantity <= MAX_CART_QUANTITY:
        raise CheckoutError("Choose a whole quantity from 1 to 999.")
    return quantity


def object_id(value):
    try:
        result = int(value)
    except (ValueError, TypeError, OverflowError):
        raise Http404 from None
    if result < 1 or result > 9223372036854775807:
        raise Http404
    return result


def get_cart(user):
    require_customer(user)
    return Cart.objects.get_or_create(customer=user)[0]


def _visible_product(product_id):
    try:
        return Product.objects.get(pk=object_id(product_id), pk__in=PurchasableProduct.objects.values("id"))
    except Product.DoesNotExist:
        raise CheckoutError("This product is no longer available.") from None


def _check_quantity(item, quantity):
    if quantity > item.stock:
        raise InsufficientStockError(f"Only {item.stock} of {item.name} left in stock.")


def add_to_cart(user, product_id, quantity=1):
    quantity = quantity_value(quantity)
    cart = get_cart(user)
    with transaction.atomic():
        Cart.objects.select_for_update().get(pk=cart.pk, customer=user)
        item = _visible_product(product_id)
        line = CartLine.objects.filter(cart=cart, product=item).first()
        amount = quantity_value(quantity + (line.quantity if line else 0))
        _check_quantity(item, amount)
        if line:
            line.quantity = amount
            line.save(update_fields=["quantity"])
        else:
            line = CartLine.objects.create(cart=cart, product=item, quantity=amount)
    return line


def set_cart_quantity(user, line_id, quantity):
    quantity = quantity_value(quantity)
    cart = get_cart(user)
    with transaction.atomic():
        Cart.objects.select_for_update().get(pk=cart.pk, customer=user)
        try:
            line = CartLine.objects.get(pk=object_id(line_id), cart=cart)
        except CartLine.DoesNotExist:
            raise Http404 from None
        item = _visible_product(line.product_id)
        _check_quantity(item, quantity)
        line.quantity = quantity
        line.save(update_fields=["quantity"])
    return line


def remove_from_cart(user, line_id):
    cart = get_cart(user)
    with transaction.atomic():
        Cart.objects.select_for_update().get(pk=cart.pk, customer=user)
        if not CartLine.objects.filter(pk=object_id(line_id), cart=cart).delete()[0]:
            raise Http404


def fingerprint_for(lines):
    """Stable (product ID, quantity, unit price, unit freight) digest for exactly the displayed lines."""
    canonical = "|".join(f"{pid}:{quantity}:{Decimal(price):.2f}:{Decimal(freight):.2f}"
                         for pid, quantity, price, freight in sorted(lines))
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def cart_review(user):
    cart = get_cart(user)
    lines = list(cart.lines.select_related("product__seller").order_by("product__seller_id", "product_id"))
    visible = set(PurchasableProduct.objects.filter(pk__in=[line.product_id for line in lines]).values_list("pk", flat=True))
    groups = OrderedDict()
    ready = bool(lines)
    for line in lines:
        item = line.product
        line.available = item.pk in visible
        line.enough_stock = line.quantity <= item.stock
        ready = ready and line.available and line.enough_stock
        line.items_total = item.price * line.quantity
        line.freight_total = item.freight * line.quantity
        line.total = line.items_total + line.freight_total
        group = groups.setdefault(item.seller_id, {"seller": item.seller, "lines": [], "items": ZERO, "freight": ZERO, "total": ZERO})
        group["lines"].append(line)
        group["items"] += line.items_total
        group["freight"] += line.freight_total
        group["total"] += line.total
    total = sum((group["total"] for group in groups.values()), ZERO)
    return {"cart": cart, "groups": list(groups.values()), "lines": lines, "ready": ready,
            "total": total, "fingerprint": fingerprint_for((l.product_id, l.quantity, l.product.price, l.product.freight) for l in lines)}


def _payments(choices, total):
    choices = choices if choices is not None else [{"method": "credit_card", "instalments": 1, "amount": total}]
    if not choices or len(choices) > 4:
        raise CheckoutError("Choose a payment method.")
    result = []
    methods = set()
    for choice in choices:
        method = choice.get("method")
        try:
            count = int(choice.get("instalments", 1))
            raw = choice.get("amount", total)
            if isinstance(raw, float):
                raise ValueError
            amount = Decimal(raw)
            if not amount.is_finite() or amount <= 0 or amount > MAX_MONEY or amount != amount.quantize(Decimal("0.01")):
                raise ValueError
        except (ValueError, TypeError, InvalidOperation, OverflowError):
            raise CheckoutError("Choose a valid payment amount and instalments.") from None
        if method in methods or method not in Payment.Method.values or not 1 <= count <= (12 if method == "credit_card" else 1):
            raise CheckoutError("Choose a valid payment method and instalments.")
        methods.add(method)
        result.append((method, count, amount))
    if sum((row[2] for row in result), ZERO) != total:
        raise CheckoutError("Payment amounts must equal the amount shown.")
    return result


def _existing(cursor, customer_id, key, review):
    cursor.execute("SELECT id, request_fingerprint FROM orders_checkout WHERE customer_id=%s AND idempotency_key=%s", [customer_id, key])
    row = cursor.fetchone()
    if row is None:
        return None
    if row[1] != review:
        raise CartChangedError()
    return Checkout.objects.get(pk=row[0], customer_id=customer_id)


def checkout(user, idempotency_key, review, payments=None):
    try:
        key = uuid.UUID(str(idempotency_key))
    except (ValueError, TypeError, AttributeError):
        raise CheckoutError("Please open the review page again.") from None
    if not isinstance(review, str) or re.fullmatch(r"[0-9a-f]{64}", review) is None:
        raise CartChangedError()
    with transaction.atomic():
        set_audit_context(user.pk, "Customer placed order")
        require_customer(user)
        cart = get_cart(user)
        with connection.cursor() as cursor:
            existing = _existing(cursor, user.pk, key, review)
            if existing:
                return existing
            cursor.execute("SELECT id FROM orders_cart WHERE id=%s AND customer_id=%s FOR UPDATE", [cart.pk, user.pk])
            cursor.fetchone()
            # A duplicate submit may have committed while this request waited for its cart.
            existing = _existing(cursor, user.pk, key, review)
            if existing:
                return existing
            cursor.execute("SELECT id, product_id, quantity FROM orders_cartline WHERE cart_id=%s ORDER BY product_id FOR UPDATE", [cart.pk])
            lines = cursor.fetchall()
            if not lines:
                raise CheckoutError("Your cart is empty.")
            ids = [line[1] for line in lines]
            cursor.execute("""SELECT id, seller_id, price, freight, stock, lead_time_days, name
                              FROM catalogue_product WHERE id=ANY(%s) ORDER BY id FOR UPDATE""", [ids])
            products = {row[0]: row for row in cursor.fetchall()}
            # Seller approval cannot change between the visibility check and commit.
            seller_ids = sorted({row[1] for row in products.values()})
            cursor.execute("SELECT id FROM accounts_seller WHERE id=ANY(%s) ORDER BY id FOR SHARE", [seller_ids])
            cursor.fetchall()
            cursor.execute("SELECT id FROM purchasable_product WHERE id=ANY(%s)", [ids])
            visible = {row[0] for row in cursor.fetchall()}
            if any(pid not in visible for pid in ids):
                raise CheckoutError("A product is no longer available. Remove it before paying.")
            current = fingerprint_for((pid, quantity, products[pid][2], products[pid][3]) for _, pid, quantity in lines)
            if current != review:
                raise CartChangedError()
            groups = OrderedDict()
            for _, pid, quantity in lines:
                item = products[pid]
                if quantity > item[4]:
                    raise InsufficientStockError(f"Only {item[4]} of {item[6]} left in stock.")
                groups.setdefault(item[1], []).append((item, quantity))
            total = sum(((products[pid][2] + products[pid][3]) * quantity for _, pid, quantity in lines), ZERO)
            if total > MAX_MONEY:
                raise CheckoutError("This cart total is too large. Please remove some items.")
            payment_rows = _payments(payments, total)
            now = timezone.now()
            cursor.execute("""INSERT INTO orders_checkout (customer_id, placed_at, total, idempotency_key, request_fingerprint)
                              VALUES (%s,%s,%s,%s,%s) RETURNING id""", [user.pk, now, total, key, current])
            checkout_id = cursor.fetchone()[0]
            for seller_id, group in groups.items():
                items_total = sum((item[2] * quantity for item, quantity in group), ZERO)
                freight_total = sum((item[3] * quantity for item, quantity in group), ZERO)
                estimate = now + timedelta(days=max(item[5] for item, _ in group) + 15)
                cursor.execute("""INSERT INTO orders_order (checkout_id,seller_id,status,items,freight,total,placed_at,paid_at,estimated_delivery)
                                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                               [checkout_id, seller_id, "paid", items_total, freight_total, items_total+freight_total, now, now, estimate])
                order_id = cursor.fetchone()[0]
                for item, quantity in group:
                    cursor.execute("""INSERT INTO orders_orderline (order_id,seller_id,product_id,quantity,unit_price,freight,shipping_limit_at)
                                      VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                                   [order_id, seller_id, item[0], quantity, item[2], item[3]*quantity, now+timedelta(days=item[5])])
                    cursor.execute("UPDATE catalogue_product SET stock=stock-%s WHERE id=%s", [quantity, item[0]])
            for sequence, (method, count, amount) in enumerate(payment_rows, 1):
                cursor.execute("""INSERT INTO orders_payment (checkout_id,sequence,method,instalments,amount)
                                  VALUES (%s,%s,%s,%s,%s)""", [checkout_id, sequence, method, count, amount])
            cursor.execute("DELETE FROM orders_cartline WHERE cart_id=%s", [cart.pk])
        return Checkout.objects.get(pk=checkout_id, customer=user)


def change_order_status(actor, order_id, action, reason=""):
    """Scoped seller shipping, operator delivery, and customer cancellation, each in one transaction."""
    order_id = object_id(order_id)
    if action not in {"ship", "deliver", "cancel"}:
        raise CheckoutError("Choose a valid order action.")
    role = {"ship": "seller", "deliver": "operator", "cancel": "customer"}[action]
    reason = (reason or "").strip() or {"ship": "Seller shipped order", "deliver": "Operator delivered order", "cancel": "Customer cancelled order"}[action]
    if len(reason) > MAX_REASON_LENGTH:
        raise CheckoutError(f"Keep the reason under {MAX_REASON_LENGTH} characters.")
    with transaction.atomic():
        set_audit_context(actor.pk, reason)
        if not User.objects.filter(pk=actor.pk, role=role, is_active=True).exists():
            raise PermissionDenied
        with connection.cursor() as cursor:
            # Lock the parent before its order, matching deferred checks and serializing sibling refunds.
            # The scoped lookup never reveals another customer's or seller's order.
            cursor.execute("""SELECT o.checkout_id FROM orders_order o JOIN orders_checkout c ON c.id=o.checkout_id
                              JOIN accounts_seller s ON s.id=o.seller_id WHERE o.id=%s AND
                              ((%s='customer' AND c.customer_id=%s) OR (%s='seller' AND s.user_id=%s AND s.status='approved')
                               OR %s='operator')""", [order_id, role, actor.pk, role, actor.pk, role])
            parent = cursor.fetchone()
            if parent is None:
                raise Http404
            cursor.execute("SELECT id FROM orders_checkout WHERE id=%s FOR UPDATE", [parent[0]])
            cursor.fetchone()
            cursor.execute("SELECT id,status,total,checkout_id FROM orders_order WHERE id=%s FOR UPDATE", [order_id])
            order = cursor.fetchone()
            expected = {"ship": {"paid"}, "deliver": {"shipped"}, "cancel": {"placed", "paid"}}[action]
            if order[1] not in expected:
                raise CheckoutError("This order has already changed. Please refresh the page.")
            if action == "cancel":
                cursor.execute("SELECT product_id,quantity FROM orders_orderline WHERE order_id=%s ORDER BY product_id", [order_id])
                lines = cursor.fetchall()
                cursor.execute("SELECT id FROM catalogue_product WHERE id=ANY(%s) ORDER BY id FOR UPDATE", [[row[0] for row in lines]])
                cursor.fetchall()
                for pid, quantity in lines:
                    cursor.execute("UPDATE catalogue_product SET stock=stock+%s WHERE id=%s", [quantity, pid])
                cursor.execute("""INSERT INTO orders_refund (order_id,checkout_id,amount,reason,refunded_at,imported)
                                  VALUES (%s,%s,%s,%s,%s,%s)""", [order_id, order[3], order[2], reason, timezone.now(), False])
            destination = {"ship": "shipped", "deliver": "delivered", "cancel": "cancelled"}[action]
            cursor.execute("UPDATE orders_order SET status=%s WHERE id=%s", [destination, order_id])
    return order_id
