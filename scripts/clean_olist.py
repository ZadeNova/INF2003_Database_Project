"""Apply the approved 18 rules before import. Run in the pinned tools service."""

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from statistics import median

from olist_common import (
    HAND_TRANSLATIONS,
    METHODS,
    RAW_FILES,
    ROOT,
    STATUSES,
    ZERO,
    checksums,
    decimal,
    exact_median,
    latest_reviews,
    money,
    read_raw,
    timestamp,
    write_csv,
    write_json,
    write_ndjson,
)
from translate_reviews import read_translations, text_hash

# Field order is also the COPY contract. Nulls are empty unquoted CSV fields.
FIELDS = {
    "users": "id password last_login is_superuser username first_name last_name email is_staff is_active date_joined role".split(),
    "customers": "id user_id olist_customer_unique_id zip_prefix city state".split(),
    "sellers": "id user_id status shop_name olist_seller_id zip_prefix city state has_generated_content".split(),
    "categories": "id slug name_en name_pt icon hand_translated".split(),
    "products": "id seller_id category_id olist_product_id name price freight stock lead_time_days weight_g length_cm height_cm width_cm active featured taken_down taken_down_reason has_generated_content demo_adjustment".split(),
    "checkouts": "id customer_id placed_at total idempotency_key olist_order_id".split(),
    "orders": "id checkout_id seller_id status items freight total placed_at paid_at shipped_at delivered_at cancelled_at estimated_delivery".split(),
    "order_lines": "id order_id seller_id product_id quantity unit_price freight shipping_limit_at".split(),
    "payments": "id checkout_id sequence method instalments amount".split(),
    "refunds": "id order_id checkout_id amount reason refunded_at imported".split(),
    "geolocation": "zip_prefix latitude longitude city state".split(),
}


def validate(raw):
    keys = {"customers": "customer_id", "products": "product_id", "sellers": "seller_id", "orders": "order_id"}
    indexes = {}
    for table, key in keys.items():
        index = {}
        for row in raw[table]:
            value = row.get(key, "")
            if not re.fullmatch(r"[0-9a-f]{32}", value) or value in index:
                raise ValueError(f"Invalid or duplicate {table}.{key}: {value!r}")
            index[value] = row
        indexes[table] = index

    def reference(row, field, target):
        if row.get(field) not in indexes[target]:
            raise ValueError(f"Unknown {field}: {row.get(field)!r}")

    for row in raw["orders"]:
        reference(row, "customer_id", "customers")
        if row["order_status"] not in STATUSES:
            raise ValueError(f"Unknown order status: {row['order_status']!r}")
        for field, value in row.items():
            if field.endswith(("timestamp", "date", "_at")) and value:
                timestamp(value)
        if not row["order_purchase_timestamp"] or not row["order_estimated_delivery_date"]:
            raise ValueError("Order purchase and estimated dates are required")
    seen = set()
    for row in raw["order_items"]:
        for field, table in (("order_id", "orders"), ("product_id", "products"), ("seller_id", "sellers")):
            reference(row, field, table)
        key = (row["order_id"], int(row["order_item_id"]))
        if key in seen or key[1] < 1:
            raise ValueError(f"Invalid or duplicate source item: {key}")
        seen.add(key)
        for field in ("price", "freight_value"):
            decimal(row[field], label=field)
        if decimal(row["price"]) == 0:
            raise ValueError("Zero product price cannot satisfy the marketplace schema")
        timestamp(row["shipping_limit_date"])
    seen = set()
    for row in raw["order_payments"]:
        reference(row, "order_id", "orders")
        key = (row["order_id"], int(row["payment_sequential"]))
        if key in seen or key[1] < 1 or int(row["payment_installments"]) < 0:
            raise ValueError(f"Invalid or duplicate payment sequence: {key}")
        seen.add(key)
        if row["payment_type"] not in METHODS:
            raise ValueError(f"Unknown payment method: {row['payment_type']!r}")
        decimal(row["payment_value"], label="payment_value")
    for row in raw["order_reviews"]:
        reference(row, "order_id", "orders")
        if not 1 <= int(row["review_score"]) <= 5:
            raise ValueError("Review score must be 1..5")
        if not row["review_creation_date"] or not row["review_answer_timestamp"]:
            raise ValueError("Review creation and answer dates are required")
        timestamp(row["review_creation_date"])
        timestamp(row["review_answer_timestamp"])
    for row in raw["customers"]:
        if not re.fullmatch(r"[0-9a-f]{32}", row["customer_unique_id"]):
            raise ValueError("Malformed source customer_unique_id")
    translations = set()
    for row in raw["categories"]:
        key = row["product_category_name"]
        if key in translations or not key or not re.fullmatch(r"[a-z0-9_]+", row["product_category_name_english"]):
            raise ValueError("Malformed or duplicate category translation")
        translations.add(key)
    for row in raw["products"]:
        for field in ("product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"):
            if row[field]:
                number = decimal(row[field], label=field)
                if number != number.to_integral_value() or number > 2147483647:
                    raise ValueError(f"Invalid physical dimension {field}")
    for table, prefix in (("customers", "customer"), ("sellers", "seller"), ("geolocation", "geolocation")):
        for row in raw[table]:
            if not re.fullmatch(r"\d{5}", row[prefix + "_zip_code_prefix"]):
                raise ValueError(f"Invalid zip prefix in {table}")
    return indexes


