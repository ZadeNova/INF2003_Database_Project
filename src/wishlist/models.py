from django.conf import settings
from django.db import models
from django.db.models.functions import Now
from django.utils import timezone


class WishlistItem(models.Model):
    pk = models.CompositePrimaryKey("customer_id", "product_id")
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    product = models.ForeignKey("catalogue.Product", on_delete=models.CASCADE)
    added_at = models.DateTimeField(default=timezone.now, db_default=Now())

    class Meta:
        db_table = "wishlist_item"


class RestockAlert(models.Model):
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    product = models.ForeignKey("catalogue.Product", on_delete=models.CASCADE)
    created_at = models.DateTimeField(db_default=Now())
    seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "restock_alert"
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "product"], condition=models.Q(seen_at__isnull=True), name="restock_one_unseen"
            )
        ]
        indexes = [models.Index(fields=["customer", "-created_at"], name="restock_customer_newest")]
