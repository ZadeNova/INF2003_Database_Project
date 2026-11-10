"""Role and seller-status access over every protected URL and action (accounts plan, P1)."""

import pytest
from account_helpers import PASSWORD, make_customer, make_operator, make_seller
from django.test import Client

from accounts.audit import change_seller_status
from accounts.models import AuditLog, Seller

pytestmark = pytest.mark.django_db

KINDS = ("anonymous", "customer", "approved", "pending", "rejected", "suspended", "operator")
SELLER_STATUSES = ("approved", "pending", "rejected", "suspended")
STATUS_PAGE = "/seller/status/"


@pytest.fixture
def people():
    users = {"customer": make_customer(), "operator": make_operator()}
    for status in SELLER_STATUSES:
        users[status] = make_seller(username=f"seller-{status}", status=status).user
    target = make_seller(username="applicant", status="pending")
    return users, target


def client_for(users, kind):
    client = Client()
    if kind != "anonymous":
        client.force_login(users[kind])
    return client


# Expected outcome per kind: "ok" (200), "login" (redirect to login), "status" (redirect to the seller's status
# page) or "forbidden" (403).
GET_MATRIX = {
    "/account/": dict(
        anonymous="login",
        customer="ok",
        approved="forbidden",
        pending="forbidden",
        rejected="forbidden",
        suspended="forbidden",
        operator="forbidden",
    ),
    "/seller/": dict(
        anonymous="login",
        customer="forbidden",
        approved="ok",
        pending="status",
        rejected="status",
        suspended="status",
        operator="forbidden",
    ),
    STATUS_PAGE: dict(
        anonymous="login",
        customer="forbidden",
        approved="ok",
        pending="ok",
        rejected="ok",
        suspended="ok",
        operator="forbidden",
    ),
    "/operator/": dict(
        anonymous="login",
        customer="forbidden",
        approved="forbidden",
        pending="forbidden",
        rejected="forbidden",
        suspended="forbidden",
        operator="ok",
    ),
    "/operator/sellers/{target}/": dict(
        anonymous="login",
        customer="forbidden",
        approved="forbidden",
        pending="forbidden",
        rejected="forbidden",
        suspended="forbidden",
        operator="ok",
    ),
    "/operator/audit/": dict(
        anonymous="login",
        customer="forbidden",
        approved="forbidden",
        pending="forbidden",
        rejected="forbidden",
        suspended="forbidden",
        operator="ok",
    ),
}


def assert_outcome(response, expected, url):
    if expected == "ok":
        assert response.status_code == 200
    elif expected == "login":
        assert response.status_code == 302 and response.url.startswith("/login/?next=")
    elif expected == "status":
        assert response.status_code == 302 and response.url == STATUS_PAGE
    else:
        assert response.status_code == 403
        assert "This page is not part of your account." in response.content.decode()


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("url", list(GET_MATRIX))
def test_get_access_matrix(people, url, kind):
    users, target = people
    response = client_for(users, kind).get(url.format(target=target.pk))
    assert_outcome(response, GET_MATRIX[url][kind], url)


# The pages of each role that show private data. The browser must not keep them, or the back button after logout shows them.
PRIVATE_PAGES = {
    "customer": ["/account/", "/wishlist/", "/alerts/", "/cart/", "/orders/"],
    "approved": [
        "/seller/",
        "/seller/status/",
        "/seller/orders/",
        "/seller/reviews/",
        "/seller/insights/",
        "/products/mine/",
        "/products/mine/new/",
    ],
    "operator": [
        "/operator/",
        "/operator/audit/",
        "/operator/orders/",
        "/operator/reviews/",
        "/operator/dashboard/",
        "/products/operator/",
        "/products/operator/categories/",
    ],
}


@pytest.mark.parametrize("kind", sorted(PRIVATE_PAGES))
def test_every_private_page_tells_the_browser_not_to_keep_it(people, kind):
    users, _ = people
    client = client_for(users, kind)
    for url in PRIVATE_PAGES[kind]:
        response = client.get(url)
        assert response.status_code == 200, url
        assert "no-store" in response["Cache-Control"], url


def test_the_login_redirect_of_a_private_page_is_not_cached_either(people):
    response = client_for(people[0], "anonymous").get("/account/")
    assert response.status_code == 302 and "no-store" in response["Cache-Control"]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("action", ["approve", "reject", "suspend", "reinstate"])
def test_only_operators_can_post_seller_actions(people, kind, action):
    users, _ = people
    # Each action's target is a seller in the state that action expects, so only access decides the outcome.
    target = make_seller(
        username="target",
        status={"approve": "pending", "reject": "pending", "suspend": "approved", "reinstate": "suspended"}[action],
    )
    before = target.status
    response = client_for(users, kind).post(
        f"/operator/sellers/{target.pk}/{action}/", {f"{action}-reason": "Policy check"}
    )
    target.refresh_from_db()
    if kind == "operator":
        assert response.status_code == 302 and target.status != before
        assert AuditLog.objects.filter(row_id=str(target.pk)).count() == 1
    else:
        assert response.status_code in (302, 403) and target.status == before
        assert response.status_code == 403 or response.url.startswith("/login/")
        assert not AuditLog.objects.exists()


