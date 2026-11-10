from django.db import migrations

from orders.migration_sql import ORDER_KEY_GUARD, ORDER_KEY_GUARD_REVERSE


class Migration(migrations.Migration):
    dependencies = [("orders", "0005_seller_row_security")]
    operations = [migrations.RunSQL(ORDER_KEY_GUARD, ORDER_KEY_GUARD_REVERSE)]
