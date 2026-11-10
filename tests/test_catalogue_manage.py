"""Seller CRUD, real cross-store failures, raster uploads, moderation and live category options."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
from io import BytesIO, StringIO

import pytest
from account_helpers import make_customer, make_operator, make_seller
from bson import Decimal128
from db_helpers import wait_until_blocked
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections, transaction
from django.test import Client
from gridfs import GridFS
from PIL import Image, PngImagePlugin
from pymongo.errors import ConnectionFailure, WriteError

from accounts.models import AuditLog
from catalogue.models import Category, Product
from catalogue.seller_forms import ProductForm
from catalogue.services import moderate_product, save_product
from config import mongo

pytestmark = pytest.mark.django_db(transaction=True)


def product_audits():
    """Edits only; creation rows are asserted where a product is created."""
    return AuditLog.objects.filter(table_name="catalogue_product").exclude(action="product.create")


@pytest.fixture
def shop(mongo_db):
    seller = make_seller()
    category = Category.objects.create(slug="housewares", name_en="Housewares", name_pt="Housewares")
    template = {
        "_id": category.pk,
        "category_id": category.pk,
        "rich": True,
        "has_generated_content": False,
        "version": 1,
        "attributes": {
            "material": {"type": "string", "values": ["cotton", "steel"]},
            "capacity": {"type": "integer", "values": [2, 4]},
            "wireless": {"type": "boolean", "values": [True, False]},
        },
    }
    mongo_db.category_templates.insert_one(template)
    client = Client()
    client.force_login(seller.user)
    return seller, category, template, client


def data(category, **changes):
    return {
        "name": "Handmade kettle",
        "category": str(category.pk),
        "price": "12.34",
        "stock": "8",
        "freight": "1.23",
        "lead_time_days": "2",
        "description": "A seller-written description.",
        "attr_material": "steel",
        "attr_capacity": "2",
        "attr_wireless": "false",
        **changes,
    }


def create(shop):
    seller, category, template, client = shop
    response = client.post("/products/mine/new/", data(category))
    assert response.status_code == 302
    return Product.objects.get(seller=seller)


def test_the_add_product_page_asks_for_the_category_once(shop):
    seller, category, template, client = shop
    page = client.get("/products/mine/new/", {"category": category.pk}).content.decode()
    assert page.count('name="category"') == 2  # the selector above the form, and the hidden value in the form
    assert '<select id="choose-category" name="category">' in page
    assert f'<input type="hidden" name="category" value="{category.pk}"' in page  # the form only carries it
    assert "Category: <strong>Housewares</strong>" in page
    # A category that is not the loaded one is still refused (the hidden value cannot be changed to another category).
    other = Category.objects.create(slug="toys", name_en="Toys", name_pt="Toys")
    assert client.post("/products/mine/new/", data(other)).status_code == 400


def photo(format_name="PNG", name="kettle.png"):
    output = BytesIO()
    image = Image.new("RGB", (24, 16), (40, 90, 120))
    extra = PngImagePlugin.PngInfo()
    extra.add_text("Comment", "PRIVATE METADATA SENTINEL")
    image.save(output, format=format_name, **({"pnginfo": extra} if format_name == "PNG" else {}))
    return SimpleUploadedFile(
        name,
        output.getvalue(),
        content_type={"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[format_name],
    )


def test_seller_creates_and_edits_own_product_in_both_stores(shop, mongo_db):
    seller, category, template, client = shop
    item = create(shop)
    spec = mongo_db.product_specs.find_one({"_id": item.pk})
    assert item.seller == seller and not item.has_generated_content and item.lead_time_days == 2
    assert spec["has_generated_content"] is False
    assert spec["attributes"] == {"material": "steel", "capacity": 2, "wireless": False}
    assert isinstance(spec["rating_summary"]["average"], Decimal128)
    created = AuditLog.objects.get(table_name="catalogue_product", action="product.create")
    assert (created.row_id, created.actor_id, created.reason) == (str(item.pk), seller.user_id, "Seller saved product")
    assert created.before is None and created.after["stock"] == 8 and str(created.after["price"]) == "12.34"
    response = client.post(f"/products/mine/{item.pk}/edit/", data(category, price="15.67", stock="5"))
    assert response.status_code == 302
    item.refresh_from_db()
    assert str(item.price) == "15.67" and item.stock == 5
    row = product_audits().get(table_name="catalogue_product")
    assert row.actor_id == seller.user_id and row.reason == "Seller saved product"
    assert row.before["stock"] == 8 and row.after["stock"] == 5
    assert Client().get(f"/products/{item.pk}/").status_code == 200


def test_edit_form_carries_what_the_seller_saw_and_hides_it_from_view(shop, mongo_db):
    _, category, _, client = shop
    item = create(shop)
    page = client.get(f"/products/mine/{item.pk}/edit/").content.decode()
    assert 'name="expected_stock" value="8"' in page and 'name="expected_price" value="12.34"' in page
    assert "Expected stock" not in page and "Expected price" not in page


def test_a_stale_form_keeps_sales_made_while_it_was_open(shop, mongo_db):
    _, category, _, client = shop
    item = create(shop)
    Product.objects.filter(pk=item.pk).update(stock=5)  # three units sold since the form was opened at 8
    form = data(category, description="Fixed the description", expected_stock="8", expected_price="12.34")
    assert client.post(f"/products/mine/{item.pk}/edit/", form).status_code == 302
    item.refresh_from_db()
    assert item.stock == 5  # not put back to 8
    assert mongo_db.product_specs.find_one({"_id": item.pk})["description"] == "Fixed the description"
    assert not product_audits().filter(after__stock=8).exists()


def test_a_field_the_seller_changed_applies_when_nobody_else_changed_it(shop, mongo_db):
    _, category, _, client = shop
    item = create(shop)
    form = data(category, stock="6", price="15.67", expected_stock="8", expected_price="12.34")
    assert client.post(f"/products/mine/{item.pk}/edit/", form).status_code == 302
    item.refresh_from_db()
    assert (item.stock, str(item.price)) == (6, "15.67")


def test_a_real_conflict_is_refused_and_the_form_expects_the_live_values_next(shop, mongo_db):
    _, category, _, client = shop
    item = create(shop)
    Product.objects.filter(pk=item.pk).update(stock=5)
    form = data(category, stock="20", description="Not saved yet", expected_stock="8", expected_price="12.34")
    response = client.post(f"/products/mine/{item.pk}/edit/", form)
    body = response.content.decode()
    assert response.status_code == 400 and "stock changed to 5 while you were editing" in body
    assert 'name="expected_stock" value="5"' in body and 'value="20"' in body  # typed value kept, live value expected
    item.refresh_from_db()
    assert item.stock == 5
    assert mongo_db.product_specs.find_one({"_id": item.pk})["description"] == "A seller-written description."
    retry = data(category, stock="20", expected_stock="5", expected_price="12.34")
    assert client.post(f"/products/mine/{item.pk}/edit/", retry).status_code == 302
    item.refresh_from_db()
    assert item.stock == 20


def test_typing_exactly_the_value_someone_else_just_set_is_not_a_conflict(shop, mongo_db):
    _, category, _, client = shop
    item = create(shop)
    Product.objects.filter(pk=item.pk).update(stock=5)
    form = data(category, stock="5", expected_stock="8", expected_price="12.34")
    assert client.post(f"/products/mine/{item.pk}/edit/", form).status_code == 302
    item.refresh_from_db()
    assert item.stock == 5


def test_a_refused_save_says_the_chosen_photo_must_be_chosen_again(shop, mongo_db):
    _, category, _, client = shop
    item = create(shop)
    Product.objects.filter(pk=item.pk).update(stock=5)
    form = data(category, stock="20", expected_stock="8", expected_price="12.34", photo=photo())
    response = client.post(f"/products/mine/{item.pk}/edit/", form)
    assert response.status_code == 400 and "Choose your photo again" in response.content.decode()


def test_a_save_waits_for_a_sale_in_flight_and_then_keeps_its_stock(shop, mongo_db):
    """Two real connections: a sale holds the product row while the seller's save arrives, then commits."""
    seller, category, _, _ = shop
    item = create(shop)
    locked, release = threading.Event(), threading.Event()

    def sell():
        connections.close_all()
        try:
            with transaction.atomic():
                Product.objects.select_for_update().get(pk=item.pk)
                Product.objects.filter(pk=item.pk).update(stock=5)
                locked.set()
                release.wait(timeout=30)
        finally:
            connections.close_all()

    def save():
        # MongoDB test routing is per thread: without it this thread would write to the real application database.
        with mongo.using_database(mongo_db.name):
            assert mongo.database_name() == mongo_db.name
            return _save()

    def _save():
        connections.close_all()
        try:
            cleaned = {
                "name": item.name,
                "category": category,
                "price": Decimal("12.34"),
                "stock": 8,  # unchanged from what the form showed
                "freight": Decimal("1.23"),
                "lead_time_days": 2,
                "description": "Saved while a sale was in flight",
                "attributes": {"material": "steel", "capacity": 2, "wireless": False},
                "photo": None,
                "expected_stock": 8,
                "expected_price": Decimal("12.34"),
            }
            return save_product(seller, seller.user, cleaned, pk=item.pk)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        sale = pool.submit(sell)
        assert locked.wait(timeout=30)
        saving = pool.submit(save)
        wait_until_blocked()  # the save is now waiting on the sale's row lock
        release.set()
        sale.result(timeout=30)
        saving.result(timeout=30)
    item.refresh_from_db()
    assert item.stock == 5  # the sale survived the save
    assert mongo_db.product_specs.find_one({"_id": item.pk})["description"] == "Saved while a sale was in flight"


