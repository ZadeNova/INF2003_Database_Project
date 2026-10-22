from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import Q


class Category(models.Model):
    slug = models.SlugField(max_length=100, unique=True)
    name_en = models.CharField(max_length=100)
    name_pt = models.CharField(max_length=100)
    icon = models.CharField(max_length=32, default="package")
    hand_translated = models.BooleanField(default=False)

    def __str__(self):
        return self.name_en


class Product(models.Model):
    seller = models.ForeignKey("accounts.Seller", on_delete=models.PROTECT, related_name="products")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    olist_product_id = models.CharField(max_length=32, null=True, blank=True)
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    freight = models.DecimalField(max_digits=12, decimal_places=2)
    stock = models.PositiveIntegerField()
    lead_time_days = models.PositiveIntegerField()
    weight_g = models.PositiveIntegerField(null=True, blank=True)
    length_cm = models.PositiveIntegerField(null=True, blank=True)
    height_cm = models.PositiveIntegerField(null=True, blank=True)
    width_cm = models.PositiveIntegerField(null=True, blank=True)
    active = models.BooleanField(default=True)
    featured = models.BooleanField(default=False)
    taken_down = models.BooleanField(default=False)
    taken_down_reason = models.TextField(blank=True, default="")
    has_generated_content = models.BooleanField(default=False)
    demo_adjustment = models.TextField(blank=True, default="")

    class Meta:
        indexes = [GinIndex(fields=["name"], opclasses=["gin_trgm_ops"], name="product_name_trgm")]
        constraints = [
            models.UniqueConstraint(fields=["seller", "olist_product_id"], name="product_source_seller_unique"),
            models.UniqueConstraint(fields=["id", "seller"], name="product_id_seller_unique"),
            models.CheckConstraint(condition=Q(price__gt=0, price__lte="9999999999.99"), name="product_price_positive_finite"),
            models.CheckConstraint(condition=Q(freight__gte=0, freight__lte="9999999999.99"), name="product_freight_nonnegative_finite"),
        ]

    @property
    def display_price(self):
        return f"S${self.price:.2f}"


class PurchasableProduct(models.Model):
    """Read-only IDs from the canonical visibility view; use as an ORM subquery."""
    id = models.BigIntegerField(primary_key=True)

    class Meta:
        managed = False
        db_table = "purchasable_product"
        default_permissions = ()
