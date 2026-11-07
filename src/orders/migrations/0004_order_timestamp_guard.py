from django.db import migrations

from orders.migration_sql import ORDER_TIMESTAMP_GUARD, ORDER_TIMESTAMP_GUARD_REVERSE


class Migration(migrations.Migration):
    dependencies = [("orders", "0003_protect_money_deletes")]
    operations = [migrations.RunSQL(ORDER_TIMESTAMP_GUARD, ORDER_TIMESTAMP_GUARD_REVERSE)]
