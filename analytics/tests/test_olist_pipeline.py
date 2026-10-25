"""The real deterministic fixture exercises every approved cleaning rule."""
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

import pytest
from clean_olist import clean, validate
from generate_content import generate
from olist_common import RAW_FILES, STATUSES, ZERO, checksums, decimal, exact_median, latest_reviews, money, read_csv, read_raw, timestamp
from translate_reviews import read_translations, text_hash

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/olist"
FX = ROOT / "data/derived/olist/fx.json"
TEMPLATES = ROOT / "data/derived/olist/templates/categories.json"


@pytest.fixture(scope="session")
def pipeline(tmp_path_factory):
    output = tmp_path_factory.mktemp("olist-clean")
    raw = read_raw(FIXTURE / "raw")
    ledger = clean(FIXTURE / "raw", output, FIXTURE / "translations.csv", FX)
    generate(output, TEMPLATES)
    tables = {p.stem: read_csv(p) for p in output.glob("*.csv")}
    documents = {p.stem: [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()] for p in output.glob("*.ndjson")}
    return output, raw, ledger, tables, documents


def kept_order_ids(tables):
    return {r["olist_order_id"] for r in tables["checkouts"]}


def test_fixture_contains_real_adversarial_cases():
    manifest = json.loads((FIXTURE / "raw/selection.json").read_text())
    for kind, rows in manifest["cases"].items():
        assert len(rows) >= (1 if kind == "no_payments" else 2), kind
    checksums(FIXTURE / "raw", verify=True)


def test_rule_1_tail_cutoff(pipeline):
    _, raw, ledger, tables, _ = pipeline
    tail = {r["order_id"] for r in raw["orders"] if r["order_purchase_timestamp"] >= "2018-09-01"}
    assert tail and tail.isdisjoint(kept_order_ids(tables))
    assert ledger["rules"]["1"]["affected"] == len(tail)


def test_rule_2_missing_lines_and_payments(pipeline):
    _, raw, _, tables, _ = pipeline
    items = {r["order_id"] for r in raw["order_items"]}
    paid = {r["order_id"] for r in raw["order_payments"]}
    assert kept_order_ids(tables) <= items & paid
    assert any(r["order_id"] not in items for r in raw["orders"])
    assert any(r["order_id"] not in paid for r in raw["orders"])


def test_rule_3_exact_payment_mismatches(pipeline):
    _, raw, ledger, tables, _ = pipeline
    paid, total = defaultdict(lambda: ZERO), defaultdict(lambda: ZERO)
    for r in raw["order_items"]:
        total[r["order_id"]] += decimal(r["price"]) + decimal(r["freight_value"])
    for r in raw["order_payments"]:
        paid[r["order_id"]] += decimal(r["payment_value"])
    bad = {oid for oid in total.keys() & paid.keys() if total[oid] != paid[oid]}
    assert bad and bad.isdisjoint(kept_order_ids(tables))
    assert ledger["rules"]["3"]["affected"] == len(bad)


def test_rule_4_undefined_payment(pipeline):
    _, raw, _, tables, _ = pipeline
    bad = {r["order_id"] for r in raw["order_payments"] if r["payment_type"] == "not_defined"}
    assert bad and bad.isdisjoint(kept_order_ids(tables))
    assert all(r["method"] != "not_defined" for r in tables["payments"])


def test_rule_5_contradictory_delivery_status(pipeline):
    _, raw, _, tables, _ = pipeline
    bad = {r["order_id"] for r in raw["orders"] if (r["order_status"] == "delivered") != bool(r["order_delivered_customer_date"])}
    assert bad and bad.isdisjoint(kept_order_ids(tables))


def test_rule_6_zero_instalments(pipeline):
    _, raw, ledger, tables, _ = pipeline
    zero = [r for r in raw["order_payments"] if r["payment_installments"] == "0" and r["order_id"] in kept_order_ids(tables)]
    assert zero and ledger["rules"]["6"]["affected"] == len(zero)
    assert all(int(r["instalments"]) >= 1 for r in tables["payments"])


