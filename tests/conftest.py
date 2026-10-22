"""Only real PostgreSQL and MongoDB. Deliberate outages use refused TCP connections."""
from contextlib import contextmanager
from copy import deepcopy
from io import StringIO
import json
import os
from pathlib import Path

import pytest
from django.core.management import call_command
from django.db import connection

from config import mongo
from config.olist_import import COLLECTIONS


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
        for name in COLLECTIONS:
            mongo_test_database[name].delete_many({})
        yield mongo_test_database
        for name in COLLECTIONS:
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
        connection.settings_dict = {**original, "HOST": "127.0.0.1", "PORT": "1",
                                    "OPTIONS": {**original["OPTIONS"], "connect_timeout": 1}}
        try:
            yield
        finally:
            connection.close()
            connection.settings_dict = original
    return unavailable
