import re

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower, Now


class User(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER = "customer"
        SELLER = "seller"
        OPERATOR = "operator"

    role = models.CharField(max_length=8, choices=Role.choices, default=Role.CUSTOMER)

    class Meta(AbstractUser.Meta):
        constraints = [
            models.CheckConstraint(condition=Q(role__in=["customer", "seller", "operator"]), name="user_role_valid"),
            # The form refuses a name that differs only in case, but that check and the insert are two steps: two
            # sign-ups at once could both pass it. The database closes the gap.
            models.UniqueConstraint(Lower("username"), name="user_username_ci_unique"),
        ]


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
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["pending", "approved", "rejected", "suspended"]), name="seller_status_valid"
            )
        ]

    @property
    def display_name(self):
        """A readable, still distinct name for imported placeholder shops ("Olist seller 0015a82c" becomes
        "Santo Andre Shop 0015A82C"); stored names and every other shop name are shown unchanged."""
        match = re.fullmatch(r"Olist seller ([0-9a-f]{8})", self.shop_name)
        if self.has_generated_content and match:
            return f"{self.city.title() or 'Imported'} Shop {match.group(1).upper()}"
        return self.shop_name

    @property
    def location(self):
        return ", ".join(part for part in (self.city.title(), self.state) if part)


class AuditLog(models.Model):
    """Written only by owner-owned SECURITY DEFINER triggers; the runtime role may only read it."""

    table_name = models.CharField(max_length=63)
    row_id = models.CharField(max_length=64)  # text, so MongoDB ObjectIds fit as well as bigint ids
    action = models.CharField(max_length=64)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="audit_entries"
    )  # NULL means a system change
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    reason = models.TextField(null=True, blank=True)  # noqa: DJ001 - NULL means no reason was given
    created_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "audit_log"
        indexes = [
            models.Index(F("created_at").desc(), F("id").desc(), name="audit_log_newest"),
            models.Index(fields=["action"], name="audit_log_action"),
            # "The history of this one row" (a seller's status page, an operator's seller detail).
            models.Index(F("table_name"), F("row_id"), F("created_at").desc(), name="audit_log_row_history"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(table_name="") & ~Q(row_id="") & ~Q(action=""), name="audit_log_identity_nonblank"
            ),
            # An operator (non-NULL actor) must give a reason. Both sides are non-NULL so the CHECK cannot pass on NULL.
            models.CheckConstraint(
                condition=Q(actor__isnull=True) | (Q(reason__isnull=False) & Q(reason__regex=r"\S")),
                name="audit_log_actor_reason",
            ),
        ]

    @property
    def action_label(self):
        from .audit import AUDIT_LABELS

        return AUDIT_LABELS.get(self.action, "Updated")

    @property
    def action_tone(self):
        from .audit import AUDIT_TONES

        return AUDIT_TONES.get(self.action, "neutral")


class Geolocation(models.Model):
    zip_prefix = models.CharField(max_length=5, primary_key=True)
    latitude = models.DecimalField(max_digits=11, decimal_places=8)
    longitude = models.DecimalField(max_digits=12, decimal_places=8)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
