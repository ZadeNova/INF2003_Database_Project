"""Select a deterministic, real raw Olist subset with adversarial cases; never invent rows."""
import argparse
import sys
from collections import defaultdict
from pathlib import Path

from olist_common import RAW_FILES, ROOT, ZERO, checksums, decimal, read_raw, write_csv, write_json

sys.path.insert(0, str(ROOT / "analytics"))
from profile_olist import profile


def make_fixture(raw_path, output, size=1000):
    raw, output = read_raw(raw_path), Path(output)
    findings = profile(raw)
    selected, cases = set(), {}
    def include(label, ids, count=2):
        chosen = sorted(set(ids))[:count]
        selected.update(chosen)
        cases[label] = chosen
    for kind, ids in findings["broken_orders"].items():
        include(kind, ids)
    totals, paid = defaultdict(lambda: ZERO), defaultdict(lambda: ZERO)
    for row in raw["order_items"]:
        totals[row["order_id"]] += decimal(row["price"]) + decimal(row["freight_value"])
    for row in raw["order_payments"]:
        paid[row["order_id"]] += decimal(row["payment_value"])
    differences = {oid: abs(total - paid[oid]) for oid, total in totals.items() if oid in paid and total != paid[oid]}
    include("one_cent_payment_mismatch", [oid for oid, difference in differences.items() if difference == decimal("0.01")])
    include("larger_payment_mismatch", [oid for oid, difference in differences.items() if difference > decimal("0.01")])
    product_sellers, order_items, review_orders = defaultdict(lambda: defaultdict(list)), defaultdict(list), defaultdict(list)
    products = {r["product_id"]: r for r in raw["products"]}
    for row in raw["order_items"]:
        product_sellers[row["product_id"]][row["seller_id"]].append(row["order_id"])
        order_items[row["order_id"]].append(row)
    for row in raw["order_reviews"]:
        review_orders[row["order_id"]].append(row)
    include("duplicate_reviews", [k for k, v in review_orders.items() if len(v) > 1])
    include("multi_seller", [k for k, v in order_items.items() if len({r["seller_id"] for r in v}) > 1])
    include("repeated_lines", [k for k, v in order_items.items()
            if len({(r["product_id"], r["seller_id"], r["price"]) for r in v}) < len(v)])
    include("zero_instalments", [r["order_id"] for r in raw["order_payments"] if r["payment_installments"] == "0"])
    include("uncategorised", [r["order_id"] for r in raw["order_items"] if not products[r["product_id"]]["product_category_name"]])
    for category in ("pc_gamer", "portateis_cozinha_e_preparadores_de_alimentos"):
        include(category, [r["order_id"] for r in raw["order_items"] if products[r["product_id"]]["product_category_name"] == category])
    include("cancelled", [r["order_id"] for r in raw["orders"] if r["order_status"] == "canceled" and order_items[r["order_id"]]])
    include("undelivered_review", [r["order_id"] for r in raw["orders"] if r["order_status"] == "shipped" and r["order_id"] in review_orders])
    shared = sorted(k for k, v in product_sellers.items() if len(v) > 1)[:2]
    for pid in shared:
        include("shared_" + pid, [min(ids) for ids in product_sellers[pid].values()], count=20)
    # Include two genuinely high-volume products, with all their source orders,
    # so active/featured and seed_demo's two adjusted products are exercised.
    popular = sorted(product_sellers, key=lambda k: (-sum(len(v) for v in product_sellers[k].values()), k))[:2]
    for pid in popular:
        include("popular_" + pid, [oid for ids in product_sellers[pid].values() for oid in ids], count=size)
    for row in sorted(raw["orders"], key=lambda r: r["order_id"]):
        if len(selected) >= size:
            break
        selected.add(row["order_id"])
    tables = {"orders": [r for r in raw["orders"] if r["order_id"] in selected]}
    for table in ("order_items", "order_payments", "order_reviews"):
        tables[table] = [r for r in raw[table] if r["order_id"] in selected]
    customer_ids = {r["customer_id"] for r in tables["orders"]}
    seller_ids = {r["seller_id"] for r in tables["order_items"]}
    product_ids = {r["product_id"] for r in tables["order_items"]}
    # Extra source products intentionally demonstrate rule 18 without fabricating
    # a row. Their history lies outside this raw subset.
    product_ids.update(sorted(set(products) - product_ids)[:2])
    tables["customers"] = [r for r in raw["customers"] if r["customer_id"] in customer_ids]
    tables["sellers"] = [r for r in raw["sellers"] if r["seller_id"] in seller_ids]
    tables["products"] = [r for r in raw["products"] if r["product_id"] in product_ids]
    prefixes = sorted({r["geolocation_zip_code_prefix"] for r in raw["geolocation"]})[:20]
    tables["geolocation"] = [r for r in raw["geolocation"] if r["geolocation_zip_code_prefix"] in prefixes]
    tables["categories"] = raw["categories"]
    for table, rows in tables.items():
        write_csv(output / RAW_FILES[table], sorted(rows, key=lambda r: tuple(r[k] for k in sorted(r))), list(raw[table][0]))
    write_json(output / "selection.json", {"source": "Unmodified real Olist rows", "cases": cases,
                "source_counts": {k: len(v) for k, v in tables.items()},
                "scarce_cases": {k: len(v) for k, v in findings["broken_orders"].items() if len(v) < 2},
                "extra_products_for_rule_18": sorted(product_ids - {r["product_id"] for r in tables["order_items"]})})
    write_json(output.parent / "profile.json", profile(tables))
    checksums(output)
    print(f"Fixture selected {len(selected)} orders")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=ROOT / "data/raw/olist")
    parser.add_argument("--output", type=Path, default=ROOT / "tests/fixtures/olist/raw")
    parser.add_argument("--size", type=int, default=1000)
    args = parser.parse_args()
    make_fixture(args.raw, args.output, args.size)
