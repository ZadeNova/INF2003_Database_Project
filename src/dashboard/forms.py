from django import forms
from django.db.models import Count

from accounts.models import Seller
from catalogue.models import Category

SELLER_CHOICES = 50


class DashboardFilters(forms.Form):
    category = forms.ModelChoiceField(
        queryset=Category.objects.order_by("name_en"), required=False, empty_label="All categories"
    )
    seller = forms.TypedChoiceField(
        label="Shop",
        coerce=int,
        empty_value=None,
        required=False,
        help_text=f"Leave on all shops, or pick one of the {SELLER_CHOICES} shops with the most products.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # One small grouped query per page view; the chosen value is still bound as a typed parameter in the SQL.
        top = (
            Seller.objects.filter(status=Seller.Status.APPROVED)
            .annotate(product_count=Count("products"))
            .order_by("-product_count", "pk")[:SELLER_CHOICES]
        )
        self.fields["seller"].choices = [("", "All shops")] + [
            (item.pk, f"{item.display_name} ({item.product_count} products)") for item in top
        ]
