"""The demonstration catalogue loader: merchants, categories, products and photos from committed files."""

import csv
import json
from io import BytesIO, StringIO

import pytest
from bson import Decimal128
from checkout_helpers import product
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from PIL import Image

from accounts.models import Seller, User
from catalogue.models import Category, Product
from reviews.ratings import empty_summary

pytestmark = pytest.mark.django_db(transaction=True)
PASSWORD = "showcase-test-password"
STATS = {"_id": "bayesian", "m": Decimal128("4"), "C": Decimal128("2")}


@pytest.fixture(autouse=True)
def seller_password(monkeypatch):
    monkeypatch.setenv("DEMO_SELLER_PASSWORD", PASSWORD)


@pytest.fixture
def stats(mongo_db):
    mongo_db.platform_stats.insert_one(dict(STATS))


def spec_for(item, **changes):
    return {
        "_id": item.pk,
        "category_id": item.category_id,
        "description": "Example",
        "attributes": {},
        "photo_file_id": None,
        "rating_summary": empty_summary(STATS),
        "latest_reviews": [],
        "has_generated_content": False,
        **changes,
    }


def photo_bytes(colour="red", size=(60, 40), fmt="JPEG"):
    buffer = BytesIO()
    Image.new("RGB", size, colour).save(buffer, format=fmt)
    return buffer.getvalue()


def licence_row(name):
    return {"file": name, "author": "A. Photographer", "source_url": "https://example.com/p/" + name, "licence": "CC0"}


