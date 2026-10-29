"""The MongoDB application user reaches its own databases only (AGENTS.md rule 5)."""

import os
from uuid import uuid4

import pytest
from pymongo.errors import OperationFailure

from config import mongo


@pytest.fixture
def client():
    with mongo.client() as connection:
        yield connection


@pytest.mark.parametrize("database", [os.environ["MONGO_DB"], "test_" + os.environ["MONGO_DB"]])
def test_app_user_reads_and_writes_its_databases(client, database):
    collection = client[database][f"role_probe_{uuid4().hex[:10]}"]
    try:
        collection.insert_one({"_id": 1, "note": "first"})
        collection.update_one({"_id": 1}, {"$set": {"note": "second"}})
        assert collection.find_one({"_id": 1})["note"] == "second"
    finally:
        collection.drop()


@pytest.mark.parametrize("database", ["admin", "local", "config", "other_app"])
def test_app_user_is_refused_on_any_other_database(client, database):
    with pytest.raises(OperationFailure) as refused:
        client[database]["role_probe"].insert_one({"x": 1})
    assert refused.value.code == 13  # Unauthorized
    with pytest.raises(OperationFailure) as refused:
        client[database]["role_probe"].find_one()
    assert refused.value.code == 13


def test_app_user_cannot_manage_users(client):
    with pytest.raises(OperationFailure):
        client["admin"].command("createUser", "intruder", pwd="x", roles=["root"])


def test_connection_follows_the_replica_set_unless_direct():
    environment = {"MONGO_APP_USER": "u", "MONGO_APP_PASSWORD": "p", "MONGO_DB": "d"}
    assert mongo.connection_options(environ=environment)["replicaSet"] == "rs0"
    direct = mongo.connection_options(environ=environment, direct=True)
    assert direct["directConnection"] is True and "replicaSet" not in direct


@pytest.mark.parametrize("missing", ["MONGO_APP_USER", "MONGO_APP_PASSWORD", "MONGO_DB"])
def test_incomplete_configuration_is_refused(missing):
    environment = {"MONGO_APP_USER": "u", "MONGO_APP_PASSWORD": "p", "MONGO_DB": "d", missing: "replace-me"}
    with pytest.raises(ValueError, match="Missing MongoDB"):
        mongo.connection_options(environ=environment)
