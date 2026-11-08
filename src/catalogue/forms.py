"""Template-derived fields keep arbitrary request keys out of MongoDB paths and operators."""

from django import forms

from .models import Category


def attribute_text(value):
    return str(value).lower() if isinstance(value, bool) else str(value)


def typed_value(value, kind):
    if kind == "integer":
        return int(value)
    if kind == "boolean":
        if value not in ("true", "false"):
            raise ValueError("Choose yes or no")
        return value == "true"
    return str(value)


def attribute_field(definition, *, required=False):
    kind, values = definition["type"], definition.get("values", [])
    if values or kind == "boolean":
        values = values or [True, False]
        return forms.TypedChoiceField(
            required=required,
            empty_value=None,
            choices=[("", "Any" if not required else "Choose")]
            + [
                (attribute_text(value), "Yes" if value is True else "No" if value is False else str(value))
                for value in values
            ],
            coerce=lambda value: typed_value(value, kind),
        )
    if kind == "integer":
        return forms.IntegerField(required=required, min_value=-(2**31), max_value=2**31 - 1)
    return forms.CharField(required=required, max_length=100)


class SearchForm(forms.Form):
    q = forms.CharField(
        label="Search", required=False, max_length=200, widget=forms.TextInput(attrs={"placeholder": "Find a product"})
    )
    category = forms.ModelChoiceField(
        label="Category", queryset=Category.objects.order_by("name_en"), required=False, empty_label="All categories"
    )
    min_price = forms.DecimalField(
        label="Minimum price (S$)", required=False, min_value=0, max_digits=12, decimal_places=2
    )
    max_price = forms.DecimalField(
        label="Maximum price (S$)", required=False, min_value=0, max_digits=12, decimal_places=2
    )
    rating = forms.TypedChoiceField(
        label="Rating",
        required=False,
        coerce=int,
        empty_value=0,
        choices=[("", "Any rating")] + [(str(score), f"{score} stars and up") for score in range(5, 0, -1)],
    )
    sort = forms.ChoiceField(
        label="Sort",
        required=False,
        choices=[
            ("recommended", "Recommended"),
            ("newest", "Newest"),
            ("price", "Price: low to high"),
            ("price_desc", "Price: high to low"),
            ("top", "Top rated"),
        ],
    )

    def __init__(self, *args, definitions=None, **kwargs):
        super().__init__(*args, **kwargs)
        for name, definition in sorted((definitions or {}).items()):
            self.fields["attr_" + name] = attribute_field(definition)
            self.fields["attr_" + name].label = name.replace("_", " ").capitalize()

    def clean(self):
        cleaned = super().clean()
        low, high = cleaned.get("min_price"), cleaned.get("max_price")
        if low is not None and high is not None and low > high:
            self.add_error("max_price", "Maximum price must be at least the minimum.")
        return cleaned
