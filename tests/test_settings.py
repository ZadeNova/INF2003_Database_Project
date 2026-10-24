"""Configuration failures must be visible before serving requests."""
import os
import subprocess
import sys

import pytest
from django.conf import settings


@pytest.mark.parametrize("changes, message", [
    ({"DJANGO_SECRET_KEY": ""}, "DJANGO_SECRET_KEY"),
    ({"DJANGO_SECRET_KEY": "short"}, "at least 50"),
    ({"DJANGO_ALLOWED_HOSTS": "*"}, "Explicit allowed hosts"),
    ({"DJANGO_DEBUG": "yes"}, "true or false"),
    ({"APP_RELEASE_ID": "bad\nrelease"}, "APP_RELEASE_ID"),
])
def test_invalid_configuration_fails(changes, message):
    result = subprocess.run([sys.executable, "-c", "import config.settings"],
        env={**os.environ, **changes}, capture_output=True, text=True)
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

def test_debug_is_enabled_only_by_an_explicit_setting():
    result = subprocess.run([sys.executable, "-c", "from config import settings; print(settings.DEBUG)"],
        env={**os.environ, "DJANGO_DEBUG": "true"}, capture_output=True, text=True)
    assert result.stdout.strip() == "True", result.stderr

def test_shared_session_configuration():
    assert settings.SESSION_ENGINE == "django.contrib.sessions.backends.db"
    assert settings.SESSION_COOKIE_HTTPONLY
    assert settings.SESSION_COOKIE_SAMESITE == "Lax"

@pytest.mark.django_db
def test_postgresql_connection_uses_non_superuser():
    from django.db import connection
    assert connection.vendor == "postgresql"
    with connection.cursor() as cursor:
        cursor.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        assert cursor.fetchone() == (False,)


def test_wsgi_startup_emits_only_nonsecret_release_identity():
    import json
    result = subprocess.run([sys.executable, "-c", "import config.wsgi"],
        env={**os.environ, "APP_RELEASE_ID": "fixture-release-123"}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    record = json.loads(result.stdout.strip())
    assert record["logger"] == "mercer.runtime" and record["release"] == "fixture-release-123"
    assert set(record) == {"ts", "level", "logger", "message", "release"}