def test_a_price_conflict_is_refused_too(shop, mongo_db):
    _, category, _, client = shop
    item = create(shop)
    Product.objects.filter(pk=item.pk).update(price="11.00")
    form = data(category, price="13.00", expected_stock="8", expected_price="12.34")
    response = client.post(f"/products/mine/{item.pk}/edit/", form)
    assert response.status_code == 400 and "price changed to 11.00 while you were editing" in response.content.decode()
    item.refresh_from_db()
    assert str(item.price) == "11.00"


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_stock", "abc"),
        ("expected_price", "x"),
        ("expected_price", "sNaN"),
        ("expected_price", "-sNaN"),
        ("expected_price", "NaN"),
        ("expected_price", "Infinity"),
    ],
)
def test_a_tampered_expected_value_is_a_refused_form_not_a_server_error(shop, mongo_db, field, value):
    _, category, _, client = shop
    item = create(shop)
    form = {**data(category, expected_stock="8", expected_price="12.34"), field: value}
    response = client.post(f"/products/mine/{item.pk}/edit/", form)
    assert response.status_code == 400 and "out of date" in response.content.decode()


def test_seller_cannot_choose_another_owner_or_edit_another_shop(shop, mongo_db):
    seller, category, template, client = shop
    other = make_seller("other")
    response = client.post(
        "/products/mine/new/", data(category, seller=str(other.pk), taken_down="true", has_generated_content="true")
    )
    assert response.status_code == 302
    item = Product.objects.get()
    assert item.seller == seller and not item.taken_down and not item.has_generated_content
    other_client = Client()
    other_client.force_login(other.user)
    assert "Handmade kettle" not in other_client.get("/products/mine/").content.decode()
    for method, path in (
        ("get", f"/products/mine/{item.pk}/edit/"),
        ("post", f"/products/mine/{item.pk}/edit/"),
        ("post", f"/products/mine/{item.pk}/deactivate/"),
    ):
        assert getattr(other_client, method)(path, data(category)).status_code == 404


