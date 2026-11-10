"""Synthetic browsing, relative to now, weighted by the real imported unit sales."""

import json
import random
from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum
from django.utils import timezone

from activity.services import EVENT_WRITE_CONCERN
from config import mongo
from orders.models import OrderLine


class Command(BaseCommand):
    help = "Append labelled synthetic views over the last 30 days, weighted by imported sales (default 200000)."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=200000)
        parser.add_argument("--seed", type=int, default=82)

    def handle(self, *args, **options):
        count = options["count"]
        if not 1 <= count <= 1000000:
            raise CommandError("Choose between 1 and 1000000 events.")
        sales = list(
            OrderLine.objects.filter(order__checkout__olist_order_id__isnull=False)
            .exclude(order__status="cancelled")
            .values("product_id", "product__category_id")
            .annotate(units=Sum("quantity"))
            .order_by("product_id")
        )
        if not sales:
            raise CommandError("Import Olist before seeding activity.")
        call_command("mongo_setup", stdout=self.stdout)
        weights = [row["units"] for row in sales]
        rng = random.Random(options["seed"])
        now = timezone.now()
        with mongo.database() as database:
            events = database.events.with_options(write_concern=EVENT_WRITE_CONCERN)
            for offset in range(0, count, 5000):
                batch = []
                for row in rng.choices(sales, weights=weights, k=min(5000, count - offset)):
                    batch.append(
                        {
                            "ts": now - timedelta(seconds=rng.randrange(30 * 24 * 60 * 60)),
                            "meta": {
                                "type": "view",
                                "product_id": row["product_id"],
                                "category": row["product__category_id"],
                                "session_key": "generated-demo-activity",
                            },
                            "is_generated": True,
                        }
                    )
                events.insert_many(batch, ordered=False)
        self.stdout.write(
            json.dumps(
                {
                    "seed_activity": "complete",
                    "events_written": count,
                    "is_generated": True,
                    "window_end": now.isoformat(),
                    "seed": options["seed"],
                }
            )
        )
