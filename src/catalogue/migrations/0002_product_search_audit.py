from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations

from catalogue.migration_sql import PRODUCT_AUDIT, PRODUCT_AUDIT_REVERSE
from config.privileges import protect_trigger_tables


class Migration(migrations.Migration):
    dependencies = [("catalogue", "0001_initial"), ("accounts", "0002_audit_log")]
    operations = [
        TrigramExtension(),
        migrations.AddIndex(model_name="product", index=GinIndex(fields=["name"],
            opclasses=["gin_trgm_ops"], name="product_name_trgm")),
        migrations.RunSQL(PRODUCT_AUDIT, PRODUCT_AUDIT_REVERSE),
        migrations.RunPython(protect_trigger_tables, migrations.RunPython.noop),
    ]