@pytest.mark.parametrize("status", ["pending", "rejected", "suspended"])
def test_unapproved_sellers_cannot_post_to_seller_pages(people, status):
    users, _ = people
    assert client_for(users, status).post("/seller/").status_code == 403


def test_htmx_requests_get_hx_redirect_when_anonymous_and_403_for_the_wrong_role(people):
    users, _ = people
    anonymous = Client().get("/operator/", HTTP_HX_REQUEST="true")
    assert anonymous.status_code == 200 and anonymous["HX-Redirect"] == "/login/"
    assert client_for(users, "customer").get("/operator/", HTTP_HX_REQUEST="true").status_code == 403


def test_suspension_applies_to_a_session_that_is_already_logged_in(people):
    users, _ = people
    seller = Seller.objects.get(user=users["approved"])
    client = client_for(users, "approved")
    assert client.get("/seller/").status_code == 200
    change_seller_status(seller.pk, "suspend", users["operator"], "Counterfeit listings")
    response = client.get("/seller/")
    assert response.status_code == 302 and response.url == STATUS_PAGE
    status_page = client.get(STATUS_PAGE).content.decode()
    assert "Counterfeit listings" in status_page and "Seller centre" not in status_page


def test_a_seller_cannot_reach_another_sellers_rows_by_tampering(people):
    users, target = people
    other = make_seller(username="other-approved", status="approved", shop_name="Other Shop Ltd")
    client = client_for(users, "approved")
    for url in (
        f"/seller/?seller={other.pk}",
        f"/seller/?seller_id={other.pk}&user={other.user_id}",
        f"{STATUS_PAGE}?seller={other.pk}",
    ):
        body = client.get(url).content.decode()
        assert "seller-approved shop" in body and "Other Shop Ltd" not in body
    assert client.get(f"/operator/sellers/{other.pk}/").status_code == 403
    assert (
        client.post(f"/operator/sellers/{target.pk}/approve/", {"approve-reason": "self-approval"}).status_code == 403
    )
    target.refresh_from_db()
    assert target.status == "pending"


EXPECTED_NAV = {
    "anonymous": ({"Shop", "Sell on Mercer"}, {"My account", "Seller centre", "Seller status", "Sellers", "Audit log"}),
    "customer": ({"Shop", "My account"}, {"Sell on Mercer", "Seller centre", "Seller status", "Sellers", "Audit log"}),
    "approved": ({"Shop", "Seller centre", "Seller status"}, {"My account", "Sell on Mercer", "Sellers", "Audit log"}),
    "pending": ({"Shop", "Seller status"}, {"Seller centre", "My account", "Sell on Mercer", "Sellers", "Audit log"}),
    "operator": ({"Shop", "Sellers", "Audit log"}, {"My account", "Sell on Mercer", "Seller centre", "Seller status"}),
}


@pytest.mark.parametrize("kind", list(EXPECTED_NAV))
def test_navigation_shows_only_the_current_roles_links(people, kind):
    users, _ = people
    body = client_for(users, kind).get("/products/").content.decode()
    nav = body[body.index('id="primary-navigation"') : body.index("</nav>", body.index('id="primary-navigation"'))]
    shown, hidden = EXPECTED_NAV[kind]
    assert all(f">{label}</a>" in nav for label in shown)
    assert not any(f">{label}</a>" in nav for label in hidden)


@pytest.mark.parametrize(
    "kind, landing",
    [
        ("customer", "/products/"),
        ("approved", "/seller/"),
        ("pending", STATUS_PAGE),
        ("rejected", STATUS_PAGE),
        ("suspended", STATUS_PAGE),
        ("operator", "/operator/"),
    ],
)
def test_login_lands_each_role_on_its_home(people, kind, landing):
    users, _ = people
    client = Client()
    response = client.post("/login/", {"username": users[kind].username, "password": PASSWORD})
    assert response.status_code == 302 and response.url == landing
    assert client.get("/login/").url == landing  # already logged in: same landing


@pytest.mark.parametrize(
    "target",
    [
        "//evil.example.com/",
        "/\\evil.example.com",
        "https://evil.example.com/",
        "http://testserver/operator/",
        "javascript:alert(1)",
        "operator/",
    ],
)
def test_login_next_must_be_a_same_site_path(people, target):
    users, _ = people
    response = Client().post("/login/", {"username": "operator", "password": PASSWORD, "next": target})
    assert response.status_code == 302 and response.url == "/operator/"


def test_login_honours_a_local_next_path(people):
    response = Client().post(
        "/login/", {"username": "seller-approved", "password": PASSWORD, "next": "/seller/status/"}
    )
    assert response.url == STATUS_PAGE
