"""Operator seller list, POST-only status actions and the audit log page."""
from datetime import datetime, timedelta, timezone

import pytest
from django.db import transaction
from django.test import Client
from django.utils.html import strip_tags

from accounts.audit import change_seller_status, set_audit_context
from accounts.models import AuditLog, Seller
from account_helpers import make_operator, make_seller

pytestmark = pytest.mark.django_db


@pytest.fixture
def operator():
    return make_operator()


@pytest.fixture
def console(operator):
    client = Client()
    client.force_login(operator)
    return client


def test_seller_list_filters_by_status_and_paginates(console):
    make_seller("approved-one", "approved")
    for number in range(27):
        make_seller(f"applicant-{number:02}", "pending")
    first = console.get("/operator/")
    body = first.content.decode()
    assert "applicant-00 shop" in body and "approved-one shop" not in body
    assert "Pending (27)" in body and "Approved (1)" in body
    assert first.context["page_obj"].paginator.num_pages == 2
    assert "applicant-26 shop" in console.get("/operator/?status=pending&page=2").content.decode()
    assert "approved-one shop" in console.get("/operator/?status=approved").content.decode()
    # An unknown or hostile status is not a filter value; the default list is shown.
    hostile = console.get("/operator/?status=approved' OR '1'='1")
    assert hostile.status_code == 200 and hostile.context["status"] == "pending"


@pytest.mark.parametrize("status, actions", [("pending", ["approve", "reject"]), ("approved", ["suspend"]),
                                             ("suspended", ["reinstate"]), ("rejected", [])])
def test_detail_offers_only_the_legal_actions(console, status, actions):
    seller = make_seller(status=status)
    response = console.get(f"/operator/sellers/{seller.pk}/")
    assert [action for action, _ in response.context["actions"]] == actions


def test_approve_with_a_reason_changes_status_and_records_the_operator(console, operator):
    seller = make_seller(status="pending")
    response = console.post(f"/operator/sellers/{seller.pk}/approve/", {"approve-reason": "Documents verified"})
    assert response.status_code == 302 and response.url == f"/operator/sellers/{seller.pk}/"
    seller.refresh_from_db()
    entry = AuditLog.objects.get()
    assert seller.status == "approved" and entry.actor == operator and entry.reason == "Documents verified"
    page = console.get(response.url).content.decode()
    assert f"Approved {seller.shop_name}." in page and "Documents verified" in page


@pytest.mark.parametrize("reason", ["", "   ", "x" * 501])
def test_a_missing_or_oversized_reason_changes_nothing(console, reason):
    seller = make_seller(status="pending")
    response = console.post(f"/operator/sellers/{seller.pk}/reject/", {"reject-reason": reason})
    assert response.status_code == 400
    assert Seller.objects.get(pk=seller.pk).status == "pending" and not AuditLog.objects.exists()


def test_repeated_post_fails_cleanly_without_a_second_audit_row(console):
    seller = make_seller(status="pending")
    url = f"/operator/sellers/{seller.pk}/approve/"
    console.post(url, {"approve-reason": "First"})
    second = console.post(url, {"approve-reason": "Second"}, follow=True)
    assert f"No change made: {seller.shop_name} is already approved." in second.content.decode()
    assert AuditLog.objects.count() == 1


def test_actions_are_post_only_and_validate_their_target(console):
    seller = make_seller(status="pending")
    assert console.get(f"/operator/sellers/{seller.pk}/approve/").status_code == 405
    assert console.post(f"/operator/sellers/{seller.pk}/delete/", {"delete-reason": "x"}).status_code == 404
    assert console.post("/operator/sellers/999999/approve/", {"approve-reason": "x"}).status_code == 404
    assert Seller.objects.get(pk=seller.pk).status == "pending"


def test_operator_actions_require_csrf(operator):
    seller = make_seller(status="pending")
    client = Client(enforce_csrf_checks=True)
    client.force_login(operator)
    response = client.post(f"/operator/sellers/{seller.pk}/approve/", {"approve-reason": "No token"})
    assert response.status_code == 403 and Seller.objects.get(pk=seller.pk).status == "pending"


def add_entry(**fields):
    defaults = {"table_name": "accounts_seller", "row_id": "1", "action": "seller.approve", "reason": None}
    return AuditLog.objects.create(**{**defaults, **fields})     # the owner (test role) may write directly


def test_audit_page_is_newest_first_with_id_tie_break_and_paginated(console):
    base = datetime(2026, 10, 22, tzinfo=timezone.utc)
    old = add_entry(created_at=base - timedelta(days=1), row_id="old")
    tied = [add_entry(created_at=base, row_id=f"tied-{n}") for n in range(30)]
    first = console.get("/operator/audit/")
    entries = list(first.context["entries"])
    assert [e.pk for e in entries] == [e.pk for e in reversed(tied)][:25]
    second = list(console.get("/operator/audit/?page=2").context["entries"])
    assert second[-1].pk == old.pk and len(second) == 6


