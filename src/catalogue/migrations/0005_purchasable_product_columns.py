from django.db import migrations

from catalogue.migration_sql import PURCHASABLE_ALL_COLUMNS, PURCHASABLE_EXPLICIT_COLUMNS


class Migration(migrations.Migration):
    dependencies = [("catalogue", "0004_product_insert_audit")]
    operations = [migrations.RunSQL(PURCHASABLE_EXPLICIT_COLUMNS, PURCHASABLE_ALL_COLUMNS)]
