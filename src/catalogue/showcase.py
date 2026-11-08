"""Load the committed demonstration catalogue: photos for named Olist products, a merchant and a few new products.

The data lives in ``data/demo_showcase/catalogue.json`` and ``data/demo_photos/``, so a fresh clone gets the same
catalogue and nothing depends on one person's database. Writes go through the same code the seller screens use
(``ProductForm`` and ``save_product``), so every rule about prices, stock, attributes, photos and audit rows applies.
Everything here is demonstration content: products and shops carry the generated-content label (AGENTS.md rule 9).
"""

import csv
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from gridfs import GridFS
from pymongo.errors import PyMongoError

from accounts.audit import set_audit_context
from accounts.models import Seller
from config import mongo

from .forms import attribute_text
from .icons import ICON_GROUPS
from .models import Category, Product
from .photos import MAX_UPLOAD, clean_photo
from .seller_forms import ProductForm
from .services import save_product

MAX_NEW_PRODUCTS = 12
MAX_NEW_CATEGORIES = 2
MAX_MERCHANTS = 3
PHOTO_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
MERCHANT_USERNAME = re.compile(r"^demo-seller-[4-9]$")
ATTRIBUTE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
LICENCE_COLUMNS = ("file", "author", "source_url", "licence")
IMPORTED_CATEGORIES = Path("/app/data/derived/olist/clean/categories.csv")


class ShowcaseError(Exception):
    """Every problem found in the catalogue file, so one run shows them all."""

    def __init__(self, problems):
        super().__init__("\n".join(problems))
        self.problems = problems


@dataclass
class Summary:
    merchants: int = 0
    categories: int = 0
    products: int = 0
    photos: int = 0
    renamed_shops: int = 0
    featured: int = 0
    missing_photos: list = field(default_factory=list)
    skipped_products: list = field(default_factory=list)


def _text(value, low, high):
    return isinstance(value, str) and low <= len(value.strip()) <= high


