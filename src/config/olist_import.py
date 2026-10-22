"""Load committed clean files only. No cleaning, translation or generation here."""
from collections import Counter
from contextlib import contextmanager
import csv
import hashlib
import json
from pathlib import Path

from bson import json_util
from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.db import connection
from psycopg import sql
from psycopg.pq import TransactionStatus

from accounts.models import CustomerProfile, Seller, Geolocation
from catalogue.models import Category, Product
from orders.models import Checkout, Order, OrderLine, Payment, Refund

TABLES = {
    "users": get_user_model(), "customers": CustomerProfile, "sellers": Seller,
    "categories": Category, "products": Product, "checkouts": Checkout,
    "orders": Order, "order_lines": OrderLine, "payments": Payment,
    "refunds": Refund, "geolocation": Geolocation,
}
COLLECTIONS = ("reviews", "product_specs", "platform_stats", "category_templates")
IMPORT_LOCK = 8201001
INVARIANTS = {
    "payment_totals": """SELECT c.id, c.total, COALESCE(sum(p.amount),0) AS paid
        FROM orders_checkout c LEFT JOIN orders_payment p ON p.checkout_id=c.id
        GROUP BY c.id HAVING c.total <> COALESCE(sum(p.amount),0)""",
    "checkout_order_totals": """SELECT c.id, c.total, COALESCE(sum(o.total),0) AS orders_total
        FROM orders_checkout c LEFT JOIN orders_order o ON o.checkout_id=c.id
        GROUP BY c.id HAVING c.total <> COALESCE(sum(o.total),0) OR count(o.id)=0""",
    "order_line_totals": """SELECT o.id, o.items, o.freight, COALESCE(sum(l.quantity*l.unit_price),0) AS line_items,
        COALESCE(sum(l.freight),0) AS line_freight FROM orders_order o
        LEFT JOIN orders_orderline l ON l.order_id=o.id GROUP BY o.id
        HAVING count(l.id)=0 OR o.items<>COALESCE(sum(l.quantity*l.unit_price),0)
        OR o.freight<>COALESCE(sum(l.freight),0)""",
    "line_ownership": """SELECT l.id, l.seller_id, o.seller_id AS order_seller, p.seller_id AS product_seller
        FROM orders_orderline l JOIN orders_order o ON o.id=l.order_id JOIN catalogue_product p ON p.id=l.product_id
        WHERE l.seller_id<>o.seller_id OR l.seller_id<>p.seller_id""",
    "one_seller_per_order": """SELECT o.id, count(DISTINCT l.seller_id) AS sellers
        FROM orders_order o LEFT JOIN orders_orderline l ON l.order_id=o.id
        GROUP BY o.id HAVING count(DISTINCT l.seller_id)<>1""",
    "one_order_per_seller": """SELECT checkout_id, seller_id, count(*) FROM orders_order
        GROUP BY checkout_id, seller_id HAVING count(*)<>1""",
    "refund_totals": """SELECT o.id, o.status, o.total, r.amount, r.checkout_id
        FROM orders_order o LEFT JOIN orders_refund r ON r.order_id=o.id
        WHERE (o.status='cancelled' AND EXISTS (SELECT 1 FROM orders_payment p WHERE p.checkout_id=o.checkout_id)
            AND (r.id IS NULL OR r.amount<>o.total OR r.checkout_id<>o.checkout_id))
        OR (r.id IS NOT NULL AND (o.status<>'cancelled' OR r.amount<>o.total OR r.checkout_id<>o.checkout_id))""",
    "profile_roles": """SELECT u.id, u.role FROM accounts_user u
        LEFT JOIN accounts_customerprofile c ON c.user_id=u.id LEFT JOIN accounts_seller s ON s.user_id=u.id
        WHERE (c.id IS NOT NULL AND u.role<>'customer') OR (s.id IS NOT NULL AND u.role<>'seller')""",
    "customer_roles": """SELECT c.id, u.role FROM orders_checkout c JOIN accounts_user u ON u.id=c.customer_id
        WHERE u.role<>'customer'""",
}


