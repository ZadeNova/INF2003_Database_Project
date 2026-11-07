"""Independent fixture calculations, time cutoffs and the runtime refresh boundary."""

import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path

import psycopg
import pytest
from account_helpers import make_operator, runtime_connection
from checkout_helpers import customer, paid_order, product
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import DataError
from django.test import Client
from django.utils import timezone

from catalogue.models import Product
from catalogue.search import visible_products
from dashboard.queries import BAYESIAN_RATING, CATEGORY_PERFORMANCE, DELAY_BUCKETS
from dashboard.services import (
    BUCKET_LABELS,
    as_of_date,
    category_performance,
    dashboard_data,
    delivery_analysis,
    end_of_day,
    label_month_to_date,
    poor_reviews_pipeline,
    query_rows,
    refresh_sales,
    stock_planning,
)
from orders.models import Order, OrderLine
from reviews.ratings import bayesian_score, empty_summary
from reviews.services import write_review

pytestmark = pytest.mark.django_db(transaction=True)


def reference_sales(as_of):
    result = defaultdict(lambda: {"units": 0, "revenue": Decimal(0)})
    for line in OrderLine.objects.select_related("order", "product"):
        day = timezone.localdate(line.order.placed_at)
        cancelled = line.order.status == "cancelled" and (
            line.order.cancelled_at is None or timezone.localdate(line.order.cancelled_at) <= as_of
        )
        if day > as_of or cancelled:
            continue
        row = result[(line.product_id, day)]
        row["units"] += line.quantity
        row["revenue"] += line.quantity * line.unit_price
    return result


def test_import_refresh_and_fixture_as_of_and_materialized_totals(imported):
    as_of = as_of_date()
    assert as_of == date(2026, 10, 24)
    actual = query_rows("SELECT * FROM daily_product_sales", {})
    assert {
        (r["product_id"], r["day"]): {"units": r["units"], "revenue": r["revenue"]} for r in actual
    } == reference_sales(as_of)


def test_every_stock_number_and_exact_replenishment_boundary(imported):
    as_of = as_of_date()
    sales = reference_sales(as_of)
    expected_ids = set(visible_products().values_list("pk", flat=True))
    rows = stock_planning(as_of)
    assert {r["product_id"] for r in rows} == expected_ids
    for row in rows:
        units = sum(
            value["units"]
            for (pid, day), value in sales.items()
            if pid == row["product_id"] and as_of - timedelta(days=27) <= day <= as_of
        )
        assert abs(row["daily_demand"] - Decimal(units) / 28) < Decimal("1e-16")
        assert row["replenish"] == (units > 0 and row["stock"] * 28 < row["lead_time_days"] * units)
        if units:
            assert abs(row["days_cover"] - Decimal(row["stock"] * 28) / units) < Decimal("1e-12")
        else:
            assert row["days_cover"] is None
    eligible = next(r for r in rows if r["daily_demand"] > 0)
    units = sum(
        value["units"]
        for (pid, day), value in sales.items()
        if pid == eligible["product_id"] and as_of - timedelta(days=27) <= day <= as_of
    )
    Product.objects.filter(pk=eligible["product_id"]).update(stock=units, lead_time_days=28)
    exact = stock_planning(as_of, seller=eligible["seller_id"])
    assert not next(r for r in exact if r["product_id"] == eligible["product_id"])["replenish"]
    Product.objects.filter(pk=eligible["product_id"]).update(lead_time_days=29)
    assert next(r for r in stock_planning(as_of) if r["product_id"] == eligible["product_id"])["replenish"]


def test_category_revenue_units_rank_and_calendar_month_change(imported):
    as_of = as_of_date()
    grouped = defaultdict(lambda: {"units": 0, "revenue": Decimal(0)})
    products = Product.objects.in_bulk()
    for (pid, day), value in reference_sales(as_of).items():
        row = grouped[(products[pid].category_id, day.replace(day=1))]
        row["units"] += value["units"]
        row["revenue"] += value["revenue"]
    rows = category_performance(as_of)
    assert len(rows) == len(grouped)
    for row in rows:
        value = grouped[(row["category_id"], row["month"])]
        assert (row["units"], row["revenue"]) == (value["units"], value["revenue"])
        rank = 1 + sum(v["revenue"] > row["revenue"] for (cid, month), v in grouped.items() if month == row["month"])
        assert row["revenue_rank"] == rank
        previous = (row["month"] - timedelta(days=1)).replace(day=1)
        previous_value = grouped.get((row["category_id"], previous))
        if previous_value and previous_value["revenue"]:
            change = (row["revenue"] - previous_value["revenue"]) * 100 / previous_value["revenue"]
            assert abs(row["change_percent"] - change) < Decimal("1e-12")
        else:
            assert row["change_percent"] is None


