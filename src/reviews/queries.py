from django.core.paginator import Paginator

from catalogue.models import Product
from orders.models import Order

from .ratings import bayesian_score
from .services import NEWEST, VISIBLE

# A written review has a title or a comment; the rest are bare star ratings.
WRITTEN = {"$or": [{"text_en": {"$nin": ["", None]}}, {"title_en": {"$nin": ["", None]}}]}


def is_written(review):
    return bool(review.get("text_en") or review.get("title_en"))


def _present(rows, products=None):
    """Add the display fields. A review is historical when its order was not delivered (one PostgreSQL read)."""
    delivered = set(
        Order.objects.filter(pk__in={r["order_id"] for r in rows}, status="delivered").values_list("pk", flat=True)
    )
    if products is None:
        products = Product.objects.in_bulk({r["product_id"] for r in rows})
    return [
        {
            **row,
            "line_id": row["order_line_id"],
            "historical": row["order_id"] not in delivered,
            "product": products.get(row["product_id"]),
        }
        for row in rows
    ]


def review_page(database, match, page_number, *, include_hidden=False):
    match = {**match, **({} if include_hidden else VISIBLE)}
    paginator = Paginator(range(database.reviews.count_documents(match)), 10)
    page = paginator.get_page(page_number)
    rows = list(
        database.reviews.find(match).sort(NEWEST).skip(page.start_index() - 1 if paginator.count else 0).limit(10)
    )
    page.object_list = _present(rows)
    return page


def latest_written_reviews(spec, product):
    """The product page's first view of its reviews, read from the specification document (the subset pattern).

    `latest_reviews` already holds the five newest visible reviews, so no second MongoDB read happens. Returns the
    written ones and how many of the five were bare star ratings.
    """
    latest = (spec or {}).get("latest_reviews", [])
    written = [row for row in latest if is_written(row)]
    return _present(written, {product.pk: product}), len(latest) - len(written)


def seller_rating(database, seller_id):
    rows = list(
        database.reviews.aggregate(
            [
                {"$match": {"seller_id": seller_id, **VISIBLE}},
                {"$group": {"_id": None, "count": {"$sum": 1}, "total": {"$sum": "$score"}}},
            ]
        )
    )
    row = rows[0] if rows else {"count": 0, "total": 0}
    return {
        "count": row["count"],
        "bayesian": bayesian_score(
            database.platform_stats.find_one({"_id": "bayesian"}), row["total"], row["count"]
        ).to_decimal(),
    }
