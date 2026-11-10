"""Real connection failures answer 503; SQL/programming bugs remain 500."""

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, override_settings
from django.urls import path


def broken_query(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT deliberately_missing_column")


def broken_constraint(request):
    get_user_model().objects.create(username="private-sentinel", role="invalid")


urlpatterns = [path("programming/", broken_query), path("constraint/", broken_constraint)]
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize("authenticated", [False, True])
def test_postgres_outage_answers_sanitized_503(postgres_unavailable, authenticated):
    client = Client()
    if authenticated:
        client.force_login(get_user_model().objects.create_user(username="buyer"))
    with postgres_unavailable():
        response = client.get("/products/")
    assert response.status_code == 503 and response["Retry-After"] == "5"
    assert "no-store" in response["Cache-Control"]
    assert "temporarily unavailable" in response.content.decode()
    assert "127.0.0.1" not in response.content.decode()


def test_htmx_request_gets_same_retryable_503(postgres_unavailable):
    with postgres_unavailable():
        response = Client().get("/products/", HTTP_HX_REQUEST="true")
    assert response.status_code == 503 and response["Retry-After"] == "5"


@pytest.mark.parametrize("route", ["/programming/", "/constraint/"])
@override_settings(ROOT_URLCONF=__name__)
def test_real_database_bugs_are_not_treated_as_outages(route):
    response = Client(raise_request_exception=False).get(route)
    assert response.status_code == 500
    assert "private-sentinel" not in response.content.decode()
    assert "deliberately_missing_column" not in response.content.decode()
