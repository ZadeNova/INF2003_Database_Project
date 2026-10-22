"""The runtime role changes rows only; the owner role changes the schema (AGENTS.md rule 5)."""
import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import errors, sql


def connect(user_variable, password_variable):
    return psycopg.connect(dbname=os.environ["POSTGRES_DB"], host=os.environ["POSTGRES_HOST"],
                           port=os.environ["POSTGRES_PORT"], user=os.environ[user_variable],
                           password=os.environ[password_variable], autocommit=True)


@pytest.fixture
def probe_table():
    """A table the owner creates after initialisation, as every migration does."""
    name = f"role_probe_{uuid4().hex[:10]}"
    with connect("POSTGRES_USER", "POSTGRES_PASSWORD") as owner:
        owner.execute(sql.SQL("CREATE TABLE {} (id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY, note text)").format(sql.Identifier(name)))
        try:
            yield name
        finally:
            owner.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(name)))


def test_runtime_role_reads_and_writes_rows_of_tables_created_later(probe_table):
    with connect("POSTGRES_RUNTIME_USER", "POSTGRES_RUNTIME_PASSWORD") as runtime:
        runtime.execute(sql.SQL("INSERT INTO {} (note) VALUES (%s)").format(sql.Identifier(probe_table)), ("first",))
        runtime.execute(sql.SQL("UPDATE {} SET note = %s").format(sql.Identifier(probe_table)), ("second",))
        assert runtime.execute(sql.SQL("SELECT note FROM {}").format(sql.Identifier(probe_table))).fetchall() == [("second",)]
        runtime.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier(probe_table)))


@pytest.mark.parametrize("statement", [
    "CREATE TABLE role_probe_forbidden (id integer)",
    "DROP TABLE {table}",
    "TRUNCATE {table}",
    "ALTER TABLE {table} ADD COLUMN extra integer",
    "CREATE SCHEMA role_probe_forbidden",
])
def test_runtime_role_is_refused_ddl_drop_and_truncate(probe_table, statement):
    with connect("POSTGRES_RUNTIME_USER", "POSTGRES_RUNTIME_PASSWORD") as runtime:
        with pytest.raises(errors.InsufficientPrivilege):
            runtime.execute(sql.SQL(statement).format(table=sql.Identifier(probe_table)))


def test_role_attributes():
    with connect("POSTGRES_USER", "POSTGRES_PASSWORD") as owner:
        rows = dict(owner.execute("""SELECT rolname, rolcreatedb FROM pg_roles
            WHERE NOT rolsuper AND rolname IN (%s, %s)""", (os.environ["POSTGRES_USER"],
                                                           os.environ["POSTGRES_RUNTIME_USER"])).fetchall())
        assert rows == {os.environ["POSTGRES_USER"]: True, os.environ["POSTGRES_RUNTIME_USER"]: False}
        database_owner, = owner.execute("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s",
                                        (os.environ["POSTGRES_DB"],)).fetchone()
        assert database_owner == os.environ["POSTGRES_USER"]


@pytest.mark.parametrize("statement", [
    "INSERT INTO django_migrations (app,name,applied) SELECT app,name,applied FROM django_migrations WHERE false",
    "UPDATE django_migrations SET name=name WHERE false",
    "DELETE FROM django_migrations WHERE false",
    "SELECT nextval(pg_get_serial_sequence('django_migrations','id'))",
])
def test_runtime_role_can_read_but_cannot_change_migration_history(statement):
    with connect("POSTGRES_RUNTIME_USER", "POSTGRES_RUNTIME_PASSWORD") as runtime:
        assert runtime.execute("SELECT count(*) FROM django_migrations").fetchone()[0] > 0
        with pytest.raises(errors.InsufficientPrivilege):
            runtime.execute(statement)
