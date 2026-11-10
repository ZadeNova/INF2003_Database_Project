"""The maintained summaries of benchmark B2 in the bench databases (amendment m, docs/plans/benchmark.md).

PostgreSQL has the application's `daily_product_sales` materialized view (built by the import) and one bench-only view of
delivery buckets with review score totals, built from the order and review tables alone. MongoDB gets the same two
summaries as collections rebuilt with `$out`, an on-demand materialized view. Both are built when the project is loaded and
rebuilt by the measured B2refresh queries.
"""

from datetime import datetime, time, timedelta

from benchmarks.source import ZONE

DAILY = "daily_product_sales"
ORDER_SCORES = "order_delivery_scores"

# PostgreSQL: the delivery bucket and the visible-review totals per delivered order, built from the order and review tables
# alone, like the MongoDB summary. (The application's own order_delivery_summary also resolves the checkout, seller,
# customer and a distance for every order; refreshing that would charge PostgreSQL display work MongoDB's summary never does.)
# A materialized view cannot take parameters, so the reporting date is written into the definition: it is a date computed
# by the loader and formatted with isoformat, never user input.
POSTGRES_ORDER_SCORES = """
CREATE MATERIALIZED VIEW bench_order_delivery_scores AS
SELECT o.id AS order_id,
       CASE WHEN d.delay_days < -7 THEN 'early_over_7'
            WHEN d.delay_days <= 0 THEN 'early_up_to_7_or_on_time'
            WHEN d.delay_days <= 7 THEN 'late_1_to_7'
            WHEN d.delay_days <= 14 THEN 'late_8_to_14' ELSE 'late_over_14' END AS bucket,
       s.score_total, s.review_count
FROM orders_order o
CROSS JOIN LATERAL (SELECT (o.delivered_at AT TIME ZONE 'Asia/Singapore')::date -
                           (o.estimated_delivery AT TIME ZONE 'Asia/Singapore')::date AS delay_days) d
LEFT JOIN (
    SELECT r.order_id, sum(r.score)::bigint AS score_total, count(*) AS review_count
    FROM reviews r
    WHERE NOT r.taken_down AND r.answered_at < '{end}'::timestamptz
    GROUP BY r.order_id
) s ON s.order_id = o.id
WHERE o.status = 'delivered' AND o.placed_at < '{end}'::timestamptz AND o.delivered_at < '{end}'::timestamptz;
CREATE UNIQUE INDEX bench_order_delivery_scores_order ON bench_order_delivery_scores(order_id);
CREATE FUNCTION bench_refresh_order_delivery_scores() RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY bench_order_delivery_scores;
END $$;
"""


def postgres_order_scores(as_of):
    """The view and its refresh function for a reporting date, as SQL text."""
    return POSTGRES_ORDER_SCORES.replace("{end}", end_of_day(as_of).isoformat())


BUCKETS = {
    "$switch": {
        "branches": [
            {"case": {"$lt": ["$delay", -7]}, "then": "early_over_7"},
            {"case": {"$lte": ["$delay", 0]}, "then": "early_up_to_7_or_on_time"},
            {"case": {"$lte": ["$delay", 7]}, "then": "late_1_to_7"},
            {"case": {"$lte": ["$delay", 14]}, "then": "late_8_to_14"},
        ],
        "default": "late_over_14",
    }
}


def end_of_day(as_of):
    return datetime.combine(as_of + timedelta(days=1), time.min, ZONE)


def daily_sales_pipeline(as_of):
    """Units and revenue per product and Singapore day, as the PostgreSQL daily_product_sales view holds them."""
    end = end_of_day(as_of)
    valid = {"placed_at": {"$lt": end}, "$or": [{"status": {"$ne": "cancelled"}}, {"cancelled_at": {"$gte": end}}]}
    day = {"$dateTrunc": {"date": "$placed_at", "unit": "day", "timezone": "Asia/Singapore"}}
    return [
        {"$match": valid},
        {"$unwind": "$lines"},
        {
            "$group": {
                "_id": {"product_id": "$lines.product_id", "day": day},
                "category_id": {"$first": "$lines.category_id"},
                "units": {"$sum": "$lines.quantity"},
                "revenue": {"$sum": {"$multiply": ["$lines.quantity", "$lines.unit_price"]}},
            }
        },
        {
            "$project": {
                "_id": 0,
                "product_id": "$_id.product_id",
                "day": "$_id.day",
                "category_id": 1,
                "units": 1,
                "revenue": 1,
            }
        },
        {"$out": DAILY},
    ]


def order_scores_pipeline(as_of):
    """Delay bucket and the integer sum and count of visible review scores per delivered order (run on `reviews`)."""
    end = end_of_day(as_of)
    delivered = {"status": "delivered", "placed_at": {"$lt": end}, "delivered_at": {"$lt": end}}
    delay = {
        "$dateDiff": {
            "startDate": "$estimated_delivery",
            "endDate": "$delivered_at",
            "unit": "day",
            "timezone": "Asia/Singapore",
        }
    }
    return [
        {"$match": {"taken_down": False, "answered_at": {"$lt": end}}},
        {"$group": {"_id": "$order_id", "total": {"$sum": "$score"}, "count": {"$sum": 1}}},
        {
            "$unionWith": {
                "coll": "orders",
                "pipeline": [{"$match": delivered}, {"$set": {"delay": delay}}, {"$project": {"delay": 1}}],
            }
        },
        {
            "$group": {
                "_id": "$_id",
                "total": {"$sum": "$total"},
                "count": {"$sum": "$count"},
                "delay": {"$max": "$delay"},
            }
        },
        {"$match": {"delay": {"$ne": None}}},
        {"$set": {"bucket": BUCKETS}},
        {"$project": {"bucket": 1, "total": 1, "count": 1}},
        {"$out": ORDER_SCORES},
    ]


def build_mongo(database, as_of):
    """Build both summary collections (used when the project is loaded; the measured refresh runs the same pipelines)."""
    list(database.orders.aggregate(daily_sales_pipeline(as_of), allowDiskUse=True))
    database[DAILY].create_index([("product_id", 1), ("day", 1)], unique=True, name="bench_daily_sales_product_day")
    list(database.reviews.aggregate(order_scores_pipeline(as_of), allowDiskUse=True))
