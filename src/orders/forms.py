from django import forms

from .models import Order, Payment


class PaymentForm(forms.Form):
    idempotency_key = forms.UUIDField(widget=forms.HiddenInput)
    fingerprint = forms.RegexField(r"^[0-9a-f]{64}$", widget=forms.HiddenInput)
    method = forms.ChoiceField(choices=Payment.Method.choices, label="Payment method")
    instalments = forms.IntegerField(min_value=1, max_value=12, initial=1,
                                    help_text="Credit card: 1 to 12. Other methods: 1.")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("method") != "credit_card" and cleaned.get("instalments", 1) != 1:
            self.add_error("instalments", "Choose 1 for this payment method.")
        return cleaned


class OrderFilterForm(forms.Form):
    status = forms.ChoiceField(required=False, choices=[("", "Any status"), *Order.Status.choices])
    order_id = forms.IntegerField(label="Order number", required=False, min_value=1, max_value=9223372036854775807)

    def apply(self, orders):
        if not self.is_valid():
            return orders.none()
        if self.cleaned_data["status"]:
            orders = orders.filter(status=self.cleaned_data["status"])
        if self.cleaned_data["order_id"]:
            orders = orders.filter(pk=self.cleaned_data["order_id"])
        return orders