def read_catalogue(path, photos_dir):
    """Parse and validate the file and the photo folder. Raises ShowcaseError listing every problem."""
    problems = []
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ShowcaseError([f"{path} does not exist"]) from None
    except ValueError as error:
        raise ShowcaseError([f"{path} is not valid JSON: {error}"]) from None
    if not isinstance(data, dict):
        raise ShowcaseError(["The catalogue must be a JSON object"])
    unknown = set(data) - {"demo_shop_names", "merchants", "categories", "products", "olist_photos"}
    problems += [f"Unknown top-level key {key!r}" for key in sorted(unknown)]
    for key in ("merchants", "categories", "products", "olist_photos"):
        data.setdefault(key, [])
        if not isinstance(data[key], list):
            problems.append(f"{key} must be a list")
            data[key] = []
    shops = data.setdefault("demo_shop_names", {})
    if not isinstance(shops, dict) or not all(_text(name, 3, 150) for name in shops.values()):
        problems.append("demo_shop_names must map a demo seller username to a name of 3 to 150 characters")
        data["demo_shop_names"] = {}

    if len(data["merchants"]) > MAX_MERCHANTS:
        problems.append(f"At most {MAX_MERCHANTS} new merchants")
    if len(data["categories"]) > MAX_NEW_CATEGORIES:
        problems.append(f"At most {MAX_NEW_CATEGORIES} new categories")
    if len(data["products"]) > MAX_NEW_PRODUCTS:
        problems.append(f"At most {MAX_NEW_PRODUCTS} new products")

    merchants = set()
    for index, merchant in enumerate(data["merchants"], 1):
        where = f"merchants[{index}]"
        if not isinstance(merchant, dict):
            problems.append(f"{where} must be an object")
            continue
        username = merchant.get("username")
        if not isinstance(username, str) or not MERCHANT_USERNAME.match(username):
            problems.append(f"{where}.username must be demo-seller-4 to demo-seller-9")
        elif username in merchants:
            problems.append(f"{where}.username {username} is repeated")
        else:
            merchants.add(username)
        if not _text(merchant.get("shop_name"), 3, 150):
            problems.append(f"{where}.shop_name must be 3 to 150 characters")
        state = merchant.get("state", "SP")
        if not (isinstance(state, str) and re.fullmatch(r"[A-Z]{2}", state)):
            problems.append(f"{where}.state must be two capital letters")
        if not _text(merchant.get("city", "sao paulo"), 1, 100):
            problems.append(f"{where}.city must be 1 to 100 characters")

    imported = _imported_slugs()
    slugs = set()
    for index, category in enumerate(data["categories"], 1):
        where = f"categories[{index}]"
        if not isinstance(category, dict):
            problems.append(f"{where} must be an object")
            continue
        slug = category.get("slug")
        if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug) or len(slug) > 100:
            problems.append(f"{where}.slug must be lowercase words joined by hyphens")
        elif slug in imported:
            problems.append(f"{where}.slug {slug} is an imported category; use it in products without listing it here")
        elif slug in slugs:
            problems.append(f"{where}.slug {slug} is repeated")
        else:
            slugs.add(slug)
        if not _text(category.get("name_en"), 2, 100):
            problems.append(f"{where}.name_en must be 2 to 100 characters")
        if "name_pt" in category and not _text(category["name_pt"], 2, 100):
            problems.append(f"{where}.name_pt must be 2 to 100 characters")
        icon = category.get("icon", "package")
        if icon not in set(ICON_GROUPS):
            problems.append(f"{where}.icon must be one of: {', '.join(sorted(ICON_GROUPS))}")
        problems += _attribute_problems(f"{where}.attributes", category.get("attributes"))

    names = set()
    for index, item in enumerate(data["products"], 1):
        where = f"products[{index}]"
        if not isinstance(item, dict):
            problems.append(f"{where} must be an object")
            continue
        if item.get("merchant") not in merchants:
            problems.append(f"{where}.merchant must be one of the merchants listed in this file")
        if not _text(item.get("name"), 3, 200):
            problems.append(f"{where}.name must be 3 to 200 characters")
        elif (item.get("merchant"), item["name"]) in names:
            problems.append(f"{where}.name is repeated for this merchant")
        else:
            names.add((item.get("merchant"), item["name"]))
        if not _text(item.get("description"), 10, 5000):
            problems.append(f"{where}.description must be 10 to 5000 characters")
        if item.get("category") is None or not isinstance(item.get("category"), str):
            problems.append(f"{where}.category must be a category slug")
        if not isinstance(item.get("attributes", {}), dict):
            problems.append(f"{where}.attributes must be an object")
        try:
            if Decimal(str(item.get("price"))) <= 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            problems.append(f'{where}.price must be a positive amount such as "24.90"')

    for index, entry in enumerate(data["olist_photos"], 1):
        where = f"olist_photos[{index}]"
        if not (
            isinstance(entry, dict) and isinstance(entry.get("product_id"), int) and _text(entry.get("name"), 3, 200)
        ):
            problems.append(f"{where} needs an integer product_id and the product's expected name")

    problems += _photo_problems(data, Path(photos_dir))
    if problems:
        raise ShowcaseError(problems)
    return data


def _imported_slugs():
    try:
        with IMPORTED_CATEGORIES.open(encoding="utf-8", newline="") as stream:
            return {row["slug"] for row in csv.DictReader(stream)}
    except OSError:
        return set()


def _attribute_problems(where, attributes):
    if attributes is None:
        return []
    if not isinstance(attributes, dict):
        return [f"{where} must be an object"]
    problems = []
    for name, definition in attributes.items():
        if not ATTRIBUTE_NAME.match(str(name)):
            problems.append(f"{where}.{name}: use lowercase letters, numbers and underscores")
            continue
        if not isinstance(definition, dict) or definition.get("type") not in {"string", "integer", "boolean"}:
            problems.append(f"{where}.{name}.type must be string, integer or boolean")
            continue
        values = definition.get("values", [])
        if not isinstance(values, list) or len(values) > 30:
            problems.append(f"{where}.{name}.values must be a list of at most 30 values")
        elif definition["type"] == "integer" and not all(
            isinstance(v, int) and not isinstance(v, bool) for v in values
        ):
            problems.append(f"{where}.{name}.values must be whole numbers")
        elif definition["type"] == "string" and not all(isinstance(v, str) and 0 < len(v) <= 100 for v in values):
            problems.append(f"{where}.{name}.values must be non-empty text of at most 100 characters")
        elif definition["type"] == "boolean" and not all(isinstance(v, bool) for v in values):
            problems.append(f"{where}.{name}.values must be true or false")
    return problems


