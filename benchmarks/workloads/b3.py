"""Fifty buyers and ten units, on real app constraints, with two PostgreSQL trigger variants."""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

from bson import Decimal128
from psycopg import sql

from benchmarks import db
from benchmarks.concurrency import PreparedRun

TABLES = ("catalogue_product", "orders_checkout", "orders_order", "orders_orderline", "orders_payment")


def mongo_transaction(database, callback):
    retries = 0
    deadline = time.monotonic() + 120
    with database.client.start_session() as session:
        while True:
            try:
                with session.start_transaction(read_concern=db.READ_CONCERN, write_concern=db.WRITE_CONCERN):
                    result = callback(session)
                    while True:
                        try:
                            session.commit_transaction()
                            return result, retries
                        except Exception as exc:
                            if not getattr(exc, "has_error_label", lambda label: False)("UnknownTransactionCommitResult") or time.monotonic() >= deadline:
                                raise
                            retries += 1
            except Exception as exc:
                if not getattr(exc, "has_error_label", lambda label: False)("TransientTransactionError") or time.monotonic() >= deadline:
                    raise
                retries += 1


def race(engine, clients, triggers, database):
    now = datetime.now(timezone.utc)
    with db.pg("bench_run") as conn:
        product = conn.execute("SELECT id,seller_id,price FROM catalogue_product ORDER BY id LIMIT 1").fetchone()
        customer = conn.execute("SELECT id FROM accounts_user WHERE role=%s ORDER BY id LIMIT 1", ["customer"]).fetchone()["id"]
        old_orders = conn.execute("SELECT max(id) AS id FROM orders_order").fetchone()["id"]
        if not triggers:
            for table in TABLES:
                conn.execute(sql.SQL("ALTER TABLE {} DISABLE TRIGGER USER").format(sql.Identifier(table)))
        conn.execute("UPDATE catalogue_product SET stock=%s WHERE id=%s", [10, product["id"]])
        assert conn.execute("SELECT stock FROM catalogue_product WHERE id=%s", [product["id"]]).fetchone()["stock"] == 10
    database.products.update_one({"_id": product["id"]}, {"$set": {"stock": 10}})
    assert database.products.find_one({"_id": product["id"]})["stock"] == 10

    prepared = PreparedRun(clients)

    def worker(worker_id):
        try:
            resource = db.pg("bench_run") if engine == "postgres" else db.mongo()
            with resource as conn:
                if engine == "postgres":
                    conn.execute("SELECT 1").fetchone()
                else:
                    conn.command("ping")
                ready_at = prepared.connected()
                prepared.begin()
                return buy_all(conn, worker_id, ready_at)
        except BaseException:
            prepared.abort()
            raise

    def buy_all(conn, worker_id, ready_at):
        records = []
        for buyer in range(worker_id, 50, clients):
            wall_started = time.time_ns()
            started = time.perf_counter_ns()
            retries, error, success = 0, None, False
            try:
                if engine == "postgres":
                    with conn.transaction():
                        row = conn.execute("UPDATE catalogue_product SET stock=stock-1 WHERE id=%s AND stock>=1 RETURNING id", [product["id"]]).fetchone()
                        if row:
                            checkout = conn.execute("INSERT INTO orders_checkout(customer_id,placed_at,total,idempotency_key) VALUES (%s,%s,%s,%s) RETURNING id",
                                                    [customer, now, product["price"], uuid4()]).fetchone()["id"]
                            order = conn.execute("""INSERT INTO orders_order(checkout_id,seller_id,status,items,freight,total,placed_at,paid_at,estimated_delivery)
                                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                                 [checkout, product["seller_id"], "paid", product["price"], 0, product["price"], now, now, now]).fetchone()["id"]
                            conn.execute("INSERT INTO orders_orderline(order_id,seller_id,product_id,quantity,unit_price,freight) VALUES (%s,%s,%s,%s,%s,%s)",
                                         [order, product["seller_id"], product["id"], 1, product["price"], 0])
                            conn.execute("INSERT INTO orders_payment(checkout_id,sequence,method,instalments,amount) VALUES (%s,%s,%s,%s,%s)",
                                         [checkout, 1, "voucher", 1, product["price"]])
                            success = True
                else:
                    def buy(session):
                        changed = conn.products.update_one({"_id": product["id"], "stock": {"$gte": 1}}, {"$inc": {"stock": -1}}, session=session)
                        if not changed.modified_count:
                            return False
                        conn.orders.insert_one({"_id": "race-" + str(buyer), "seller_id": product["seller_id"], "paid_amount": Decimal128(product["price"]),
                            "lines": [{"product_id": product["id"], "quantity": 1, "unit_price": Decimal128(product["price"]), "freight": Decimal128("0")}],
                            "bench_run": True}, session=session)
                        return True
                    success, retries = mongo_transaction(conn, buy)
            except Exception as exc:
                error = type(exc).__name__
            records.append({"latency_ns": time.perf_counter_ns() - started, "retries": retries, "error": error, "success": success,
                            "worker": worker_id, "started_at_ns": wall_started, "ended_at_ns": time.time_ns(), "connection_ready_at_ns": ready_at})
        return records, time.perf_counter_ns()

    # Each worker retains its connection; the same fifty buyers run at every concurrency.
    with ThreadPoolExecutor(max_workers=clients) as pool:
        groups = list(pool.map(worker, range(clients)))
    records = [record for group, finished in groups for record in group]
    elapsed = max(finished for group, finished in groups) - prepared.started_ns
    successes = sum(row["success"] for row in records)
    refusals = sum(not row["success"] and row["error"] is None for row in records)
    if engine == "postgres":
        with db.pg("bench_run") as conn:
            stock = conn.execute("SELECT stock FROM catalogue_product WHERE id=%s", [product["id"]]).fetchone()["stock"]
            orders = conn.execute("SELECT count(*) AS n FROM orders_order WHERE id>%s", [old_orders]).fetchone()["n"]
            unbalanced = conn.execute("""SELECT o.id FROM orders_order o JOIN orders_checkout c ON c.id=o.checkout_id
                JOIN orders_payment p ON p.checkout_id=c.id JOIN orders_orderline l ON l.order_id=o.id
                WHERE o.id>%s AND (o.total<>c.total OR p.amount<>c.total OR l.quantity*l.unit_price+l.freight<>o.total)""", [old_orders]).fetchall()
            trigger_state = conn.execute("""SELECT c.relname,t.tgname,t.tgenabled FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
                WHERE c.relname=ANY(%s) AND NOT t.tgisinternal ORDER BY c.relname,t.tgname""", [list(TABLES)]).fetchall()
    else:
        stock = database.products.find_one({"_id": product["id"]})["stock"]
        added = list(database.orders.find({"bench_run": True}))
        orders = len(added)
        unbalanced = [o["_id"] for o in added if sum(line["quantity"] * line["unit_price"].to_decimal() + line["freight"].to_decimal() for line in o["lines"]) != o["paid_amount"].to_decimal()]
        trigger_state = None
    evidence = {"successes": successes, "refusals": refusals, "stock": stock, "orders": orders, "unbalanced": unbalanced, "trigger_state": trigger_state}
    passed = successes == 10 and refusals == 40 and stock == 0 and orders == 10 and not unbalanced and not any(r["error"] for r in records)
    return records, elapsed, passed, evidence
