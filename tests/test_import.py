"""COPY import, failure rollback and injection negatives on the real two-store fixture."""
from io import StringIO
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil

import psycopg
from psycopg import sql
import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction

from catalogue.models import Product
from orders.models import Checkout, Payment, Refund, Order
from config.olist_import import TABLES, COLLECTIONS, sql_invariants, reconcile

pytestmark = pytest.mark.django_db(transaction=True)
SOURCE = Path("/app/tests/fixtures/olist/clean")
PAYLOAD = "x'); DROP TABLE accounts_user; --"


def refresh_checksums(path):
    content = "".join(hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n" for p in sorted(path.iterdir()) if p.name != "checksums.txt")
    (path / "checksums.txt").write_text(content,encoding="utf-8")


def alter_csv(path, table, field, value):
    file = path / (table + ".csv")
    with file.open(newline="",encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    rows[0][field] = value
    with file.open("w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fields,lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    refresh_checksums(path)


@pytest.fixture
def source(tmp_path):
    target = tmp_path / "clean"
    shutil.copytree(SOURCE,target)
    return target


def assert_empty(mongo_db):
    assert all(not model.objects.exists() for model in TABLES.values())
    assert all(mongo_db[name].count_documents({}) == 0 for name in COLLECTIONS)
    with connection.cursor() as cursor:
        cursor.execute("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal AND tgenabled='D'")
        assert cursor.fetchall() == []


def test_import_reconciles_money_ownership_and_mongo_references(imported,mongo_db):
    assert set(sql_invariants().values()) == {0}
    reconcile(mongo_db,imported)
    assert Product.objects.count() == imported["output_counts"]["products"]
    assert Refund.objects.count() == Order.objects.filter(status="cancelled").count()
    assert all(not u.has_usable_password() for u in get_user_model().objects.all())
    assert mongo_db.reviews.count_documents({"from_order_review": True}) > 0


def test_sequences_are_repaired_for_every_loaded_identity(imported):
    with connection.cursor() as cursor:
        for model in TABLES.values():
            if model._meta.pk.column != "id":
                continue
            cursor.execute("SELECT pg_get_serial_sequence(%s,%s)",[model._meta.db_table,"id"])
            sequence=cursor.fetchone()[0]
            cursor.execute("SELECT nextval(%s::regclass)",[sequence])
            maximum = model.objects.order_by("-id").values_list("id",flat=True).first() or 0
            assert cursor.fetchone()[0] > maximum


def test_import_refuses_nonempty_database_without_changing_data(imported,mongo_db):
    before=(get_user_model().objects.count(),mongo_db.reviews.count_documents({}))
    with pytest.raises(CommandError,match="empty database"):
        call_command("import_olist",source=SOURCE,stdout=StringIO())
    assert before==(get_user_model().objects.count(),mongo_db.reviews.count_documents({}))


def test_import_refuses_nonempty_mongo_database(mongo_db):
    mongo_db.platform_stats.insert_one({"_id":"bayesian","m": __import__("bson").Decimal128("4"),"C":__import__("bson").Decimal128("2")})
    with pytest.raises(CommandError,match="empty MongoDB"):
        call_command("import_olist",source=SOURCE,stdout=StringIO())
    assert not get_user_model().objects.exists()
    assert mongo_db.platform_stats.count_documents({}) == 1


def test_import_cannot_commit_mongo_inside_some_other_postgres_transaction(mongo_db):
    with transaction.atomic(),pytest.raises(CommandError,match="must own its transaction"):
        call_command("import_olist",source=SOURCE,stdout=StringIO())
    assert_empty(mongo_db)


@pytest.mark.parametrize("table,field,value,invariant",[("checkouts","total","999.99","payment_totals"),("refunds","amount","0.01","refund_totals")])
def test_invariant_failure_reports_diagnostic_rows_and_rolls_back(source,mongo_db,table,field,value,invariant):
    alter_csv(source,table,field,value)
    with pytest.raises(CommandError,match="Invariant "+invariant+" failed; diagnostic rows:") as error:
        call_command("import_olist",source=source,stdout=StringIO())
    assert '"id"' in str(error.value)
    assert_empty(mongo_db)


def test_malformed_copy_value_is_data_not_sql_and_restores_triggers(source,mongo_db):
    alter_csv(source,"products","price",PAYLOAD)
    with pytest.raises(CommandError,match="Import failed") as error:
        call_command("import_olist",source=source,stdout=StringIO())
    assert isinstance(error.value.__cause__, psycopg.Error)
    assert error.value.__cause__.sqlstate == "22P02"
    assert_empty(mongo_db)
    # Retry of the valid data is safe after the failed transaction.
    call_command("import_olist",source=SOURCE,stdout=StringIO())
    assert Product.objects.exists()


def test_injection_text_survives_copy_as_literal_data_through_all_sql_stages(source,mongo_db):
    alter_csv(source,"products","name",PAYLOAD)
    call_command("import_olist",source=source,stdout=StringIO())
    assert Product.objects.order_by("id").first().name == PAYLOAD
    assert get_user_model().objects.count() > 0
    assert set(sql_invariants().values()) == {0}


def test_file_controlled_sql_header_is_rejected(source,mongo_db):
    path=source/"products.csv"
    path.write_text(path.read_text().replace("name,",PAYLOAD+",",1),encoding="utf-8")
    refresh_checksums(source)
    with pytest.raises(CommandError,match="Unexpected CSV header"):
        call_command("import_olist",source=source,stdout=StringIO())
    assert_empty(mongo_db)


def test_checksum_path_injection_is_rejected(source,mongo_db):
    with (source/"checksums.txt").open("a") as stream:
        stream.write("0"*64+"  ../../.env\n")
    with pytest.raises(CommandError,match="Invalid checksums manifest"):
        call_command("import_olist",source=source,stdout=StringIO())
    assert_empty(mongo_db)


def test_source_path_with_sql_metacharacters_is_only_a_filesystem_path(source,tmp_path):
    target=tmp_path/'source"; DROP TABLE accounts_user; --'
    source.rename(target)
    call_command("import_olist",source=target,stdout=StringIO())
    assert Product.objects.exists()


def test_mongo_reference_failure_rolls_back_both_databases(source,mongo_db):
    path=source/"product_specs.ndjson"
    rows=path.read_text().splitlines()
    row=json.loads(rows[0]);row["category_id"]=999999
    rows[0]=json.dumps(row)
    path.write_text("\n".join(rows)+"\n",encoding="utf-8")
    refresh_checksums(source)
    with pytest.raises(CommandError,match="mongo_product_reference"):
        call_command("import_olist",source=source,stdout=StringIO())
    assert_empty(mongo_db)


def test_malformed_ndjson_fails_clearly_and_restores_both_databases(source,mongo_db):
    path=source/"product_specs.ndjson"
    path.write_text("null\n",encoding="utf-8")
    refresh_checksums(source)
    with pytest.raises(CommandError,match="Invalid clean input") as error:
        call_command("import_olist",source=source,stdout=StringIO())
    assert isinstance(error.value.__cause__, TypeError)
    assert_empty(mongo_db)


def test_runtime_role_reads_imported_test_database_and_cannot_disable_triggers(imported):
    with psycopg.connect(dbname=connection.settings_dict["NAME"],host=os.environ["POSTGRES_HOST"],
                        user=os.environ["POSTGRES_RUNTIME_USER"],password=os.environ["POSTGRES_RUNTIME_PASSWORD"],autocommit=True) as runtime:
        assert runtime.execute("SELECT count(*) FROM catalogue_product").fetchone()[0] == imported["output_counts"]["products"]
        assert runtime.execute("SELECT count(*) FROM purchasable_product").fetchone()[0] > 0
        assert runtime.execute("SELECT count(*) FROM django_migrations").fetchone()[0] > 0
        for statement in ("CREATE TABLE intrusion(id bigint)","TRUNCATE catalogue_product","DROP TABLE catalogue_product", "ALTER TABLE accounts_user DISABLE TRIGGER USER", "CREATE TEMP TABLE intrusion(id bigint)",
                          "INSERT INTO django_migrations (app,name,applied) SELECT app,name,applied FROM django_migrations WHERE false",
                          "UPDATE django_migrations SET name=name WHERE false", "DELETE FROM django_migrations WHERE false",
                          "SELECT nextval(pg_get_serial_sequence('django_migrations','id'))"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                runtime.execute(statement)


def test_trigger_state_and_hostile_catalog_identifiers_are_preserved():
    name='probe\"; DROP TABLE accounts_user; --'
    with connection.cursor() as cursor:
        cursor.execute("CREATE FUNCTION phase1a_probe() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$")
        cursor.execute(sql.SQL("CREATE TRIGGER {} BEFORE INSERT ON accounts_user FOR EACH ROW EXECUTE FUNCTION phase1a_probe()").format(sql.Identifier(name)))
        cursor.execute(sql.SQL("ALTER TABLE accounts_user DISABLE TRIGGER {}").format(sql.Identifier(name)))
    try:
        call_command("import_olist",source=SOURCE,stdout=StringIO())
        with connection.cursor() as cursor:
            cursor.execute("SELECT tgenabled FROM pg_trigger WHERE tgname=%s",[name])
            assert cursor.fetchone() == ("D",)
        assert get_user_model().objects.exists()
    finally:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("DROP TRIGGER {} ON accounts_user").format(sql.Identifier(name)))
            cursor.execute("DROP FUNCTION phase1a_probe()")


@pytest.mark.parametrize("field", ["total", "customer_id", "placed_at"])
def test_checkout_header_allowance_does_not_allow_missing_imported_fields(source, mongo_db, field):
    path = source / "checkouts.csv"
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    fields.remove(field)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    refresh_checksums(source)
    with pytest.raises(CommandError, match="Unexpected CSV header: checkouts"):
        call_command("import_olist", source=source, stdout=StringIO())
    assert_empty(mongo_db)


def test_import_rejects_a_source_refund_missing_its_imported_label(source,mongo_db):
    alter_csv(source,"refunds","imported","False")
    with pytest.raises(CommandError,match="Invariant imported_refund_provenance failed"):
        call_command("import_olist",source=source,stdout=StringIO())
    assert_empty(mongo_db)
