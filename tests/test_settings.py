"""Configuration failures must be visible before serving requests."""

import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"DJANGO_SECRET_KEY": ""}, "DJANGO_SECRET_KEY"),
        ({"DJANGO_SECRET_KEY": "short"}, "at least 50"),
        ({"DJANGO_ALLOWED_HOSTS": "*"}, "Explicit allowed hosts"),
        ({"DJANGO_DEBUG": "yes"}, "true or false"),
        ({"APP_RELEASE_ID": "bad\nrelease"}, "APP_RELEASE_ID"),
        ({"REDIS_ENABLED": "flase"}, "REDIS_ENABLED must be true or false"),
        ({"REDIS_ENABLED": "true", "REDIS_PASSWORD": ""}, "REDIS_PASSWORD"),
        ({"REDIS_KEY_PREFIX": "other:v1:"}, "REDIS_KEY_PREFIX"),
    ],
)
def test_invalid_configuration_fails(changes, message):
    result = subprocess.run(
        [sys.executable, "-c", "import config.settings"], env={**os.environ, **changes}, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert message in result.stderr


def test_local_configuration():
    code = """from django.conf import settings as s
assert not s.DEBUG
assert not s.SESSION_COOKIE_SECURE and not s.CSRF_COOKIE_SECURE
assert not s.SECURE_SSL_REDIRECT and not s.SECURE_HSTS_SECONDS
assert s.SECURE_PROXY_SSL_HEADER is None
assert s.DATABASES['default']['OPTIONS']['sslmode'] == 'disable'
"""
    result = subprocess.run([sys.executable, "-c", code], env=os.environ, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_postgresql_session_options_are_applied_only_when_asked_for():
    code = """from django.conf import settings as s
print(s.DATABASES['default']['OPTIONS'].get('options'))
"""
    options = "-c lock_timeout=10s -c statement_timeout=25s -c idle_in_transaction_session_timeout=60s"
    base = {key: value for key, value in os.environ.items() if key != "POSTGRES_SESSION_OPTIONS"}
    plain = subprocess.run([sys.executable, "-c", code], env=base, capture_output=True, text=True)
    asked = subprocess.run(
        [sys.executable, "-c", code], env={**base, "POSTGRES_SESSION_OPTIONS": options}, capture_output=True, text=True
    )
    assert plain.stdout.strip() == "None" and asked.stdout.strip() == options, plain.stderr + asked.stderr


@pytest.mark.django_db
def test_the_web_services_timeouts_are_real_postgresql_settings_for_the_runtime_role():
    import psycopg
    from account_helpers import runtime_connection
    from django.db import connection

    options = "-c lock_timeout=10s -c statement_timeout=25s -c idle_in_transaction_session_timeout=60s"
    with runtime_connection() as plain:
        assert plain.execute("SHOW lock_timeout").fetchone() == ("0",)  # no limit without the options
    with psycopg.connect(
        dbname=connection.settings_dict["NAME"],
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        user=os.environ["POSTGRES_RUNTIME_USER"],
        password=os.environ["POSTGRES_RUNTIME_PASSWORD"],
        options=options,
    ) as limited:
        names = ("lock_timeout", "statement_timeout", "idle_in_transaction_session_timeout")
        assert [limited.execute(f"SHOW {name}").fetchone()[0] for name in names] == ["10s", "25s", "1min"]


def test_debug_is_enabled_only_by_an_explicit_setting():
    result = subprocess.run(
        [sys.executable, "-c", "from config import settings; print(settings.DEBUG)"],
        env={**os.environ, "DJANGO_DEBUG": "true"},
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "True", result.stderr


def test_redis_may_be_disabled_without_a_password_and_the_client_is_then_never_imported():
    code = """import sys
from django.conf import settings as s
from config import redis_store
assert not s.REDIS_ENABLED and s.REDIS_PASSWORD == ''
assert redis_store.window_hit('login', 'x', 1, 60).allowed and redis_store.window_hit('login', 'x', 1, 60).allowed
assert redis_store.dashboard_version() is None
assert 'redis' not in sys.modules
"""
    environment = {
        **os.environ,
        "REDIS_ENABLED": "false",
        "REDIS_PASSWORD": "",
        "DJANGO_SETTINGS_MODULE": "config.settings",
    }
    setup = "import django; django.setup()\n"
    result = subprocess.run([sys.executable, "-c", setup + code], env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.django_db
def test_postgresql_connection_uses_non_superuser():
    from django.db import connection

    assert connection.vendor == "postgresql"
    with connection.cursor() as cursor:
        cursor.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        assert cursor.fetchone() == (False,)


def test_wsgi_startup_emits_only_nonsecret_release_identity():
    import json

    result = subprocess.run(
        [sys.executable, "-c", "import config.wsgi"],
        env={**os.environ, "APP_RELEASE_ID": "fixture-release-123"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    record = json.loads(result.stdout.strip())
    assert record["logger"] == "mercer.runtime" and record["release"] == "fixture-release-123"
    assert set(record) == {"ts", "level", "logger", "message", "release"}
