"""The runtime role reads the audit log and fires the audit trigger, but cannot write or tamper with either.

Connected as the actual runtime role (the web service's credentials) to the database pytest is using, so the
rows it sees must be committed: these tests use transactional_db.
"""
import os

import psycopg
import pytest
from django.db import connection
from psycopg import errors, sql

from accounts.models import AuditLog
from config.privileges import grant_runtime
from account_helpers import make_operator, make_seller, runtime_connection

pytestmark = pytest.mark.django_db(transaction=True)
RUNTIME = os.environ["POSTGRES_RUNTIME_USER"]


@pytest.fixture
def runtime():
    with runtime_connection() as conn:
        yield conn


@pytest.fixture
def audited_seller(runtime):
    """A seller approved by the runtime role exactly as the web service does it, leaving one audit row."""
    operator, seller = make_operator(), make_seller(status="pending")
    with runtime.transaction():
        runtime.execute("SELECT set_config('mercer.actor_id', %s, true), set_config('mercer.audit_reason', %s, true)",
                        [str(operator.pk), "Approved by runtime"])
        runtime.execute("UPDATE accounts_seller SET status = %s WHERE id = %s", ["approved", seller.pk])
    return operator, seller


def test_runtime_status_change_writes_the_audit_row_through_the_trigger(runtime, audited_seller):
    operator, seller = audited_seller
    rows = runtime.execute("SELECT action, actor_id, reason, before->>'status', after->>'status' FROM audit_log "
                           "WHERE row_id = %s", [str(seller.pk)]).fetchall()
    assert rows == [("seller.approve", operator.pk, "Approved by runtime", "pending", "approved")]
    # Context is transaction-local: a later runtime change on the same connection is a system change.
    runtime.execute("UPDATE accounts_seller SET status = %s WHERE id = %s", ["suspended", seller.pk])
    assert runtime.execute("SELECT actor_id, reason FROM audit_log WHERE action = %s",
                           ["seller.suspend"]).fetchall() == [(None, None)]


DIRECT_WRITES = [
    "INSERT INTO audit_log (table_name, row_id, action, created_at) VALUES ('accounts_seller', '1', 'forged', now())",
    "UPDATE audit_log SET reason = 'rewritten'",
    "DELETE FROM audit_log",
    "TRUNCATE audit_log",
    "SELECT nextval(pg_get_serial_sequence('audit_log', 'id'))",
    "SELECT setval(pg_get_serial_sequence('audit_log', 'id'), 1)",
    "SELECT currval(pg_get_serial_sequence('audit_log', 'id'))",
]


@pytest.mark.parametrize("statement", DIRECT_WRITES)
def test_runtime_cannot_write_the_audit_log_or_its_sequence_directly(runtime, audited_seller, statement):
    with pytest.raises(errors.InsufficientPrivilege):
        runtime.execute(statement)
    assert AuditLog.objects.count() == 1 and AuditLog.objects.get().reason == "Approved by runtime"


TAMPERING = [
    "CREATE OR REPLACE FUNCTION public.audit_seller_status() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END $$",
    "ALTER FUNCTION public.audit_seller_status() OWNER TO {runtime}",
    "ALTER FUNCTION public.audit_seller_status() SET search_path = pg_temp, public",
    "DROP FUNCTION public.check_seller_status_transition() CASCADE",
    "ALTER TABLE accounts_seller DISABLE TRIGGER seller_status_audit",
    "ALTER TABLE accounts_seller DISABLE TRIGGER USER",
    "DROP TRIGGER seller_status_transition ON accounts_seller",
    "CREATE FUNCTION public.forged() RETURNS integer LANGUAGE sql AS 'SELECT 1'",
    "CREATE TABLE pg_temp.audit_log (id integer)",
    "CREATE SCHEMA forged",
    "SET session_replication_role = replica",
]


@pytest.mark.parametrize("statement", TAMPERING)
def test_runtime_cannot_tamper_with_triggers_functions_or_search_path(runtime, statement):
    with pytest.raises(errors.InsufficientPrivilege):
        runtime.execute(statement.replace("{runtime}", sql.Identifier(RUNTIME).as_string(runtime)))


def test_illegal_transition_is_refused_for_runtime_too(runtime):
    seller = make_seller(status="suspended")
    with pytest.raises(errors.CheckViolation):
        runtime.execute("UPDATE accounts_seller SET status = %s WHERE id = %s", ["pending", seller.pk])


def test_rerunning_the_broad_grants_does_not_restore_audit_writes(runtime, audited_seller):
    with connection.schema_editor() as editor:
        grant_runtime(None, editor)
    for statement in DIRECT_WRITES:
        with pytest.raises(errors.InsufficientPrivilege):
            runtime.execute(statement)
    assert runtime.execute("SELECT count(*) FROM audit_log").fetchone()[0] == 1


def test_trigger_functions_are_owner_owned_with_a_pinned_search_path():
    with connection.cursor() as cursor:
        cursor.execute("""SELECT p.proname, pg_get_userbyid(p.proowner), p.prosecdef, p.proconfig,
                                 has_function_privilege(%s, p.oid, 'EXECUTE')
                          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                          WHERE n.nspname = 'public' AND p.proname IN ('audit_seller_status', 'check_seller_status_transition')
                          ORDER BY p.proname""", [RUNTIME])
        rows = cursor.fetchall()
    owner = os.environ["POSTGRES_USER"]
    assert rows == [("audit_seller_status", owner, True, ["search_path=public, pg_temp"], False),
                    ("check_seller_status_transition", owner, False, ["search_path=public, pg_temp"], False)]


@pytest.mark.parametrize("dbname", ["test", "application"])
def test_runtime_table_privileges_on_the_audit_log(dbname):
    """Checked in pytest's database and, read-only, in the migrated application database."""
    name = connection.settings_dict["NAME"] if dbname == "test" else os.environ["POSTGRES_DB"]
    with psycopg.connect(dbname=name, host=os.environ["POSTGRES_HOST"], port=os.environ["POSTGRES_PORT"],
                         user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"]) as owner:
        if owner.execute("SELECT to_regclass('public.audit_log')").fetchone()[0] is None:
            pytest.fail(f"audit_log is missing in {dbname}: run `docker compose run --rm migrate` first")
        privileges = owner.execute("""SELECT privilege, has_table_privilege(%s, 'public.audit_log', privilege)
                                      FROM unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER']) privilege""",
                                   [RUNTIME]).fetchall()
        sequence = owner.execute("""SELECT has_sequence_privilege(%s, pg_get_serial_sequence('public.audit_log', 'id'), p)
                                    FROM unnest(ARRAY['USAGE','SELECT','UPDATE']) p""", [RUNTIME]).fetchall()
    assert dict(privileges) == {"SELECT": True, "INSERT": False, "UPDATE": False, "DELETE": False,
                                "TRUNCATE": False, "REFERENCES": False, "TRIGGER": False}
    assert sequence == [(False,), (False,), (False,)]
