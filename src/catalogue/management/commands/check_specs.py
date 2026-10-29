"""Inspect product/spec IDs; explicitly requested repair removes only orphan specs and their photos."""

import json

from django.core.management.base import BaseCommand, CommandError
from gridfs import GridFS
from pymongo.errors import PyMongoError

from catalogue.models import Product
from config import mongo


class Command(BaseCommand):
    help = "Report products without specifications and orphan specifications; --repair removes orphan specs/photos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--repair", action="store_true", help="Remove specifications whose PostgreSQL product no longer exists"
        )

    def handle(self, *args, **options):
        products = dict(Product.objects.values_list("pk", "category_id"))
        try:
            with mongo.client() as client:
                database = client[mongo.database_name()]
                documents = {
                    row["_id"]: row for row in database.product_specs.find({}, {"category_id": 1, "photo_file_id": 1})
                }
                missing = sorted(set(products) - set(documents))
                orphans = sorted(set(documents) - set(products))
                mismatched = sorted(
                    pk for pk in products.keys() & documents.keys() if products[pk] != documents[pk]["category_id"]
                )
                removed = 0
                if options["repair"]:
                    for pk in orphans:
                        photo_id = documents[pk].get("photo_file_id")
                        database.product_specs.delete_one({"_id": pk})
                        if photo_id:
                            GridFS(database, collection="photos").delete(photo_id)
                        removed += 1
                self.stdout.write(
                    json.dumps(
                        {
                            "missing_product_specs": missing,
                            "orphan_specs": orphans,
                            "category_mismatches": mismatched,
                            "removed_orphan_specs": removed,
                        },
                        sort_keys=True,
                    )
                )
                if missing or mismatched or (orphans and not options["repair"]):
                    raise CommandError(
                        "Specifications need attention. Use --repair to remove orphans; restore missing or mismatched specifications from their source."
                    )
        except PyMongoError as error:
            raise CommandError(
                f"Specification check failed ({type(error).__name__}); verify database health."
            ) from None
