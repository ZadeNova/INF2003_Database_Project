"""Serial, independent journeys against a freshly imported fixture and runtime web."""
import os
import re
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

from helpers import apply_and_create_product, buy, deliver, demo_products, login, other_sellers, set_stock
from PIL import Image
from playwright.sync_api import expect


def unique(prefix):
    return f"ci-{prefix}-{uuid4().hex[:12]}"


def test_customer_registers(page):
    username = unique("customer")
    page.goto("/register/")
    page.get_by_label("Username", exact=True).fill(username)
    page.get_by_label("Password", exact=True).fill(os.environ["DEMO_CUSTOMER_PASSWORD"])
    page.get_by_label("Password confirmation", exact=True).fill(os.environ["DEMO_CUSTOMER_PASSWORD"])
    page.get_by_role("button", name="Create account", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("Account created")
    login(page, username)
    expect(page.get_by_role("button", name="Log out", exact=True)).to_be_visible()
    page.goto("/account/")
    expect(page.get_by_role("heading", name=username, exact=True)).to_be_visible()


def test_seller_application_approval_photo_and_edit_scoping(page):
    username, shop, product = unique("seller"), unique("shop"), unique("photo")
    image = BytesIO()
    Image.new("RGB", (32, 32), "navy").save(image, format="PNG")
    created = apply_and_create_product(page, username, shop, product, photo=image.getvalue())
    page.goto(created["path"])
    expect(page.get_by_role("heading", level=1, name=product, exact=True)).to_be_visible()
    photo = page.locator(".product-detail__media img")
    expect(photo).to_have_attribute("src", re.compile(r"/products/photos/"))
    page.wait_for_function("document.querySelector('.product-detail__media img').naturalWidth > 0")
    login(page, "demo-seller", "seller")
    response = page.goto(created["edit"])
    assert response.status == 404


def test_browse_attribute_facet_and_open_product(page):
    page.goto("/products/")
    category = page.get_by_label("Category", exact=True)
    choices = category.locator("option").evaluate_all("options => options.filter(o => o.value).map(o => o.value)")
    selected = None
    for choice in choices:
        page.get_by_label("Category", exact=True).select_option(choice)
        page.get_by_role("button", name="Search", exact=True).click()
        fields = page.locator('select[name^="attr_"]')
        products = page.locator(".catalogue-results > .product-grid > .product-card h2 a")
        if fields.count() and products.count():
            field = fields.first
            name = field.get_attribute("name")
            label = page.locator(f'label[for="{field.get_attribute("id")}"]').inner_text()
            path = products.first.get_attribute("href")
            page.goto(path)
            values = page.locator(".detail-list dt").all_inner_texts()
            if label in values:
                value = page.locator(".detail-list dd").nth(values.index(label)).inner_text()
                selected = (choice, name, value, path)
                break
            page.goto("/products/")
    assert selected is not None, "The fixture needs an active product with a selectable category attribute"
    choice, name, value, path = selected
    page.goto(f"/products/?category={choice}")
    page.locator(f'select[name="{name}"]').select_option(label=value)
    page.get_by_role("button", name="Search", exact=True).click()
    expect(page.get_by_role("navigation", name="Active filters")).to_contain_text(value)
    link = page.locator(f'.catalogue-results > .product-grid a[href="{path}"]').first
    expect(link).to_be_visible()
    link.click()
    expect(page.get_by_role("heading", name="Customer reviews", exact=True)).to_be_visible()


def test_three_seller_checkout_ship_deliver_cancel_and_refund(page):
    products = demo_products(page)
    ready = products["ready"]
    set_stock(page, ready["edit"], 5)
    second = other_sellers(page, ready["shop_url"], 1)[0]
    # The small fixture exposes only two established shops. Make the third through
    # the real application/approval UI, independently of the seller-upload test.
    third = apply_and_create_product(page, unique("checkout-seller"), unique("checkout-shop"), unique("checkout-product"))
    paths = [ready["path"], second, third["path"]]
    orders = buy(page, "demo-chee-long", paths)
    assert len(orders) == 3
    delivered = orders[ready["shop"]]
    cancelled = next(path for path in orders.values() if path != delivered)
    deliver(page, delivered)
    login(page, "demo-chee-long")
    page.goto(delivered)
    expect(page.locator(".page__header").get_by_text("Delivered", exact=True)).to_be_visible()
    page.goto(cancelled)
    total = Decimal(page.locator(".checkout-totals dd").last.inner_text().removeprefix("S$").replace(",", ""))
    page.get_by_label("Reason (optional)", exact=True).fill("Browser journey cancellation")
    page.get_by_role("button", name="Cancel order", exact=True).click()
    expect(page.locator(".page__header").get_by_text("Cancelled", exact=True)).to_be_visible()
    refunded = page.get_by_role("heading", name=re.compile(r"^Refunded S\$")).text_content().strip()
    assert Decimal(refunded.removeprefix("Refunded S$").replace(",", "")) == total


def test_delivered_review_appears_and_operator_takes_it_down(page):
    ready = demo_products(page)["ready"]
    set_stock(page, ready["edit"], 5)
    orders = buy(page, "demo-erfan", [ready["path"]])
    order = orders[ready["shop"]]
    deliver(page, order)
    login(page, "demo-erfan")
    page.goto(order)
    review = page.get_by_role("link", name="Write or edit review", exact=True).first
    line_id = re.search(r"/line/(\d+)/", review.get_attribute("href")).group(1)
    review.click()
    title = unique("review")
    page.get_by_label("Score", exact=True).select_option("5")
    page.get_by_label("Title", exact=True).fill(title)
    page.get_by_label("Text", exact=True).fill("Delivered and reviewed through the real browser.")
    page.get_by_role("button", name="Save review", exact=True).click()
    page.goto(ready["path"])
    expect(page.locator("#reviews")).to_contain_text(title)
    login(page, "demo-operator", "operator")
    page.goto(f"/operator/reviews/{line_id}/")
    page.get_by_label("Action", exact=True).select_option("takedown")
    page.get_by_label("Reason", exact=True).fill("Browser journey: operator moderation")
    page.get_by_role("button", name="Save decision", exact=True).click()
    page.goto(ready["path"])
    expect(page.locator("#reviews")).not_to_contain_text(title)


def test_wishlist_restock_shows_one_unseen_alert(page):
    sold_out = demo_products(page)["sold_out"]
    set_stock(page, sold_out["edit"], 0)
    login(page, "demo-joash")
    page.goto("/alerts/")  # Clear only this customer's existing visible alerts on a rerun.
    page.goto(sold_out["path"])
    summary = page.locator(".product-detail__info")
    expect(summary).to_contain_text("Sold out")
    saved = summary.get_by_role("button", name="Remove from wishlist", exact=True)
    if saved.count():
        saved.click()
    summary.get_by_role("button", name="Save to wishlist", exact=True).click()
    expect(summary.get_by_role("button", name="Remove from wishlist", exact=True)).to_have_attribute("aria-pressed", "true")
    login(page, "demo-seller", "seller")
    set_stock(page, sold_out["edit"], 5)
    login(page, "demo-joash")
    expect(page.get_by_label("1 unseen restock alerts", exact=True)).to_have_text("1")
    page.goto("/alerts/")
    expect(page.locator(f'a[href="{sold_out["path"]}"]').first).to_be_visible()
    expect(page.get_by_label("1 unseen restock alerts", exact=True)).to_have_count(0)


def test_dashboard_insights_and_trending_render(page):
    login(page, "demo-operator", "operator")
    page.goto("/operator/dashboard/")
    for title in ("Replenishment priorities", "Category performance", "Delivery delay and review score",
                  "Seller delivery risk", "Products with poor reviews"):
        panel = page.locator("section").filter(has=page.get_by_role("heading", name=title, exact=True))
        expect(panel).to_contain_text("As of 24 October 2026")
    expect(page.locator("#category-revenue")).to_be_visible()
    login(page, "demo-seller", "seller")
    page.goto("/seller/insights/")
    expect(page.get_by_role("heading", name="Insights", exact=True)).to_be_visible()
    expect(page.get_by_role("region", name="Product browsing and sales", exact=True)).to_contain_text("Includes generated views.")
    page.goto("/products/")
    trending = page.locator("section.panel").filter(has=page.get_by_role("heading", name="Trending", exact=True))
    expect(trending).to_have_count(1)
    expect(trending.locator(".trending-pick").first).to_be_visible()
    expect(trending).to_contain_text("Includes generated views")


def test_failure_artifact_canary(page, request):
    login(page, "demo-chee-long")
    page.goto("/products/")
    expect(page.get_by_role("heading", name="A little of everything", exact=True)).to_be_visible()
    assert not request.config.getoption("--force-browser-failure"), "Intentional browser failure to verify retained trace and screenshot artifacts"
