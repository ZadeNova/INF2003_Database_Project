"""The shared form partial must not swallow errors that belong to a hidden field."""

from django import forms
from django.template.loader import render_to_string


class WithHiddenField(forms.Form):
    visible = forms.CharField(required=False)
    token = forms.CharField(widget=forms.HiddenInput)


def render(form):
    return render_to_string("accounts/_form_fields.html", {"form": form})


def test_hidden_fields_render_bare_and_their_errors_stay_visible():
    page = render(WithHiddenField(data={"visible": "x", "token": ""}))
    assert 'type="hidden"' in page and "This field is required." in page
    assert "Token" not in page  # no label block for a hidden field


def test_a_valid_hidden_field_adds_no_error_and_no_visible_block():
    page = render(WithHiddenField(data={"visible": "x", "token": "abc"}))
    assert 'value="abc"' in page and "form-error" not in page and "Token" not in page