def test_audit_filters_by_actor_and_action(console, operator):
    other = make_operator("operator-2")
    pending, approved = make_seller("a", "pending"), make_seller("b", "approved")
    change_seller_status(pending.pk, "approve", operator, "Mine")
    change_seller_status(approved.pk, "suspend", other, "Theirs")
    # A system reinstatement. The whole test is one transaction, so, like every action, it sets both settings.
    with transaction.atomic():
        set_audit_context(None, "")
        Seller.objects.filter(pk=approved.pk).update(status="approved")
    def actions(query):
        return sorted(e.action for e in console.get("/operator/audit/?" + query).context["entries"])
    assert actions(f"actor={operator.pk}") == ["seller.approve"]
    assert actions(f"actor={other.pk}") == ["seller.suspend"]
    assert actions("actor=system") == ["seller.reinstate"]
    assert actions("action=seller.suspend") == ["seller.suspend"]
    assert actions(f"actor={operator.pk}&action=seller.suspend") == []
    page = console.get(f"/operator/audit/?actor={other.pk}").content.decode()
    assert f"actor={other.pk}" in console.get(f"/operator/audit/?actor={other.pk}").context["query"]
    assert "Theirs" in page and "Mine" not in page


@pytest.mark.parametrize("query", ["actor=1%20OR%201%3D1", "actor=-1", "action=seller.approve'%20OR%20'1'%3D'1",
                                   "action[$ne]=x", "reason=Mine", "row_id=1"])
def test_hostile_or_unsupported_filters_do_not_become_queries(console, operator, query):
    seller = make_seller(status="pending")
    change_seller_status(seller.pk, "approve", operator, "Kept")
    response = console.get("/operator/audit/?" + query)
    assert response.status_code == 200
    assert AuditLog.objects.count() == 1 and Seller.objects.filter(pk=seller.pk).exists()


def test_audit_output_is_escaped(console, operator):
    seller = make_seller(status="pending", shop_name="<img src=x onerror=alert(1)>")
    change_seller_status(seller.pk, "reject", operator, "<script>alert('reason')</script>")
    body = console.get("/operator/audit/").content.decode()
    assert "<script>alert" not in body and "<img src=x" not in body
    assert "&lt;script&gt;" in body and "&lt;img src=x" in body


def test_audit_page_uses_plain_decision_labels_and_links_to_the_shop(console, operator):
    seller = make_seller(status="pending", shop_name="Willow Goods")
    change_seller_status(seller.pk, "approve", operator, "Documents verified")
    body = console.get("/operator/audit/").content.decode()
    visible = strip_tags(body)
    assert "accounts_seller" not in visible and "Row" not in visible and "trigger" not in visible.lower()
    assert ">seller.approve<" not in body and "seller.approve" not in visible
    assert "Approved" in visible and "Willow Goods" in visible
    assert f'href="/operator/sellers/{seller.pk}/"' in body
    assert '<option value="seller.approve">Approved</option>' in body


@pytest.mark.parametrize("status, label", Seller.Status.choices)
def test_seller_list_and_detail_use_capitalised_status_labels(console, status, label):
    seller = make_seller(status=status, shop_name="Olist seller ab12cd34")
    seller.has_generated_content = True
    seller.save(update_fields=["has_generated_content"])
    body = console.get(f"/operator/sellers/{seller.pk}/").content.decode()
    assert f'>{label}</span>' in body and f'>{status}</span>' not in body
    assert f'>{label} ({1})</a>' in console.get(f"/operator/?status={status}").content.decode()
    for url in (f"/operator/?status={status}", f"/operator/sellers/{seller.pk}/"):
        body = console.get(url).content.decode()
        assert "Sao Paulo Shop AB12CD34" in body and "Olist seller ab12cd34" not in body
        assert "Generated name" in body


def test_imported_shops_in_one_city_keep_distinct_readable_names(console):
    names = []
    for code in ("ab12cd34", "ef56ab78"):
        seller = make_seller(f"imported-{code}", "approved", shop_name=f"Olist seller {code}")
        Seller.objects.filter(pk=seller.pk).update(has_generated_content=True)
        names.append(Seller.objects.get(pk=seller.pk).display_name)
    assert names == ["Sao Paulo Shop AB12CD34", "Sao Paulo Shop EF56AB78"]
    body = console.get("/operator/?status=approved").content.decode()
    assert all(name in body for name in names)
    # A shop name an applicant typed is never rewritten, even if it looks like an imported one.
    typed = make_seller("typed", "pending", shop_name="Olist seller 12345678")
    assert typed.display_name == "Olist seller 12345678"