def test_rule_7_latest_review_and_undelivered_history(pipeline):
    _, raw, _, tables, docs = pipeline
    selected = latest_reviews(raw)
    checkouts = {int(r["id"]): r["olist_order_id"] for r in tables["checkouts"]}
    statuses = {int(r["id"]): r["status"] for r in tables["orders"]}
    assert len({r["order_line_id"] for r in docs["reviews"]}) == len(docs["reviews"])
    assert any(statuses[r["order_id"]] != "delivered" for r in docs["reviews"])
    for row in docs["reviews"]:
        source = selected[checkouts[row["checkout_id"]]]
        assert row["olist_review_id"] == source["review_id"]
        assert row["answered_at"]["$date"] == timestamp(source["review_answer_timestamp"])
        assert row["text_pt"] == source["review_comment_message"]


def test_rule_8_split_shared_products(pipeline):
    _, _, _, tables, _ = pipeline
    pairs = {(r["olist_product_id"], r["seller_id"]) for r in tables["products"]}
    assert len(pairs) == len(tables["products"])
    assert any(v > 1 for v in Counter(r["olist_product_id"] for r in tables["products"]).values())


def test_rule_9_equal_price_line_collapse(pipeline):
    _, raw, _, tables, _ = pipeline
    grouped = Counter((r["order_id"], r["product_id"], r["seller_id"], decimal(r["price"]))
                      for r in raw["order_items"] if r["order_id"] in kept_order_ids(tables))
    assert any(v > 1 for v in grouped.values())
    assert len(tables["order_lines"]) == len(grouped)
    assert sum(int(r["quantity"]) for r in tables["order_lines"]) == sum(grouped.values())


def test_rule_10_split_orders_and_ownership(pipeline):
    _, _, _, tables, _ = pipeline
    products = {r["id"]: r for r in tables["products"]}
    orders = {r["id"]: r for r in tables["orders"]}
    assert any(v > 1 for v in Counter(r["checkout_id"] for r in orders.values()).values())
    assert len({(r["checkout_id"], r["seller_id"]) for r in orders.values()}) == len(orders)
    for row in tables["order_lines"]:
        assert row["seller_id"] == orders[row["order_id"]]["seller_id"] == products[row["product_id"]]["seller_id"]


def test_rule_11_status_and_category_mapping(pipeline):
    _, raw, _, tables, _ = pipeline
    checkouts = {r["id"]: r["olist_order_id"] for r in tables["checkouts"]}
    source = {r["order_id"]: r for r in raw["orders"]}
    for row in tables["orders"]:
        assert row["status"] == STATUSES[source[checkouts[row["checkout_id"]]]["order_status"]]
    assert len(tables["categories"]) == 74
    assert sum(r["hand_translated"] == "True" for r in tables["categories"]) == 2
    assert any(r["name_en"] == "Uncategorised" for r in tables["categories"])


def test_rule_12_geolocation_and_leading_zero_prefix(pipeline):
    _, raw, _, tables, _ = pipeline
    from statistics import median
    grouped = defaultdict(list)
    for row in raw["geolocation"]:
        grouped[row["geolocation_zip_code_prefix"]].append(row)
    assert len(tables["geolocation"]) == len(grouped)
    assert any(r["zip_prefix"].startswith("0") for r in tables["geolocation"])
    for row in tables["geolocation"]:
        source = grouped[row["zip_prefix"]]
        assert Decimal(row["latitude"]) == median(Decimal(r["geolocation_lat"]) for r in source).quantize(Decimal("0.00000001"))
        assert row["city"] == sorted(Counter(r["geolocation_city"] for r in source).items(), key=lambda x: (-x[1], x[0]))[0][0]


def test_rule_13_fixed_shift_and_local_timezone(pipeline):
    _, raw, _, tables, _ = pipeline
    source = {r["order_id"]: r for r in raw["orders"]}
    for row in tables["checkouts"]:
        assert row["placed_at"] == timestamp(source[row["olist_order_id"]]["order_purchase_timestamp"])
        assert row["placed_at"].endswith("+08:00")
    assert timestamp("2018-08-31 00:00:00") == "2026-10-30T00:00:00+08:00"


