from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

from orders.migration_sql import (ORDER_LIFECYCLE, ORDER_LIFECYCLE_REVERSE,
                                  MONEY_INVARIANTS, MONEY_INVARIANTS_REVERSE)


class Migration(migrations.Migration):
    dependencies = [("orders", "0001_initial"), ("accounts", "0002_audit_log")]
    operations = [
        migrations.AddField(model_name="checkout", name="request_fingerprint",
                            field=models.CharField(max_length=64, blank=True, default="", db_default="")),
        migrations.CreateModel(name="Cart", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("customer", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                                             related_name="cart", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="CartLine", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("quantity", models.PositiveIntegerField()),
            ("cart", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="orders.cart")),
            ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cart_lines", to="catalogue.product")),
        ], options={"constraints": [
            models.UniqueConstraint(fields=("cart", "product"), name="cart_product_unique"),
            models.CheckConstraint(condition=models.Q(quantity__gte=1, quantity__lte=999), name="cart_quantity_valid"),
        ]}),
        migrations.RunSQL(ORDER_LIFECYCLE, ORDER_LIFECYCLE_REVERSE),
        migrations.RunSQL(MONEY_INVARIANTS, MONEY_INVARIANTS_REVERSE),
    ]
