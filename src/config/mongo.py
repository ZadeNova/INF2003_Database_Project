"""One MongoDB connection policy for Django and offline tools (no Django import)."""

import atexit
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from config.db_timing import command_listener

REPLICA_SET = "rs0"
_database = ContextVar("mongo_database", default=None)
_clients = {}
_clients_lock = Lock()
# After a connection failure the same client is not tried again for a few seconds: a MongoDB that is down or hung would
# otherwise hold every web worker for the full server-selection timeout on each request, and pages that never touch it
# (the cart, checkout) would queue behind them. Keyed like the pools, so a deliberate outage test cannot affect a healthy one.
BACKOFF_SECONDS = 5.0
_down_until = {}


def connection_options(*, environ=None, direct=False):
    """Keyword arguments for MongoClient. Inside Compose the client follows the replica set; host-side tools
    pass direct=True because the member advertises itself as mongo:27017, a name only containers resolve."""
    env = os.environ if environ is None else environ
    values = {key: env.get(key, "") for key in ("MONGO_APP_USER", "MONGO_APP_PASSWORD", "MONGO_DB")}
    if any(not value or value.startswith("replace-") for value in values.values()):
        raise ValueError("Missing MongoDB connection configuration")
    options = {
        "host": env.get("MONGO_HOST", "mongo"),
        "port": int(env.get("MONGO_PORT", "27017")),
        "username": values["MONGO_APP_USER"],
        "password": values["MONGO_APP_PASSWORD"],
        "authSource": "admin",
        "serverSelectionTimeoutMS": 3000,
        "connectTimeoutMS": 3000,
    }
    # Web workers set this so that no single operation can outlast gunicorn's own timeout; the importer and the other
    # offline tools do not (their operations are long on purpose).
    if env.get("MONGO_SOCKET_TIMEOUT_MS"):
        options["socketTimeoutMS"] = int(env["MONGO_SOCKET_TIMEOUT_MS"])
    if direct:
        options["directConnection"] = True
    else:
        options["replicaSet"] = REPLICA_SET
    return options


@contextmanager
def client(*, environ=None, direct=False):
    """Borrow a process-local pool. Exiting a request never closes other requests' connections.

    Include the process and connection policy in the key: workers do not share a pre-fork client, and a real
    refused-connection outage test cannot accidentally reuse a healthy pool. Database selection stays explicit.
    """
    options = connection_options(environ=environ, direct=direct)
    key = (os.getpid(), tuple(sorted(options.items())))
    if time.monotonic() < _down_until.get(key, 0.0):
        raise ServerSelectionTimeoutError("MongoDB is being skipped for a few seconds after a connection failure")
    with _clients_lock:
        if key not in _clients:
            _clients[key] = MongoClient(**options, event_listeners=[command_listener])
        pooled = _clients[key]
    try:
        yield pooled
    except ConnectionFailure:  # includes a server-selection timeout and a network timeout
        _down_until[key] = time.monotonic() + BACKOFF_SECONDS
        raise


@contextmanager
def database(*, environ=None, direct=False):
    """The application database (or the one a test routed to) from the pooled client: what almost every caller wants."""
    with client(environ=environ, direct=direct) as pooled:
        yield pooled[database_name(environ)]


def close_clients():
    """Release pools at process shutdown, not at the end of a view or management-command context."""
    with _clients_lock:
        for pooled in _clients.values():
            pooled.close()
        _clients.clear()
        _down_until.clear()


atexit.register(close_clients)


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
