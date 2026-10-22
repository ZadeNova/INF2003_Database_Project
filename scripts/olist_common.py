"""Shared deterministic file formats and exact arithmetic for the Olist pipeline."""
import csv
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
RAW_FILES = {name: f"olist_{name}_dataset.csv" for name in
             ("customers", "geolocation", "order_items", "order_payments", "order_reviews", "orders", "products", "sellers")}
RAW_FILES["categories"] = "product_category_name_translation.csv"
SHIFT = timedelta(weeks=426)
SG = ZoneInfo("Asia/Singapore")
CENT = Decimal("0.01")
ZERO = Decimal("0.00")
STATUSES = {"created": "placed", "approved": "paid", "processing": "paid", "invoiced": "paid",
            "shipped": "shipped", "delivered": "delivered", "canceled": "cancelled", "unavailable": "cancelled"}
METHODS = {"credit_card", "boleto", "voucher", "debit_card", "not_defined"}
DELAY_BUCKETS = ("early_over_7", "early_up_to_7_or_on_time", "late_1_to_7", "late_8_to_14", "late_over_14")
HAND_TRANSLATIONS = {"portateis_cozinha_e_preparadores_de_alimentos": "portable_kitchen_and_food_preparers",
                     "pc_gamer": "gaming_pc"}


def decimal(value, *, label="number", nonnegative=True):
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"Malformed {label}: {value!r}") from None
    if not number.is_finite() or (nonnegative and number < 0):
        raise ValueError(f"Invalid {label}: {value!r}")
    return number


def money(value):
    return decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def exact_median(values):
    return money(median(values))


def timestamp(value):
    if not value:
        return ""
    parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return (parsed + SHIFT).replace(tzinfo=SG).isoformat()


def read_raw(path):
    # dtype=str and keep_default_na=False are both essential: zip prefixes and
    # text such as 'NA' must survive unchanged. No money column becomes a float.
    import pandas as pd
    result = {}
    for table, name in RAW_FILES.items():
        with (Path(path) / name).open(encoding="utf-8", newline="") as stream:
            header = next(csv.reader(stream), [])
        if not header or len(header) != len(set(header)):
            raise ValueError(f"Empty or duplicate columns in {name}")
        frame = pd.read_csv(Path(path) / name, dtype=str, keep_default_na=False)
        if frame.columns.duplicated().any() or frame.isna().any().any():
            raise ValueError(f"Malformed columns or missing cells in {name}")
        result[table] = frame.to_dict("records")
    return result


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows, fields=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def json_default(value):
    if isinstance(value, Decimal):
        return {"$numberDecimal": str(value)}
    raise TypeError(type(value).__name__)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                               default=json_default) + "\n", encoding="utf-8", newline="\n")


def write_ndjson(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                                    default=json_default) + "\n")


def checksums(path, *, verify=False):
    path = Path(path)
    files = sorted(p for p in path.rglob("*") if p.is_file() and p.name != "checksums.txt")
    content = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(path).as_posix()}\n" for p in files)
    target = path / "checksums.txt"
    if verify:
        if not target.exists() or target.read_text(encoding="utf-8") != content:
            raise ValueError(f"Checksums differ: {target}")
    else:
        target.write_text(content, encoding="utf-8", newline="\n")
    return content


def latest_reviews(raw):
    selected = {}
    for row in sorted(raw["order_reviews"], key=lambda r: (r["review_answer_timestamp"], r["review_id"])):
        selected[row["order_id"]] = row
    return selected


def delay_bucket(delivered, estimated):
    days = (datetime.fromisoformat(delivered).date() - datetime.fromisoformat(estimated).date()).days
    return ("early_over_7" if days < -7 else "early_up_to_7_or_on_time" if days <= 0
            else "late_1_to_7" if days <= 7 else "late_8_to_14" if days <= 14 else "late_over_14")


def delay_scores(raw):
    groups = {k: [] for k in DELAY_BUCKETS}
    reviews = latest_reviews(raw)
    for order in raw["orders"]:
        review = reviews.get(order["order_id"])
        if order["order_status"] == "delivered" and order["order_delivered_customer_date"] and review:
            bucket = delay_bucket(order["order_delivered_customer_date"], order["order_estimated_delivery_date"])
            groups[bucket].append(int(review["review_score"]))
    return {key: {"count": len(scores), "average": str((Decimal(sum(scores)) / len(scores)).quantize(Decimal("0.0001")))
                  if scores else None} for key, scores in groups.items()}
