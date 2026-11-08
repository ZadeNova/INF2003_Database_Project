"""Only real PostgreSQL, MongoDB and Redis. Deliberate outages use refused TCP connections."""

import json
import os
from contextlib import contextmanager
from copy import deepcopy
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.db import connection

from config import mongo, redis_store
from config.olist_import import COLLECTIONS

# Redis is on in the whole suite, on its own database index and key prefix. The application's keys (database 0, prefix
# "mercer:") are out of reach: the guard below refuses to clear anything else.
TEST_REDIS_DB = 15
TEST_REDIS_PREFIX = "mercer-test:v1:"


def clear_test_keys(settings):
    if not settings.REDIS_ENABLED:
        return
    assert settings.REDIS_DB == TEST_REDIS_DB and settings.REDIS_KEY_PREFIX == TEST_REDIS_PREFIX, "refusing to clear"
    redis_store.delete_matching("*")


@pytest.fixture(autouse=True)
def redis_isolated(settings):
    settings.REDIS_DB = TEST_REDIS_DB
    settings.REDIS_KEY_PREFIX = TEST_REDIS_PREFIX
    redis_store.reset_for_tests()
    clear_test_keys(settings)
    yield
    redis_store.reset_for_tests()  # a test that broke the connection must not leave a back-off behind
    clear_test_keys(settings)
    redis_store.reset_for_tests()


@pytest.fixture(scope="session")
def mongo_test_database():
    name = "test_" + os.environ["MONGO_DB"]
    call_command("mongo_setup", database=name, stdout=StringIO())
    with mongo.client() as client:
        yield client[name]


@pytest.fixture(autouse=True)
def mongo_db(mongo_test_database):
    # Never touch the application collections during pytest.
    with mongo.using_database(mongo_test_database.name):
        for name in (*COLLECTIONS, "order_review_scores", "events", "photos.files", "photos.chunks"):
            mongo_test_database[name].delete_many({})
        yield mongo_test_database
        for name in (*COLLECTIONS, "order_review_scores", "events", "photos.files", "photos.chunks"):
            mongo_test_database[name].delete_many({})


@pytest.fixture
def imported():
    source = Path("/app/tests/fixtures/olist/clean")
    call_command("import_olist", source=source, stdout=StringIO())
    return json.loads((source / "cleaning_ledger.json").read_text())


@pytest.fixture
def postgres_unavailable(transactional_db):
    @contextmanager
    def unavailable():
        connection.close()
        original = deepcopy(connection.settings_dict)
        connection.settings_dict = {
            **original,
            "HOST": "127.0.0.1",
            "PORT": "1",
            "OPTIONS": {**original["OPTIONS"], "connect_timeout": 1},
        }
        try:
            yield
        finally:
            connection.close()
            connection.settings_dict = original

    return unavailable
