"""Bench-only connections, durable writes and guarded reset boundaries."""
import os
from contextlib import contextmanager

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from pymongo import MongoClient
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from config.database import connection_parameters
from config.mongo import connection_options

WRITE_CONCERN = WriteConcern(w="majority", j=True)
READ_CONCERN = ReadConcern("snapshot")


def guard():
    if os.environ.get("POSTGRES_HOST") != "bench-db" or os.environ.get("POSTGRES_DB") != "bench" or os.environ.get("MONGO_DB") != "bench":
        raise ValueError("Refusing a benchmark outside the isolated bench services/database")


def pg(name="bench"):
    guard()
    if name not in {"bench", "bench_run", "postgres"}:
        raise ValueError("Unapproved benchmark database")
    conn = psycopg.connect(**{**connection_parameters(), "dbname": name}, autocommit=True, row_factory=dict_row)
    conn.execute("SET statement_timeout = '120s'")
    return conn


@contextmanager
def mongo():
    guard()
    with MongoClient(**connection_options(), w="majority", journal=True, retryReads=False, retryWrites=False) as client:
        yield client.get_database("bench", write_concern=WRITE_CONCERN)


def recreate(name, template):
    if (name, template) not in {("bench_run", "bench_template"), ("bench_template", "bench")}:
        raise ValueError("Unapproved reset target")
    with pg("postgres") as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
        conn.execute(sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(sql.Identifier(name), sql.Identifier(template)))


def settings(database):
    with pg() as conn:
        postgres = {name: conn.execute(sql.SQL("SHOW {}").format(sql.Identifier(name))).fetchone()[name]
                    for name in ("fsync", "synchronous_commit", "full_page_writes", "shared_buffers", "server_version")}
    # The bench user is deliberately readWrite only; serverStatus/getCmdLineOpts require extra privileges.
    # Host run.py obtains the root-only readback with docker exec and never exposes its credentials.
    return {"postgres": postgres, "mongo_write_concern": database.write_concern.document,
            "mongo_transaction_read_concern": READ_CONCERN.document, "mongo_version": database.client.server_info()["version"]}
