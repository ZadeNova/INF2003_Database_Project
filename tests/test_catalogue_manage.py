"""Seller CRUD, real cross-store failures, raster uploads, moderation and live category options."""
from copy import deepcopy
from io import BytesIO, StringIO
import json

from bson import Decimal128
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from gridfs import GridFS
from PIL import Image, PngImagePlugin
from pymongo.errors import ConnectionFailure, WriteError
import pytest

from accounts.models import AuditLog
from catalogue.models import Category, Product
from catalogue.seller_forms import ProductForm
from catalogue.services import save_product
from account_helpers import make_customer, make_operator, make_seller

pytestmark = pytest.mark.django_db(transaction=True)


def product_audits():
    return AuditLog.objects.filter(table_name="catalogue_product")


@pytest.fixture
def shop(mongo_db):
    seller = make_seller()
    category = Category.objects.create(slug="housewares", name_en="Housewares", name_pt="Housewares")
    template = {"_id": category.pk, "category_id": category.pk, "rich": True,
                "has_generated_content": False, "version": 1, "attributes": {
                    "material": {"type": "string", "values": ["cotton", "steel"]},
                    "capacity": {"type": "integer", "values": [2, 4]},
                    "wireless": {"type": "boolean", "values": [True, False]}}}
    mongo_db.category_templates.insert_one(template)
    client = Client()
    client.force_login(seller.user)
    return seller, category, template, client


def data(category, **changes):
    return {"name": "Handmade kettle", "category": str(category.pk), "price": "12.34", "stock": "8",
            "freight": "1.23", "lead_time_days": "2", "description": "A seller-written description.",
            "attr_material": "steel", "attr_capacity": "2", "attr_wireless": "false", **changes}


def create(shop):
    seller, category, template, client = shop
    response = client.post("/products/mine/new/", data(category))
    assert response.status_code == 302
    return Product.objects.get(seller=seller)