@pytest.mark.parametrize(
    "field,value",
    [
        ("lead_time_days", ""),
        ("lead_time_days", "366"),
        ("stock", "-1"),
        ("stock", "100000"),
        ("price", "0.00"),
        ("freight", "-0.01"),
        ("attr_material", '{"$ne":null}'),
        ("attr_capacity", "3"),
        ("attr_wireless", "not-bool"),
        ("attr_$where", "sleep(1000)"),
    ],
)
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
    form = ProductForm(
        data(category, stock="1", price="99.99"),
        template=template,
        instance=item,
        spec=mongo_db.product_specs.find_one({"_id": item.pk}),
    )
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
    form = ProductForm(
        data(category, stock="1"),
        template=template,
        instance=item,
        spec=mongo_db.product_specs.find_one({"_id": item.pk}),
    )
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
        upload = SimpleUploadedFile(
            "image.svg", b'<svg xmlns="http://www.w3.org/2000/svg"/>', content_type="image/svg+xml"
        )
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


def test_a_product_decision_without_a_reason_is_a_validation_error_like_every_other_service(shop, mongo_db):
    item, operator = create(shop), make_operator()
    for reason in ("", "   ", None):
        with pytest.raises(ValidationError, match="Give a reason"):
            moderate_product(operator, item.pk, "takedown", reason)
    assert not product_audits().exists()


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
    assert (
        client.post(
            f"/products/operator/categories/{category.pk}/", {"name": name, "kind": "string", "values": "x"}
        ).status_code
        == 400
    )
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
    rating = {
        "count": 1,
        "sum": 5,
        "average": Decimal128("5"),
        "distribution": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 1},
        "bayesian": Decimal128("4.5"),
    }
    reviews = [{"score": 5, "text_en": "Existing review"}]
    mongo_db.product_specs.update_one({"_id": item.pk}, {"$set": {"rating_summary": rating, "latest_reviews": reviews}})
    assert (
        client.post(f"/products/mine/{item.pk}/edit/", data(category, description="Updated description")).status_code
        == 302
    )
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
        for path in (
            "/products/operator/",
            "/products/operator/categories/",
            f"/products/operator/{item.pk}/",
            f"/products/operator/categories/{category.pk}/",
        ):
            assert client.get(path).status_code == 403
            assert client.post(path, {"action": "takedown", "reason": "No"}).status_code == 403
    operator = make_operator()
    csrf = Client(enforce_csrf_checks=True)
    csrf.force_login(operator)
    assert csrf.post(f"/products/operator/{item.pk}/", {"action": "takedown", "reason": "No"}).status_code == 403
    assert (
        csrf.post(f"/products/operator/categories/{category.pk}/", {"name": "finish", "kind": "string"}).status_code
        == 403
    )


@pytest.mark.parametrize("path", ["/products/mine/", "/products/operator/"])
def test_a_nul_byte_in_the_product_list_search_is_ignored_not_a_server_error(shop, path):
    seller, category, template, seller_client = shop
    create(shop)
    if path == "/products/operator/":
        seller_client = Client()
        seller_client.force_login(make_operator())
    response = seller_client.get(path, {"q": "kettle\x00"})
    assert response.status_code == 200 and b"Handmade kettle" in response.content


def test_the_audit_page_shows_a_price_and_stock_line_only_when_they_changed(shop, mongo_db):
    item = create(shop)
    operator = make_operator()
    client = Client()
    client.force_login(operator)
    assert (
        client.post(f"/products/operator/{item.pk}/", {"action": "takedown", "reason": "No change"}).status_code == 302
    )
    client.post(f"/products/operator/{item.pk}/", {"action": "restore", "reason": "Fine"})
    assert shop[3].post(f"/products/mine/{item.pk}/edit/", data(shop[1], price="15.00")).status_code == 302
    body = client.get("/operator/audit/").content.decode()
    # Four product rows (create, takedown, restore, edit); only the creation and the edit changed price or stock.
    assert body.count("Price: S$") == 2 and "S$12.34 → S$15.00" in body
