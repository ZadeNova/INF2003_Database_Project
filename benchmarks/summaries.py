"""The maintained summaries of benchmark B2 in the bench databases (amendment m, docs/plans/benchmark.md).

PostgreSQL has the application's `daily_product_sales` materialized view (built by the import) and one bench-only view of
delivery buckets with review score totals. MongoDB gets the same two summaries as collections rebuilt with `$out`, an
on-demand materialized view. Both are built when the project is loaded and rebuilt by the measured B2refresh queries.
"""

from datetime import datetime, time, timedelta

from benchmarks.source import ZONE

DAILY = "daily_product_sales"
ORDER_SCORES = "order_delivery_scores"

# PostgreSQL: delivery bucket and visible-review totals per delivered order, derived from the application's own
# order_delivery_summary view (the delivery side) and the bench review copy (the score side), at the same cut-off.
POSTGRES_ORDER_SCORES = """
CREATE MATERIALIZED VIEW bench_order_delivery_scores AS
SELECT d.order_id, d.bucket, s.score_total, s.review_count
FROM order_delivery_summary d
LEFT JOIN (
    SELECT r.order_id, sum(r.score)::bigint AS score_total, count(*) AS review_count
    FROM reviews r
    WHERE NOT r.taken_down
      AND r.answered_at < (((SELECT max(as_of) FROM order_delivery_summary) + 1)::timestamp AT TIME ZONE 'Asia/Singapore')
    GROUP BY r.order_id
) s ON s.order_id = d.order_id;
CREATE UNIQUE INDEX bench_order_delivery_scores_order ON bench_order_delivery_scores(order_id);
CREATE FUNCTION bench_refresh_order_delivery_scores() RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    -- The delivery side lives in the application's own view, so keeping the scores current means refreshing that view
    -- first (this is what the application's refresh_sales does) and then the bench view built on it. Refreshing only the
    -- second would leave a changed delivery stale and would not pay for recomputing the delays.
    PERFORM public.refresh_order_delivery_summary();
    REFRESH MATERIALIZED VIEW CONCURRENTLY bench_order_delivery_scores;
END $$;
"""

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