def photo(format_name="PNG", name="kettle.png"):
    output = BytesIO()
    image = Image.new("RGB", (24, 16), (40, 90, 120))
    extra = PngImagePlugin.PngInfo()
    extra.add_text("Comment", "PRIVATE METADATA SENTINEL")
    image.save(output, format=format_name, **({"pnginfo": extra} if format_name == "PNG" else {}))
    return SimpleUploadedFile(name, output.getvalue(), content_type={"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[format_name])


def test_seller_creates_and_edits_own_product_in_both_stores(shop, mongo_db):
    seller, category, template, client = shop
    item = create(shop)
    spec = mongo_db.product_specs.find_one({"_id": item.pk})
    assert item.seller == seller and not item.has_generated_content and item.lead_time_days == 2
    assert spec["has_generated_content"] is False
    assert spec["attributes"] == {"material": "steel", "capacity": 2, "wireless": False}
    assert isinstance(spec["rating_summary"]["average"], Decimal128)
    response = client.post(f"/products/mine/{item.pk}/edit/", data(category, price="15.67", stock="5"))
    assert response.status_code == 302
    item.refresh_from_db()
    assert str(item.price) == "15.67" and item.stock == 5
    row = product_audits().get(table_name="catalogue_product")
    assert row.actor_id == seller.user_id and row.reason == "Seller saved product"
    assert row.before["stock"] == 8 and row.after["stock"] == 5
    assert Client().get(f"/products/{item.pk}/").status_code == 200


def test_seller_cannot_choose_another_owner_or_edit_another_shop(shop, mongo_db):
    seller, category, template, client = shop
    other = make_seller("other")
    response = client.post("/products/mine/new/", data(category, seller=str(other.pk), taken_down="true", has_generated_content="true"))
    assert response.status_code == 302
    item = Product.objects.get()
    assert item.seller == seller and not item.taken_down and not item.has_generated_content
    other_client = Client()
    other_client.force_login(other.user)
    assert "Handmade kettle" not in other_client.get("/products/mine/").content.decode()
    for method, path in (("get", f"/products/mine/{item.pk}/edit/"),
                         ("post", f"/products/mine/{item.pk}/edit/"),
                         ("post", f"/products/mine/{item.pk}/deactivate/")):
        assert getattr(other_client, method)(path, data(category)).status_code == 404


@pytest.mark.parametrize("field,value", [("lead_time_days", ""), ("stock", "-1"), ("price", "0.00"),
    ("freight", "-0.01"), ("attr_material", '{"$ne":null}'), ("attr_capacity", "3"),
    ("attr_wireless", "not-bool"), ("attr_$where", "sleep(1000)")])
def test_required_fields_and_template_values_are_validated(shop, mongo_db, field, value):
    _, category, _, client = shop
    assert client.post("/products/mine/new/", data(category, **{field: value})).status_code == 400
    assert not Product.objects.exists() and mongo_db.product_specs.count_documents({}) == 0


def test_deactivate_is_post_only_and_audited_and_keeps_spec(shop, mongo_db):
    seller, category, template, client = shop
    item = create(shop)
    path = f"/products/mine/{item.pk}/deactivate/"
    assert client.get(path).status_code == 405
    assert client.post(path).status_code == 302
    item.refresh_from_db()
    assert not item.active and mongo_db.product_specs.find_one({"_id": item.pk}) is not None
    row = product_audits().get()
    assert row.action == "product.deactivate" and row.actor_id == seller.user_id
    assert Client().get(f"/products/{item.pk}/").status_code == 404


def test_real_mongodb_connection_failure_after_sql_write_rolls_it_back(shop, mongo_db, monkeypatch):
    seller, category, template, client = shop
    item = create(shop)
    form = ProductForm(data(category, stock="1", price="99.99"), template=template, instance=item,
                       spec=mongo_db.product_specs.find_one({"_id": item.pk}))
    assert form.is_valid(), form.errors
    monkeypatch.setenv("MONGO_HOST", "127.0.0.1")
    monkeypatch.setenv("MONGO_PORT", "1")
    with pytest.raises(ConnectionFailure):
        save_product(seller, seller.user, form.cleaned_data, pk=item.pk)
    item.refresh_from_db()
    assert item.stock == 8 and str(item.price) == "12.34"
    assert not product_audits().exists()
    assert mongo_db.product_specs.find_one({"_id": item.pk})["description"] == "A seller-written description."


def test_real_mongodb_validator_failure_rolls_back_sql_and_audit(shop, mongo_db):
    seller, category, template, client = shop
    item = create(shop)
    form = ProductForm(data(category, stock="1"), template=template, instance=item,
                       spec=mongo_db.product_specs.find_one({"_id": item.pk}))
    assert form.is_valid()
    invalid_spec = {**form.cleaned_data, "attributes": ["not an outer-schema object"]}
    with pytest.raises(WriteError) as error:
        save_product(seller, seller.user, invalid_spec, pk=item.pk)
    assert error.value.code == 121
    item.refresh_from_db()
    assert item.stock == 8 and not product_audits().exists()
    assert mongo_db.product_specs.find_one({"_id": item.pk})["attributes"]["material"] == "steel"


@pytest.mark.parametrize("format_name,name", [("PNG", "photo.png"), ("JPEG", "photo.jpg"), ("WEBP", "photo.webp")])
def test_photos_are_reencoded_in_gridfs_and_served_with_cache_headers(shop, mongo_db, format_name, name):
    _, category, _, client = shop
    upload = photo(format_name, name)
    original = upload.read()
    upload.seek(0)
    assert client.post("/products/mine/new/", data(category, photo=upload)).status_code == 302
    item = Product.objects.get()
    spec = mongo_db.product_specs.find_one({"_id": item.pk})
    file = GridFS(mongo_db, collection="photos").get(spec["photo_file_id"])
    stored = file.read()
    assert stored != original and b"PRIVATE METADATA SENTINEL" not in stored
    assert Image.open(BytesIO(stored)).format in {"PNG", "JPEG"}
    response = Client().get(f"/products/photos/{spec['photo_file_id']}/")
    assert response.status_code == 200 and "max-age" in response["Cache-Control"] and response["ETag"]
    assert b"".join(response.streaming_content) == stored
    assert str(spec["photo_file_id"]) in Client().get(f"/products/{item.pk}/").content.decode()


def test_replacing_photo_deletes_old_file_after_storing_new_one(shop, mongo_db):
    _, category, _, client = shop
    assert client.post("/products/mine/new/", data(category, photo=photo())).status_code == 302
    item = Product.objects.get()
    old = mongo_db.product_specs.find_one({"_id": item.pk})["photo_file_id"]
    assert client.post(f"/products/mine/{item.pk}/edit/", data(category, photo=photo())).status_code == 302
    new = mongo_db.product_specs.find_one({"_id": item.pk})["photo_file_id"]
    files = GridFS(mongo_db, collection="photos")
    assert new != old and files.exists(new) and not files.exists(old)


@pytest.mark.parametrize("kind", ["svg", "oversize", "not_image", "gif", "fake_extension"])
def test_invalid_uploads_are_rejected_before_either_store_changes(shop, mongo_db, kind):
    _, category, _, client = shop
    if kind == "svg":
        upload = SimpleUploadedFile("image.svg", b'<svg xmlns="http://www.w3.org/2000/svg"/>', content_type="image/svg+xml")
    elif kind == "oversize":
        upload = SimpleUploadedFile("big.jpg", b"x" * (2 * 1024 * 1024 + 1), content_type="image/jpeg")
    elif kind == "not_image":
        upload = SimpleUploadedFile("bad.jpg", b"not an image", content_type="image/jpeg")
    elif kind == "fake_extension":
        upload = photo(name="image.svg")
    else:
        output = BytesIO()
        Image.new("RGB", (10, 10)).save(output, format="GIF")
        upload = SimpleUploadedFile("fake.png", output.getvalue(), content_type="image/png")
    assert client.post("/products/mine/new/", data(category, photo=upload)).status_code == 400
    assert not Product.objects.exists() and mongo_db.product_specs.count_documents({}) == 0


def test_seller_mutations_require_csrf_and_an_approved_seller(shop):
    seller, category, template, _ = shop
    csrf = Client(enforce_csrf_checks=True)
    csrf.force_login(seller.user)
    assert csrf.post("/products/mine/new/", data(category)).status_code == 403
    for status in ("pending", "rejected", "suspended"):
        blocked = make_seller(status, status=status)
        client = Client()
        client.force_login(blocked.user)
        assert client.get("/products/mine/").url == "/seller/status/"
        assert client.post("/products/mine/new/", data(category)).status_code == 403
    for user in (make_customer(), make_operator()):
        client = Client()
        client.force_login(user)
        assert client.get("/products/mine/").status_code == 403


def test_operator_takedown_restore_and_stale_actions_are_audited(shop, mongo_db):
    seller, category, template, seller_client = shop
    item = create(shop)
    operator = make_operator()
    client = Client()
    client.force_login(operator)
    path = f"/products/operator/{item.pk}/"
    assert client.post(path, {"action": "takedown", "reason": "Misleading description"}).status_code == 302
    assert Client().get(f"/products/{item.pk}/").status_code == 404
    assert seller_client.get(f"/products/mine/{item.pk}/edit/").status_code == 404
    assert seller_client.post(f"/products/mine/{item.pk}/edit/", data(category, taken_down="false")).status_code == 404
    assert client.post(path, {"action": "takedown", "reason": "Repeated action"}).status_code == 400
    row = product_audits().get()
    assert row.action == "product.takedown" and row.actor == operator and row.reason == "Misleading description"
    assert client.post(path, {"action": "restore", "reason": "Description corrected"}).status_code == 302
    assert Client().get(f"/products/{item.pk}/").status_code == 200
    item.refresh_from_db()
    assert not item.taken_down and item.taken_down_reason == ""
    assert seller_client.get(path).status_code == 403


def test_adding_an_option_needs_no_migration_or_collmod_and_immediately_facets(shop, mongo_db):
    seller, category, template, seller_client = shop
    item = create(shop)
    before = mongo_db.product_specs.options()
    operator = make_operator()
    client = Client()
    client.force_login(operator)
    path = f"/products/operator/categories/{category.pk}/"
    assert client.post(path, {"name": "finish", "kind": "string", "values": "matte\ngloss"}).status_code == 302
    assert mongo_db.category_templates.find_one({"_id": category.pk})["version"] == 2
    assert 'name="attr_finish"' in seller_client.get(f"/products/mine/{item.pk}/edit/").content.decode()
    assert seller_client.post(f"/products/mine/{item.pk}/edit/", data(category, attr_finish="matte")).status_code == 302
    response = Client().get("/products/", {"category": category.pk, "attr_finish": "matte"})
    assert response.status_code == 200 and response.context["result_count"] == 1
    assert ("finish", [{"value": "matte", "count": 1}]) in response.context["facet_groups"]
    assert mongo_db.product_specs.options() == before
    assert "spec_attributes" in mongo_db.product_specs.index_information()
    assert client.post(path, {"name": "finish", "kind": "string", "values": "other"}).status_code == 400


@pytest.mark.parametrize("name", ["$where", "colour.$ne", "finish);DROP TABLE catalogue_product;--"])
def test_operator_option_name_injection_is_rejected(shop, mongo_db, name):
    _, category, template, _ = shop
    operator = make_operator()
    client = Client()
    client.force_login(operator)
    assert client.post(f"/products/operator/categories/{category.pk}/", {"name": name, "kind": "string", "values": "x"}).status_code == 400
    assert mongo_db.category_templates.find_one({"_id": category.pk})["version"] == 1


def test_check_specs_reports_and_repairs_only_orphans(shop, mongo_db):
    item = create(shop)
    orphan = deepcopy(mongo_db.product_specs.find_one({"_id": item.pk}))
    orphan["_id"] = 999999
    mongo_db.product_specs.insert_one(orphan)
    output = StringIO()
    with pytest.raises(CommandError):
        call_command("check_specs", stdout=output)
    assert json.loads(output.getvalue())["orphan_specs"] == [999999]
    output = StringIO()
    call_command("check_specs", repair=True, stdout=output)
    assert json.loads(output.getvalue())["removed_orphan_specs"] == 1
    assert mongo_db.product_specs.find_one({"_id": item.pk}) is not None
    mongo_db.product_specs.delete_one({"_id": item.pk})
    output = StringIO()
    with pytest.raises(CommandError):
        call_command("check_specs", stdout=output)
    assert json.loads(output.getvalue())["missing_product_specs"] == [item.pk]


def test_product_audit_page_shows_the_shop_product_actor_and_values(shop, mongo_db):
    seller, category, template, client = shop
    item = create(shop)
    client.post(f"/products/mine/{item.pk}/edit/", data(category, stock="3", price="20.00"))
    operator = make_operator()
    client.force_login(operator)
    response = client.get("/operator/audit/")
    body = response.content.decode()
    assert response.status_code == 200
    assert item.name in body and seller.display_name in body and seller.user.username in body
    assert "12.34" in body and "20.00" in body and "Stock: 8" in body and "3" in body
    assert "Shop unavailable" not in body


def test_editing_keeps_rating_summary_and_latest_reviews_owned_by_reviews(shop, mongo_db):
    seller, category, template, client = shop
    item = create(shop)
    rating = {"count": 1, "sum": 5, "average": Decimal128("5"),
              "distribution": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 1}, "bayesian": Decimal128("4.5")}
    reviews = [{"score": 5, "text_en": "Existing review"}]
    mongo_db.product_specs.update_one({"_id": item.pk}, {"$set": {"rating_summary": rating, "latest_reviews": reviews}})
    assert client.post(f"/products/mine/{item.pk}/edit/", data(category, description="Updated description")).status_code == 302
    spec = mongo_db.product_specs.find_one({"_id": item.pk})
    assert spec["rating_summary"] == rating and spec["latest_reviews"] == reviews


def test_operator_restoration_does_not_reactivate_a_seller_deactivated_product(shop, mongo_db):
    seller, category, template, seller_client = shop
    item = create(shop)
    seller_client.post(f"/products/mine/{item.pk}/deactivate/")
    operator = make_operator()
    client = Client()
    client.force_login(operator)
    path = f"/products/operator/{item.pk}/"
    assert client.post(path, {"action": "takedown", "reason": "Review"}).status_code == 302
    assert client.post(path, {"action": "restore", "reason": "Approved"}).status_code == 302
    item.refresh_from_db()
    assert not item.active and not item.taken_down
    assert Client().get(f"/products/{item.pk}/").status_code == 404


def test_operator_pages_require_the_role_and_csrf(shop, mongo_db):
    seller, category, template, client = shop
    item = create(shop)
    for user in (seller.user, make_customer()):
        client.force_login(user)
        for path in ("/products/operator/", "/products/operator/categories/", f"/products/operator/{item.pk}/",
                     f"/products/operator/categories/{category.pk}/"):
            assert client.get(path).status_code == 403
            assert client.post(path, {"action": "takedown", "reason": "No"}).status_code == 403
    operator = make_operator()
    csrf = Client(enforce_csrf_checks=True)
    csrf.force_login(operator)
    assert csrf.post(f"/products/operator/{item.pk}/", {"action": "takedown", "reason": "No"}).status_code == 403
    assert csrf.post(f"/products/operator/categories/{category.pk}/", {"name": "finish", "kind": "string"}).status_code == 403