def test_month_to_date_drops_only_the_change_of_the_month_the_reporting_date_cuts_short():
    rows = [
        {"month": date(2018, 9, 1), "change_percent": Decimal(5)},
        {"month": date(2018, 10, 1), "change_percent": Decimal(-60)},
    ]
    labelled = label_month_to_date(rows, date(2018, 10, 17))
    assert [(r["month_to_date"], r["change_percent"]) for r in labelled] == [(False, Decimal(5)), (True, None)]
    # A reporting date on the last day of the month completes it, so its change stays.
    assert label_month_to_date(rows[1:], date(2018, 10, 31)) == [{**rows[1], "month_to_date": False}]
    assert rows[1]["change_percent"] == Decimal(-60)  # the input rows are not modified


def test_dashboard_page_marks_the_cut_short_month(imported):
    as_of = as_of_date()
    partial = (as_of + timedelta(days=1)).day != 1
    client = Client()
    client.force_login(make_operator())
    assert (b"month to date" in client.get("/operator/dashboard/").content) is partial


def test_demo_orders_do_not_move_anchor_and_future_events_do_not_enter_sales(imported):
    as_of = as_of_date()
    before = category_performance(as_of)
    item = Product.objects.first()
    buyer = customer("later")
    placed, order = paid_order(buyer, item)
    OrderLine.objects.create(order=order, seller=item.seller, product=item, quantity=100, unit_price=10, freight=2)
    Order.objects.filter(pk=order.pk).update(placed_at=end_of_day(as_of) + timedelta(days=30))
    assert as_of_date() == as_of
    refresh_sales()
    assert category_performance(as_of) == before
    assert max(r["day"] for r in query_rows("SELECT day FROM daily_product_sales", {})) <= as_of
    # A cancellation after the cutoff is a later event too: the sale still belongs to the historical window.
    cancelled = Order.objects.filter(status="cancelled").first()
    Order.objects.filter(pk=cancelled.pk).update(cancelled_at=end_of_day(as_of) + timedelta(days=2))
    refresh_sales()
    actual = query_rows("SELECT * FROM daily_product_sales", {})
    assert {
        (r["product_id"], r["day"]): {"units": r["units"], "revenue": r["revenue"]} for r in actual
    } == reference_sales(as_of)


def reference_deliveries(as_of, database):
    end = end_of_day(as_of)
    score_groups = defaultdict(list)
    for review in database.reviews.find({}):
        answered = (
            review["answered_at"].replace(tzinfo=timezone.get_default_timezone())
            if timezone.is_naive(review["answered_at"])
            else review["answered_at"]
        )
        # MongoDB's naive datetimes are UTC, not business-local.
        from datetime import timezone as dt_timezone

        answered = review["answered_at"].replace(tzinfo=dt_timezone.utc)
        if not review.get("taken_down") and not review.get("from_order_review") and answered < end:
            score_groups[review["order_id"]].append(review["score"])
    buckets = {key: [] for key in BUCKET_LABELS}
    sellers = defaultdict(lambda: {"orders": 0, "late": 0, "scores": []})
    orders = Order.objects.filter(status="delivered", delivered_at__lt=end, placed_at__lt=end)
    for order in orders:
        days = (timezone.localdate(order.delivered_at) - timezone.localdate(order.estimated_delivery)).days
        bucket = (
            "early_over_7"
            if days < -7
            else "early_up_to_7_or_on_time"
            if days <= 0
            else "late_1_to_7"
            if days <= 7
            else "late_8_to_14"
            if days <= 14
            else "late_over_14"
        )
        seller = sellers[order.seller_id]
        seller["orders"] += 1
        seller["late"] += int(days > 0)
        scores = score_groups.get(order.pk)
        if scores:
            score = Decimal(sum(scores)) / len(scores)
            buckets[bucket].append(score)
            seller["scores"].append(score)
    return buckets, sellers


