"""A separate fixture-loaded Compose bench project, never application or full-data databases."""
from pathlib import Path

import pytest

from benchmarks import db
from benchmarks.state import verify_manifest
from benchmarks.workloads.b5 import mongo_footprint


@pytest.fixture(scope="session")
def source():
    return Path("/app/fixtures/olist/clean")


@pytest.fixture(scope="session")
def database(source):
    with db.mongo() as database:
        provenance = verify_manifest(database, source)
        expected = Path("/app/benchmarks/golden/fixture/source.json").read_text()
        import json
        assert provenance["manifest_sha256"] == json.loads(expected)["manifest_sha256"], "Tests require the separate fixture project"
        yield database


@pytest.fixture
def provenance(database, source):
    return verify_manifest(database, source)


@pytest.fixture(scope="session", autouse=True)
def fresh_storage(database):
    assert database.meta.find_one({"_id": "state"})["restores_since_load"] == 0, "Start tests on a freshly loaded fixture project"
    return mongo_footprint(database)
