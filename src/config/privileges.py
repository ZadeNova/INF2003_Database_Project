"""Install identical owner/runtime separation in application and pytest databases."""
import os

from psycopg import sql

# Tables written only by owner-owned SECURITY DEFINER triggers (accounts plan, P2). Runtime may read them;
# every broad grant below is followed by these revocations so it can never restore a forbidden write.
TRIGGER_WRITTEN_TABLES = ("audit_log",)


def grant_runtime(apps, schema_editor):
    role = os.environ["POSTGRES_RUNTIME_USER"]
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        database = cursor.fetchone()[0]
        cursor.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(database)))
        cursor.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(database), sql.Identifier(role)))
        cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
        cursor.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}").format(sql.Identifier(role)))
        cursor.execute(sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(sql.Identifier(role)))
        cursor.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}").format(sql.Identifier(role)))
        cursor.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {}").format(sql.Identifier(role)))
        # Django creates its migration recorder before the first migration.
        # Web may inspect that history, but only the owner may change it.
        cursor.execute(sql.SQL("REVOKE ALL ON TABLE django_migrations FROM {}").format(sql.Identifier(role)))
        cursor.execute(sql.SQL("GRANT SELECT ON TABLE django_migrations TO {}").format(sql.Identifier(role)))
        cursor.execute("""SELECT n.nspname, c.relname FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE c.oid=pg_get_serial_sequence(%s, %s)::regclass""", ["django_migrations", "id"])
        sequence = cursor.fetchone()
        if sequence:
            cursor.execute(sql.SQL("REVOKE ALL ON SEQUENCE {} FROM {}").format(
                sql.Identifier(*sequence), sql.Identifier(role)))
        restrict_trigger_tables(cursor, role)


def restrict_trigger_tables(cursor, role):
    for table in TRIGGER_WRITTEN_TABLES:
        cursor.execute("SELECT to_regclass(%s)", ["public." + table])
        if cursor.fetchone()[0] is None:  # not created yet; its own migration applies this
            continue
        target = sql.Identifier("public", table)
        cursor.execute(sql.SQL("REVOKE ALL ON TABLE {} FROM {}").format(target, sql.Identifier(role)))
        cursor.execute(sql.SQL("GRANT SELECT ON TABLE {} TO {}").format(target, sql.Identifier(role)))
        cursor.execute("""SELECT n.nspname, c.relname FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE c.oid=pg_get_serial_sequence(%s, %s)::regclass""", ["public." + table, "id"])
        sequence = cursor.fetchone()
        if sequence:
            cursor.execute(sql.SQL("REVOKE ALL ON SEQUENCE {} FROM {}").format(
                sql.Identifier(*sequence), sql.Identifier(role)))


def protect_trigger_tables(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        restrict_trigger_tables(cursor, os.environ["POSTGRES_RUNTIME_USER"])
