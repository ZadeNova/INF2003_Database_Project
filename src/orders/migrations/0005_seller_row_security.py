import os

from django.db import migrations
from psycopg import sql

from orders.migration_sql import SELLER_ROW_SECURITY, SELLER_ROW_SECURITY_REVERSE


def grant_lock(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        role = sql.Identifier(os.environ["POSTGRES_RUNTIME_USER"])
        cursor.execute(sql.SQL("GRANT EXECUTE ON FUNCTION public.lock_checkout_of_order(bigint) TO {}").format(role))


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0004_order_timestamp_guard"),
        ("catalogue", "0004_product_insert_audit"),
        ("accounts", "0002_audit_log"),
    ]
    operations = [
        migrations.RunSQL(SELLER_ROW_SECURITY, SELLER_ROW_SECURITY_REVERSE),
        migrations.RunPython(grant_lock, migrations.RunPython.noop),
    ]
