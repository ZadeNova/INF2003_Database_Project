"""Atomic checkout, replay, freight and lifecycle behaviour on real databases."""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from checkout_helpers import customer, product
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404

from accounts.audit import change_seller_status
from accounts.models import AuditLog, Seller, User
from catalogue.models import Product
from config.olist_import import INVARIANTS, sql_invariants
from orders.models import Checkout, Order, OrderLine, Payment, Refund
from orders.services import CartChangedError, CheckoutError, InsufficientStockError, add_to_cart, cart_review, change_order_status, checkout, remove_from_cart, set_cart_quantity

pytestmark = pytest.mark.django_db(transaction=True)
PAYLOAD = "x'); DROP TABLE orders_checkout; --"


def buy(buyer, key=None, payments=None):
    review = cart_review(buyer)
    return checkout(buyer, key or uuid.uuid4(), review["fingerprint"], payments)


def assert_balanced():
    with connection.cursor() as cursor:
        for name in ("payment_totals", "checkout_order_totals", "order_line_totals"):
            cursor.execute(INVARIANTS[name])
            assert cursor.fetchall() == []
        cursor.execute("""SELECT c.id FROM orders_checkout c WHERE
                          (SELECT COALESCE(sum(amount),0) FROM orders_refund WHERE checkout_id=c.id) <>
                          (SELECT COALESCE(sum(total),0) FROM orders_order WHERE checkout_id=c.id AND status='cancelled')""")
        assert cursor.fetchall() == []


def test_three_seller_purchase_splits_and_balances_exactly():
    buyer = customer()
    products = [product("first", price="10.01", freight="1.23"), product("second", price="20.02", freight="2.34"),
                product("third", price="30.03", freight="3.45")]
    for quantity, item in enumerate(products, 1):
        add_to_cart(buyer, item.pk, quantity)
    record = buy(buyer)
    assert record.orders.count() == 3 and OrderLine.objects.count() == 3
    expected = sum(((item.price+item.freight)*quantity for quantity,item in enumerate(products,1)), Decimal("0.00"))
    assert record.total == expected == record.payments.get().amount
    assert not buyer.cart.lines.exists()
    for quantity,item in enumerate(products,1):
        item.refresh_from_db()
        line = OrderLine.objects.get(product=item)
        assert item.stock == 20-quantity and line.freight == item.freight*quantity and line.unit_price == item.price
        assert line.order.estimated_delivery == line.order.placed_at + timedelta(days=item.lead_time_days+15)
        assert line.shipping_limit_at == line.order.placed_at + timedelta(days=item.lead_time_days)
        assert line.order.paid_at == record.placed_at and line.order.status == "paid"
    assert_balanced()


def test_estimate_uses_longest_lead_in_each_shop_order():
    buyer, first = customer(), product(lead=2)
    second = Product.objects.create(seller=first.seller, category=first.category, name="Long lead", price=2, freight=1,
                                    stock=10, lead_time_days=11)
    for item in (first, second):
        add_to_cart(buyer, item.pk, 2)
    order = buy(buyer).orders.get()
    assert order.estimated_delivery == order.placed_at + timedelta(days=26)
    assert order.freight == 6 and order.lines.count() == 2


def test_idempotency_replays_after_cart_emptied_and_does_not_consume_new_cart():
    buyer, item = customer(), product()
    add_to_cart(buyer, item.pk, 2)
    key, review = uuid.uuid4(), cart_review(buyer)["fingerprint"]
    first = checkout(buyer, key, review)
    assert checkout(buyer, key, review).pk == first.pk
    add_to_cart(buyer, item.pk)
    assert checkout(buyer, key, review).pk == first.pk
    assert buyer.cart.lines.get().quantity == 1 and Checkout.objects.count() == 1
    item.refresh_from_db()
    assert item.stock == 18
    with pytest.raises(CartChangedError):
        checkout(buyer, key, cart_review(buyer)["fingerprint"])


@pytest.mark.parametrize("field,value", [("price", Decimal("11.00")), ("freight", Decimal("3.00"))])
def test_price_or_freight_change_after_review_requires_review_again(field, value):
    buyer, item = customer(), product()
    add_to_cart(buyer, item.pk)
    review = cart_review(buyer)["fingerprint"]
    Product.objects.filter(pk=item.pk).update(**{field: value})
    with pytest.raises(CartChangedError):
        checkout(buyer, uuid.uuid4(), review)
    assert not Checkout.objects.exists() and buyer.cart.lines.count() == 1
    record = buy(buyer)
    assert record.total == (value+Decimal("2") if field == "price" else Decimal("10")+value)


def test_changed_quantity_or_added_line_is_refused():
    buyer, item = customer(), product()
    add_to_cart(buyer, item.pk)
    review = cart_review(buyer)["fingerprint"]
    set_cart_quantity(buyer, buyer.cart.lines.get().pk, 2)
    with pytest.raises(CartChangedError):
        checkout(buyer, uuid.uuid4(), review)
    review = cart_review(buyer)["fingerprint"]
    add_to_cart(buyer, product("extra").pk)
    with pytest.raises(CartChangedError):
        checkout(buyer, uuid.uuid4(), review)
    assert not Checkout.objects.exists()


