"""Review contract and exit checks against real PostgreSQL and MongoDB."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal, localcontext
from io import StringIO

import psycopg
import pytest
from account_helpers import make_operator, runtime_connection
from bson import Decimal128
from checkout_helpers import customer, paid_order, product
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import close_old_connections, connection
from django.http import Http404
from django.test import Client
from pymongo.errors import DuplicateKeyError

from accounts.models import AuditLog
from catalogue.search import search_page, visible_products
from catalogue.services import save_product
from config import mongo
from orders.models import OrderLine
from reviews.ratings import bayesian_score, empty_summary
from reviews.services import NEWEST, VISIBLE, moderate_review, write_review

pytestmark = pytest.mark.django_db(transaction=True)
STATS = {"_id": "bayesian", "m": Decimal128("4"), "C": Decimal128("2")}


@pytest.fixture
def graph(mongo_db):
    buyer, item = customer(), product()
    mongo_db.platform_stats.insert_one(dict(STATS))
    mongo_db.product_specs.insert_one(
        {
            "_id": item.pk,
            "category_id": item.category_id,
            "description": "Example",
            "attributes": {},
            "photo_file_id": None,
            "rating_summary": empty_summary(STATS),
            "latest_reviews": [],
            "has_generated_content": False,
        }
    )
    return buyer, item


def line_for(buyer, item, status="delivered"):
    _, order = paid_order(buyer, item, status=status)
    return OrderLine.objects.create(order=order, seller=item.seller, product=item, quantity=1, unit_price=10, freight=2)


def assert_summary(database, item):
    rows = list(database.reviews.find({"product_id": item.pk, **VISIBLE}).sort(NEWEST))
    spec = database.product_specs.find_one({"_id": item.pk})
    summary = spec["rating_summary"]
    assert summary["count"] == len(rows)
    assert summary["sum"] == sum(row["score"] for row in rows)
    assert summary["distribution"] == {str(n): sum(r["score"] == n for r in rows) for n in range(1, 6)}
    with localcontext() as context:
        context.prec = 28
        assert summary["average"].to_decimal() == (Decimal(summary["sum"]) / len(rows) if rows else Decimal(0))
    assert abs(
        summary["bayesian"].to_decimal() - bayesian_score(STATS, summary["sum"], len(rows)).to_decimal()
    ) < Decimal("1e-27")
    assert spec["latest_reviews"] == rows[:5]


def test_create_edit_delete_and_latest_five_equal_full_recomputation(graph, mongo_db):
    buyer, item = graph
    original = deepcopy(mongo_db.product_specs.find_one({"_id": item.pk}))
    lines = [line_for(buyer, item) for _ in range(7)]
    for line in lines:
        write_review(buyer, line.pk, "create", {"score": 4, "title": "Delivered", "text": "Excellent"})
        assert_summary(mongo_db, item)
    write_review(buyer, lines[-1].pk, "edit", {"score": 2, "title": "Changed", "text": "Updated"})
    assert_summary(mongo_db, item)
    for line in lines:
        write_review(buyer, line.pk, "delete")
        assert_summary(mongo_db, item)
    assert mongo_db.product_specs.find_one({"_id": item.pk}) == original


@pytest.mark.parametrize("status", ["paid", "shipped", "cancelled", "placed"])
def test_undelivered_reviews_are_refused(graph, mongo_db, status):
    buyer, item = graph
    line = line_for(buyer, item, status)
    with pytest.raises(ValidationError):
        write_review(buyer, line.pk, "create", {"score": 5})
    client = Client()
    client.force_login(buyer)
    assert client.post(f"/reviews/line/{line.pk}/", {"action": "create", "score": 5}).status_code == 404
    assert mongo_db.reviews.count_documents({}) == 0


def saved_messages(response):
    return [str(message) for message in response.context["messages"]]


def test_editing_a_taken_down_review_says_it_stays_hidden(graph, mongo_db):
    buyer, item = graph
    line = line_for(buyer, item)
    write_review(buyer, line.pk, "create", {"score": 5, "title": "Good", "text": "Fine"})
    client = Client()
    client.force_login(buyer)
    form = {"action": "edit", "score": 4, "title": "Better", "text": "Still fine"}
    assert saved_messages(client.post(f"/reviews/line/{line.pk}/", form, follow=True)) == ["Review saved."]
    moderate_review(make_operator(), line.pk, "takedown", "Evidence checked")
    response = client.post(f"/reviews/line/{line.pk}/", form, follow=True)
    assert saved_messages(response) == ["Review saved, but it stays hidden until an operator restores it."]
    assert mongo_db.reviews.find_one({"order_line_id": line.pk})["taken_down"] is True


def test_other_customer_and_duplicate_and_invalid_scores_are_refused(graph, mongo_db):
    buyer, item = graph
    line = line_for(buyer, item)
    with pytest.raises(Http404):
        write_review(customer("other"), line.pk, "create", {"score": 5})
    for score in [0, 6, True, {"$gt": 0}, "5; DROP TABLE orders_order"]:
        with pytest.raises(ValidationError):
            write_review(buyer, line.pk, "create", {"score": score})
    write_review(buyer, line.pk, "create", {"score": 5})
    with pytest.raises(ValidationError):
        write_review(buyer, line.pk, "create", {"score": 5})
    row = mongo_db.reviews.find_one({})
    row.pop("_id")
    with pytest.raises(DuplicateKeyError):
        mongo_db.reviews.insert_one(row)
    assert_summary(mongo_db, item)


def test_concurrent_reviews_on_one_product_both_land(graph, mongo_db):
    buyer, item = graph
    lines = [line_for(buyer, item) for _ in range(2)]

    def write(line):
        close_old_connections()
        try:
            with mongo.using_database(mongo_db.name):
                write_review(buyer, line.pk, "create", {"score": 4})
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(write, lines))
    assert mongo_db.reviews.count_documents({}) == 2
    assert_summary(mongo_db, item)


def test_take_down_restore_and_audit_are_consistent(graph, mongo_db):
    buyer, item = graph
    line = line_for(buyer, item)
    operator = make_operator()
    write_review(buyer, line.pk, "create", {"score": 3})
    for action in ["takedown", "restore"]:
        moderate_review(operator, line.pk, action, "Evidence checked")
        assert_summary(mongo_db, item)
    audits = list(AuditLog.objects.filter(table_name="reviews").order_by("id"))
    assert [a.action for a in audits] == ["review.takedown", "review.restore"]
    assert all(a.row_id == str(line.pk) and a.actor_id == operator.pk for a in audits)
    with pytest.raises(ValidationError):
        moderate_review(operator, line.pk, "restore", "Repeat")
    assert AuditLog.objects.filter(table_name="reviews").count() == 2


def test_failed_summary_update_rolls_back_review_and_sql_audit(graph, mongo_db):
    buyer, item = graph
    line = line_for(buyer, item)
    operator = make_operator()
    write_review(buyer, line.pk, "create", {"score": 4})
    before = mongo_db.reviews.find_one({})
    mongo_db.product_specs.delete_one({"_id": item.pk})
    with pytest.raises(ValidationError):
        moderate_review(operator, line.pk, "takedown", "Must roll back")
    assert mongo_db.reviews.find_one({}) == before
    assert not AuditLog.objects.filter(table_name="reviews").exists()


def test_literal_injection_text_and_narrow_audit_function(graph, mongo_db):
    buyer, item = graph
    operator = make_operator()
    line = line_for(buyer, item)
    payload = "'; DROP TABLE catalogue_product; -- {$where: sleep(999)} <script>bad</script>"
    write_review(buyer, line.pk, "create", {"score": 5, "title": payload, "text": payload})
    moderate_review(operator, line.pk, "takedown", payload)
    assert AuditLog.objects.get(table_name="reviews").reason == payload
    assert mongo_db.reviews.count_documents({}) == 1
    with runtime_connection() as runtime:
        for review_id, action, reason in [
            (str(line.pk), payload, "Reason"),
            (payload, "takedown", "Reason"),
            (str(line.pk), "takedown", " "),
        ]:
            with pytest.raises(psycopg.errors.CheckViolation), runtime.transaction():
                runtime.execute(
                    "SELECT set_config('mercer.actor_id', %s, true), set_config('mercer.audit_reason', %s, true)",
                    [str(operator.pk), reason],
                )
                runtime.execute("SELECT public.audit_review_moderation(%s, %s)", [review_id, action])
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            runtime.execute(
                "INSERT INTO audit_log(table_name,row_id,action,created_at) VALUES ('reviews','1','forged',now())"
            )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            runtime.execute("SELECT public.audit_review_moderation(%s, %s)", [str(line.pk), "restore"])
        with runtime.transaction():
            runtime.execute(
                "SELECT set_config('mercer.actor_id', %s, true), set_config('mercer.audit_reason', %s, true)",
                [str(operator.pk), payload],
            )
            runtime.execute("SELECT public.audit_review_moderation(%s, %s)", [str(line.pk), "restore"])
    assert AuditLog.objects.filter(table_name="reviews").count() == 2
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT prosecdef, proconfig, pg_get_userbyid(proowner)=current_user FROM pg_proc WHERE proname=%s",
            ["audit_review_moderation"],
        )
        assert cursor.fetchone() == (True, ["search_path=public, pg_temp"], True)


def test_customer_ui_and_seller_scoping_and_operator_roles(graph, mongo_db):
    buyer, item = graph
    line = line_for(buyer, item)
    client = Client()
    client.force_login(buyer)
    path = f"/reviews/line/{line.pk}/"
    assert client.get(path).status_code == 200
    assert (
        client.post(path, {"action": "create", "score": "4", "title": "Only our shop", "text": "Good"}).status_code
        == 302
    )
    page = client.get(f"/products/{item.pk}/")
    assert b"4.0 / 5 from 1 review" in page.content and b"Only our shop" in page.content
    assert client.post(path, {"action": "edit", "score": "2", "text": "Changed"}).status_code == 302
    assert_summary(mongo_db, item)
    seller = Client()
    seller.force_login(item.seller.user)
    assert b"Changed" in seller.get("/seller/reviews/").content
    other = product("other")
    seller.force_login(other.seller.user)
    assert b"Changed" not in seller.get("/seller/reviews/?seller_id=" + str(item.seller_id)).content
    assert seller.post(path, {"action": "delete"}).status_code == 403
    assert client.get("/operator/reviews/").status_code == 403
    assert client.post(path, {"action": "delete"}).status_code == 302
    assert_summary(mongo_db, item)


def test_seller_rating_match_uses_seller_date_index_and_only_own_documents(imported, mongo_db):
    from reviews.queries import seller_rating

    for _ in range(2):
        call_command("mongo_setup", database=mongo_db.name, stdout=StringIO())
    seller_id = mongo_db.reviews.find_one({})["seller_id"]
    match = {"seller_id": seller_id, **VISIBLE}
    expected = list(mongo_db.reviews.find(match))
    assert 0 < len(expected) < mongo_db.reviews.count_documents({})
    assert seller_rating(mongo_db, seller_id)["count"] == len(expected)
    explained = mongo_db.command("explain", {"find": "reviews", "filter": match}, verbosity="executionStats")

    def index_scans(node):
        if isinstance(node, dict):
            if node.get("stage") == "IXSCAN":
                yield node.get("indexName")
            for child in node.values():
                yield from index_scans(child)
        elif isinstance(node, list):
            for child in node:
                yield from index_scans(child)

    assert "review_seller_date" in set(index_scans(explained["queryPlanner"]["winningPlan"]))
    stats = explained["executionStats"]
    assert stats["nReturned"] == len(expected)
    assert stats["totalDocsExamined"] == mongo_db.reviews.count_documents({"seller_id": seller_id})
    assert mongo_db.reviews.index_information()["review_seller_date"]["key"] == [("seller_id", 1), ("answered_at", -1)]


def test_operator_newest_first_list_is_served_by_an_index_without_an_in_memory_sort(mongo_db):
    for _ in range(2):
        call_command("mongo_setup", database=mongo_db.name, stdout=StringIO())
    assert mongo_db.reviews.index_information()["review_newest"]["key"] == [
        ("answered_at", -1),
        ("olist_review_id", -1),
        ("order_line_id", -1),
    ]
    explained = mongo_db.command(
        "explain", {"find": "reviews", "filter": {}, "sort": dict(NEWEST), "limit": 10}, verbosity="queryPlanner"
    )

    def stages(node):
        if isinstance(node, dict):
            if "stage" in node:
                yield node["stage"]
            for child in node.values():
                yield from stages(child)
        elif isinstance(node, list):
            for child in node:
                yield from stages(child)

    found = set(stages(explained["queryPlanner"]["winningPlan"]))
    assert "IXSCAN" in found and "SORT" not in found


@pytest.mark.parametrize("without_historical", [False, True])
def test_imported_display_translation_history_pagination_and_takedown(imported, mongo_db, without_historical):
    historical = mongo_db.reviews.find_one({"text_pt": {"$ne": ""}})
    line = OrderLine.objects.select_related("order__checkout", "product").get(pk=historical["order_line_id"])
    # Imported undelivered history must remain visible and labelled.
    from orders.models import Order

    undelivered = set(Order.objects.exclude(status="delivered").values_list("pk", flat=True))
    if without_historical:
        mongo_db.reviews.delete_many({"order_id": {"$in": list(undelivered)}})
    row = mongo_db.reviews.find_one({"order_id": {"$in": list(undelivered)}})
    if row is None:
        pending = line_for(line.order.checkout.customer, line.product, status="paid")
        row = {
            **historical,
            "_id": pending.pk,
            "order_line_id": pending.pk,
            "order_id": pending.order_id,
            "checkout_id": pending.order.checkout_id,
            "product_id": pending.product_id,
            "seller_id": pending.seller_id,
            "customer_id": pending.order.checkout.customer_id,
            "olist_review_id": None,
        }
        mongo_db.reviews.insert_one(row)
    assert row is not None
    assert Order.objects.get(pk=row["order_id"]).status != "delivered"
    from reviews.queries import review_page

    assert review_page(mongo_db, {"order_line_id": row["order_line_id"]}, 1).object_list[0]["historical"]
    from catalogue.models import Product

    Product.objects.filter(pk=row["product_id"]).update(active=True)
    ordered = list(mongo_db.reviews.find({"product_id": row["product_id"], **VISIBLE}).sort(NEWEST))
    number = next(index for index, review in enumerate(ordered) if review["_id"] == row["_id"]) // 10 + 1
    page = Client().get(f"/products/{row['product_id']}/", {"page": number})
    assert page.status_code == 200
    assert any(
        review["line_id"] == row["order_line_id"] and review["historical"] for review in page.context["reviews_page"]
    )
    assert b"Historical review (order not delivered)" in page.content
    Product.objects.filter(pk=line.product_id).update(active=True)
    page = Client().get(f"/products/{line.product_id}/?lang=pt")
    assert page.status_code == 200 and b"Portuguese original" in page.content
    page = Client().get(f"/products/{line.product_id}/?lang=en")
    assert b"Machine-translated from Portuguese" in page.content
    from reviews.queries import review_page

    first = review_page(mongo_db, {}, 1)
    second = review_page(mongo_db, {}, 2)
    assert len(first.object_list) == 10 and not {r["line_id"] for r in first} & {r["line_id"] for r in second}


def test_bayesian_prior_for_new_product_and_top_rated_path(graph, mongo_db):
    buyer, item = graph
    created = save_product(
        item.seller,
        item.seller.user,
        {
            "name": "New",
            "category": item.category,
            "price": item.price,
            "stock": 2,
            "freight": item.freight,
            "lead_time_days": 2,
            "description": "New",
            "attributes": {},
        },
    )
    assert mongo_db.product_specs.find_one({"_id": created.pk})["rating_summary"]["bayesian"] == STATS["m"]
    # A single five-star review shrinks more than a body of very good reviews.
    write_review(buyer, line_for(buyer, created).pk, "create", {"score": 5})
    for _ in range(6):
        write_review(buyer, line_for(buyer, item).pk, "create", {"score": 5})
    write_review(buyer, line_for(buyer, item).pk, "create", {"score": 4})
    assert_summary(mongo_db, item)
    from catalogue.forms import SearchForm

    form = SearchForm({"category": item.category_id, "sort": "top"})
    assert form.is_valid(), form.errors
    page, _ = search_page(mongo_db, visible_products(), form.cleaned_data, {}, 1)
    assert [p.pk for p in page][:2] == [item.pk, created.pk]


def test_imported_summary_returns_byte_exact_after_insert_and_delete(imported, mongo_db):
    from accounts.models import User
    from catalogue.models import Product
    from orders.models import Order

    order = Order.objects.filter(status="delivered").select_related("checkout").first()
    buyer = User.objects.get(pk=order.checkout.customer_id)
    for spec in mongo_db.product_specs.find({}).limit(20):
        item = Product.objects.get(pk=spec["_id"])
        line = line_for(buyer, item)
        write_review(buyer, line.pk, "create", {"score": 5})
        write_review(buyer, line.pk, "delete")
        assert mongo_db.product_specs.find_one({"_id": item.pk}) == spec
