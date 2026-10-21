"""The connection policy is shared by Django and standalone tools."""
import pytest
from config.database import connection_parameters

BASE = {"POSTGRES_DB": "app", "POSTGRES_USER": "runtime", "POSTGRES_PASSWORD": "test-only",
        "POSTGRES_HOST": "db.example"}


def test_sslmode_is_off_unless_requested():
    assert connection_parameters(environ=BASE)["sslmode"] == "disable"
    assert connection_parameters(environ={**BASE, "POSTGRES_SSLMODE": "require"})["sslmode"] == "require"


@pytest.mark.parametrize("missing", ["POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST"])
def test_missing_or_placeholder_values_are_refused(missing):
    with pytest.raises(ValueError, match="Missing PostgreSQL"):
        connection_parameters(environ={**BASE, missing: ""})
    with pytest.raises(ValueError, match="Missing PostgreSQL"):
        connection_parameters(environ={**BASE, missing: "replace-me"})


def test_dsn_cannot_inject_unreviewed_options():
    dsn = "postgresql://runtime:test-only@db.example/app"
    assert connection_parameters(dsn, environ=BASE)["dbname"] == "app"
    assert connection_parameters(dsn + "?sslmode=require", environ=BASE)["sslmode"] == "require"
    for suffix in ("?hostaddr=127.0.0.1", "?service=other", "?sslrootcert=/tmp/ca.pem"):
        with pytest.raises(ValueError):
            connection_parameters(dsn + suffix, environ=BASE)
    with pytest.raises(ValueError) as error:
        connection_parameters("password=private invalid", environ=BASE)
    assert "private" not in str(error.value)
