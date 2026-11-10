import json
import resource
import time
from collections import defaultdict
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection, transaction
from psycopg import Error as PsycopgError
from pymongo.errors import PyMongoError

from config import mongo
from config.olist_import import (
    IMPORT_LOCK,
    TABLES,
    copy_table,
    ensure_empty,
    insert_documents,
    loading_triggers,
    reconcile,
    repair_sequences,
    sql_invariants,
    verify_manifest,
)


class Command(BaseCommand):
    help = "COPY the approved cleaned Olist files into empty PostgreSQL and MongoDB databases as the owner."

    def add_arguments(self, parser):
        parser.add_argument("--source", type=Path, default=Path("/app/data/derived/olist/clean"))

    def handle(self, *args, **options):
        if connection.in_atomic_block:
            raise CommandError(
                "import_olist must own its transaction; run it as a standalone owner command through migrate."
            )
        started = time.perf_counter()
        source = options["source"]
        attempted_ids = defaultdict(list)
        postgres_commit_pending = False
        try:
            ledger = verify_manifest(source)
            self.stdout.write("Checksums and CSV headers verified.")
            with mongo.database() as database:
                try:
                    with transaction.atomic():
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [IMPORT_LOCK])
                            cursor.execute(
                                "SELECT pg_get_userbyid(datdba)=current_user FROM pg_database WHERE datname=current_database()"
                            )
                            if not cursor.fetchone()[0]:
                                raise CommandError(
                                    "The PostgreSQL database owner must run import_olist through migrate."
                                )
                        ensure_empty(database)
                        call_command("mongo_setup", database=mongo.database_name(), stdout=self.stdout)
                        with loading_triggers():
                            for label, model in TABLES.items():
                                copy_table(source, label, model)
                                self.stdout.write(f"PostgreSQL {label}: {model.objects.count()} rows")
                        repair_sequences()
                        # Check deferred FK constraints before a MongoDB commit.
                        with connection.cursor() as cursor:
                            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
                        sql_invariants(importing=True)
                        self.stdout.write(
                            "PostgreSQL money, refunds, totals, roles and ownership invariants: no diagnostic rows."
                        )
                        with database.client.start_session() as session:
                            insert_documents(database, source, session, self.stdout.write, attempted_ids)
                            reconcile(database, ledger, session=session)
                        self.stdout.write("Cross-store references and ledger row counts reconciled.")
                        postgres_commit_pending = True
                except Exception as import_error:
                    # Also cover an uncertain MongoDB commit acknowledgement.
                    # Delete only IDs attempted by this import, never unrelated rows.
                    try:
                        for name, ids in attempted_ids.items():
                            for offset in range(0, len(ids), 1000):
                                database[name].delete_many({"_id": {"$in": ids[offset : offset + 1000]}})
                    except PyMongoError as cleanup_error:
                        raise CommandError(
                            "PostgreSQL rolled back, but MongoDB cleanup could not be confirmed. Reset this local project's databases before retrying."
                        ) from cleanup_error
                    if postgres_commit_pending:
                        raise CommandError(
                            "PostgreSQL's final commit outcome could not be confirmed. Attempted MongoDB IDs were cleaned. Reset this local project's databases before retrying."
                        ) from import_error
                    raise
        except CommandError:
            raise
        except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
            raise CommandError(f"Invalid clean input ({type(error).__name__}); PostgreSQL rows rolled back.") from error
        except (DatabaseError, PsycopgError, PyMongoError) as error:
            raise CommandError(
                f"Import failed ({type(error).__name__}); rows rolled back and trigger state restored. Check input, database health and owner privileges."
            ) from error
        # The import is committed. A refresh failure must never claim that these source rows rolled back.
        from config import redis_store
        from dashboard.services import ORDER_SCORES, refresh_sales

        redis_store.bump_dashboard()  # the imported rows are history: bump even if the refresh below fails
        try:
            # A summary left over from an earlier load must never be trusted if the refresh below fails.
            with mongo.database() as database:
                database[ORDER_SCORES].delete_many({})
            refresh_sales()
        except (DatabaseError, PyMongoError) as error:
            raise CommandError(
                "Import committed, but sales history refresh failed. Use the operator refresh button after checking PostgreSQL and MongoDB."
            ) from error
        self.stdout.write("Daily product sales, delivery summary and review score summary refreshed.")
        duration = time.perf_counter() - started
        self.stdout.write(f"Olist import complete in {duration:.3f} seconds.")
        self.stdout.write(
            "Import metrics: "
            + json.dumps(
                {
                    "duration_seconds": round(duration, 3),
                    "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    "source": str(source),
                    "output_counts": ledger["output_counts"],
                },
                sort_keys=True,
            )
        )
