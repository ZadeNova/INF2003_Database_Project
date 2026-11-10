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


class WithHelpAndErrors(forms.Form):
    name = forms.CharField(help_text="Letters only.")


def test_every_id_a_field_points_at_with_aria_describedby_exists_on_the_page():
    import re

    page = str(WithHelpAndErrors(data={"name": ""})["name"]) + render(WithHelpAndErrors(data={"name": ""}))
    pointed_at = re.search(r'aria-describedby="([^"]+)"', page).group(1).split()
    assert len(pointed_at) == 2  # the help text and the error
    for element_id in pointed_at:
        assert f'id="{element_id}"' in page, element_id


def test_a_valid_hidden_field_adds_no_error_and_no_visible_block():
    page = render(WithHiddenField(data={"visible": "x", "token": "abc"}))
    assert 'value="abc"' in page and "form-error" not in page and "Token" not in page
