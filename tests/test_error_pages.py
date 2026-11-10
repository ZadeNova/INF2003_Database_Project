"""Every error a visitor can meet is a branded page that explains what to do and shows nothing internal."""

import pytest
from django.conf import settings
from django.test import Client

pytestmark = pytest.mark.django_db


def test_a_form_sent_without_a_valid_csrf_token_gets_the_branded_page():
    response = Client(enforce_csrf_checks=True).post("/login/", {"username": "alice", "password": "x"})
    page = response.content.decode()
    assert response.status_code == 403
    assert "Your session expired before the form was sent." in page and "DEBUG" not in page
    assert "check your order history" in page  # the order warning, as on the 503 page


def test_a_request_for_an_unknown_host_gets_the_branded_400_page():
    response = Client().get("/", HTTP_HOST="evil.example.com")
    assert response.status_code == 400
    assert "We couldn't understand that request." in response.content.decode()


def test_an_unexpected_failure_gets_the_branded_500_page_without_internals(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr("catalogue.views.visible_products", boom)
    response = Client(raise_request_exception=False).get("/products/")
    page = response.content.decode()
    assert response.status_code == 500
    assert "Something went wrong on our side." in page
    assert "secret internal detail" not in page and "Traceback" not in page and "RuntimeError" not in page


def test_a_request_body_over_the_limit_is_refused_before_it_is_read():
    declared = settings.REQUEST_BODY_LIMIT_BYTES + 1
    response = Client().post("/login/", {"username": "alice", "password": "x"}, CONTENT_LENGTH=str(declared))
    assert response.status_code == 413 and "That request is too large." in response.content.decode()
    assert "no-store" in response["Cache-Control"]


def test_a_photo_upload_at_the_photo_limit_still_fits_under_the_body_limit():
    # The body limit must stay above the 2 MB photo rule plus the form fields around it.
    assert settings.REQUEST_BODY_LIMIT_BYTES >= 2 * 1024 * 1024 + 256 * 1024