def test_rule_14_exact_sgd_rounding_and_payment_allocation(pipeline):
    _, raw, _, tables, _ = pipeline
    fx = json.loads(FX.read_text())
    rate = Decimal(fx["eur_sgd"]) / Decimal(fx["eur_brl"])
    # Validate each persisted line against original items, not the cleaning code's totals.
    checkouts = {r["id"]: r["olist_order_id"] for r in tables["checkouts"]}
    orders = {r["id"]: r for r in tables["orders"]}
    products = {r["id"]: r for r in tables["products"]}
    sellers = {r["id"]: r["olist_seller_id"] for r in tables["sellers"]}
    for line in tables["order_lines"]:
        oid = checkouts[orders[line["order_id"]]["checkout_id"]]
        pid = products[line["product_id"]]["olist_product_id"]
        sources = [r for r in raw["order_items"] if r["order_id"] == oid and r["product_id"] == pid and r["seller_id"] == sellers[line["seller_id"]]
                   and money(Decimal(r["price"]) * rate) == Decimal(line["unit_price"])]
        assert len(sources) >= int(line["quantity"])
        assert Decimal(line["freight"]) == sum((money(Decimal(r["freight_value"]) * rate) for r in sources), ZERO)
    for checkout in tables["checkouts"]:
        paid = sum((Decimal(r["amount"]) for r in tables["payments"] if r["checkout_id"] == checkout["id"]), ZERO)
        assert paid == Decimal(checkout["total"])
    assert money("0.005") == Decimal("0.01")


def test_rule_15_active_and_featured(pipeline):
    _, _, _, tables, _ = pipeline
    order_checkout = {r["id"]: r["checkout_id"] for r in tables["orders"]}
    appearances = defaultdict(set)
    for line in tables["order_lines"]:
        appearances[line["product_id"]].add(order_checkout[line["order_id"]])
    for row in tables["products"]:
        assert (row["active"] == "True") == (len(appearances[row["id"]]) >= 2)
    assert sum(r["featured"] == "True" for r in tables["products"]) == 15


def test_rule_16_product_freight_median(pipeline):
    _, _, _, tables, _ = pipeline
    for product in tables["products"]:
        assert Decimal(product["freight"]) == exact_median([Decimal(r["freight"]) for r in tables["order_lines"] if r["product_id"] == product["id"]])


def test_rule_17_imported_refunds(pipeline):
    _, _, _, tables, _ = pipeline
    cancelled = {r["id"]: r for r in tables["orders"] if r["status"] == "cancelled"}
    assert cancelled and {r["order_id"] for r in tables["refunds"]} == set(cancelled)
    for row in tables["refunds"]:
        assert row["imported"] == "True" and row["amount"] == cancelled[row["order_id"]]["total"]
        assert row["checkout_id"] == cancelled[row["order_id"]]["checkout_id"]


def test_rule_18_removes_exactly_products_without_lines(pipeline):
    _, raw, ledger, tables, _ = pipeline
    surviving = {r["product_id"] for r in raw["order_items"] if r["order_id"] in kept_order_ids(tables)}
    dropped = {r["product_id"] for r in raw["products"]} - surviving
    assert dropped == set(ledger["rules"]["18"]["source_product_ids"])
    assert {r["olist_product_id"] for r in tables["products"]} == surviving
    all_pairs = {(r["product_id"], r["seller_id"]) for r in raw["order_items"]}
    kept_pairs = {(r["product_id"], r["seller_id"]) for r in raw["order_items"] if r["order_id"] in kept_order_ids(tables)}
    assert {(r["olist_product_id"], r["olist_seller_id"]) for r in ledger["rules"]["18"]["seller_product_keys"]} == all_pairs - kept_pairs
    assert ledger["rules"]["18"]["affected"] == len(all_pairs - kept_pairs)


def test_source_ledger_accounts_for_every_row(pipeline):
    _, raw, ledger, _, _ = pipeline
    for table, values in ledger["tables"].items():
        assert values["read"] == len(raw[table]) == values["kept"] + values["removed"]
        assert 0 <= values["transformed"] <= values["kept"]


def test_two_equivalent_runs_are_byte_identical_and_generation_idempotent(pipeline, tmp_path):
    output, raw, _, _, _ = pipeline
    shuffled = tmp_path / "raw"
    from olist_common import write_csv
    for table, rows in raw.items():
        write_csv(shuffled / RAW_FILES[table], list(reversed(rows)))
    other = tmp_path / "clean"
    clean(shuffled, other, FIXTURE / "translations.csv", FX)
    generate(other, TEMPLATES)
    # Source bytes differ deliberately; the ledger records those hashes. All data
    # outputs stay identical, while provenance correctly records the difference.
    for path in output.iterdir():
        if path.name not in {"checksums.txt", "cleaning_ledger.json"}:
            assert path.read_bytes() == (other / path.name).read_bytes(), path.name
    same = tmp_path / "same"
    clean(FIXTURE / "raw", same, FIXTURE / "translations.csv", FX)
    generate(same, TEMPLATES)
    assert checksums(output, verify=True) == checksums(same, verify=True)
    before = checksums(same, verify=True)
    generate(same, TEMPLATES)
    assert checksums(same, verify=True) == before