class Folder:
    def __init__(self, tmp_path):
        self.root = tmp_path
        self.photos = tmp_path / "photos"
        self.photos.mkdir()
        self.catalogue = tmp_path / "catalogue.json"
        self.licences = []

    def photo(self, name, data=None, licensed=True):
        (self.photos / name).write_bytes(data if data is not None else photo_bytes())
        if licensed:
            self.licences.append(licence_row(name))

    def write(self, **sections):
        base = {"demo_shop_names": {}, "merchants": [], "categories": [], "products": [], "olist_photos": []}
        self.catalogue.write_text(json.dumps({**base, **sections}), encoding="utf-8")
        with (self.photos / "licences.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["file", "author", "source_url", "licence"])
            writer.writeheader()
            writer.writerows(self.licences)

    def run(self):
        out = StringIO()
        call_command("seed_showcase", catalogue=self.catalogue, photos=self.photos, stdout=out)
        return out.getvalue()


@pytest.fixture
def folder(tmp_path, stats):
    return Folder(tmp_path)


MERCHANT = {"username": "demo-seller-4", "shop_name": "Harbour Garden Supply", "city": "sao paulo", "state": "SP"}
CATEGORY = {
    "slug": "garden-decor-test",
    "name_en": "Garden decor",
    "icon": "leaf",
    "attributes": {"material": {"type": "string", "values": ["steel", "wood"]}},
}


def new_product(**changes):
    item = {
        "merchant": "demo-seller-4",
        "category": "garden-decor-test",
        "name": "Steel garden trowel",
        "description": "A sturdy hand trowel for potting and planting.",
        "price": "24.90",
        "freight": "4.50",
        "stock": 40,
        "lead_time_days": 3,
        "attributes": {"material": "steel"},
        "photo": "trowel.jpg",
    }
    return {**item, **changes}


def test_loads_merchant_category_products_and_photos_and_reruns_cleanly(folder, mongo_db):
    existing = product("lamp")
    other = product("other")
    Product.objects.filter(pk=other.pk).update(featured=True)  # an old featured product must be cleared
    folder.photo("trowel.jpg")
    folder.photo(f"{existing.pk}.jpg", photo_bytes("blue"))
    mongo_db.product_specs.insert_one(spec_for(existing))
    folder.write(
        demo_shop_names={existing.seller.user.username: "Renamed Lamp House"},
        merchants=[MERCHANT],
        categories=[CATEGORY],
        products=[new_product()],
        olist_photos=[{"product_id": existing.pk, "name": "lamp"}],
    )
    output = folder.run()
    assert "1 merchants, 1 new categories, 1 new products, 2 photos, 1 demo shops renamed" in output

    seller = Seller.objects.get(user__username="demo-seller-4")
    assert seller.status == "approved" and seller.shop_name == "Harbour Garden Supply" and seller.has_generated_content
    assert User.objects.get(username="demo-seller-4").check_password(PASSWORD)
    category = Category.objects.get(slug="garden-decor-test")
    assert category.icon == "leaf" and category.name_pt == "Garden decor"
    assert mongo_db.category_templates.find_one({"category_id": category.pk})["attributes"] == CATEGORY["attributes"]

    item = Product.objects.get(name="Steel garden trowel")
    assert str(item.price) == "24.90" and item.featured and item.has_generated_content and item.seller == seller
    spec = mongo_db.product_specs.find_one({"_id": item.pk})
    assert spec["attributes"] == {"material": "steel"} and spec["has_generated_content"] is True
    stored = mongo_db.photos.files.find_one({"_id": spec["photo_file_id"]})
    assert stored["metadata"]["content_type"] == "image/jpeg" and stored["metadata"]["product_id"] == item.pk

    existing.refresh_from_db()
    other.refresh_from_db()
    assert existing.featured and not other.featured
    assert mongo_db.product_specs.find_one({"_id": existing.pk})["photo_file_id"] is not None
    assert Seller.objects.get(pk=existing.seller_id).shop_name == "Renamed Lamp House"

    files = mongo_db.photos.files.count_documents({})
    template_version = mongo_db.category_templates.find_one({"category_id": category.pk})["version"]
    folder.run()
    assert Product.objects.filter(name="Steel garden trowel").count() == 1
    assert Category.objects.filter(slug="garden-decor-test").count() == 1
    assert mongo_db.photos.files.count_documents({}) == files  # replaced, not accumulated
    assert mongo_db.category_templates.find_one({"category_id": category.pk})["version"] == template_version


def test_the_new_merchant_can_log_in_and_sees_only_their_own_products(folder, mongo_db):
    folder.photo("trowel.jpg")
    folder.write(merchants=[MERCHANT], categories=[CATEGORY], products=[new_product()])
    folder.run()
    client = Client()
    assert client.login(username="demo-seller-4", password=PASSWORD)
    page = client.get("/products/mine/")
    assert page.status_code == 200 and "Steel garden trowel" in page.content.decode()
    assert client.get("/products/").status_code == 200


def test_missing_photos_are_reported_not_fatal_and_unknown_products_are_skipped(folder, mongo_db):
    existing = product("lamp")
    mongo_db.product_specs.insert_one(spec_for(existing))
    folder.write(
        merchants=[MERCHANT],
        categories=[CATEGORY],
        products=[new_product()],
        olist_photos=[{"product_id": existing.pk, "name": "lamp"}, {"product_id": 9999999, "name": "Not here"}],
    )
    output = folder.run()
    assert "Photos not supplied yet (2): trowel.jpg, " + f"{existing.pk}.jpg" in output
    assert "Skipped 1 showcase products not in this database" in output
    assert Product.objects.filter(name="Steel garden trowel", featured=True).exists()


def test_a_renamed_product_stops_the_load_instead_of_matching_a_photo_to_the_wrong_name(folder, mongo_db):
    existing = product("lamp")
    mongo_db.product_specs.insert_one(spec_for(existing))
    folder.write(olist_photos=[{"product_id": existing.pk, "name": "A different generated name"}])
    with pytest.raises(CommandError, match="regenerated"):
        folder.run()


def test_every_structural_problem_is_listed_at_once_and_nothing_is_written(folder, mongo_db):
    folder.photo("big.jpg", b"x" * (2 * 1024 * 1024 + 1))
    folder.photo("unlicensed.jpg", licensed=False)
    folder.write(
        merchants=[{**MERCHANT, "username": "somebody-else"}],
        categories=[{**CATEGORY, "icon": "rocket"}],
        products=[
            new_product(price="free", photo="big.jpg"),
            new_product(name="Second", merchant="nobody", photo="unlicensed.jpg"),
            new_product(photo="../escape.jpg"),
        ],
    )
    with pytest.raises(CommandError) as raised:
        folder.run()
    text = str(raised.value)
    for fragment in (
        "username must be demo-seller-4 to demo-seller-9",
        "icon must be one of",
        "price must be a positive amount",
        "merchant must be one of the merchants listed",
        "larger than 2 MB",
        "needs a complete row in licences.csv",
        "must be a plain .jpg",
    ):
        assert fragment in text
    assert not Seller.objects.filter(user__username="somebody-else").exists()
    assert not Category.objects.filter(slug="garden-decor-test").exists()


def test_limits_on_new_products_and_categories_and_imported_slugs(folder, mongo_db, monkeypatch):
    import catalogue.showcase as showcase

    monkeypatch.setattr(showcase, "_imported_slugs", lambda: {"garden-tools"})
    folder.write(
        merchants=[MERCHANT],
        categories=[
            CATEGORY,
            {**CATEGORY, "slug": "second"},
            {**CATEGORY, "slug": "third"},
            {**CATEGORY, "slug": "garden-tools"},
        ],
        products=[new_product(name=f"Product number {number}") for number in range(13)],
    )
    with pytest.raises(CommandError) as raised:
        folder.run()
    text = str(raised.value)
    assert "At most 12 new products" in text and "At most 2 new categories" in text
    assert "is an imported category" in text


def test_a_product_the_seller_form_would_refuse_is_refused_here_too(folder, mongo_db):
    folder.photo("trowel.jpg")
    folder.write(
        merchants=[MERCHANT],
        categories=[CATEGORY],
        products=[new_product(attributes={"material": "diamond"}, stock=100000)],
    )
    with pytest.raises(CommandError) as raised:
        folder.run()
    assert "stock" in str(raised.value) and "attr_material" in str(raised.value)


def test_not_an_image_is_refused_with_the_file_name(folder, mongo_db):
    folder.photo("trowel.jpg", b"this is not an image")
    folder.write(merchants=[MERCHANT], categories=[CATEGORY], products=[new_product()])
    with pytest.raises(CommandError, match="trowel.jpg"):
        folder.run()


def test_the_password_variable_is_required(folder, monkeypatch):
    monkeypatch.setenv("DEMO_SELLER_PASSWORD", "")
    folder.write()
    with pytest.raises(CommandError, match="DEMO_SELLER_PASSWORD"):
        folder.run()


def test_featured_products_lead_a_category_page_by_default(folder, mongo_db):
    first, second, third = product("a"), product("b"), product("c")
    for item in (second, third):
        Product.objects.filter(pk=item.pk).update(category=first.category)
    Product.objects.filter(pk=first.pk).update(featured=True)  # the oldest id, yet it leads
    for item in (first, second, third):
        mongo_db.product_specs.insert_one(spec_for(item))
    response = Client().get("/products/", {"category": first.category_id})
    assert [p.pk for p in response.context["page_obj"]] == [first.pk, third.pk, second.pk]
    newest = Client().get("/products/", {"category": first.category_id, "sort": "newest"})
    assert [p.pk for p in newest.context["page_obj"]] == [third.pk, second.pk, first.pk]
