from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Now


class User(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER = "customer"
        SELLER = "seller"
        OPERATOR = "operator"

    role = models.CharField(max_length=8, choices=Role.choices, default=Role.CUSTOMER)

    class Meta(AbstractUser.Meta):
        constraints = [models.CheckConstraint(condition=Q(role__in=["customer", "seller", "operator"]), name="user_role_valid")]


class CustomerProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="customer_profile")
    olist_customer_unique_id = models.CharField(max_length=32, unique=True, null=True, blank=True)
    zip_prefix = models.CharField(max_length=5, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=2, blank=True)


class Seller(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        APPROVED = "approved"
        REJECTED = "rejected"
        SUSPENDED = "suspended"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="seller")
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.PENDING)
    shop_name = models.CharField(max_length=150)
    olist_seller_id = models.CharField(max_length=32, unique=True, null=True, blank=True)
    zip_prefix = models.CharField(max_length=5, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=2, blank=True)
    has_generated_content = models.BooleanField(default=False)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(status__in=["pending", "approved", "rejected", "suspended"]), name="seller_status_valid")]


class AuditLog(models.Model):
    """Written only by owner-owned SECURITY DEFINER triggers; the runtime role may only read it."""
    table_name = models.CharField(max_length=63)
    row_id = models.CharField(max_length=64)  # text, so MongoDB ObjectIds fit as well as bigint ids
    action = models.CharField(max_length=64)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                              related_name="audit_entries")  # NULL means a system change
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "audit_log"
        indexes = [models.Index(F("created_at").desc(), F("id").desc(), name="audit_log_newest"),
                   models.Index(fields=["action"], name="audit_log_action")]
        constraints = [
            models.CheckConstraint(condition=~Q(table_name="") & ~Q(row_id="") & ~Q(action=""), name="audit_log_identity_nonblank"),
            # An operator (non-NULL actor) must give a reason. Both sides are non-NULL so the CHECK cannot pass on NULL.
            models.CheckConstraint(condition=Q(actor__isnull=True) | (Q(reason__isnull=False) & Q(reason__regex=r"\S")),
                                   name="audit_log_actor_reason"),
        ]


class Geolocation(models.Model):
    zip_prefix = models.CharField(max_length=5, primary_key=True)
    latitude = models.DecimalField(max_digits=11, decimal_places=8)
    longitude = models.DecimalField(max_digits=12, decimal_places=8)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