def test_generated_content_and_bayesian_subset(pipeline):
    _, _, _, tables, docs = pipeline
    templates = json.loads(TEMPLATES.read_text())
    assert len(templates["categories"]) == 15
    assert all(r["has_generated_content"] == "True" and int(r["stock"]) >= 20 and 3 <= int(r["lead_time_days"]) <= 14 for r in tables["products"])
    assert len(docs["category_templates"]) == 74
    mean = Decimal(sum(r["score"] for r in docs["reviews"])) / len(docs["reviews"])
    from statistics import median
    prior = median([Decimal(sum(r["product_id"] == spec["_id"] for r in docs["reviews"])) for spec in docs["product_specs"]])
    assert Decimal(docs["platform_stats"][0]["m"]["$numberDecimal"]) == mean
    assert Decimal(docs["platform_stats"][0]["C"]["$numberDecimal"]) == prior
    for spec in docs["product_specs"]:
        history = [r for r in docs["reviews"] if r["product_id"] == spec["_id"]]
        assert spec["rating_summary"]["count"] == len(history)
        assert spec["rating_summary"]["sum"] == sum(r["score"] for r in history)
        assert len(spec["latest_reviews"]) == min(5, len(history))
        assert spec["has_generated_content"] and spec["attributes"]
        assert spec["rating_summary"]["distribution"] == {str(i): sum(r["score"] == i for r in history) for i in range(1,6)}
        expected = ((Decimal(sum(r["score"] for r in history)) + prior*mean)/(len(history)+prior)
                    if len(history)+prior else Decimal("0"))
        assert Decimal(spec["rating_summary"]["bayesian"]["$numberDecimal"]) == expected
        latest = sorted(history,key=lambda r:(r["answered_at"]["$date"],r["olist_review_id"],r["order_line_id"]),reverse=True)[:5]
        assert [r["order_line_id"] for r in spec["latest_reviews"]] == [r["order_line_id"] for r in latest]


@pytest.mark.parametrize("table,field,value", [
    ("order_items", "price", "NaN"), ("order_items", "price", "-1"),
    ("order_payments", "payment_value", "bad"), ("orders", "order_status", "intruder"),
    ("customers", "customer_zip_code_prefix", "0123"),
    ("order_items", "product_id", "x'); DROP TABLE catalogue_product; --"),
])
def test_malformed_or_inconsistent_raw_input_fails(pipeline, table, field, value):
    import copy
    rows = copy.deepcopy(pipeline[1])
    rows[table][0][field] = value
    with pytest.raises(ValueError):
        validate(rows)


def test_translation_hashes_are_verified_and_preserve_originals():
    rows = read_translations(FIXTURE / "translations.csv")
    assert rows and all(text_hash(r["source_text"]) == key and r["machine_translated"] == "true" for key, r in rows.items())


@pytest.mark.parametrize("days,bucket", [(-8,"early_over_7"),(-7,"early_up_to_7_or_on_time"),
    (0,"early_up_to_7_or_on_time"),(1,"late_1_to_7"),(7,"late_1_to_7"),
    (8,"late_8_to_14"),(14,"late_8_to_14"),(15,"late_over_14")])
def test_delivery_delay_bucket_boundaries_are_nonoverlapping(days,bucket):
    from datetime import datetime, timedelta

    from olist_common import delay_bucket
    estimated=datetime(2018,8,1)
    assert delay_bucket((estimated+timedelta(days=days)).isoformat(),estimated.isoformat()) == bucket


def test_missing_translations_fail_without_fake_english(tmp_path):
    with pytest.raises(ValueError, match="Missing translation"):
        clean(FIXTURE / "raw", tmp_path / "out", tmp_path / "missing.csv", FX)


def test_malformed_duplicate_csv_headers_fail_before_pandas_can_rename_them(tmp_path):
    (tmp_path / RAW_FILES["customers"]).write_text("customer_id,customer_id\n",encoding="utf-8")
    with pytest.raises(ValueError,match="duplicate columns"):
        read_raw(tmp_path)