def test_delay_bucket_scores_and_each_seller_risk_match_direct_calculation(imported, mongo_db):
    as_of = as_of_date()
    expected, seller_values = reference_deliveries(as_of, mongo_db)
    buckets, sellers, excluded = delivery_analysis(as_of, mongo_db)
    for row in buckets:
        values = expected[row["key"]]
        assert row["reviewed_orders"] == len(values)
        average = sum(values, Decimal(0)) / len(values) if values else None
        assert row["average_score"] == average
    eligible = {sid: value for sid, value in seller_values.items() if value["orders"] >= 10}
    assert {row["seller_id"] for row in sellers} == set(eligible)
    assert excluded == len(seller_values) - len(eligible)
    expected_order = sorted(
        eligible,
        key=lambda sid: (
            not (Decimal(eligible[sid]["late"]) / eligible[sid]["orders"] > Decimal("0.20")),
            -Decimal(eligible[sid]["late"]) / eligible[sid]["orders"],
            sid,
        ),
    )
    assert [row["seller_id"] for row in sellers] == expected_order
    for row in sellers:
        value = seller_values[row["seller_id"]]
        assert row["orders"] == value["orders"]
        assert row["late_share"] == Decimal(value["late"]) / value["orders"]
        assert row["at_risk"] == (row["late_share"] > Decimal("0.20"))
        assert row["average_score"] == (
            sum(value["scores"], Decimal(0)) / len(value["scores"]) if value["scores"] else None
        )
    assert all(r["distance_km"] is None or 0 <= r["distance_km"] <= 21000 for r in buckets)


def test_seller_risk_minimum_cutoff_ordering_and_excluded_panel_note(imported, mongo_db):
    as_of = as_of_date()
    end = end_of_day(as_of)
    buyer = customer("risk-buyer")
    items = [product(name) for name in ["risk-small", "risk-boundary", "risk-tie", "risk-covered"]]
    for item, (count, late) in zip(items, [(9, 9), (10, 3), (10, 3), (10, 2)]):
        for index in range(count):
            _, order = paid_order(buyer, item, status="delivered")
            delivered = end - timedelta(days=2)
            Order.objects.filter(pk=order.pk).update(
                placed_at=delivered - timedelta(days=2),
                delivered_at=delivered,
                estimated_delivery=delivered - timedelta(days=int(index < late)),
            )
    # A delivery after the reporting date cannot push the small seller over the minimum.
    _, future = paid_order(buyer, items[0], status="delivered")
    Order.objects.filter(pk=future.pk).update(
        placed_at=end - timedelta(days=4), delivered_at=end, estimated_delivery=end - timedelta(days=1)
    )
    data = dashboard_data(as_of)
    rows = {row["seller_id"]: row for row in data["seller_rows"]}
    assert items[0].seller_id not in rows
    assert rows[items[1].seller_id]["orders"] == 10
    assert rows[items[1].seller_id]["late_share"] == Decimal("0.30")
    assert rows[items[1].seller_id]["at_risk"]
    assert not rows[items[3].seller_id]["at_risk"]
    _, direct = reference_deliveries(as_of, mongo_db)
    eligible = {sid: value for sid, value in direct.items() if value["orders"] >= 10}
    expected = sorted(
        eligible,
        key=lambda sid: (
            not (Decimal(eligible[sid]["late"]) / eligible[sid]["orders"] > Decimal("0.20")),
            -Decimal(eligible[sid]["late"]) / eligible[sid]["orders"],
            sid,
        ),
    )
    assert [row["seller_id"] for row in data["seller_rows"]] == expected
    assert data["seller_excluded_count"] == sum(value["orders"] < 10 for value in direct.values())
    assert data["seller_min_orders"] == 10
    client = Client()
    client.force_login(make_operator())
    response = client.get("/operator/dashboard/")
    assert response.status_code == 200
    assert b"At least 10 delivered orders" in response.content
    note = f"{data['seller_excluded_count']} sellers with fewer deliveries are excluded."
    assert note.encode() in response.content
    assert items[0].seller.shop_name.encode() not in response.content


