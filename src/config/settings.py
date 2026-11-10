"""Environment-driven configuration. One local setup: plain HTTP on 127.0.0.1, secrets from the git-ignored .env."""

import os
import re
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from config.database import connection_parameters

ENVIRON = os.environ
BASE_DIR = Path(__file__).resolve().parent.parent


def required(name):
    value = ENVIRON.get(name, "")
    if not value or value.startswith("replace-"):
        raise ImproperlyConfigured(f"{name} must be set to a non-placeholder value")
    return value


def boolean(name, default=False):
    value = ENVIRON.get(name, str(default)).lower()
    if value not in {"true", "false"}:
        raise ImproperlyConfigured(f"{name} must be true or false")
    return value == "true"


DEBUG = boolean("DJANGO_DEBUG")
SECRET_KEY = required("DJANGO_SECRET_KEY")
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must contain at least 50 characters")
RELEASE_ID = ENVIRON.get("APP_RELEASE_ID", "local")
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", RELEASE_ID):
    raise ImproperlyConfigured("APP_RELEASE_ID must be a nonsecret release identifier")
ALLOWED_HOSTS = [v.strip() for v in required("DJANGO_ALLOWED_HOSTS").split(",") if v.strip()]
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("Explicit allowed hosts are required")
CSRF_TRUSTED_ORIGINS = [v.strip() for v in ENVIRON.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if v.strip()]
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "config",
    "accounts",
    "catalogue",
    "orders",
    "reviews",
    "wishlist",
    "dashboard",
    "activity",
]
# Django caps urlencoded bodies but streams a multipart body of any size to disk before any view or form can refuse it.
# A photo is at most 2 MB, so no request needs more than this.
REQUEST_BODY_LIMIT_BYTES = 3 * 1024 * 1024
MIDDLEWARE = [
    "config.middleware.RequestSizeLimitMiddleware",
    "config.middleware.DatabaseUnavailableMiddleware",
    # After DatabaseUnavailableMiddleware so its process_exception sees an exception first (they run in
    # reverse order) and can record the class before the 503 is produced.
    "config.middleware.RequestLoggingMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.role_navigation",
                "wishlist.context_processors.alerts_badge",
            ]
        },
    }
]
try:
    database = connection_parameters(environ=ENVIRON)
except ValueError as error:
    raise ImproperlyConfigured(str(error)) from None
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": database.pop("dbname"),
        "USER": database.pop("user"),
        "PASSWORD": database.pop("password"),
        "HOST": database.pop("host"),
        "PORT": database.pop("port", "5432"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            **database,
            "connect_timeout": 3,
            # Set only on the web service (compose.yaml): lock, statement and idle-in-transaction timeouts.
            **({"options": ENVIRON["POSTGRES_SESSION_OPTIONS"]} if ENVIRON.get("POSTGRES_SESSION_OPTIONS") else {}),
        },
    }
}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en"
TIME_ZONE = "Asia/Singapore"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 1209600
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
# Redis: a cache and a rate limiter, never a source of truth (docs/plans/redis.md). Separate settings rather than a URL,
# because Django's debug page hides settings named like PASSWORD but would show a URL that contains one. With
# REDIS_ENABLED=false the client is never imported and every code path uses the databases.
REDIS_ENABLED = boolean("REDIS_ENABLED", True)
REDIS_HOST = ENVIRON.get("REDIS_HOST", "redis")
REDIS_PORT = int(ENVIRON.get("REDIS_PORT", "6379"))
REDIS_DB = int(ENVIRON.get("REDIS_DB", "0"))
REDIS_USER = ENVIRON.get("REDIS_USER", "mercer")
REDIS_KEY_PREFIX = ENVIRON.get("REDIS_KEY_PREFIX", "mercer:v1:")
if not re.fullmatch(r"mercer[A-Za-z0-9_-]*:v[0-9]+:", REDIS_KEY_PREFIX):
    raise ImproperlyConfigured("REDIS_KEY_PREFIX must look like mercer:v1: (the Redis ACL allows keys named mercer*)")
REDIS_PASSWORD = required("REDIS_PASSWORD") if REDIS_ENABLED else ""
REDIS_TIMEOUT_SECONDS = 0.2  # connect and read; a slow Redis must not slow the shop
REDIS_BACKOFF_SECONDS = 30  # after a connection failure Redis is skipped for this long
# name: (attempts, window in seconds). Logins are counted per username and address before the password is checked;
# the address-wide limit counts failures only and is loose, because many people share one address (Docker, a school).
RATE_LIMITS = {
    "login": (5, 15 * 60),
    "login_ip": (100, 15 * 60),
    "review": (10, 60 * 60),
}
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/products/"
LOGOUT_REDIRECT_URL = "/products/"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# One JSON line per event on standard output (collected by Docker). Only our own request and
# error loggers, Django's 5xx error records and Django's security warnings are routed here; the formatter
# never emits exception messages. Gunicorn's access log stays disabled.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "config.jsonlog.JsonFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "stream": "ext://sys.stdout", "formatter": "json"}},
    "loggers": {
        "mercer": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
