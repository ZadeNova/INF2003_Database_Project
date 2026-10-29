"""Twenty genuinely separate PostgreSQL connections contend for five units, ten consecutive runs."""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from time import monotonic

import pytest
from account_helpers import make_operator
from checkout_helpers import customer, product
from django.db import OperationalError, connection, connections, transaction
from psycopg import errors

from accounts.audit import change_seller_status
from accounts.models import Seller
from catalogue.models import Product
from catalogue.services import deactivate_product
from orders.models import Checkout, Order, OrderLine, Payment
from orders.services import CartChangedError, CheckoutError, InsufficientStockError, add_to_cart, cart_review, checkout

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize("run", range(10))
def test_last_five_units_have_exactly_five_winners(run):
    item = product(stock=5)
    buyers = [customer(f"race-{run}-{i}") for i in range(20)]
    reviews = {}
    for buyer in buyers:
        add_to_cart(buyer, item.pk)
        reviews[buyer.pk] = cart_review(buyer)["fingerprint"]
    barrier = threading.Barrier(20)

    def contend(buyer):
        connections.close_all()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pid = cursor.fetchone()[0]
            barrier.wait(timeout=30)
            try:
                return pid, checkout(buyer, uuid.uuid4(), reviews[buyer.pk]).pk
            except InsufficientStockError:
                return pid, None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=20) as pool:
        outcomes = list(pool.map(contend, buyers))
    assert len({pid for pid, _ in outcomes}) == 20
    assert sum(pk is not None for _, pk in outcomes) == 5
    item.refresh_from_db()
    assert (
        item.stock == 0
        and Checkout.objects.count() == 5
        and OrderLine.objects.count() == 5
        and Payment.objects.count() == 5
    )


def test_same_key_race_replays_one_checkout():
    buyer, item = customer(), product(stock=5)
    add_to_cart(buyer, item.pk)
    key, review = uuid.uuid4(), cart_review(buyer)["fingerprint"]
    barrier = threading.Barrier(2)

    def contend(_):
        connections.close_all()
        try:
            barrier.wait(timeout=30)
            return checkout(buyer, key, review).pk
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(contend, range(2)))
    assert outcomes[0] == outcomes[1] and Checkout.objects.count() == 1
    item.refresh_from_db()
    assert item.stock == 4 and not buyer.cart.lines.exists()


def _backend_pid():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        return cursor.fetchone()[0]


def _on_connection(label, pids, finished, action):
    connections.close_all()
    try:
        pids[label] = _backend_pid()
        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout = '15s'")
        return action()
    finally:
        finished.set()
        connections.close_all()


def _wait_for_block(pid, finished, blocker=None):
    """Observe PostgreSQL's actual wait graph; events alone cannot prove a statement blocked."""
    deadline = monotonic() + 10
    with connection.cursor() as cursor:
        while monotonic() < deadline:
            cursor.execute("SELECT pg_blocking_pids(%s)", [pid])
            blockers = cursor.fetchone()[0]
            if blockers and (blocker is None or blocker in blockers):
                return
            assert not finished.is_set(), "The contender completed without waiting for the held lock"
    pytest.fail("The contender did not reach the expected PostgreSQL lock wait")