def photo_name(entry, photos_dir):
    """The photo file for an Olist showcase entry: the named one, else <product id> with any allowed extension."""
    if entry.get("photo"):
        return entry["photo"]
    for suffix in PHOTO_TYPES:
        if (Path(photos_dir) / f"{entry.get('product_id')}{suffix}").exists():
            return f"{entry['product_id']}{suffix}"
    return f"{entry.get('product_id')}.jpg"


def _licences(photos_dir):
    path = photos_dir / "licences.csv"
    if not path.exists():
        return {}, [f"{path} is missing (columns: {', '.join(LICENCE_COLUMNS)})"]
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != LICENCE_COLUMNS:
            return {}, [f"{path} must have exactly the columns {', '.join(LICENCE_COLUMNS)}"]
        return {row["file"]: row for row in reader}, []


def _photo_problems(data, photos_dir):
    referenced = [item.get("photo") for item in data["products"] if isinstance(item, dict) and item.get("photo")]
    referenced += [photo_name(entry, photos_dir) for entry in data["olist_photos"] if isinstance(entry, dict)]
    licences, problems = _licences(photos_dir)
    seen = set()
    for name in referenced:
        if name in seen:
            problems.append(f"Photo {name} is used more than once")
            continue
        seen.add(name)
        if not isinstance(name, str) or Path(name).name != name or Path(name).suffix.lower() not in PHOTO_TYPES:
            problems.append(f"Photo {name!r} must be a plain .jpg, .jpeg, .png or .webp file name")
            continue
        path = photos_dir / name
        if not path.exists():
            continue  # reported as missing, not as an error: photos arrive after the catalogue
        if path.stat().st_size > MAX_UPLOAD:
            problems.append(f"Photo {name} is larger than 2 MB")
        row = licences.get(name)
        if row is None or not all((row.get(column) or "").strip() for column in LICENCE_COLUMNS):
            problems.append(f"Photo {name} needs a complete row in licences.csv ({', '.join(LICENCE_COLUMNS)})")
        elif not row["source_url"].startswith("https://"):
            problems.append(f"Photo {name}: source_url must start with https://")
    return problems


def _encoded_photo(photos_dir, name):
    path = Path(photos_dir) / name
    upload = SimpleUploadedFile(name, path.read_bytes(), content_type=PHOTO_TYPES[path.suffix.lower()])
    try:
        return clean_photo(upload)
    except ValidationError as error:
        raise ShowcaseError([f"Photo {name}: {' '.join(error.messages)}"]) from None


def _delete_photo(database, file_id):
    if file_id:
        try:
            GridFS(database, collection="photos").delete(file_id)
        except PyMongoError:
            pass


