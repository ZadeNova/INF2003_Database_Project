import os
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone

from accounts.models import CustomerProfile, Seller
from catalogue.models import Product
from orders.models import Order, OrderLine

MEMBERS = ("chee-long", "erfan", "syahfariz", "jun-keat", "joash")
RELISTED_LABEL = "relisted for demo visibility"
APPLICANT = "demo-applicant"
APPLICANT_SHOP = "Demo applicant shop (generated, pending approval)"


class Command(BaseCommand):
    help = "Create demo logins (including a pending seller) from environment passwords and label two demo stock adjustments."

    def handle(self, *args, **options):
        passwords = {}
        for role in ("customer", "seller", "operator"):
            value = os.environ.get("DEMO_" + role.upper() + "_PASSWORD", "")
            if not value or value.startswith("replace-"):
                raise CommandError("All three DEMO_*_PASSWORD variables must be supplied; no fallback passwords exist.")
            passwords[role] = value
        User = get_user_model()
        with transaction.atomic():
            latest = Order.objects.filter(checkout__olist_order_id__isnull=False).aggregate(latest=Max("placed_at"))["latest"]
            if latest is None:
                raise CommandError("Import Olist before seeding demo accounts.")
            as_of = timezone.localdate(latest)
            start = timezone.make_aware(datetime.combine(as_of - timedelta(days=27), time.min))
            end = timezone.make_aware(datetime.combine(as_of + timedelta(days=1), time.min))
            recent_lines = OrderLine.objects.filter(order__checkout__olist_order_id__isnull=False,
                order__placed_at__gte=start, order__placed_at__lt=end).exclude(order__status="cancelled")
            seller = Seller.objects.filter(user__username="demo-seller").first()
            if seller is None:
                eligible = (Product.objects.values("seller_id").annotate(n=Count("id"))
                            .filter(n__gte=2).values("seller_id"))
                seller = (Seller.objects.filter(status="approved", olist_seller_id__isnull=False, pk__in=eligible,
                                                id__in=recent_lines.values("seller_id"))
                          .annotate(volume=Count("orders")).order_by("-volume", "olist_seller_id").first())
            if seller is None:
                raise CommandError("Import Olist first: a real approved seller with at least two products is required.")
            if User.objects.filter(username="demo-seller").exclude(pk=seller.user_id).exists():
                raise CommandError("demo-seller is already owned by a different account")
            for name in MEMBERS:
                user, _ = User.objects.get_or_create(username="demo-" + name, defaults={"role": "customer"})
                if user.role != "customer":
                    raise CommandError("A demo customer name belongs to another role")
                user.set_password(passwords["customer"])
                user.save()
                CustomerProfile.objects.get_or_create(user=user)
            operator, _ = User.objects.get_or_create(username="demo-operator", defaults={"role": "operator", "is_staff": True})
            if operator.role != "operator":
                raise CommandError("demo-operator belongs to another role")
            operator.set_password(passwords["operator"])
            operator.save()
            # A pending application for the approval demo. Reruns keep any status an operator has decided.
            applicant, _ = User.objects.get_or_create(username=APPLICANT, defaults={"role": "seller"})
            if applicant.role != "seller":
                raise CommandError(APPLICANT + " belongs to another role")
            applicant.set_password(passwords["seller"])
            applicant.save()
            Seller.objects.get_or_create(user=applicant, defaults={
                "status": "pending", "shop_name": APPLICANT_SHOP, "city": "sao paulo", "state": "SP",
                "zip_prefix": "01310", "has_generated_content": True})
            user = seller.user
            if user.role != "seller":
                raise CommandError("Imported seller has an invalid user role")
            user.username = "demo-seller"
            user.set_password(passwords["seller"])
            user.save()
            flagged = seller.products.filter(id__in=recent_lines.values("product_id"), taken_down=False).order_by("id").first()
            sold_out = seller.products.exclude(pk=flagged.pk if flagged else None).filter(taken_down=False).order_by("-active", "id").first()
            if flagged is None or sold_out is None:
                raise CommandError("The demo seller needs two visible products and recent imported demand.")
            for product, stock, lead_time, label in (
                (sold_out, 0, 7, "Demo adjustment: sold out for the later wishlist demonstration"),
                (flagged, 1, 30, "Demo adjustment: low stock and 30-day lead time; recent 28-day imported demand for the later dashboard demonstration"),
            ):
                # Rule 15 derives imported visibility from distinct retained
                # orders. Earlier seeding may already have changed active.
                imported_orders = product.order_lines.filter(
                    order__checkout__olist_order_id__isnull=False).values("order_id").distinct().count()
                if imported_orders < 2 or not product.active or RELISTED_LABEL in product.demo_adjustment:
                    label += "; " + RELISTED_LABEL
                product.stock = stock
                product.lead_time_days = lead_time
                product.active = True
                product.has_generated_content = True
                product.demo_adjustment = label
                product.save(update_fields=["stock", "lead_time_days", "active", "has_generated_content", "demo_adjustment"])
        self.stdout.write("Demo customers: " + ", ".join("demo-" + name for name in MEMBERS))
        self.stdout.write("Demo operator: demo-operator; seller: demo-seller (real high-volume Olist seller); "
                          "pending applicant: " + APPLICANT + ". Passwords were not printed.")
        self.stdout.write("Two products carry explicit demo-adjustment labels; no historical money or orders changed.")