def clean(raw_path, output, translations_path, fx_path):
    raw_path, output = Path(raw_path), Path(output)
    raw = read_raw(raw_path)
    indexes = validate(raw)
    translations = read_translations(translations_path)
    fx = json.loads(Path(fx_path).read_text(encoding="utf-8"))
    rate = decimal(fx["eur_sgd"]) / decimal(fx["eur_brl"])
    if rate <= 0:
        raise ValueError("FX cross rate must be positive")
    items, payments = defaultdict(list), defaultdict(list)
    for row in raw["order_items"]:
        items[row["order_id"]].append(row)
    for row in raw["order_payments"]:
        payments[row["order_id"]].append(row)
    rules = {str(i): {"affected": 0} for i in range(1, 19)}
    removed, reasons = set(), defaultdict(list)
    for row in raw["orders"]:
        oid = row["order_id"]
        paid = sum((decimal(p["payment_value"]) for p in payments[oid]), ZERO)
        total = sum((decimal(p["price"]) + decimal(p["freight_value"]) for p in items[oid]), ZERO)
        tests = {
            1: row["order_purchase_timestamp"] >= "2018-09-01",
            2: not items[oid] or not payments[oid],
            3: bool(items[oid] and payments[oid] and paid != total),
            4: any(p["payment_type"] == "not_defined" for p in payments[oid]),
            5: (row["order_status"] == "delivered") != bool(row["order_delivered_customer_date"]),
        }
        for number, applies in tests.items():
            if applies:
                removed.add(oid)
                reasons[str(number)].append(oid)
    for number, ids in reasons.items():
        rules[number] = {"affected": len(ids), "source_order_ids": sorted(ids)}
    kept_orders = sorted((r for r in raw["orders"] if r["order_id"] not in removed), key=lambda r: r["order_id"])
    if not kept_orders:
        raise ValueError("Cleaning leaves no valid orders")
    kept_ids = {r["order_id"] for r in kept_orders}
    kept_items = [r for r in raw["order_items"] if r["order_id"] in kept_ids]
    rules["6"]["affected"] = sum(
        p["payment_installments"] == "0" for p in raw["order_payments"] if p["order_id"] in kept_ids
    )
    selected = latest_reviews(raw)
    rules["7"] = {
        "affected": len(raw["order_reviews"]) - len(selected),
        "removed_with_orders": sum(oid not in kept_ids for oid in selected),
    }
    selected = {k: v for k, v in selected.items() if k in kept_ids}
    pairs = sorted({(r["product_id"], r["seller_id"]) for r in kept_items})
    product_ids = {key: i for i, key in enumerate(pairs, 1)}
    seller_ids = {key: i for i, key in enumerate(sorted(indexes["sellers"]), 1)}
    customer_rows = defaultdict(list)
    for row in raw["customers"]:
        customer_rows[row["customer_unique_id"]].append(row)
    customer_ids = {key: i for i, key in enumerate(sorted(customer_rows), 1)}
    result = {key: [] for key in FIELDS}
    joined = {"customer": {}, "seller": {}}
    first_purchase = min(r["order_purchase_timestamp"] for r in raw["orders"])
    for row in raw["orders"]:
        key = indexes["customers"][row["customer_id"]]["customer_unique_id"]
        joined["customer"][key] = min(
            joined["customer"].get(key, row["order_purchase_timestamp"]), row["order_purchase_timestamp"]
        )
    for row in raw["order_items"]:
        date = indexes["orders"][row["order_id"]]["order_purchase_timestamp"]
        joined["seller"][row["seller_id"]] = min(joined["seller"].get(row["seller_id"], date), date)
    for role, keys, offset in (
        ("customer", sorted(customer_ids), 0),
        ("seller", sorted(seller_ids), len(customer_ids)),
    ):
        for i, key in enumerate(keys, offset + 1):
            result["users"].append(
                dict(
                    id=i,
                    password="!olist-import",
                    last_login="",
                    is_superuser=False,
                    username=f"olist-{role}-{key}",
                    first_name="",
                    last_name="",
                    email="",
                    is_staff=False,
                    is_active=True,
                    date_joined=timestamp(joined[role].get(key, first_purchase)),
                    role=role,
                )
            )
    purchases = {r["customer_id"]: r["order_purchase_timestamp"] for r in kept_orders}
    for key, i in customer_ids.items():
        # The latest retained purchase address wins; stable source ID breaks ties.
        row = max(customer_rows[key], key=lambda r: (purchases.get(r["customer_id"], ""), r["customer_id"]))
        result["customers"].append(
            dict(
                id=i,
                user_id=i,
                olist_customer_unique_id=key,
                zip_prefix=row["customer_zip_code_prefix"],
                city=row["customer_city"],
                state=row["customer_state"],
            )
        )
    for key, i in seller_ids.items():
        row = indexes["sellers"][key]
        result["sellers"].append(
            dict(
                id=i,
                user_id=len(customer_ids) + i,
                status="approved",
                shop_name=f"Olist seller {key[:8]}",
                olist_seller_id=key,
                zip_prefix=row["seller_zip_code_prefix"],
                city=row["seller_city"],
                state=row["seller_state"],
                has_generated_content=True,
            )
        )
    names = {r["product_category_name"]: r["product_category_name_english"] for r in raw["categories"]}
    names.update(HAND_TRANSLATIONS)
    category_names = sorted(
        {r["product_category_name"] for r in raw["products"] if r["product_category_name"]} | set(names)
    )
    category_names.append("")
    categories = {key: i for i, key in enumerate(category_names, 1)}
    for key, i in categories.items():
        if key and key not in names:
            raise ValueError(f"Missing category translation: {key}")
        english = names.get(key, "uncategorised")
        result["categories"].append(
            dict(
                id=i,
                slug=english.replace("_", "-"),
                name_en=english.replace("_", " ").capitalize(),
                name_pt=key or "Sem categoria",
                icon="package",
                hand_translated=key in HAND_TRANSLATIONS,
            )
        )
    by_product = defaultdict(list)
    for row in kept_items:
        by_product[(row["product_id"], row["seller_id"])].append(row)
    top_categories = Counter(indexes["products"][r["product_id"]]["product_category_name"] for r in kept_items)
    featured = set()
    for cat, _ in sorted(top_categories.items(), key=lambda x: (-x[1], x[0]))[:15]:
        choices = [
            (len(rows), key)
            for key, rows in by_product.items()
            if indexes["products"][key[0]]["product_category_name"] == cat
        ]
        featured.add(sorted(choices, key=lambda x: (-x[0], x[1]))[0][1])
    grouped_lines = defaultdict(list)
    for row in kept_items:
        # Original exact price is part of the key: unequal-price repeats never collapse.
        grouped_lines[(row["order_id"], row["product_id"], row["seller_id"], decimal(row["price"]))].append(row)
    product_freight = defaultdict(list)
    for (_, pid, sid, _), rows in grouped_lines.items():
        product_freight[(pid, sid)].append(sum((money(decimal(r["freight_value"]) * rate) for r in rows), ZERO))
    for key, i in product_ids.items():
        source = indexes["products"][key[0]]
        rows = by_product[key]
        dimensions = {}
        for original, field in (
            ("product_weight_g", "weight_g"),
            ("product_length_cm", "length_cm"),
            ("product_height_cm", "height_cm"),
            ("product_width_cm", "width_cm"),
        ):
            dimensions[field] = str(int(decimal(source[original]))) if source[original] else ""
        result["products"].append(
            dict(
                id=i,
                seller_id=seller_ids[key[1]],
                category_id=categories[source["product_category_name"]],
                olist_product_id=key[0],
                name="Pending generated content",
                price=exact_median([money(decimal(r["price"]) * rate) for r in rows]),
                freight=exact_median(product_freight[key]),
                stock=0,
                lead_time_days=0,
                active=len({r["order_id"] for r in rows}) >= 2,
                featured=key in featured,
                taken_down=False,
                taken_down_reason="",
                has_generated_content=False,
                demo_adjustment="",
                **dimensions,
            )
        )
    checkout_ids = {r["order_id"]: i for i, r in enumerate(kept_orders, 1)}
    order_keys = sorted({(r["order_id"], r["seller_id"]) for r in kept_items})
    order_ids = {key: i for i, key in enumerate(order_keys, 1)}
    line_ids = defaultdict(list)
    for i, (key, rows) in enumerate(sorted(grouped_lines.items()), 1):
        oid, pid, sid, price = key
        row = dict(
            id=i,
            order_id=order_ids[(oid, sid)],
            seller_id=seller_ids[sid],
            product_id=product_ids[(pid, sid)],
            quantity=len(rows),
            unit_price=money(price * rate),
            freight=sum((money(decimal(r["freight_value"]) * rate) for r in rows), ZERO),
            shipping_limit_at=timestamp(min(r["shipping_limit_date"] for r in rows)),
        )
        result["order_lines"].append(row)
        line_ids[oid].append(row)
    lines_by_order = defaultdict(list)
    for row in result["order_lines"]:
        lines_by_order[row["order_id"]].append(row)
    for key, i in order_ids.items():
        oid, sid = key
        source = indexes["orders"][oid]
        lines = lines_by_order[i]
        subtotal = sum((r["quantity"] * r["unit_price"] for r in lines), ZERO)
        freight = sum((r["freight"] for r in lines), ZERO)
        status = STATUSES[source["order_status"]]
        # Olist has no cancellation timestamp. Purchase time is the deterministic
        # conservative refund/cancellation anchor, explicitly recorded in the ledger.
        placed = timestamp(source["order_purchase_timestamp"])
        result["orders"].append(
            dict(
                id=i,
                checkout_id=checkout_ids[oid],
                seller_id=seller_ids[sid],
                status=status,
                items=subtotal,
                freight=freight,
                total=subtotal + freight,
                placed_at=placed,
                paid_at=timestamp(source["order_approved_at"]),
                shipped_at=timestamp(source["order_delivered_carrier_date"]),
                delivered_at=timestamp(source["order_delivered_customer_date"]),
                cancelled_at=placed if status == "cancelled" else "",
                estimated_delivery=timestamp(source["order_estimated_delivery_date"]),
            )
        )
        if status == "cancelled":
            result["refunds"].append(
                dict(
                    id=len(result["refunds"]) + 1,
                    order_id=i,
                    checkout_id=checkout_ids[oid],
                    amount=subtotal + freight,
                    reason="Imported Olist cancellation; time anchored to purchase",
                    refunded_at=placed,
                    imported=True,
                )
            )
    for source in kept_orders:
        oid = source["order_id"]
        total = sum((r["quantity"] * r["unit_price"] + r["freight"] for r in line_ids[oid]), ZERO)
        result["checkouts"].append(
            dict(
                id=checkout_ids[oid],
                customer_id=customer_ids[indexes["customers"][source["customer_id"]]["customer_unique_id"]],
                placed_at=timestamp(source["order_purchase_timestamp"]),
                total=total,
                idempotency_key="",
                olist_order_id=oid,
            )
        )
        original = sorted(payments[oid], key=lambda p: int(p["payment_sequential"]))
        paid = sum((decimal(p["payment_value"]) for p in original), ZERO)
        amounts = [money(total * decimal(p["payment_value"]) / paid) for p in original]
        largest = max(
            range(len(original)),
            key=lambda j: (decimal(original[j]["payment_value"]), -int(original[j]["payment_sequential"])),
        )
        amounts[largest] += total - sum(amounts, ZERO)
        if any(v < 0 for v in amounts):
            raise ValueError(f"Payment allocation became negative for {oid}")
        for p, amount in zip(original, amounts):
            result["payments"].append(
                dict(
                    id=len(result["payments"]) + 1,
                    checkout_id=checkout_ids[oid],
                    sequence=int(p["payment_sequential"]),
                    method=p["payment_type"],
                    instalments=max(1, int(p["payment_installments"])),
                    amount=amount,
                )
            )
    geo = defaultdict(list)
    for row in raw["geolocation"]:
        geo[row["geolocation_zip_code_prefix"]].append(row)
    for prefix, rows in sorted(geo.items()):

        def mode(field):
            return sorted(Counter(r[field] for r in rows).items(), key=lambda x: (-x[1], x[0]))[0][0]

        latitude = median([decimal(r["geolocation_lat"], nonnegative=False) for r in rows])
        longitude = median([decimal(r["geolocation_lng"], nonnegative=False) for r in rows])
        result["geolocation"].append(
            dict(
                zip_prefix=prefix,
                latitude=latitude.quantize(Decimal("0.00000001")),
                longitude=longitude.quantize(Decimal("0.00000001")),
                city=mode("geolocation_city"),
                state=mode("geolocation_state"),
            )
        )
    reviews = []

    def translated(text):
        if not text:
            return ""
        entry = translations.get(text_hash(text))
        if not entry or entry["source_text"] != text:
            raise ValueError(f"Missing translation for source hash {text_hash(text)}; run translate_reviews.py")
        return entry["english_text"]

    for oid, source in sorted(selected.items()):
        for line in line_ids[oid]:
            reviews.append(
                dict(
                    _id=line["id"],
                    order_line_id=line["id"],
                    order_id=line["order_id"],
                    checkout_id=checkout_ids[oid],
                    product_id=line["product_id"],
                    seller_id=line["seller_id"],
                    customer_id=result["checkouts"][checkout_ids[oid] - 1]["customer_id"],
                    score=int(source["review_score"]),
                    title_pt=source["review_comment_title"],
                    text_pt=source["review_comment_message"],
                    title_en=translated(source["review_comment_title"]),
                    text_en=translated(source["review_comment_message"]),
                    machine_translated=True,
                    from_order_review=len(line_ids[oid]) > 1,
                    olist_review_id=source["review_id"],
                    created_at={"$date": timestamp(source["review_creation_date"])},
                    answered_at={"$date": timestamp(source["review_answer_timestamp"])},
                )
            )
    reviews.sort(key=lambda r: r["order_line_id"])
    review_groups = defaultdict(list)
    for row in reviews:
        review_groups[row["product_id"]].append(row)
    counts = [len(review_groups[i]) for i in product_ids.values()]
    prior = median([Decimal(count) for count in counts])
    mean = Decimal(sum(r["score"] for r in reviews)) / len(reviews) if reviews else Decimal("0")
    specs = []
    for product in result["products"]:
        history = review_groups[product["id"]]
        count, score_sum = len(history), sum(r["score"] for r in history)
        latest = sorted(
            history, key=lambda r: (r["answered_at"]["$date"], r["olist_review_id"], r["order_line_id"]), reverse=True
        )[:5]
        summary = {
            "count": count,
            "sum": score_sum,
            "average": Decimal(score_sum) / count if count else Decimal("0"),
            "distribution": {str(i): sum(r["score"] == i for r in history) for i in range(1, 6)},
            "bayesian": (Decimal(score_sum) + prior * mean) / (count + prior) if count + prior else Decimal("0"),
        }
        # Decimal128 can represent at most 34 significant digits; pipeline arithmetic
        # uses Decimal's default 28-digit context, with no float round-trip.
        specs.append(
            dict(
                _id=product["id"],
                category_id=product["category_id"],
                description="Pending generated content",
                attributes={},
                photo_file_id=None,
                rating_summary=summary,
                latest_reviews=latest,
                has_generated_content=False,
            )
        )
    rules["8"]["affected"] = sum(len(v) - 1 for v in _seller_sets(raw["order_items"]).values())
    rules["9"]["affected"] = len(kept_items) - len(result["order_lines"])
    rules["10"]["affected"] = sum(v > 1 for v in Counter(oid for oid, _ in order_keys).values())
    rules["11"]["affected"] = len(kept_orders)
    rules["12"]["affected"] = len(raw["geolocation"]) - len(result["geolocation"])
    rules["13"]["affected"] = len(kept_orders)
    rules["14"]["affected"] = len(kept_items)
    rules["15"]["affected"] = sum(p["active"] for p in result["products"])
    rules["16"]["affected"] = len(result["products"])
    rules["17"]["affected"] = len(result["refunds"])
    kept_source_products = {p for p, _ in product_ids}
    dropped_products = sorted(set(indexes["products"]) - kept_source_products)
    all_pairs = {(r["product_id"], r["seller_id"]) for r in raw["order_items"]}
    dropped_pairs = sorted(all_pairs - set(product_ids))
    rules["18"] = {
        "affected": len(dropped_pairs),
        "source_product_ids": dropped_products,
        "seller_product_keys": [{"olist_product_id": pid, "olist_seller_id": sid} for pid, sid in dropped_pairs],
        "source_products_without_any_original_lines": sorted(set(indexes["products"]) - {p for p, _ in all_pairs}),
    }
    source_kept = {
        "orders": len(kept_orders),
        "order_items": len(kept_items),
        "order_payments": sum(r["order_id"] in kept_ids for r in raw["order_payments"]),
        "order_reviews": len(selected),
        "products": len(kept_source_products),
    }
    ledger = {
        "version": 1,
        "rules": rules,
        "tables": {},
        "output_counts": {k: len(v) for k, v in result.items()},
        "assumptions": {
            "refund_time": "Purchase time: Olist has no cancellation timestamp",
            "customer_address": "Latest retained purchase, then source customer ID",
            "user_date_joined": "Earliest source purchase for that customer/seller; earliest dataset purchase if no observed activity; Olist provides no signup date",
            "geolocation": "All source points contribute to medians; grouping is transformation, not row removal",
            "freight_median": "Median collapsed order-line freight, rounded half-up",
            "prior_population": "All retained seller-products including zero-review products",
        },
        "fx": fx,
        "shift_weeks": 426,
        "source_sha256": {
            name: hashlib.sha256((raw_path / name).read_bytes()).hexdigest() for name in RAW_FILES.values()
        },
    }
    for key, rows in raw.items():
        kept = source_kept.get(key, len(rows))
        ledger["tables"][key] = dict(read=len(rows), kept=kept, removed=len(rows) - kept, transformed=kept)
    ledger["output_counts"].update(reviews=len(reviews), product_specs=len(specs), platform_stats=1)
    nullable = {
        "users": {"last_login"},
        "products": {"weight_g", "length_cm", "height_cm", "width_cm"},
        "checkouts": {"idempotency_key", "olist_order_id"},
        "orders": {"paid_at", "shipped_at", "delivered_at", "cancelled_at"},
    }
    for table, rows in result.items():
        for row in rows:
            for field in nullable.get(table, set()):
                if row[field] == "":
                    row[field] = "\\N"
        write_csv(output / f"{table}.csv", rows, FIELDS[table])
    write_ndjson(output / "reviews.ndjson", reviews)
    write_ndjson(output / "product_specs.ndjson", specs)
    write_ndjson(output / "platform_stats.ndjson", [{"_id": "bayesian", "m": mean, "C": prior}])
    write_json(output / "cleaning_ledger.json", ledger)
    checksums(output)
    print(json.dumps({"output_counts": ledger["output_counts"], "removed_orders": len(removed)}, sort_keys=True))
    return ledger


def _seller_sets(rows):
    result = defaultdict(set)
    for row in rows:
        result[row["product_id"]].add(row["seller_id"])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=ROOT / "data/raw/olist")
    parser.add_argument("--output", type=Path, default=ROOT / "data/derived/olist/clean")
    parser.add_argument("--translations", type=Path, default=ROOT / "data/derived/olist/translations.csv")
    parser.add_argument("--fx", type=Path, default=ROOT / "data/derived/olist/fx.json")
    args = parser.parse_args()
    try:
        clean(args.raw, args.output, args.translations, args.fx)
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f"Cleaning failed: {error}\n")


if __name__ == "__main__":
    main()
