import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from catalogue import showcase


class Command(BaseCommand):
    help = (
        "Load the demonstration catalogue (data/demo_showcase/catalogue.json and data/demo_photos): photos for named "
        "Olist products, the demo shop names, new merchants, categories and products. Safe to run repeatedly."
    )

    def add_arguments(self, parser):
        parser.add_argument("--catalogue", type=Path, default=Path("/app/data/demo_showcase/catalogue.json"))
        parser.add_argument("--photos", type=Path, default=Path("/app/data/demo_photos"))

    def handle(self, *args, catalogue, photos, **options):
        password = os.environ.get("DEMO_SELLER_PASSWORD", "")
        if not password or password.startswith("replace-"):
            raise CommandError("DEMO_SELLER_PASSWORD must be supplied; no fallback password exists.")
        try:
            summary = showcase.load(catalogue, photos, password)
        except showcase.ShowcaseError as error:
            problems = "\n  - ".join(error.problems)
            raise CommandError("The demonstration catalogue has problems:\n  - " + problems) from None
        self.stdout.write(
            f"Showcase: {summary.merchants} merchants, {summary.categories} new categories, {summary.products} new "
            f"products, {summary.photos} photos, {summary.renamed_shops} demo shops renamed, "
            f"{summary.featured} featured."
        )
        if summary.skipped_products:
            self.stdout.write(f"Skipped {len(summary.skipped_products)} showcase products not in this database.")
        if summary.missing_photos:
            names = ", ".join(summary.missing_photos)
            self.stdout.write(f"Photos not supplied yet ({len(summary.missing_photos)}): {names}")