@pytest.mark.parametrize("first_locker", ["checkout", "deactivate"])
def test_checkout_and_product_deactivation_share_seller_first_lock_order(first_locker):
    """The independent review's two-statement gap must serialize in either direction."""
    buyer, item = customer(), product(stock=5)
    add_to_cart(buyer, item.pk)
    review = cart_review(buyer)["fingerprint"]
    locked = {name: threading.Event() for name in ("checkout", "deactivate")}
    attempted = {name: threading.Event() for name in locked}
    finished = {name: threading.Event() for name in locked}
    release, pids = threading.Event(), {}

    def checkout_gap(execute, sql, params, many, context):
        if "FROM accounts_seller WHERE" in sql:
            attempted["checkout"].set()
        result = execute(sql, params, many, context)
        if "FROM catalogue_product WHERE id=ANY" in sql:
            locked["checkout"].set()
            if first_locker == "checkout":
                assert release.wait(10)
        return result

    def catalogue_gap(execute, sql, params, many, context):
        seller_lock = '"accounts_seller"' in sql and "FOR UPDATE" in sql
        if seller_lock:
            attempted["deactivate"].set()
        result = execute(sql, params, many, context)
        if seller_lock:
            locked["deactivate"].set()
            if first_locker == "deactivate":
                assert release.wait(10)
        return result

    def buy():
        try:
            with connection.execute_wrapper(checkout_gap):
                return checkout(buyer, uuid.uuid4(), review).pk
        except CheckoutError:
            return None

    def deactivate():
        with connection.execute_wrapper(catalogue_gap):
            return deactivate_product(item.seller, item.seller.user, item.pk).active

    actions = {"checkout": buy, "deactivate": deactivate}
    second = "deactivate" if first_locker == "checkout" else "checkout"
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            first_locker: pool.submit(_on_connection, first_locker, pids, finished[first_locker], actions[first_locker])
        }
        try:
            assert locked[first_locker].wait(10)
            futures[second] = pool.submit(_on_connection, second, pids, finished[second], actions[second])
            assert attempted[second].wait(10)
            _wait_for_block(pids[second], finished[second], pids[first_locker])
        finally:
            release.set()
        outcomes = {name: future.result(timeout=20) for name, future in futures.items()}
    item.refresh_from_db()
    assert not item.active and outcomes["deactivate"] is False
    if outcomes["checkout"] is None:
        assert not Checkout.objects.exists() and not Payment.objects.exists()
        assert item.stock == 5 and buyer.cart.lines.count() == 1
    else:
        record = Checkout.objects.get(pk=outcomes["checkout"])
        assert record.orders.get().status == "paid" and record.payments.get().amount == record.total
        assert record.orders.get().lines.get().quantity == 1
        assert item.stock == 4 and not buyer.cart.lines.exists()
    assert (outcomes["checkout"] is not None) == (first_locker == "checkout")


@pytest.mark.parametrize("run", range(10))
def test_opposite_cart_orders_lock_products_in_ascending_id_order(run):
    low, high = product("low", stock=5), product("high", stock=5)
    buyers = [customer(f"opposite-{run}-{i}") for i in range(2)]
    for buyer, items in zip(buyers, ((low, high), (high, low)), strict=True):
        for item in items:
            add_to_cart(buyer, item.pk)
    reviews = {buyer.pk: cart_review(buyer)["fingerprint"] for buyer in buyers}
    barrier, pids = threading.Barrier(2), {}
    started = {buyer.pk: threading.Event() for buyer in buyers}
    finished = {buyer.pk: threading.Event() for buyer in buyers}

    def buy(buyer):
        def product_gap(execute, sql, params, many, context):
            if "FROM catalogue_product WHERE id=ANY" in sql:
                started[buyer.pk].set()
            return execute(sql, params, many, context)

        barrier.wait(timeout=10)
        with connection.execute_wrapper(product_gap):
            return checkout(buyer, uuid.uuid4(), reviews[buyer.pk]).pk

    with ThreadPoolExecutor(max_workers=2) as pool:
        with transaction.atomic():
            # Hold the higher row so real lock acquisition stops between the two rows.
            # Ascending checkout holds low while waiting; descending checkout leaves it free.
            Product.objects.select_for_update().get(pk=high.pk)
            futures = [
                pool.submit(_on_connection, buyer.pk, pids, finished[buyer.pk], lambda buyer=buyer: buy(buyer))
                for buyer in buyers
            ]
            for buyer in buyers:
                assert started[buyer.pk].wait(10)
                _wait_for_block(pids[buyer.pk], finished[buyer.pk])
            assert len(set(pids.values())) == 2
            with pytest.raises(OperationalError) as caught, transaction.atomic():
                Product.objects.select_for_update(nowait=True).get(pk=low.pk)
            assert isinstance(caught.value.__cause__, errors.LockNotAvailable)
        outcomes = [future.result(timeout=20) for future in futures]
    assert len(set(outcomes)) == 2 and Checkout.objects.count() == 2 and Payment.objects.count() == 2
    assert Order.objects.count() == 4 and OrderLine.objects.count() == 4
    for item in (low, high):
        item.refresh_from_db()
        assert item.stock == 3
        assert list(OrderLine.objects.filter(product=item).values_list("quantity", flat=True)) == [1, 1]
    assert all(not buyer.cart.lines.exists() for buyer in buyers)


