from decimal import Decimal

from django import forms

from .forms import attribute_field, attribute_text, typed_value
from .models import MAX_STOCK, Category, Product


class ProductForm(forms.ModelForm):
    description = forms.CharField(max_length=5000, widget=forms.Textarea(attrs={"rows": 4}))
    photo = forms.FileField(
        required=False,
        help_text="JPEG, PNG or WebP, up to 2 MB.",
        widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
    )
    price = forms.DecimalField(min_value=Decimal("0.01"), max_digits=12, decimal_places=2, label="Price (S$)")
    freight = forms.DecimalField(min_value=0, max_digits=12, decimal_places=2, label="Shipping fee (S$)")
    stock = forms.IntegerField(min_value=0, max_value=MAX_STOCK, help_text="Up to 99,999 units per product.")
    lead_time_days = forms.IntegerField(label="Ready to ship in (days)", min_value=0, max_value=2**31 - 1)
    # What the seller saw when the form was opened. Sales change stock while a form is open, so the service
    # compares these with the live row instead of overwriting it with an old value.
    expected_stock = forms.CharField(required=False, widget=forms.HiddenInput)
    expected_price = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Product
        fields = ["name", "category", "price", "stock", "freight", "lead_time_days"]
        # The category is chosen once, in the selector above the form; the form carries it as a hidden value.
        widgets = {"category": forms.HiddenInput}

    def __init__(self, *args, template=None, spec=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.template = template
        self.fields["category"].queryset = Category.objects.order_by("name_en")
        self.initial["description"] = (spec or {}).get("description", "")
        if self.instance.pk and not self.is_bound:
            self.initial["expected_stock"] = self.instance.stock
            self.initial["expected_price"] = self.instance.price
        for name, definition in sorted((template or {}).get("attributes", {}).items()):
            self.fields["attr_" + name] = attribute_field(definition, required=definition.get("required", False))
            self.fields["attr_" + name].label = name.replace("_", " ").capitalize()
            value = (spec or {}).get("attributes", {}).get(name)
            if value is not None:
                self.initial["attr_" + name] = attribute_text(value)

    def clean_photo(self):
        from .photos import clean_photo

        upload = self.cleaned_data.get("photo")
        return clean_photo(upload) if upload else None

    def clean(self):
        cleaned = super().clean()
        for name, kind in (("stock", int), ("price", Decimal)):
            raw = (cleaned.get("expected_" + name) or "").strip()
            try:
                value = kind(raw) if raw else None
                if isinstance(value, Decimal) and not value.is_finite():  # NaN and Infinity cannot be compared safely
                    raise ValueError
            except (ValueError, ArithmeticError):
                raise forms.ValidationError("This form is out of date. Reload the page and try again.") from None
            cleaned["expected_" + name] = value
        if self.template is None:
            raise forms.ValidationError("This category is temporarily unavailable.")
        if cleaned.get("category") and cleaned["category"].pk != self.template["category_id"]:
            self.add_error("category", "Choose a category and load its options first.")
        allowed = {"attr_" + key for key in self.template["attributes"]}
        if self.is_bound and any(key.startswith("attr_") and key not in allowed for key in self.data):
            raise forms.ValidationError("Some options do not belong to this category. Reload its options.")
        cleaned["attributes"] = {
            name: cleaned["attr_" + name]
            for name in self.template["attributes"]
            if cleaned.get("attr_" + name) is not None and cleaned.get("attr_" + name) != ""
        }
        return cleaned


class TemplateAttributeForm(forms.Form):
    name = forms.RegexField(
        regex=r"^[a-z][a-z0-9_]{0,39}$",
        max_length=40,
        label="Attribute name",
        help_text="Lowercase letters, numbers and underscores, starting with a letter.",
    )
    kind = forms.ChoiceField(
        label="Type", choices=[("string", "Text"), ("integer", "Whole number"), ("boolean", "Yes or no")]
    )
    values = forms.CharField(
        label="Allowed values",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        max_length=3000,
        help_text="One per line. Leave blank for any text or whole number.",
    )

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("kind")
        if kind is None:
            return cleaned
        lines = [line.strip() for line in cleaned.get("values", "").splitlines() if line.strip()]
        if len(lines) > 30 or any(len(line) > 100 for line in lines):
            self.add_error("values", "Use up to 30 values, each no longer than 100 characters.")
            return cleaned
        try:
            values = [typed_value(line, kind) for line in lines]
            if kind == "integer" and any(value < -(2**31) or value >= 2**31 for value in values):
                raise ValueError
        except ValueError:
            self.add_error("values", "Use whole numbers, or true and false for yes or no.")
            return cleaned
        if kind == "boolean" and not values:
            values = [True, False]
        cleaned["definition"] = {"type": kind, "values": list(dict.fromkeys(values))}
        return cleaned
