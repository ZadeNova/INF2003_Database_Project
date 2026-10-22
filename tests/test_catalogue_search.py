"""Fixture-backed facets never count products PostgreSQL has hidden or priced out."""
import csv
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
from bson import Decimal128
from django.test import Client

from accounts.models import Seller
from catalogue.icons import CATEGORY_ICONS
from catalogue.models import Category, Product
from catalogue.search import candidates, facet_match, visible_products

pytestmark = pytest.mark.django_db(transaction=True)


def sample(mongo_db):
    item = visible_products().first()
    return item, mongo_db.product_specs.find_one({"_id": item.pk})


def test_two_attributes_and_price_range_equal_direct_fixture_count(imported, mongo_db):
    item, spec = sample(mongo_db)
    attrs = dict(list(spec["attributes"].items())[:2])
    assert len(attrs) == 2
    params = {"category": item.category_id, "min_price": str(item.price), "max_price": str(item.price),
              **{"attr_" + key: str(value).lower() if isinstance(value, bool) else str(value)
                 for key, value in attrs.items()}}
    response = Client().get("/products/", params)
    assert response.status_code == 200
    sql_ids = list(visible_products().filter(category=item.category, price=item.price).values_list("pk", flat=True))
    direct = {"_id": {"$in": sql_ids}, **{"attributes." + key: value for key, value in attrs.items()}}
    expected = set(row["_id"] for row in mongo_db.product_specs.find(direct))
    page = response.context["page_obj"]
    assert page.paginator.count == mongo_db.product_specs.count_documents(direct) == len(expected)
    assert {row.pk for row in page} == expected
    for name, values in response.context["facet_groups"]:
        for value in values:
            assert value["count"] == mongo_db.product_specs.count_documents({**direct, "attributes." + name: value["value"]})


@pytest.mark.parametrize("hidden", ["inactive", "taken_down", "suspended"])
def test_facet_counts_and_shops_exclude_hidden_products(imported, mongo_db, hidden):
    item, spec = sample(mongo_db)
    if hidden == "suspended":
        Seller.objects.filter(pk=item.seller_id).update(status="suspended")
    else:
        Product.objects.filter(pk=item.pk).update(**{"active": False} if hidden == "inactive" else {"taken_down": True})
    response = Client().get("/products/", {"category": item.category_id})
    expected = set(visible_products().filter(category=item.category).values_list("pk", flat=True))
    assert response.status_code == 200 and response.context["result_count"] == len(expected)
    assert item.pk not in {p.pk for p in response.context["page_obj"]}
    assert Client().get(f"/products/{item.pk}/").status_code == 404
    shop = Client().get(f"/products/shops/{item.seller_id}/")
    assert shop.status_code == (404 if hidden == "suspended" else 200)


def test_sold_out_products_stay_in_search_counts(imported, mongo_db):
    item, _ = sample(mongo_db)
    Product.objects.filter(pk=item.pk).update(stock=0)
    response = Client().get("/products/", {"category": item.category_id})
    assert item.pk in {p.pk for p in response.context["page_obj"]}


@pytest.mark.parametrize("sort", ["price", "price_desc", "newest", "top"])
def test_search_sorting_and_pagination_are_deterministic(imported, mongo_db, sort):
    category = visible_products().values_list("category_id", flat=True).first()
    ids = list(visible_products().filter(category_id=category).values_list("pk", flat=True))
    response = Client().get("/products/", {"category": category, "sort": sort})
    actual = [p.pk for p in response.context["page_obj"]]
    if sort == "top":
        expected = [r["_id"] for r in mongo_db.product_specs.find({"_id": {"$in": ids}}).sort(
            [("rating_summary.bayesian", -1), ("_id", -1)]).limit(24)]
    else:
        ordering = {"price": ("price", "id"), "price_desc": ("-price", "-id"), "newest": ("-id",)}[sort]
        expected = list(visible_products().filter(category_id=category).order_by(*ordering).values_list("pk", flat=True)[:24])
    assert response.status_code == 200 and actual == expected
    assert Client().get("/products/", {"category": category, "sort": sort, "page": "999999"}).status_code == 200


def test_trigram_search_finds_a_typo_and_substrings(imported, mongo_db):
    item, _ = sample(mongo_db)
    Product.objects.filter(pk=item.pk).update(name="Portable Hose Nozzle")
    for query in ("Portable Hse Nozle", "Nozz"):
        response = Client().get("/products/", {"q": query})
        assert response.status_code == 200
        assert item.pk in {p.pk for p in response.context["page_obj"]}


@pytest.mark.parametrize("parameters", [
    {"q": "'; DROP TABLE catalogue_product; --"},
    {"q": '{"$where":"sleep(1000)"}'},
    {"category": "1); DELETE FROM catalogue_product; --"},
    {"q": "test", "min_price": "0 OR 1=1"},
    {"q": "test", "max_price": "NaN"},
    {"q": "test", "sort": "price;DROP TABLE catalogue_product"},
    {"q": "test", "rating": '{"$ne":null}'},
    {"q": "test", "attr_$where": "sleep(1000)"},
])
def test_search_injection_parameters_cannot_become_queries(imported, mongo_db, parameters):
    before = Product.objects.count()
    assert Client().get("/products/", parameters).status_code in (200, 400)
    assert Product.objects.count() == before
    assert mongo_db.product_specs.count_documents({}) == before


def test_attribute_value_injection_is_rejected_as_a_choice(imported, mongo_db):
    item, spec = sample(mongo_db)
    key = next(iter(spec["attributes"]))
    response = Client().get("/products/", {"category": item.category_id, "attr_" + key: '{"$ne":null}'})
    assert response.status_code == 400
    assert mongo_db.product_specs.find_one({"_id": item.pk})["attributes"] == spec["attributes"]


def test_all_imported_categories_have_a_real_sprite_icon(imported):
    symbols = {element.attrib["id"].removeprefix("i-") for element in ET.parse("/app/static/img/icons.svg").iter()
               if element.tag.endswith("symbol")}
    slugs = {row["slug"] for row in csv.DictReader(Path("/app/tests/fixtures/olist/clean/categories.csv").open())}
    assert slugs == set(CATEGORY_ICONS)
    assert all(CATEGORY_ICONS[slug] in symbols for slug in slugs)
    assert {category.icon_name for category in Category.objects.exclude(slug="uncategorised")} != {"package"}


def test_category_shop_and_generated_labels_render(imported, mongo_db):
    item, spec = sample(mongo_db)
    client = Client()
    for path in (f"/products/category/{item.category.slug}/", f"/products/shops/{item.seller_id}/", f"/products/{item.pk}/"):
        response = client.get(path)
        assert response.status_code == 200 and "generated" in response.content.decode().lower()
        assert client.post(path).status_code == 405