def test_seller_suspension_waits_until_checkout_commits():
    buyer, item, operator = customer(), product(stock=5), make_operator()
    add_to_cart(buyer, item.pk)
    review = cart_review(buyer)["fingerprint"]
    waiting_buyer = customer("waiting")
    add_to_cart(waiting_buyer, item.pk)
    waiting_review = cart_review(waiting_buyer)["fingerprint"]
    visible, attempted, release = threading.Event(), threading.Event(), threading.Event()
    finished = {name: threading.Event() for name in ("checkout", "suspend")}
    pids = {}

    def visibility_gap(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if "SELECT id FROM purchasable_product WHERE" in sql:
            visible.set()
            assert release.wait(10)
        return result

    def suspension_gap(execute, sql, params, many, context):
        if '"accounts_seller"' in sql and "FOR UPDATE" in sql:
            attempted.set()
        return execute(sql, params, many, context)

    def buy():
        with transaction.atomic(), connection.execute_wrapper(visibility_gap):
            record = checkout(buyer, uuid.uuid4(), review)
            # Check immediately before the transaction commits, while its locks still apply.
            assert Seller.objects.get(pk=item.seller_id).status == "approved"
        return record.pk

    def suspend():
        with connection.execute_wrapper(suspension_gap):
            return change_seller_status(item.seller_id, "suspend", operator, "Race regression").status

    with ThreadPoolExecutor(max_workers=2) as pool:
        purchase = pool.submit(_on_connection, "checkout", pids, finished["checkout"], buy)
        try:
            assert visible.wait(10)
            suspension = pool.submit(_on_connection, "suspend", pids, finished["suspend"], suspend)
            assert attempted.wait(10)
            _wait_for_block(pids["suspend"], finished["suspend"], pids["checkout"])
        finally:
            release.set()
        checkout_id, status = purchase.result(timeout=20), suspension.result(timeout=20)
    assert status == Seller.Status.SUSPENDED
    item.refresh_from_db()
    assert item.seller.status == Seller.Status.SUSPENDED and item.stock == 4
    record = Checkout.objects.get(pk=checkout_id)
    assert record.orders.get().status == "paid" and record.payments.get().amount == record.total
    # A cart reviewed before suspension cannot buy from that seller after it commits.
    with pytest.raises(CheckoutError, match="no longer available"):
        checkout(waiting_buyer, uuid.uuid4(), waiting_review)
    assert Checkout.objects.count() == 1


def test_checkout_rechecks_seller_after_locking_products():
    buyer, item, replacement = customer(), product(), product("replacement")
    add_to_cart(buyer, item.pk)
    review = cart_review(buyer)["fingerprint"]
    discovered, release, finished = threading.Event(), threading.Event(), threading.Event()
    pids = {}

    def ownership_gap(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if "SELECT DISTINCT p.seller_id FROM orders_cartline" in sql:
            discovered.set()
            assert release.wait(10)
        return result

    def buy():
        with connection.execute_wrapper(ownership_gap):
            return checkout(buyer, uuid.uuid4(), review)

    with ThreadPoolExecutor(max_workers=1) as pool:
        purchase = pool.submit(_on_connection, "checkout", pids, finished, buy)
        try:
            assert discovered.wait(10)
            Product.objects.filter(pk=item.pk).update(seller=replacement.seller)
        finally:
            release.set()
        with pytest.raises(CartChangedError):
            purchase.result(timeout=20)
    assert not Checkout.objects.exists() and not OrderLine.objects.exists() and not Payment.objects.exists()
    item.refresh_from_db()
    assert item.stock == 20 and buyer.cart.lines.count() == 1