def test_all_five_half_open_delay_boundaries_and_future_delivery_cutoff(imported):
    as_of = as_of_date()
    end = end_of_day(as_of)
    order = Order.objects.filter(status="delivered", delivered_at__lt=end).first()
    delivered = end - timedelta(days=10)
    for delay, expected in [
        (-8, "early_over_7"),
        (-7, "early_up_to_7_or_on_time"),
        (0, "early_up_to_7_or_on_time"),
        (1, "late_1_to_7"),
        (7, "late_1_to_7"),
        (8, "late_8_to_14"),
        (14, "late_8_to_14"),
        (15, "late_over_14"),
    ]:
        Order.objects.filter(pk=order.pk).update(
            delivered_at=delivered, estimated_delivery=delivered - timedelta(days=delay)
        )
        row = next(r for r in query_rows(DELAY_BUCKETS, {"end": end}) if r["order_id"] == order.pk)
        assert row["bucket"] == expected
    Order.objects.filter(pk=order.pk).update(delivered_at=end)
    assert order.pk not in {r["order_id"] for r in query_rows(DELAY_BUCKETS, {"end": end})}


def test_poor_review_pipeline_excludes_later_and_hidden_reviews(imported, mongo_db):
    as_of = as_of_date()
    end = end_of_day(as_of)
    buyer, item = customer(), product("poor")
    stats = mongo_db.platform_stats.find_one({"_id": "bayesian"})
    mongo_db.product_specs.insert_one(
        {
            "_id": item.pk,
            "category_id": item.category_id,
            "description": "Poor example",
            "attributes": {},
            "photo_file_id": None,
            "rating_summary": empty_summary(stats),
            "latest_reviews": [],
            "has_generated_content": False,
        }
    )
    for _ in range(6):
        _, order = paid_order(buyer, item, status="delivered")
        line = OrderLine.objects.create(
            order=order, seller=item.seller, product=item, quantity=1, unit_price=10, freight=2
        )
        write_review(buyer, line.pk, "create", {"score": 1})
    mongo_db.reviews.update_many({"product_id": item.pk}, {"$set": {"answered_at": end - timedelta(days=1)}})
    mongo_db.reviews.update_one({"order_line_id": line.pk}, {"$set": {"answered_at": end}})
    rows = list(mongo_db.reviews.aggregate(poor_reviews_pipeline(end)))
    row = next(r for r in rows if r["_id"] == item.pk)
    assert row["count"] == 5 and row["average"].to_decimal() == 1
    mongo_db.reviews.update_one(
        {"product_id": item.pk, "order_line_id": {"$ne": line.pk}}, {"$set": {"taken_down": True}}
    )
    assert item.pk not in {r["_id"] for r in mongo_db.reviews.aggregate(poor_reviews_pipeline(end))}


@pytest.mark.parametrize("field", ["category", "seller"])
def test_raw_stock_filters_bind_injection_values(imported, field):
    payload = "1; DROP TABLE catalogue_product; --"
    count = Product.objects.count()
    with pytest.raises(DataError):
        stock_planning(as_of_date(), **{field: payload})
    assert Product.objects.count() == count


def test_raw_date_filters_and_bayesian_prior_bind_injection_values(imported):
    payload = "2026-10-24'; DROP TABLE orders_order; --"
    with pytest.raises(ValidationError):
        stock_planning(payload)
    with pytest.raises(DataError):
        query_rows(CATEGORY_PERFORMANCE, {"as_of": payload})
    with pytest.raises(DataError):
        query_rows(DELAY_BUCKETS, {"end": payload})
    prefix = "WITH reviews AS (SELECT NULL::bigint AS product_id, NULL::integer AS score, false AS taken_down, now() AS answered_at WHERE false) "
    with pytest.raises(DataError):
        query_rows(prefix + BAYESIAN_RATING, {"C": payload, "m": 4, "end": end_of_day(as_of_date())})
    assert Order.objects.exists() and Product.objects.exists()