def fail(name, rows):
    raise CommandError(f"Invariant {name} failed; diagnostic rows: " + json.dumps(rows[:10], default=str, sort_keys=True))


def sql_invariants(*, importing=False):
    checks = dict(INVARIANTS)
    if importing:
        # Provenance is an import-time rule, not an ongoing money invariant: an imported paid
        # order can later be cancelled by its customer, creating an application refund.
        checks["imported_refund_provenance"] = "SELECT id FROM orders_refund WHERE NOT imported"
    counts = {}
    with connection.cursor() as cursor:
        for name, query in checks.items():
            cursor.execute(query)
            rows = cursor.fetchmany(10)
            if rows:
                fields = [c.name for c in cursor.description]
                fail(name, [dict(zip(fields, row)) for row in rows])
            counts[name] = 0
    return counts


def verify_manifest(source):
    source = Path(source).resolve()
    expected = {f"{key}.csv" for key in TABLES} | {f"{key}.ndjson" for key in COLLECTIONS} | {"cleaning_ledger.json"}
    lines = (source / "checksums.txt").read_text(encoding="utf-8").splitlines()
    found = set()
    for line in lines:
        digest, sep, name = line.partition("  ")
        if not sep or len(digest) != 64 or name not in expected or name in found:
            raise CommandError("Invalid checksums manifest: expected only the approved clean files")
        path = (source / name).resolve()
        if path.parent != source:
            raise CommandError("Clean file resolves outside the source directory")
        actual = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                actual.update(block)
        if actual.hexdigest() != digest:
            raise CommandError(f"Checksum failed: {name}")
        found.add(name)
    if found != expected:
        raise CommandError("Missing clean files in checksums manifest")
    for label, model in TABLES.items():
        with (source / f"{label}.csv").open(encoding="utf-8", newline="") as stream:
            fields = next(csv.reader(stream))
        approved = {field.column for field in model._meta.local_fields}
        # New application metadata has a database default and is absent from the fixed clean dataset.
        optional = {"request_fingerprint"} if label == "checkouts" else set()
        if (len(fields) != len(set(fields)) or not set(fields) <= approved
                or not approved - set(fields) <= optional):
            raise CommandError(f"Unexpected CSV header: {label}")
    ledger = json.loads((source / "cleaning_ledger.json").read_text(encoding="utf-8"))
    if set(ledger["output_counts"]) != set(TABLES) | set(COLLECTIONS):
        raise CommandError("Ledger has missing or unexpected output tables")
    return ledger


def ensure_empty(database):
    for label, model in TABLES.items():
        if model.objects.exists():
            raise CommandError(f"Import requires an empty database; {label} already contains rows. Reset local databases before importing.")
    for name in COLLECTIONS:
        if database[name].find_one({}, {"_id": 1}) is not None:
            raise CommandError(f"Import requires empty MongoDB collections; {name} already contains documents.")


@contextmanager
def loading_triggers():
    previous = []
    with connection.cursor() as cursor:
        for model in TABLES.values():
            table = model._meta.db_table
            cursor.execute("SELECT tgname, tgenabled FROM pg_trigger WHERE tgrelid=%s::regclass AND NOT tgisinternal", [table])
            previous.extend((table, name, mode) for name, mode in cursor.fetchall())
            cursor.execute(sql.SQL("ALTER TABLE {} DISABLE TRIGGER USER").format(sql.Identifier(table)))
    try:
        yield
    finally:
        # A failed PostgreSQL transaction cannot execute ALTER TABLE. Rolling it
        # back restores all DISABLE statements, because PostgreSQL DDL is atomic.
        if connection.connection.info.transaction_status != TransactionStatus.INERROR:
            with connection.cursor() as cursor:
                # Django FKs are initially deferred. Flush their events before
                # ALTER TABLE, which PostgreSQL rejects with pending FK events.
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
                modes = {"O": "ENABLE", "D": "DISABLE", "R": "ENABLE REPLICA", "A": "ENABLE ALWAYS"}
                for table, name, mode in previous:
                    cursor.execute(sql.SQL("ALTER TABLE {} {} TRIGGER {}").format(
                        sql.Identifier(table), sql.SQL(modes[mode]), sql.Identifier(name)))


