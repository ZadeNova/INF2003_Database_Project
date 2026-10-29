"""Deployment/operator readiness check, deliberately separate from process liveness."""

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor
from pymongo.errors import PyMongoError

from config import mongo


class Command(BaseCommand):
    help = "Check PostgreSQL and MongoDB connectivity and pending migrations without exposing connection details."

    def handle(self, *args, **options):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            executor = MigrationExecutor(connection)
            if executor.migration_plan(executor.loader.graph.leaf_nodes()):
                raise CommandError("Database migrations are pending.")
        except DatabaseError:
            raise CommandError("Database unavailable.") from None
        try:
            with mongo.client() as client:
                hello = client[mongo.database_name()].command("hello")
        except (PyMongoError, ValueError):
            raise CommandError("MongoDB unavailable.") from None
        if hello.get("setName") != mongo.REPLICA_SET or not hello.get("isWritablePrimary"):
            raise CommandError("MongoDB is not a writable primary of the expected replica set.")
        self.stdout.write('{"postgresql": "ok", "mongodb": "ok", "migrations": "applied"}')
