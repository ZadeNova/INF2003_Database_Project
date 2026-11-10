from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalogue", "0005_purchasable_product_columns")]
    operations = [
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(condition=models.Q(lead_time_days__lte=365), name="product_lead_time_capped"),
        ),
    ]
