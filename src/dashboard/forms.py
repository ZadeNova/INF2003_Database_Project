from django import forms

from catalogue.models import Category
from config.ids import BIGINT_MAX


class DashboardFilters(forms.Form):
    category = forms.ModelChoiceField(queryset=Category.objects.order_by("name_en"), required=False)
    seller = forms.IntegerField(
        label="Seller number",
        min_value=1,
        max_value=BIGINT_MAX,
        required=False,
        help_text="Optional shop number from the operator's seller list.",
    )
