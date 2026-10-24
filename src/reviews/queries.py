from django.core.paginator import Paginator

from catalogue.models import Product
from orders.models import Order
from .ratings import bayesian_score
from .services import NEWEST, VISIBLE


def review_page(database, match, page_number, *, include_hidden=False):
    match = {**match, **({} if include_hidden else VISIBLE)}
    paginator = Paginator(range(database.reviews.count_documents(match)), 10)
    page = paginator.get_page(page_number)
    rows = list(database.reviews.find(match).sort(NEWEST).skip(page.start_index() - 1 if paginator.count else 0).limit(10))
    delivered = set(Order.objects.filter(pk__in={r["order_id"] for r in rows}, status="delivered").values_list("pk", flat=True))
    products = Product.objects.in_bulk({r["product_id"] for r in rows})
    page.object_list = [{**row, "line_id": row["order_line_id"], "historical": row["order_id"] not in delivered,
                         "product": products.get(row["product_id"])} for row in rows]
    return page


def seller_rating(database, seller_id):
    rows = list(database.reviews.aggregate([
        {"$match": {"seller_id": seller_id, **VISIBLE}},
        {"$group": {"_id": None, "count": {"$sum": 1}, "total": {"$sum": "$score"}}},
    ]))
    row = rows[0] if rows else {"count": 0, "total": 0}
    return {"count": row["count"], "bayesian": bayesian_score(
        database.platform_stats.find_one({"_id": "bayesian"}), row["total"], row["count"]).to_decimal()}
