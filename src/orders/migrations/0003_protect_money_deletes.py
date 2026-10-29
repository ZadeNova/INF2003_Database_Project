from django.db import migrations

from config.privileges import protect_money_tables


class Migration(migrations.Migration):
    dependencies = [("orders", "0002_checkout")]
    operations = [migrations.RunPython(protect_money_tables, migrations.RunPython.noop)]
