"""Helpers for deterministic PostgreSQL concurrency tests."""

import threading
from contextlib import contextmanager

from django.db import connection


def wait_until_blocked(attempts=100):
    """Wait until another session is blocked on a lock, so a test can release it at exactly the right moment.

    pg_stat_activity is cached for the length of a transaction, so the snapshot is cleared on every poll;
    otherwise a test that polls inside its own transaction never sees the other session.
    """
    for _ in range(attempts):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_stat_clear_snapshot()")
            cursor.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                "AND pid <> pg_backend_pid() AND wait_event_type = 'Lock'"
            )
            if cursor.fetchone()[0]:
                return
        threading.Event().wait(0.1)
    raise AssertionError("no session became blocked on a lock")


@contextmanager
def timestamp_guard_off():
    """Let a test place an order in time by switching the lifecycle timestamp guard off (the owner may; runtime may not)."""
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE orders_order DISABLE TRIGGER order_timestamp_guard")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE orders_order ENABLE TRIGGER order_timestamp_guard")