@pytest.mark.parametrize("hide", ["active", "taken_down", "seller"])
def test_canonical_visibility_is_used_for_add_review_and_checkout(hide):
    buyer, item = customer(), product()
    add_to_cart(buyer, item.pk)
    review = cart_review(buyer)["fingerprint"]
    if hide == "seller":
        Seller.objects.filter(pk=item.seller_id).update(status="suspended")
    else:
        Product.objects.filter(pk=item.pk).update(**{hide: hide == "taken_down"})
    context = cart_review(buyer)
    assert not context["ready"] and not context["lines"][0].available
    with pytest.raises(CheckoutError, match="no longer available"):
        add_to_cart(buyer, item.pk)
    with pytest.raises(CheckoutError, match="no longer available"):
        checkout(buyer, uuid.uuid4(), review)
    assert not Checkout.objects.exists() and buyer.cart.lines.count() == 1
    remove_from_cart(buyer, buyer.cart.lines.get().pk)
    assert not buyer.cart.lines.exists()


def test_stock_failure_rolls_back_every_shop_payment_and_stock_change():
    buyer, first, second = customer(), product("first"), product("second")
    for item in (first, second):
        add_to_cart(buyer, item.pk, 2)
    review = cart_review(buyer)["fingerprint"]
    Product.objects.filter(pk=second.pk).update(stock=1)
    with pytest.raises(InsufficientStockError):
        checkout(buyer, uuid.uuid4(), review)
    first.refresh_from_db()
    assert first.stock == 20 and buyer.cart.lines.count() == 2
    assert not any(model.objects.exists() for model in (Checkout, Order, OrderLine, Payment))


def test_one_cart_line_per_product_and_quantities_are_validated():
    buyer, item = customer(), product(stock=999)
    line = add_to_cart(buyer, item.pk)
    assert add_to_cart(buyer, item.pk, 2).pk == line.pk
    line.refresh_from_db()
    assert line.quantity == 3
    for bad in (0, -1, 1000, "1.5", PAYLOAD):
        with pytest.raises(CheckoutError):
            set_cart_quantity(buyer, line.pk, bad)
    set_cart_quantity(buyer, line.pk, 999)
    with pytest.raises(CheckoutError):
        add_to_cart(buyer, item.pk)


@pytest.mark.parametrize("method,count", [("credit_card", 1), ("credit_card", 12), ("boleto",1), ("voucher",1), ("debit_card",1)])
def test_supported_payment_methods_and_instalments(method, count):
    buyer, item = customer(), product()
    add_to_cart(buyer,item.pk)
    payment = buy(buyer, payments=[{"method": method, "instalments": count}]).payments.get()
    assert payment.method == method and payment.instalments == count and payment.amount == 12


def test_multiple_payment_methods_balance_one_checkout():
    buyer, item = customer(), product()
    add_to_cart(buyer,item.pk)
    record = buy(buyer, payments=[{"method":"voucher","amount":"2.00"}, {"method":"credit_card","amount":"10.00","instalments":3}])
    assert list(record.payments.order_by("sequence").values_list("amount",flat=True)) == [Decimal("2"), Decimal("10")]
    assert_balanced()


@pytest.mark.parametrize("choice", [{"method":PAYLOAD}, {"method":"credit_card","instalments":13},
    {"method":"credit_card","instalments":0}, {"method":"boleto","instalments":2},
    {"method":"credit_card","amount":"11.99"}, {"method":"credit_card","amount":"NaN"},
    {"method":"credit_card","amount":12.0}, {"method":"credit_card","amount":PAYLOAD}])
def test_bad_payment_rolls_back_without_charging(choice):
    buyer, item = customer(), product()
    add_to_cart(buyer,item.pk)
    with pytest.raises(CheckoutError):
        buy(buyer,payments=[choice])
    assert not Checkout.objects.exists() and buyer.cart.lines.count() == 1
    item.refresh_from_db()
    assert item.stock == 20


