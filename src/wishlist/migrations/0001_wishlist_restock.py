import django.db.models.deletion
import django.db.models.functions.datetime
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


TRIGGER = """
CREATE FUNCTION public.alert_product_restock() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $$
BEGIN
    INSERT INTO public.restock_alert(customer_id, product_id, created_at, seen_at)
    SELECT w.customer_id, NEW.id, pg_catalog.now(), NULL
    FROM public.wishlist_item w WHERE w.product_id = NEW.id
    ON CONFLICT (customer_id, product_id) WHERE seen_at IS NULL DO NOTHING;
    RETURN NULL;
END $$;
CREATE TRIGGER product_restock_alert AFTER UPDATE OF stock ON public.catalogue_product
FOR EACH ROW WHEN (OLD.stock = 0 AND NEW.stock > 0)
EXECUTE FUNCTION public.alert_product_restock();
REVOKE EXECUTE ON FUNCTION public.alert_product_restock() FROM PUBLIC;
"""


class Migration(migrations.Migration):
    dependencies = [("catalogue", "0002_product_search_audit"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="WishlistItem", fields=[
            ("pk", models.CompositePrimaryKey("customer_id", "product_id", blank=True, editable=False, primary_key=True, serialize=False)),
            ("added_at", models.DateTimeField(default=django.utils.timezone.now, db_default=django.db.models.functions.datetime.Now())),
            ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="catalogue.product")),
        ], options={"db_table": "wishlist_item"}),
        migrations.CreateModel(name="RestockAlert", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("created_at", models.DateTimeField(db_default=django.db.models.functions.datetime.Now())),
            ("seen_at", models.DateTimeField(null=True, blank=True)),
            ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="catalogue.product")),
        ], options={"db_table": "restock_alert",
            "constraints": [models.UniqueConstraint(fields=["customer", "product"], condition=models.Q(seen_at__isnull=True), name="restock_one_unseen")],
            "indexes": [models.Index(fields=["customer", "-created_at"], name="restock_customer_newest")]}),
        migrations.RunSQL(TRIGGER, "DROP TRIGGER product_restock_alert ON public.catalogue_product; DROP FUNCTION public.alert_product_restock()"),
    ]