def copy_table(source, label, model):
    path = Path(source) / f"{label}.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        fields = next(csv.reader(stream))
    query = sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE, NULL '\\N')").format(
        sql.Identifier(model._meta.db_table), sql.SQL(", ").join(map(sql.Identifier, fields)))
    with connection.cursor() as cursor, path.open("rb") as stream:
        with cursor.copy(query) as copy:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                copy.write(block)


def repair_sequences():
    with connection.cursor() as cursor:
        for model in TABLES.values():
            if model is Geolocation:
                continue
            table = model._meta.db_table
            cursor.execute("SELECT pg_get_serial_sequence(%s, %s)", [table, "id"])
            sequence = cursor.fetchone()[0]
            cursor.execute(sql.SQL("SELECT setval(%s::regclass, COALESCE(max(id), 1), max(id) IS NOT NULL) FROM {}").format(
                sql.Identifier(table)), [sequence])


def insert_documents(database, source, session, progress, attempted_ids):
    for name in COLLECTIONS:
        count, batch = 0, []
        with (Path(source) / f"{name}.ndjson").open(encoding="utf-8") as stream:
            for line in stream:
                document = json_util.loads(line)
                if "_id" not in document:
                    raise CommandError(f"Explicit MongoDB document ID missing in {name}")
                batch.append(document)
                attempted_ids[name].append(document["_id"])
                if len(batch) == 1000:
                    # Bound each transaction rather than holding the full corpus
                    # beyond MongoDB's transaction lifetime/cache limits.
                    with session.start_transaction():
                        database[name].insert_many(batch, ordered=True, session=session)
                    count += len(batch)
                    batch = []
                    if count % 5000 == 0:
                        progress(f"MongoDB {name}: {count} documents loaded")
            if batch:
                with session.start_transaction():
                    database[name].insert_many(batch, ordered=True, session=session)
                count += len(batch)
        progress(f"MongoDB {name}: {count} documents")


def reconcile(database, ledger, session=None):
    for label, model in TABLES.items():
        actual = model.objects.count()
        if actual != ledger["output_counts"][label]:
            fail("row_count", [{"table": label, "actual": actual, "expected": ledger["output_counts"][label]}])
    with connection.cursor() as cursor:
        cursor.execute("""SELECT l.id, l.order_id, o.checkout_id, l.product_id, l.seller_id, c.customer_id
            FROM orders_orderline l JOIN orders_order o ON o.id=l.order_id JOIN orders_checkout c ON c.id=o.checkout_id""")
        links = {r[0]: dict(zip(("order_id", "checkout_id", "product_id", "seller_id", "customer_id"), r[1:])) for r in cursor.fetchall()}
    products = dict(Product.objects.values_list("id", "category_id"))
    categories = set(Category.objects.values_list("id", flat=True))
    for name in COLLECTIONS:
        actual = database[name].count_documents({}, session=session)
        if actual != ledger["output_counts"][name]:
            fail("document_count", [{"collection": name, "actual": actual, "expected": ledger["output_counts"][name]}])
    for row in database.reviews.find({}, session=session):
        expected = links.get(row["order_line_id"])
        if expected is None or any(row[key] != value for key, value in expected.items()):
            fail("mongo_review_ownership", [{"order_line_id": row["order_line_id"], "expected": expected}])
    for row in database.product_specs.find({}, {"_id": 1, "category_id": 1, "latest_reviews": 1}, session=session):
        if products.get(row["_id"]) != row["category_id"]:
            fail("mongo_product_reference", [{"product_id": row["_id"], "category_id": row["category_id"]}])
        if any(r["product_id"] != row["_id"] or r["order_line_id"] not in links for r in row["latest_reviews"]):
            fail("mongo_subset_reference", [{"product_id": row["_id"]}])
    template_ids = {r["_id"] for r in database.category_templates.find({}, {"_id": 1, "category_id": 1}, session=session) if r["_id"] == r["category_id"]}
    if categories != template_ids:
        fail("mongo_template_reference", [{"missing": sorted(categories - template_ids), "extra": sorted(template_ids - categories)}])