def test_ship_deliver_and_cancel_with_stock_refund_and_audit():
    buyer,item = customer(),product()
    operator=User.objects.create_user(username="operator",role="operator")
    add_to_cart(buyer,item.pk,2)
    first=buy(buyer).orders.get()
    change_order_status(item.seller.user,first.pk,"ship")
    change_order_status(operator,first.pk,"deliver")
    first.refresh_from_db()
    assert first.status == "delivered" and first.shipped_at and first.delivered_at
    add_to_cart(buyer,item.pk,3)
    other=buy(buyer).orders.get()
    change_order_status(buyer,other.pk,"cancel",PAYLOAD)
    item.refresh_from_db()
    other.refresh_from_db()
    assert item.stock == 18 and other.status == "cancelled" and other.cancelled_at
    assert (other.refund.amount,other.refund.reason,other.refund.checkout_id) == (Decimal("36"),PAYLOAD,other.checkout_id)
    audit=AuditLog.objects.get(table_name="orders_order",action="order.cancelled")
    assert audit.actor_id == buyer.pk and audit.reason == PAYLOAD
    # A real seller transition adds another kind of audit event. Order assertions must remain scoped
    # when catalogue's product-create and stock-change audit triggers are integrated too.
    change_seller_status(item.seller_id,"suspend",operator,"Audit isolation check")
    assert AuditLog.objects.filter(table_name="accounts_seller",action="seller.suspend").exists()
    assert list(AuditLog.objects.filter(table_name="orders_order").order_by("pk").values_list("action",flat=True)) == ["order.shipped","order.delivered","order.cancelled"]
    with pytest.raises(CheckoutError):
        change_order_status(buyer,other.pk,"cancel")
    assert Refund.objects.count() == 1
    assert_balanced()
    assert set(sql_invariants().values()) == {0}


def test_shipped_order_cannot_be_cancelled():
    buyer,item=customer(),product()
    add_to_cart(buyer,item.pk)
    order=buy(buyer).orders.get()
    change_order_status(item.seller.user,order.pk,"ship")
    with pytest.raises(CheckoutError):
        change_order_status(buyer,order.pk,"cancel")
    assert not Refund.objects.exists()
    item.refresh_from_db()
    assert item.stock == 19


def test_an_oversized_cancel_reason_is_refused_before_anything_changes():
    # The form's maxlength is only a browser hint; a hand-made POST must not store megabytes in refunds and audit rows.
    buyer,item=customer(),product()
    add_to_cart(buyer,item.pk)
    order=buy(buyer).orders.get()
    audit_rows=AuditLog.objects.count()
    with pytest.raises(CheckoutError, match="under 1000 characters"):
        change_order_status(buyer,order.pk,"cancel","x"*1001)
    order.refresh_from_db()
    assert order.status == "paid" and not Refund.objects.exists() and AuditLog.objects.count() == audit_rows
    change_order_status(buyer,order.pk,"cancel","y"*1000)
    assert Refund.objects.get().reason == "y"*1000


def test_services_scope_cart_order_and_actor_roles():
    buyer,other,item,foreign=customer(),customer("other"),product(),product("foreign")
    line=add_to_cart(buyer,item.pk)
    for operation in (lambda:set_cart_quantity(other,line.pk,2),lambda:remove_from_cart(other,line.pk)):
        with pytest.raises(Http404):
            operation()
    order=buy(buyer).orders.get()
    for actor,action,error in [(other,"cancel",Http404),(foreign.seller.user,"ship",Http404),(buyer,"ship",PermissionDenied),
                                (item.seller.user,"deliver",PermissionDenied)]:
        with pytest.raises(error):
            change_order_status(actor,order.pk,action)
    with pytest.raises(PermissionDenied):
        add_to_cart(item.seller.user,item.pk)
    Seller.objects.filter(pk=item.seller_id).update(status="suspended")
    with pytest.raises(Http404):
        change_order_status(item.seller.user,order.pk,"ship")


def test_sql_injection_negatives_cover_checkout_replay_and_order_actions():
    buyer,item=customer(),product()
    add_to_cart(buyer,item.pk)
    review=cart_review(buyer)["fingerprint"]
    with pytest.raises(CheckoutError):
        checkout(buyer,PAYLOAD,review)
    with pytest.raises(CartChangedError):
        checkout(buyer,uuid.uuid4(),PAYLOAD)
    order=buy(buyer).orders.get()
    with pytest.raises(Http404):
        change_order_status(buyer,PAYLOAD,"cancel")
    with pytest.raises(CheckoutError):
        change_order_status(buyer,order.pk,PAYLOAD)
    assert Order.objects.get(pk=order.pk).status == "paid" and Checkout.objects.count()==1


def test_each_payment_method_is_recorded_once():
    buyer,item=customer(),product()
    add_to_cart(buyer,item.pk)
    with pytest.raises(CheckoutError):
        buy(buyer,payments=[{"method":"voucher","amount":"6"},{"method":"voucher","amount":"6"}])
    assert not Checkout.objects.exists()


def test_customer_can_cancel_imported_paid_history_with_a_nonimported_refund(imported):
    order=Order.objects.filter(status="paid").select_related("checkout__customer").order_by("pk").first()
    assert order is not None and order.checkout.olist_order_id
    before={line.product_id: (line.product.stock,line.quantity) for line in order.lines.select_related("product")}
    change_order_status(order.checkout.customer,order.pk,"cancel","Cancel historical order")
    order.refresh_from_db()
    assert order.status=="cancelled" and not order.refund.imported
    for pid,(stock,quantity) in before.items():
        assert Product.objects.get(pk=pid).stock==stock+quantity
    assert set(sql_invariants().values())=={0}
