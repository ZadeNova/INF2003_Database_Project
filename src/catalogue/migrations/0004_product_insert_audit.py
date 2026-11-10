from django.db import migrations

from catalogue.migration_sql import PRODUCT_INSERT_AUDIT, PRODUCT_INSERT_AUDIT_REVERSE


class Migration(migrations.Migration):
    dependencies = [("catalogue", "0003_product_stock_cap")]
    operations = [migrations.RunSQL(PRODUCT_INSERT_AUDIT, PRODUCT_INSERT_AUDIT_REVERSE)]
