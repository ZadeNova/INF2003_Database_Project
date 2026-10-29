"""Deterministic anomalies. Barriers precede locking reads to avoid deadlocking the demonstration."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from psycopg.errors import SerializationFailure

from benchmarks import db
from benchmarks.workloads.b3 import mongo_transaction

STRATEGIES = {
    "postgres": ("read_committed", "for_update", "serializable"),
    "mongo": ("read_modify_write", "transaction", "atomic_inc"),
}


def demonstrate(engine, strategy, database):
    with db.pg("bench_run") as conn:
        pid = conn.execute("SELECT min(id) AS id FROM catalogue_product").fetchone()["id"]
        conn.execute("UPDATE catalogue_product SET stock=%s WHERE id=%s", [10, pid])
    database.products.update_one({"_id": pid}, {"$set": {"stock": 10}})
    barrier = threading.Barrier(2, timeout=30)

    def worker(index):
        retries, error = 0, None
        started = time.perf_counter_ns()
        try:
            if engine == "postgres":
                with db.pg("bench_run") as conn:
                    while True:
                        try:
                            with conn.transaction():
                                if strategy == "serializable":
                                    conn.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                                if strategy == "for_update":
                                    # Both transactions are ready before the first locking read. Waiting after
                                    # SELECT FOR UPDATE would make the second reader unable to reach a barrier.
                                    barrier.wait()
                                statement = "SELECT stock FROM catalogue_product WHERE id=%s" + (
                                    " FOR UPDATE" if strategy == "for_update" else ""
                                )
                                stock = conn.execute(statement, [pid]).fetchone()["stock"]
                                if strategy != "for_update" and retries == 0:
                                    barrier.wait()
                                conn.execute("UPDATE catalogue_product SET stock=%s WHERE id=%s", [stock - 1, pid])
                            break
                        except SerializationFailure:
                            retries += 1
                            if retries > 20:
                                raise
            elif strategy == "transaction":
                attempts = 0

                def decrement(session):
                    nonlocal attempts
                    stock = database.products.find_one({"_id": pid}, session=session)["stock"]
                    if attempts == 0:
                        attempts += 1
                        barrier.wait()
                    database.products.update_one({"_id": pid}, {"$set": {"stock": stock - 1}}, session=session)

                _, retries = mongo_transaction(database, decrement)
            elif strategy == "atomic_inc":
                barrier.wait()
                database.products.update_one({"_id": pid}, {"$inc": {"stock": -1}})
            else:
                stock = database.products.find_one({"_id": pid})["stock"]
                barrier.wait()
                database.products.update_one({"_id": pid}, {"$set": {"stock": stock - 1}})
        except Exception as exc:
            error = type(exc).__name__
        return {"latency_ns": time.perf_counter_ns() - started, "retries": retries, "error": error}

    started = time.perf_counter_ns()
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(worker, range(2)))
    elapsed = time.perf_counter_ns() - started
    if engine == "postgres":
        with db.pg("bench_run") as conn:
            stock = conn.execute("SELECT stock FROM catalogue_product WHERE id=%s", [pid]).fetchone()["stock"]
    else:
        stock = database.products.find_one({"_id": pid})["stock"]
    expected = 9 if strategy in {"read_committed", "read_modify_write"} else 8
    retries = sum(row["retries"] for row in records)
    passed = stock == expected and not any(row["error"] for row in records)
    if strategy in {"serializable", "transaction"}:
        passed = passed and retries > 0
    return (
        records,
        elapsed,
        passed,
        {"strategy": strategy, "expected_stock": expected, "observed_stock": stock, "retries": retries},
    )
