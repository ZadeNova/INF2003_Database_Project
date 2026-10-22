"""One MongoDB connection policy for Django and offline tools (no Django import)."""
import os
from contextlib import contextmanager
from contextvars import ContextVar
from pymongo import MongoClient

REPLICA_SET = "rs0"
_database = ContextVar("mongo_database", default=None)


def connection_options(*, environ=None, direct=False):
    """Keyword arguments for MongoClient. Inside Compose the client follows the replica set; host-side tools
    pass direct=True because the member advertises itself as mongo:27017, a name only containers resolve."""
    env = os.environ if environ is None else environ
    values = {key: env.get(key, "") for key in ("MONGO_APP_USER", "MONGO_APP_PASSWORD", "MONGO_DB")}
    if any(not value or value.startswith("replace-") for value in values.values()):
        raise ValueError("Missing MongoDB connection configuration")
    options = {
        "host": env.get("MONGO_HOST", "mongo"), "port": int(env.get("MONGO_PORT", "27017")),
        "username": values["MONGO_APP_USER"], "password": values["MONGO_APP_PASSWORD"],
        "authSource": "admin", "serverSelectionTimeoutMS": 3000,
    }
    if direct:
        options["directConnection"] = True
    else:
        options["replicaSet"] = REPLICA_SET
    return options


def client(*, environ=None, direct=False):
    return MongoClient(**connection_options(environ=environ, direct=direct))


def database_name(environ=None):
    return _database.get() or (os.environ if environ is None else environ)["MONGO_DB"]


@contextmanager
def using_database(name):
    """Explicit test routing; never replace a real database with a mock."""
    allowed = {os.environ["MONGO_DB"], "test_" + os.environ["MONGO_DB"]}
    if name not in allowed:
        raise ValueError("MongoDB database must be the configured application or test database")
    token = _database.set(name)
    try:
        yield
    finally:
        _database.reset(token)
