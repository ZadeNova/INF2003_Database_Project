"""Dynamic SQL identifiers are psycopg Identifiers, values are bound parameters."""

import pytest
from django.contrib.auth import get_user_model
from django.db import ProgrammingError, connection, transaction

from accounts.models import CustomerProfile
from config.privileges import grant_runtime

pytestmark = pytest.mark.django_db


def test_runtime_role_name_cannot_inject_ddl(monkeypatch):
    user = get_user_model().objects.create_user(username="preserved")
    monkeypatch.setenv("POSTGRES_RUNTIME_USER", 'missing"; DROP TABLE accounts_user; --')
    with pytest.raises(ProgrammingError), transaction.atomic(), connection.schema_editor() as editor:
        grant_runtime(None, editor)
    assert get_user_model().objects.filter(pk=user.pk).exists()


def test_profile_trigger_uses_row_values_without_executing_injected_text():
    payload = "x'); DROP TABLE accounts_user; --"
    user = get_user_model().objects.create_user(username=payload)
    CustomerProfile.objects.create(user=user, city=payload)
    assert CustomerProfile.objects.get(user=user).city == payload
    with pytest.raises(ProgrammingError), transaction.atomic(), connection.cursor() as cursor:
        # The same metadata path used by sequence repair treats a SQL fragment
        # as one relation name. It cannot become a second statement.
        cursor.execute("SELECT pg_get_serial_sequence(%s,%s)", [payload, "id"])
    assert get_user_model().objects.filter(pk=user.pk).exists()
