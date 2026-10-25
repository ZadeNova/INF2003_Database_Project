from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.migrations.recorder import MigrationRecorder
from django.test import override_settings
from django.urls import reverse


@pytest.mark.django_db
def test_health_is_safe_and_has_no_database_queries(client,django_assert_num_queries):
    with django_assert_num_queries(0):
        response=client.get(reverse("health"))
        head=client.head(reverse("health"))
    assert response.status_code == head.status_code == 200
    assert response.json() == {"status":"ok"}
    assert response["Cache-Control"] == "no-store" and not head.content and not response.cookies


def test_health_survives_database_failure(client,postgres_unavailable):
    with postgres_unavailable():
        assert client.get("/health/").status_code == 200


def test_health_rejects_mutations(client):
    assert client.post("/health/").status_code == client.delete("/health/").status_code == 405


@override_settings(ALLOWED_HOSTS=["localhost"])
def test_health_validates_host(client):
    assert client.get("/health/",HTTP_HOST="unexpected.example").status_code == 400


@pytest.mark.django_db
def test_database_readiness_command():
    output=StringIO()
    call_command("check_database",stdout=output)
    assert output.getvalue().strip() == '{"postgresql": "ok", "mongodb": "ok", "migrations": "applied"}'


def test_database_failure_is_sanitized(postgres_unavailable):
    with postgres_unavailable(),pytest.raises(CommandError,match=r"^Database unavailable\.$"):
        call_command("check_database")


@pytest.mark.django_db
def test_mongodb_failure_is_sanitized(monkeypatch):
    monkeypatch.setenv("MONGO_HOST","127.0.0.1")
    monkeypatch.setenv("MONGO_PORT","1")
    with pytest.raises(CommandError,match=r"^MongoDB unavailable\.$"):
        call_command("check_database")


@pytest.mark.django_db
def test_pending_migrations_fail_readiness():
    # Remove the actual leaf migration record; the test transaction restores it.
    MigrationRecorder.Migration.objects.filter(app="sessions",name="0001_initial").delete()
    with pytest.raises(CommandError,match="migrations are pending"):
        call_command("check_database")