def load(catalogue_path, photos_dir, password):
    """Validate, then create or update merchants, categories, products and photos. Safe to run repeatedly."""
    photos_dir = Path(photos_dir)
    data = read_catalogue(catalogue_path, photos_dir)
    summary = Summary()
    User = get_user_model()
    showcase_ids = set()
    with mongo.client() as client:
        database = client[mongo.database_name()]

        with transaction.atomic():
            set_audit_context()
            for username, shop_name in data["demo_shop_names"].items():
                updated = Seller.objects.filter(user__username=username).update(shop_name=shop_name)
                summary.renamed_shops += updated
            sellers = {}
            for merchant in data["merchants"]:
                user, _ = User.objects.get_or_create(username=merchant["username"], defaults={"role": "seller"})
                if user.role != "seller":
                    raise ShowcaseError([f"{merchant['username']} belongs to another role"])
                user.set_password(password)
                user.save()
                seller, _ = Seller.objects.update_or_create(
                    user=user,
                    defaults={
                        "status": Seller.Status.APPROVED,
                        "shop_name": merchant["shop_name"].strip(),
                        "city": merchant.get("city", "sao paulo"),
                        "state": merchant.get("state", "SP"),
                        "has_generated_content": True,
                    },
                )
                sellers[merchant["username"]] = seller
                summary.merchants += 1

            for entry in data["categories"]:
                category, _ = Category.objects.update_or_create(
                    slug=entry["slug"],
                    defaults={
                        "name_en": entry["name_en"].strip(),
                        "name_pt": entry.get("name_pt", entry["name_en"]).strip(),
                        "icon": entry.get("icon", "package"),
                        "hand_translated": "name_pt" in entry,
                    },
                )
                template = database.category_templates.find_one({"category_id": category.pk})
                attributes = entry.get("attributes", {})
                if template is None:
                    database.category_templates.insert_one(
                        {
                            "_id": category.pk,
                            "category_id": category.pk,
                            "attributes": attributes,
                            "rich": True,
                            "has_generated_content": True,
                            "version": 1,
                        }
                    )
                elif template["attributes"] != attributes:
                    database.category_templates.update_one(
                        {"category_id": category.pk}, {"$set": {"attributes": attributes}, "$inc": {"version": 1}}
                    )
                summary.categories += 1

        for item in data["products"]:
            product = _save_new_product(database, item, sellers[item["merchant"]], photos_dir, summary)
            showcase_ids.add(product.pk)
            summary.products += 1

        for entry in data["olist_photos"]:
            name = photo_name(entry, photos_dir)
            product = Product.objects.filter(pk=entry["product_id"]).first()
            if product is None:
                summary.skipped_products.append(entry["product_id"])  # a smaller import, such as the test fixture
                continue
            if product.name != entry["name"]:
                raise ShowcaseError(
                    [
                        f"Product {product.pk} is now called {product.name!r}, not {entry['name']!r}: "
                        "the data was regenerated, so choose its showcase entry again"
                    ]
                )
            showcase_ids.add(product.pk)
            if not (photos_dir / name).exists():
                summary.missing_photos.append(name)
                continue
            photo = _encoded_photo(photos_dir, name)
            spec = database.product_specs.find_one({"_id": product.pk}, {"photo_file_id": 1})
            if spec is None:
                raise ShowcaseError([f"Product {product.pk} has no specification document"])
            new = GridFS(database, collection="photos").put(
                photo.data, metadata={"content_type": photo.content_type, "product_id": product.pk}
            )
            database.product_specs.update_one({"_id": product.pk}, {"$set": {"photo_file_id": new}})
            _delete_photo(database, spec.get("photo_file_id"))
            summary.photos += 1

    with transaction.atomic():
        set_audit_context()
        Product.objects.filter(featured=True).exclude(pk__in=showcase_ids).update(featured=False)
        summary.featured = Product.objects.filter(pk__in=showcase_ids).update(featured=True)
    return summary


def _save_new_product(database, item, seller, photos_dir, summary):
    category = Category.objects.filter(slug=item["category"]).first()
    if category is None:
        raise ShowcaseError([f"Product {item['name']!r}: category {item['category']!r} does not exist"])
    template = database.category_templates.find_one({"category_id": category.pk})
    if template is None:
        raise ShowcaseError([f"Category {item['category']!r} has no attribute template"])
    data = {
        "name": item["name"].strip(),
        "category": category.pk,
        "description": item["description"].strip(),
        "price": str(item["price"]),
        "freight": str(item.get("freight", "5.00")),
        "stock": str(item.get("stock", 40)),
        "lead_time_days": str(item.get("lead_time_days", 3)),
    }
    for key, value in item.get("attributes", {}).items():
        data["attr_" + key] = attribute_text(value)
    files = {}
    name = item.get("photo")
    if name and (photos_dir / name).exists():
        path = photos_dir / name
        files["photo"] = SimpleUploadedFile(name, path.read_bytes(), content_type=PHOTO_TYPES[path.suffix.lower()])
    elif name:
        summary.missing_photos.append(name)
    form = ProductForm(data, files, template=template)
    if not form.is_valid():
        details = "; ".join(
            f"{'photo ' + name if key == 'photo' else key}: {' '.join(messages)}"
            for key, messages in form.errors.items()
        )
        raise ShowcaseError([f"Product {item['name']!r}: {details}"])
    existing = Product.objects.filter(seller=seller, name=data["name"]).first()
    saved = save_product(seller, seller.user, form.cleaned_data, pk=existing.pk if existing else None)
    # Demonstration content, whoever wrote it: keep the generated-content label on the product and its specification.
    with transaction.atomic():
        set_audit_context()
        Product.objects.filter(pk=saved.pk).update(has_generated_content=True)
    database.product_specs.update_one({"_id": saved.pk}, {"$set": {"has_generated_content": True}})
    if files:
        summary.photos += 1
    return saved
