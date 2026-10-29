from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.validators import RegexValidator

from .audit import AUDIT_LABELS, SELLER_ACTIONS
from .models import AuditLog, User

zip_prefix_validator = RegexValidator(r"^[0-9]{5}$", "Enter the first five digits of the postcode.")
state_validator = RegexValidator(r"^[A-Za-z]{2}$", "Enter the two-letter state code, for example SP.")


class CustomerCreationForm(UserCreationForm):
    """Role, staff and status are never form fields: the view sets the role; anything else posted is ignored.

    The optional location follows Olist: five-digit zip prefix, city and two-letter state.
    """

    zip_prefix = forms.CharField(label="Zip prefix", max_length=5, required=False, validators=[zip_prefix_validator])
    city = forms.CharField(max_length=100, required=False)
    state = forms.CharField(max_length=2, required=False, validators=[state_validator])

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username",)

    def clean_city(self):
        return self.cleaned_data["city"].strip()

    def clean_state(self):
        return self.cleaned_data["state"].upper()


class SellerApplicationForm(CustomerCreationForm):
    shop_name = forms.CharField(max_length=150)
    field_order = ("username", "shop_name", "city", "state", "zip_prefix", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("zip_prefix", "city", "state"):
            self.fields[name].required = True

    def clean_shop_name(self):
        name = self.cleaned_data["shop_name"].strip()
        if not name:
            raise forms.ValidationError("Enter a shop name.")
        return name


class ReasonForm(forms.Form):
    reason = forms.CharField(
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="The seller sees this reason on their status page.",
    )

    def clean_reason(self):
        reason = self.cleaned_data["reason"].strip()
        if not reason:
            raise forms.ValidationError("Give a reason.")
        return reason


class AuditFilterForm(forms.Form):
    """Only the actor and action filters; both are validated choices, never text placed into a query."""

    actor = forms.TypedChoiceField(label="Made by", required=False, coerce=str)
    action = forms.ChoiceField(label="Decision", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        actors = (
            User.objects.filter(pk__in=AuditLog.objects.filter(actor__isnull=False).values("actor_id"))
            .order_by("username")
            .values_list("pk", "username")
        )
        self.fields["actor"].choices = [("", "Anyone"), ("system", "System")] + [(str(pk), name) for pk, name in actors]
        actions = sorted(
            {"seller." + name for name in SELLER_ACTIONS}
            | set(AuditLog.objects.values_list("action", flat=True).distinct())
        )
        self.fields["action"].choices = [("", "Any decision")] + [
            (name, AUDIT_LABELS.get(name, "Updated")) for name in actions
        ]
