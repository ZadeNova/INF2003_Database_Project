"""Tell PostgreSQL which seller a seller-centre request belongs to (row-level security, docs/plans/seller-rls.md).

The setting is session-level, because seller pages read outside a transaction, so it must never survive into another
request on a reused connection: the seller mixin sets it, renders the response, and releases it in a `finally`.
"""

import logging

from django.db import Error, connection

logger = logging.getLogger("mercer.errors")


def confine_to_seller(seller_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('mercer.seller_id', %s, false)", [str(int(seller_id))])


def release():
    """Clear the setting. If that is impossible (the database has gone), drop the connection: a reconnect starts a fresh
    session without the setting, and the original failure is not replaced by this one."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('mercer.seller_id', '', false)")
    except Error:
        logger.warning("rowsecurity.release_failed")
        connection.close()
