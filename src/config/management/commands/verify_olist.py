"""Re-run import invariants and compare raw/imported delivery-delay findings."""
import json
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils.timezone import localtime

from config import mongo
from config.olist_import import reconcile, sql_invariants


class Command(BaseCommand):
    help = "Verify imported money/ownership/references and the raw-versus-imported delay buckets (before seed_demo)."

    def add_arguments(self, parser):
        parser.add_argument("--source", type=Path, default=Path("/app/data/derived/olist/clean"))
        parser.add_argument("--profile", type=Path, default=Path("/app/data/derived/olist/profile.json"))

    def handle(self, *args, **options):
        ledger = json.loads((options["source"] / "cleaning_ledger.json").read_text())
        raw = json.loads(options["profile"].read_text())["delivery_delay_scores"]
        result = {"sql_invariants": sql_invariants()}
        with mongo.client() as client:
            database = client[mongo.database_name()]
            reconcile(database, ledger)
            # The same original order review is copied to every collapsed line.
            # Count it once per source checkout for an unbiased raw comparison.
            scores = {r["_id"]: r["score"] for r in database.reviews.aggregate([
                {"$group": {"_id": "$checkout_id", "score": {"$first": "$score"}}}])}
        groups = {k: [] for k in ("early_over_7", "early_up_to_7_or_on_time", "late_1_to_7", "late_8_to_14", "late_over_14")}
        with connection.cursor() as cursor:
            cursor.execute("""SELECT DISTINCT checkout_id, delivered_at, estimated_delivery
                FROM orders_order WHERE status=%s AND delivered_at IS NOT NULL""", ["delivered"])
            for checkout, delivered, estimated in cursor.fetchall():
                if checkout not in scores:
                    continue
                days = (localtime(delivered).date() - localtime(estimated).date()).days
                bucket = ("early_over_7" if days < -7 else "early_up_to_7_or_on_time" if days <= 0
                          else "late_1_to_7" if days <= 7 else "late_8_to_14" if days <= 14 else "late_over_14")
                groups[bucket].append(scores[checkout])
        comparisons = {}
        averages, raw_averages = [], []
        for bucket, values in groups.items():
            average = Decimal(sum(values)) / len(values) if values else None
            raw_average = Decimal(raw[bucket]["average"]) if raw[bucket]["average"] is not None else None
            difference = abs(average - raw_average) if average is not None and raw_average is not None else None
            if average is None or raw_average is None or difference > Decimal("0.05"):
                raise CommandError(f"Delay bucket {bucket} does not reconcile within 0.05: raw={raw_average}, imported={average}")
            averages.append(average)
            raw_averages.append(raw_average)
            comparisons[bucket] = {"raw_average": str(raw_average), "imported_average": str(average.quantize(Decimal("0.0001"))),
                                   "absolute_difference": str(difference), "raw_orders": raw[bucket]["count"], "imported_orders": len(values)}
        def pattern(values):
            return ["decrease" if a > b else "increase" if a < b else "equal" for a, b in zip(values, values[1:])]
        if pattern(averages) != pattern(raw_averages):
            raise CommandError("Imported delay/review averages no longer have the raw ordering pattern")
        result.update(cross_store_reconciliation="passed", delivery_delay=comparisons,
                      delivery_delay_pattern=pattern(averages), raw_delivery_delay_pattern=pattern(raw_averages))
        self.stdout.write(json.dumps(result, sort_keys=True))
