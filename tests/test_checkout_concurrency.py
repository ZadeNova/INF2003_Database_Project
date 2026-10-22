"""Twenty genuinely separate PostgreSQL connections contend for five units, ten consecutive runs."""
from concurrent.futures import ThreadPoolExecutor
import threading
import uuid

import pytest
from django.db import connections, connection

from checkout_helpers import customer, product
from orders.models import Checkout, OrderLine, Payment
from orders.services import add_to_cart, cart_review, checkout, InsufficientStockError

pytestmark=pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize("run",range(10))
def test_last_five_units_have_exactly_five_winners(run):
    item=product(stock=5)
    buyers=[customer(f"race-{run}-{i}") for i in range(20)]
    reviews={}
    for buyer in buyers:
        add_to_cart(buyer,item.pk)
        reviews[buyer.pk]=cart_review(buyer)["fingerprint"]
    barrier=threading.Barrier(20)
    def contend(buyer):
        connections.close_all()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pid=cursor.fetchone()[0]
            barrier.wait(timeout=30)
            try:
                return pid,checkout(buyer,uuid.uuid4(),reviews[buyer.pk]).pk
            except InsufficientStockError:
                return pid,None
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=20) as pool:
        outcomes=list(pool.map(contend,buyers))
    assert len({pid for pid,_ in outcomes})==20
    assert sum(pk is not None for _,pk in outcomes)==5
    item.refresh_from_db()
    assert item.stock==0 and Checkout.objects.count()==5 and OrderLine.objects.count()==5 and Payment.objects.count()==5


def test_same_key_race_replays_one_checkout():
    buyer,item=customer(),product(stock=5)
    add_to_cart(buyer,item.pk)
    key,review=uuid.uuid4(),cart_review(buyer)["fingerprint"]
    barrier=threading.Barrier(2)
    def contend(_):
        connections.close_all()
        try:
            barrier.wait(timeout=30)
            return checkout(buyer,key,review).pk
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(contend,range(2)))
    assert outcomes[0]==outcomes[1] and Checkout.objects.count()==1
    item.refresh_from_db()
    assert item.stock==4 and not buyer.cart.lines.exists()
