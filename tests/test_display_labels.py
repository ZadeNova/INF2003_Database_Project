"""Batch 4 display fixes: one generated label per card, readable category names, the dashboard shop filter and the
Seller Insights order."""

from datetime import timedelta

import pytest
from account_helpers import make_operator
from checkout_helpers import product
from django.test import Client
from django.utils import timezone

from accounts.models import Seller, User
from activity.services import seller_insights
from catalogue.category_names import DISPLAY_NAMES, display_name
from catalogue.models import Category, Product
from dashboard.forms import SELLER_CHOICES, DashboardFilters

pytestmark = pytest.mark.django_db(transaction=True)


def listing(item):
    client = Client()
    page = client.get("/products/")  # not a search, so the cards come straight from PostgreSQL
    assert page.status_code == 200
    return page.content.decode()


def test_card_carries_one_generated_label_not_two(mongo_db):
    item = product("lamp")
    Product.objects.filter(pk=item.pk).update(has_generated_content=True)
    Seller.objects.filter(pk=item.seller_id).update(has_generated_content=True)
    body = listing(item)
    assert body.count("Generated name, shop and stock.") == 1
    assert 'class="name-tag"' not in body and "Generated name</span>" not in body


def test_shop_tag_still_shows_when_only_the_shop_name_is_generated(mongo_db):
    item = product("lamp")
    Seller.objects.filter(pk=item.seller_id).update(has_generated_content=True)
    body = listing(item)
    assert 'class="name-tag"' in body and "Generated name, shop and stock." not in body


def test_detail_page_has_a_footnote_and_no_second_shop_tag(mongo_db):
    item = product("lamp")
    Product.objects.filter(pk=item.pk).update(has_generated_content=True)
    Seller.objects.filter(pk=item.seller_id).update(has_generated_content=True)
    body = Client().get(f"/products/{item.pk}/").content.decode()
    assert body.count("Name, shop name, description, attributes, stock and lead time are") == 1
    assert 'class="name-tag"' not in body


def test_display_names_fix_typos_and_leave_other_names_alone():
    assert display_name("Costruction tools tools") == "Construction tools: tools"
    assert display_name("Fashio female clothing") == "Fashion female clothing"
    assert display_name("Housewares") == "Housewares"
    # Every shown name is distinct, so two categories can never look the same on a page.
    shown = [display_name(name) for name in DISPLAY_NAMES] + ["Home appliances"]
    assert len(set(shown)) == len(shown)
    assert Category(slug="x", name_en="Home appliances 2", name_pt="x").display_name == "More home appliances"
    assert str(Category(slug="y", name_en="Costruction tools garden", name_pt="y")) == "Construction tools: garden"


def test_category_page_shows_the_readable_name():
    category = Category.objects.create(slug="costruction-tools-tools", name_en="Costruction tools tools", name_pt="x")
    item = product("drill")
    Product.objects.filter(pk=item.pk).update(category=category)
    body = listing(Product.objects.get(pk=item.pk))
    assert "Construction tools: tools" in body and "Costruction" not in body


def test_dashboard_filter_labels_and_shop_choices():
    second = product("second")
    pending = Seller.objects.create(
        user=User.objects.create_user(username="pending-seller", role="seller"), shop_name="pending", status="pending"
    )
    Product.objects.create(
        seller=pending, category=second.category, name="p", stock=1, price=1, freight=1, lead_time_days=1
    )
    Product.objects.create(
        seller=second.seller,
        category=second.category,
        name="extra",
        stock=1,
        price=1,
        freight=1,
        lead_time_days=1,
    )
    form = DashboardFilters()
    assert form.fields["category"].empty_label == "All categories"
    choices = form.fields["seller"].choices
    assert choices[0] == ("", "All shops")
    # Only approved shops are offered, busiest first; the label carries the count, not an internal number alone.
    assert [value for value, _ in choices[1:]] == [second.seller_id]
    assert "2 products" in choices[1][1]
    assert SELLER_CHOICES == 50
    chosen = DashboardFilters({"seller": str(second.seller_id)})
    assert chosen.is_valid() and chosen.cleaned_data["seller"] == second.seller_id
    empty = DashboardFilters({"seller": ""})
    assert empty.is_valid() and empty.cleaned_data["seller"] is None
    # A shop that is not in the list, or text, is refused instead of reaching the SQL.
    assert not DashboardFilters({"seller": str(pending.pk)}).is_valid()
    assert not DashboardFilters({"seller": "1 OR 1=1"}).is_valid()


def test_dashboard_page_rejects_unlisted_shop_with_400():
    client = Client()
    client.force_login(make_operator())
    assert client.get("/operator/dashboard/", {"seller": "999999"}).status_code == 400


def test_insights_sort_by_views_then_conversion(mongo_db):
    quiet, busy, tied = product("quiet"), product("busy"), product("tied")
    # Put all three under one seller.
    Product.objects.filter(pk__in=[busy.pk, tied.pk]).update(seller=quiet.seller)
    now = timezone.now()
    for item, views in [(quiet, 1), (busy, 5), (tied, 5)]:
        mongo_db.events.insert_many(
            [
                {
                    "ts": now - timedelta(hours=1),
                    "meta": {"type": "view", "product_id": item.pk, "category": item.category_id, "session_key": "s"},
                    "is_generated": False,
                }
                for _ in range(views)
            ]
        )
    order = [row["product"].pk for row in seller_insights(quiet.seller, now=now)["insights"]]
    # Equal views and conversion fall back to the newer product first; the quiet product is last.
    assert order == [tied.pk, busy.pk, quiet.pk]


def test_imported_products_show_a_short_sku_and_new_products_do_not(mongo_db):
    item = product("lamp")
    Product.objects.filter(pk=item.pk).update(olist_product_id="fec3b4abcdef0123456789abcdef0123")
    body = listing(item)
    assert "SKU FEC3B4" in body
    assert "SKU FEC3B4" in Client().get(f"/products/{item.pk}/").content.decode()
    other = product("desk")
    assert other.sku is None
    assert (
        "SKU None" not in listing(other) and "SKU None" not in Client().get(f"/products/{other.pk}/").content.decode()
    )
