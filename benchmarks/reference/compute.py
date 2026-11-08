"""Reproduce the analytical definitions with Python data structures and Decimal arithmetic."""

import argparse
import hashlib
import json
import random
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from benchmarks.canonical import csv_bytes
from benchmarks.source import SEED, ZONE, csv_rows, instant, local_day, manifest, ndjson


def parameters(specs):
    """Fixed seed and stable ordering, including actual one/two/three-attribute matches."""
    counts = Counter((k, type(v).__name__, json.dumps(v)) for spec in specs for k, v in spec["attributes"].items())
    strings = sorted((n, k, v) for (k, kind, v), n in counts.items() if kind == "str")
    booleans = sorted((n, k, v) for (k, kind, v), n in counts.items() if kind == "bool")
    integers = sorted((k, json.loads(v)) for k, kind, v in counts if kind == "int")
    rng = random.Random(SEED)
    triples = sorted((s for s in specs if len(s["attributes"]) >= 3), key=lambda s: s["_id"])
    chosen = rng.choice(triples)
    attrs = sorted(chosen["attributes"].items())
    range_key = integers[0][0]
    range_values = sorted(v for k, v in integers if k == range_key)
    selections = [
        ("selective", [[strings[0][1], "eq", json.loads(strings[0][2])]]),
        ("broad", [[strings[-1][1], "eq", json.loads(strings[-1][2])]]),
        ("boolean", [[booleans[-1][1], "eq", json.loads(booleans[-1][2])]]),
        ("range", [[range_key, "gte", range_values[len(range_values) // 2]]]),
        ("two", [[k, "eq", v] for k, v in attrs[:2]]),
        ("three", [[k, "eq", v] for k, v in attrs[:3]]),
    ]
    return [{"name": name, "predicates": predicates} for name, predicates in selections]


def matches(attributes, predicates):
    for key, operation, value in predicates:
        actual = attributes.get(key)
        if type(actual) is not type(value):
            return False
        if operation == "eq" and actual != value or operation == "gte" and actual < value:
            return False
    return True


def compute(source):
    provenance = manifest(source)
    products = {int(p["id"]): p for p in csv_rows(source, "products")}
    sellers = {int(s["id"]): s for s in csv_rows(source, "sellers")}
    orders = {int(o["id"]): o for o in csv_rows(source, "orders")}
    specs = list(ndjson(source, "product_specs"))
    params = parameters(specs)
    outputs = {
        "B1_" + p["name"]: [{"product_id": s["_id"]} for s in specs if matches(s["attributes"], p["predicates"])]
        for p in params
    }
    as_of = max(local_day(instant(o["placed_at"])) for o in orders.values())
    end = datetime.combine(as_of + timedelta(days=1), time.min, ZONE)
    daily = defaultdict(lambda: [0, Decimal(0)])
    for line in csv_rows(source, "order_lines"):
        order = orders[int(line["order_id"])]
        day = local_day(instant(order["placed_at"]))
        cancellation = instant(order["cancelled_at"])
        if day <= as_of and (order["status"] != "cancelled" or cancellation and local_day(cancellation) > as_of):
            sale = daily[int(line["product_id"]), day]
            sale[0] += int(line["quantity"])
            sale[1] += int(line["quantity"]) * Decimal(line["unit_price"])
    monthly = defaultdict(lambda: [0, Decimal(0)])
    units_28 = Counter()
    for (pid, day), (units, revenue) in daily.items():
        values = monthly[int(products[pid]["category_id"]), day.replace(day=1)]
        values[0] += units
        values[1] += revenue
        if day >= as_of - timedelta(days=27):
            units_28[pid] += units
    category_rows = []
    for (category, month), (units, revenue) in sorted(monthly.items()):
        previous_month = (month - timedelta(days=1)).replace(day=1)
        previous = monthly.get((category, previous_month))
        rank = 1 + sum(r > revenue for (c, m), (u, r) in monthly.items() if m == month)
        category_rows.append(
            {
                "category_id": category,
                "month": month,
                "units": units,
                "revenue": revenue,
                "revenue_rank": rank,
                "change_percent": (revenue - previous[1]) * 100 / previous[1] if previous and previous[1] else None,
            }
        )
    outputs["B2a"] = category_rows
    stock = []
    for pid, product in products.items():
        if (
            product["active"] != "True"
            or product["taken_down"] == "True"
            or sellers[int(product["seller_id"])]["status"] != "approved"
        ):
            continue
        units = units_28[pid]
        stock.append(
            {
                "product_id": pid,
                "daily_demand": Decimal(units) / 28,
                "days_cover": Decimal(product["stock"]) * 28 / units if units else None,
                "replenish": units > 0 and int(product["stock"]) * 28 < int(product["lead_time_days"]) * units,
            }
        )
    outputs["B2b"] = stock
    ratings = defaultdict(list)
    order_scores = defaultdict(list)
    for review in ndjson(source, "reviews"):
        if review.get("taken_down", False) or review["answered_at"] >= end:
            continue
        ratings[review["product_id"]].append(review["score"])
        order_scores[review["order_id"]].append(review["score"])  # copies count, as in the app
    stats = next(ndjson(source, "platform_stats"))
    grouped = defaultdict(list)
    for pid, product in products.items():
        grouped["product", pid].extend(ratings[pid])
        grouped["seller", int(product["seller_id"])].extend(ratings[pid])
    outputs["B2c"] = [
        {
            "entity": entity,
            "entity_id": identity,
            "review_count": len(scores),
            "score_sum": sum(scores),
            "bayesian": (stats["C"] * stats["m"] + sum(scores)) / (stats["C"] + len(scores))
            if stats["C"] + len(scores)
            else Decimal(0),
        }
        for (entity, identity), scores in grouped.items()
    ]
    outputs["B2c_index"] = [row for row in outputs["B2c"] if row["entity"] == "product" and row["entity_id"] == 1]
    buckets = defaultdict(lambda: {"orders": 0, "scores": []})
    for oid, order in orders.items():
        delivered = instant(order["delivered_at"])
        if order["status"] != "delivered" or instant(order["placed_at"]) >= end or delivered >= end:
            continue
        delay = (local_day(delivered) - local_day(instant(order["estimated_delivery"]))).days
        bucket = (
            "early_over_7"
            if delay < -7
            else "early_up_to_7_or_on_time"
            if delay <= 0
            else "late_1_to_7"
            if delay <= 7
            else "late_8_to_14"
            if delay <= 14
            else "late_over_14"
        )
        buckets[bucket]["orders"] += 1
        if order_scores[oid]:
            buckets[bucket]["scores"].append(Decimal(sum(order_scores[oid])) / len(order_scores[oid]))
    outputs["B2d"] = [
        {
            "bucket": key,
            "orders": value["orders"],
            "reviewed_orders": len(value["scores"]),
            "average_score": sum(value["scores"], Decimal(0)) / len(value["scores"]) if value["scores"] else None,
        }
        for key, value in buckets.items()
    ]
    return outputs, params, {**provenance, "as_of": as_of.isoformat(), "seed": SEED}


def generate(source, destination):
    outputs, params, provenance = compute(source)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "parameters.json").write_bytes((json.dumps(params, indent=2) + "\n").encode())
    # Do not include the machine-specific source path in deterministic golden metadata.
    provenance.pop("source")
    (destination / "source.json").write_bytes((json.dumps(provenance, indent=2, sort_keys=True) + "\n").encode())
    for name, rows in outputs.items():
        (destination / f"{name}.csv").write_bytes(csv_bytes(name, rows))
    checksums = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(destination.iterdir())
        if path.name != "checksums.txt"
    }
    (destination / "checksums.txt").write_bytes(
        "".join(f"{digest}  {name}\n" for name, digest in checksums.items()).encode()
    )
    print(json.dumps({"golden": str(destination), "outputs": {name: len(rows) for name, rows in outputs.items()}}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.source, args.output)


if __name__ == "__main__":
    main()
