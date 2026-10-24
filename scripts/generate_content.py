"""Generate labelled product content with seed 82, stable per source seller-product.

Adding/reordering other rows never changes a product's generated content. Templates
are maintained separately in data/derived/olist/templates/categories.json.
"""
import argparse
import hashlib
import json
import random
from pathlib import Path

from olist_common import ROOT, checksums, read_csv, write_csv, write_ndjson

SEED = 82


def generate(output, template_path):
    output = Path(output)
    templates = json.loads(Path(template_path).read_text(encoding="utf-8"))
    if templates["seed"] != SEED:
        raise ValueError("Unexpected generation seed")
    products = read_csv(output / "products.csv")
    categories = {r["id"]: r for r in read_csv(output / "categories.csv")}
    sellers = {r["id"]: r["olist_seller_id"] for r in read_csv(output / "sellers.csv")}
    specs = {}
    with (output / "product_specs.ndjson").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            specs[row["_id"]] = row
    for row in products:
        category = categories[row["category_id"]]
        template = templates["categories"].get(category["name_pt"], templates["generic"])
        stable_key = f"{SEED}:{row['olist_product_id']}:{sellers[row['seller_id']]}"
        rng = random.Random(int(hashlib.sha256(stable_key.encode()).hexdigest(), 16))
        attributes = {name: rng.choice(definition["values"]) for name, definition in sorted(template["attributes"].items())}
        word = rng.choice(template["words"])
        row["name"] = f"{word} {category['name_en']} {row['olist_product_id'][:6].upper()}"
        row["stock"] = rng.randint(20, 200)
        row["lead_time_days"] = rng.randint(3, 14)
        row["has_generated_content"] = True
        attributes_text = "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in attributes.items())
        spec = specs[int(row["id"])]
        spec["description"] = f"Generated demonstration description for {row['name']}. {attributes_text}. Names, attributes, stock and lead times are generated; historical sales are Olist data."
        spec["attributes"] = attributes
        spec["has_generated_content"] = True
    documents = []
    for cid, category in sorted(categories.items(), key=lambda x: int(x[0])):
        template = templates["categories"].get(category["name_pt"], templates["generic"])
        documents.append({"_id": int(cid), "category_id": int(cid), "attributes": template["attributes"],
                          "rich": category["name_pt"] in templates["categories"], "has_generated_content": True, "version": 1})
    write_csv(output / "products.csv", products)
    write_ndjson(output / "product_specs.ndjson", [specs[key] for key in sorted(specs)])
    write_ndjson(output / "category_templates.ndjson", documents)
    ledger_path = output / "cleaning_ledger.json"
    ledger = json.loads(ledger_path.read_text())
    ledger["output_counts"]["category_templates"] = len(documents)
    ledger["generation"] = {"seed": SEED, "algorithm": "per-product SHA256 seed, random.Random, sorted template attributes",
                            "template_sha256": hashlib.sha256(Path(template_path).read_bytes()).hexdigest()}
    from olist_common import write_json
    write_json(ledger_path, ledger)
    checksums(output)
    print(f"Generated content for {len(products)} seller-products and {len(documents)} category templates (seed {SEED})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/derived/olist/clean")
    parser.add_argument("--templates", type=Path, default=ROOT / "data/derived/olist/templates/categories.json")
    parser.add_argument("--checksum-root", type=Path, help="Refresh all approved derived checksums after the pipeline and profiler finish")
    args = parser.parse_args()
    generate(args.output, args.templates)
    if args.checksum_root:
        checksums(args.checksum_root)
