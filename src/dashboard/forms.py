from django import forms

from catalogue.models import Category


class DashboardFilters(forms.Form):
    category = forms.ModelChoiceField(queryset=Category.objects.order_by("name_en"), required=False)
    seller = forms.IntegerField(
        label="Seller number",
        min_value=1,
        max_value=2**63 - 1,
        required=False,
        help_text="Optional shop number from the operator's seller list.",
    )
