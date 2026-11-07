from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalogue", "0002_product_search_audit")]
    operations = [
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(condition=models.Q(stock__lte=1000000), name="product_stock_capped"),
        ),
    ]