def test_named_bayesian_sql_matches_product_and_seller_hand_calculation(imported, mongo_db):
    stats = mongo_db.platform_stats.find_one({"_id": "bayesian"})
    item = Product.objects.first()
    prefix = "WITH reviews AS (SELECT %(product)s::bigint AS product_id, 5 AS score, false AS taken_down, %(answered)s::timestamptz AS answered_at) "
    rows = query_rows(
        prefix + BAYESIAN_RATING,
        {
            "product": item.pk,
            "answered": end_of_day(as_of_date()) - timedelta(days=1),
            "C": stats["C"].to_decimal(),
            "m": stats["m"].to_decimal(),
            "end": end_of_day(as_of_date()),
        },
    )
    for entity, entity_id in [("product", item.pk), ("seller", item.seller_id)]:
        row = next(r for r in rows if r["entity"] == entity and r["entity_id"] == entity_id)
        assert row["review_count"] == 1 and row["score_sum"] == 5
        assert abs(row["bayesian"] - bayesian_score(stats, 5, 1).to_decimal()) < Decimal("1e-16")


def test_runtime_refresh_function_but_not_direct_refresh_and_public_revocation(imported):
    with runtime_connection() as runtime:
        for _ in range(2):
            runtime.execute("SELECT public.refresh_daily_product_sales()")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            runtime.execute("REFRESH MATERIALIZED VIEW public.daily_product_sales")
        row = runtime.execute(
            "SELECT prosecdef,proconfig,pg_get_userbyid(proowner)=current_user FROM pg_proc WHERE proname=%s",
            ["refresh_daily_product_sales"],
        ).fetchone()
        assert row == (True, ["search_path=public, pg_temp"], False)
        acl = runtime.execute(
            "SELECT acl.grantee FROM pg_proc p CROSS JOIN LATERAL aclexplode(p.proacl) acl WHERE p.proname=%s AND acl.privilege_type='EXECUTE'",
            ["refresh_daily_product_sales"],
        ).fetchall()
        assert (0,) not in acl


def test_operator_dashboard_all_panels_and_roles_and_refresh_csrf(imported):
    operator = make_operator()
    client = Client()
    client.force_login(operator)
    response = client.get("/operator/dashboard/")
    assert response.status_code == 200 and response.context["as_of"] == as_of_date()
    for title in [
        b"Replenishment priorities",
        b"Category performance",
        b"Delivery delay and review score",
        b"Seller delivery risk",
        b"Products with poor reviews",
    ]:
        assert title in response.content
    assert response.content.count(b"As of 24 October 2026") == 5
    assert client.post("/operator/dashboard/refresh/", {"view": "x; DROP TABLE orders_order"}).status_code == 302
    assert client.get("/operator/dashboard/refresh/").status_code == 405
    secure = Client(enforce_csrf_checks=True)
    secure.force_login(operator)
    assert secure.post("/operator/dashboard/refresh/").status_code == 403
    client.force_login(customer("customer"))
    assert client.get("/operator/dashboard/").status_code == 403
    client.force_login(Product.objects.first().seller.user)
    assert client.get("/operator/dashboard/").status_code == 403
    assert Client().get("/operator/dashboard/").status_code == 302
    client.force_login(operator)
    for field in ["category", "seller"]:
        assert client.get("/operator/dashboard/", {field: "1 OR 1=1"}).status_code == 400


@pytest.mark.slow
def test_full_data_delay_pattern_matches_profile_within_tolerance(mongo_db):
    source = Path("/app/data/derived/olist/clean")
    profile = source.parent / "profile.json"
    if not (source / "checksums.txt").exists() or not profile.exists():
        pytest.skip("Full Olist files are local-only; fixture calculations run in every suite")
    call_command("import_olist", source=source, stdout=StringIO())
    actual, _, _ = delivery_analysis(as_of_date(), mongo_db)
    expected = json.loads(profile.read_text())["delivery_delay_scores"]
    for row in actual:
        assert row["average_score"] is not None
        assert abs(row["average_score"] - Decimal(expected[row["key"]]["average"])) <= Decimal("0.05")
    averages = [r["average_score"] for r in actual]

    def pattern(values):
        return [a > b for a, b in zip(values, values[1:])]

    assert pattern(averages) == pattern([Decimal(expected[key]["average"]) for key in BUCKET_LABELS])
