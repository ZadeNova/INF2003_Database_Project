"""The comparison uses real imported history, not mocked database results."""
from io import StringIO
import json
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

pytestmark=pytest.mark.django_db(transaction=True)


def test_delivery_comparison_reports_real_bucket_differences(imported):
    # Small raw fixtures can change averages more than the full-data tolerance
    # when a broken order is removed. Both outcomes must report actual numbers.
    with pytest.raises(CommandError,match="Delay bucket late_over_14 does not reconcile within 0.05: raw=.*imported="):
        call_command("verify_olist", source=Path("/app/tests/fixtures/olist/clean"),
                     profile=Path("/app/tests/fixtures/olist/profile.json"),stdout=StringIO())


def test_comparison_success_uses_an_independent_retained_raw_population(imported,tmp_path):
    import csv
    from collections import defaultdict
    from datetime import datetime
    from decimal import Decimal
    root=Path("/app/tests/fixtures/olist")
    with (root/"clean/checkouts.csv").open() as stream:
        retained={r["olist_order_id"] for r in csv.DictReader(stream)}
    with (root/"raw/olist_order_reviews_dataset.csv").open() as stream:
        rows=list(csv.DictReader(stream))
    latest={r["order_id"]:r for r in sorted(rows,key=lambda r:(r["review_answer_timestamp"],r["review_id"]))}
    groups=defaultdict(list)
    with (root/"raw/olist_orders_dataset.csv").open() as stream:
        for order in csv.DictReader(stream):
            if order["order_id"] not in retained or order["order_status"]!="delivered" or order["order_id"] not in latest:
                continue
            days=(datetime.fromisoformat(order["order_delivered_customer_date"]).date()-datetime.fromisoformat(order["order_estimated_delivery_date"]).date()).days
            bounds=[("early_over_7",days < -7),("early_up_to_7_or_on_time",-7 <= days <= 0),
                    ("late_1_to_7",1 <= days <= 7),("late_8_to_14",8 <= days <= 14),("late_over_14",days > 14)]
            bucket=next(k for k,matches in bounds if matches)
            groups[bucket].append(int(latest[order["order_id"]]["review_score"]))
    profile={"delivery_delay_scores":{k:{"count":len(v),"average":str(Decimal(sum(v))/len(v))} for k,v in groups.items()}}
    path=tmp_path/"retained-raw-profile.json";path.write_text(json.dumps(profile))
    output=StringIO()
    call_command("verify_olist",source=root/"clean",profile=path,stdout=output)
    result=json.loads(output.getvalue())
    assert result["cross_store_reconciliation"] == "passed"
    assert len(result["delivery_delay"]) == 5
    assert all(Decimal(row["absolute_difference"]) <= Decimal("0.05") for row in result["delivery_delay"].values())
    assert result["delivery_delay_pattern"] == result["raw_delivery_delay_pattern"]
