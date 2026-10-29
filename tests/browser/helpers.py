"""Small browser actions shared by independent demo journeys."""
import os
import re

from playwright.sync_api import expect


def login(page, username, role="customer"):
    page.goto("/products/")
    logout = page.get_by_role("button", name="Log out", exact=True)
    if logout.count():
        logout.click()
    page.goto("/login/")
    page.get_by_label("Username", exact=True).fill(username)
    page.get_by_label("Password", exact=True).fill(os.environ[f"DEMO_{role.upper()}_PASSWORD"])
    page.get_by_role("button", name="Log in", exact=True).click()
    expect(page.get_by_role("button", name="Log out", exact=True)).to_be_visible()


def apply_and_create_product(page, username, shop, product, *, photo=None):
    page.goto("/products/")
    logout = page.get_by_role("button", name="Log out", exact=True)
    if logout.count():
        logout.click()
    page.goto("/sell/apply/")
    for label, value in [("Username", username), ("Shop name", shop), ("City", "sao paulo"),
                         ("State", "SP"), ("Zip prefix", "01310")]:
        page.get_by_label(label, exact=True).fill(value)
    for label in ("Password", "Password confirmation"):
        page.get_by_label(label, exact=True).fill(os.environ["DEMO_SELLER_PASSWORD"])
    page.get_by_role("button", name="Submit application", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("Application submitted")
    login(page, username, "seller")
    expect(page).to_have_url(re.compile(r"/seller/status/$"))
    expect(page.get_by_text("Pending", exact=True)).to_be_visible()
    login(page, "demo-operator", "operator")
    page.goto("/operator/?status=pending")
    page.get_by_role("link", name=shop, exact=True).click()
    form = page.locator('form[action$="/approve/"]')
    form.get_by_label("Reason", exact=True).fill("Browser journey: verified application")
    form.get_by_role("button", name="Approve seller", exact=True).click()
    expect(page.locator(".page__header").get_by_text("Approved", exact=True)).to_be_visible()
    login(page, username, "seller")
    page.goto("/products/mine/new/")
    page.get_by_label("Category options", exact=True).select_option(label="Uncategorised")
    page.get_by_role("button", name="Load options", exact=True).click()
    for label, value in [("Name", product), ("Price (S$)", "12.34"), ("Stock", "8"),
                         ("Shipping fee (S$)", "1.25"), ("Ready to ship in (days)", "2"),
                         ("Description", "Generated product for the browser regression journey.")]:
        page.get_by_label(label, exact=True).fill(value)
    if photo:
        page.get_by_label("Photo", exact=True).set_input_files({"name": "sample.png", "mimeType": "image/png", "buffer": photo})
    page.get_by_role("button", name="Save product", exact=True).click()
    page.get_by_role("link", name=product, exact=True).click()
    edit_path = re.search(r"/products/mine/\d+/edit/", page.url).group(0)
    product_id = re.search(r"/mine/(\d+)/", edit_path).group(1)
    return {"path": f"/products/{product_id}/", "edit": edit_path}


def set_stock(page, edit_path, quantity):
    page.goto(edit_path)
    page.get_by_label("Stock", exact=True).fill(str(quantity))
    page.get_by_role("button", name="Save product", exact=True).click()
    expect(page.get_by_role("heading", name="My products", exact=True)).to_be_visible()


def demo_products(page):
    """Find seed_demo's labelled products through the seller's own UI, not SQL."""
    login(page, "demo-seller", "seller")
    page.goto("/products/mine/")
    edits, pages = [], 0
    while True:
        pages += 1
        rows = page.locator(".optable__row--products").filter(has=page.get_by_text("Active", exact=True))
        for index in range(rows.count()):
            row = rows.nth(index)
            # seed_demo starts at 0/1; these journeys restock to five and buy one.
            # Ordinary imported stock starts at twenty, so skip its detail pages.
            if int(row.locator(":scope > span").nth(3).inner_text()) <= 5:
                edits.append(row.locator('a[href$="/edit/"]').get_attribute("href"))
        following = page.get_by_role("link", name="Next", exact=True)
        if not following.count():
            break
        following.click()
    found = {}
    for edit in edits:
        product_id = re.search(r"/mine/(\d+)/edit/", edit).group(1)
        path = f"/products/{product_id}/"
        response = page.goto(path)
        if response.status == 404:
            continue
        text = page.locator(".product-detail__info").inner_text()
        key = "sold_out" if "Demo adjustment: sold out" in text else "ready" if "Demo adjustment: low stock" in text else None
        if key:
            shop = page.locator('.product-detail__info a[href^="/products/shops/"]')
            found[key] = {"id": product_id, "path": path, "edit": edit, "shop": shop.text_content().strip(), "shop_url": shop.get_attribute("href")}
        if len(found) == 2:
            return found
    missing = {"sold_out", "ready"} - found.keys()
    raise AssertionError(f"seed_demo products {sorted(missing)} not found after the last seller page "
                         f"({pages} pages, {len(edits)} low-stock candidates checked)")


def other_sellers(page, excluded_shop, count):
    page.goto("/products/")
    selected, shops = [], {excluded_shop}
    for _ in range(10):
        cards = page.locator(".catalogue-results > .product-grid > .product-card")
        for index in range(cards.count()):
            card = cards.nth(index)
            shop = card.locator('a[href^="/products/shops/"]').get_attribute("href")
            if shop not in shops and card.locator(".product-card__stock").text_content().strip() == "In stock":
                selected.append(card.locator("h2 a").get_attribute("href"))
                shops.add(shop)
                if len(selected) == count:
                    return selected
        following = page.get_by_role("link", name="Next", exact=True)
        if not following.count():
            break
        following.click()
    raise AssertionError("The fixture must expose enough distinct in-stock shops")


def buy(page, username, paths):
    login(page, username)
    page.goto("/cart/")
    while page.get_by_role("button", name="Remove", exact=True).count():
        before = page.get_by_role("button", name="Remove", exact=True).count()
        page.get_by_role("button", name="Remove", exact=True).first.click()
        expect(page.get_by_role("button", name="Remove", exact=True)).to_have_count(before - 1)
    for path in paths:
        page.goto(path)
        page.get_by_role("button", name="Add to cart", exact=True).click()
        expect(page.locator("#cart-feedback")).to_contain_text("Added to your cart.")
    page.goto("/cart/")
    page.get_by_role("link", name="Review and pay", exact=True).click()
    expect(page.get_by_role("heading", name="Review and pay", exact=True)).to_be_visible()
    page.get_by_label("Payment method", exact=True).select_option("boleto")
    page.get_by_role("button", name="Place order and pay", exact=True).click()
    expect(page).to_have_url(re.compile(r"/checkouts/\d+/$"))
    expect(page.get_by_role("heading", name="Payment received", exact=True)).to_be_visible()
    links = page.locator('h2 a[href^="/orders/"]')
    return {links.nth(index).text_content().strip(): links.nth(index).get_attribute("href") for index in range(links.count())}


def deliver(page, order_path):
    order_id = re.search(r"/orders/(\d+)/", order_path).group(1)
    for username, role, area, action, status in [
        ("demo-seller", "seller", "seller", "Mark shipped", "Shipped"),
        ("demo-operator", "operator", "operator", "Mark delivered", "Delivered"),
    ]:
        login(page, username, role)
        page.goto(f"/{area}/orders/")
        page.get_by_label("Order number", exact=True).fill(order_id)
        page.get_by_role("button", name="Filter", exact=True).click()
        page.get_by_role("button", name=action, exact=True).click()
        page.goto(f"/{area}/orders/?order_id={order_id}")
        expect(page.get_by_role("region", name="Orders", exact=True)).to_contain_text(status)
