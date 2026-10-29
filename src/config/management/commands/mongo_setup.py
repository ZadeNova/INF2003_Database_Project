from django.core.management.base import BaseCommand, CommandError
from pymongo.errors import PyMongoError

from config import mongo
from config.mongo_schema import setup


class Command(BaseCommand):
    help = "Idempotently create marketplace collections, validators, activity time series and indexes with readWrite."

    def add_arguments(self, parser):
        parser.add_argument("--database", default=None, help="Configured app database or its test_ database only")

    def handle(self, *args, **options):
        name = options["database"] or mongo.database_name()
        try:
            with mongo.using_database(name), mongo.client() as client:
                setup(client[name])
        except ValueError as error:
            raise CommandError(str(error)) from None
        except PyMongoError as error:
            raise CommandError(
                f"MongoDB setup failed ({type(error).__name__}); verify database health and readWrite privileges."
            ) from None
        self.stdout.write("MongoDB collections, validators and indexes ready.")
