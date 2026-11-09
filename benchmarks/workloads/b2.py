"""The app's SQL text, live CTEs and equivalent pipelines with Singapore day boundaries."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from bson import Decimal128

from benchmarks import db, idiomatic_sql, summaries
from benchmarks.query import Query
from benchmarks.source import ZONE
from dashboard.queries import (
    BAYESIAN_RATING,
    CATEGORY_PERFORMANCE,
    DELAY_BUCKETS,
    STOCK_PLANNING,
    STOCK_PLANNING_FAST,
)


def view_select():
    with db.pg() as conn:
        return (
            conn.execute("SELECT pg_get_viewdef('daily_product_sales'::regclass, true) AS definition")
            .fetchone()["definition"]
            .rstrip("; \n")
        )


def live_query(statement, definition):
    statement = statement.strip()
    prefix = "WITH daily_product_sales AS (" + definition + ")"
    return prefix + ", " + statement[5:] if statement.startswith("WITH ") else prefix + " " + statement


def queries(as_of, stats):
    end = datetime.combine(as_of + timedelta(days=1), time.min, ZONE)
    start = datetime.combine(as_of - timedelta(days=27), time.min, ZONE)
    day = datetime.combine(as_of, time.min, ZONE)
    parameters = {
        "as_of": as_of,
        "start": start,
        "end": end,
        "category": None,
        "seller": None,
        "C": stats["C"].to_decimal(),
        "m": stats["m"].to_decimal(),
    }
    definition = view_select()
    delay = (
        "WITH delays AS ("
        + DELAY_BUCKETS.strip()
        + """), scores AS (
      SELECT order_id, avg(score::numeric) AS score FROM reviews
      WHERE NOT taken_down AND answered_at < %(end)s GROUP BY order_id)
      SELECT d.bucket, count(*) AS orders, count(s.score) AS reviewed_orders, avg(s.score) AS average_score
      FROM delays d LEFT JOIN scores s ON s.order_id=d.order_id GROUP BY d.bucket ORDER BY d.bucket"""
    )
    result = [
        Query("B2a", "postgres", "live", live_query(CATEGORY_PERFORMANCE, definition), parameters, golden="B2a"),
        Query("B2a", "postgres", "view", CATEGORY_PERFORMANCE, parameters, golden="B2a"),
        Query("B2b", "postgres", "live", live_query(STOCK_PLANNING, definition), parameters, golden="B2b"),
        Query("B2b", "postgres", "view", STOCK_PLANNING, parameters, golden="B2b"),
        Query("B2c", "postgres", "live", BAYESIAN_RATING, parameters, golden="B2c"),
        Query("B2d", "postgres", "live", delay, parameters, golden="B2d"),
        Query("B2refresh", "postgres", "refresh", "SELECT public.refresh_daily_product_sales()", {}),
        # The query the application runs for B2b: one grouped sum over the last 28 days, live and on the maintained view.
        # These resolve names and sort for display, so they are reported with the originals (amendment m).
        Query("B2b", "postgres", "app", live_query(STOCK_PLANNING_FAST, definition), parameters, golden="B2b"),
        Query("B2b", "postgres", "app_summary", STOCK_PLANNING_FAST, parameters, golden="B2b"),
        # Idiomatic and summary: the golden columns only, the same question the MongoDB pipelines answer.
        Query("B2a", "postgres", "idiomatic", idiomatic_sql.CATEGORY_IDIOMATIC, parameters, golden="B2a"),
        Query("B2a", "postgres", "summary", idiomatic_sql.CATEGORY_SUMMARY, parameters, golden="B2a"),
        Query("B2b", "postgres", "idiomatic", idiomatic_sql.STOCK_IDIOMATIC, parameters, golden="B2b"),
        Query("B2b", "postgres", "summary", idiomatic_sql.STOCK_SUMMARY, parameters, golden="B2b"),
        Query("B2d", "postgres", "idiomatic", idiomatic_sql.DELAY_IDIOMATIC, parameters, golden="B2d"),
    ]
    valid = {"placed_at": {"$lt": end}, "$or": [{"status": {"$ne": "cancelled"}}, {"cancelled_at": {"$gte": end}}]}
    month = {"$dateTrunc": {"date": "$placed_at", "unit": "month", "timezone": "Asia/Singapore"}}
    category_head = [{"$match": valid}, {"$unwind": "$lines"}]
    # As first written: group by product, join the product for its category, group again.
    category_as_written = [
        {
            "$group": {
                "_id": {"product": "$lines.product_id", "month": month},
                "units": {"$sum": "$lines.quantity"},
                "revenue": {"$sum": {"$multiply": ["$lines.quantity", "$lines.unit_price"]}},
            }
        },
        {"$lookup": {"from": "products", "localField": "_id.product", "foreignField": "_id", "as": "product"}},
        {"$unwind": "$product"},
        {
            "$group": {
                "_id": {"category": "$product.category_id", "month": "$_id.month"},
                "units": {"$sum": "$units"},
                "revenue": {"$sum": "$revenue"},
            }
        },
    ]
    category_tail = [
        {"$set": {"category_id": "$_id.category", "month": "$_id.month"}},
        {
            "$setWindowFields": {
                "partitionBy": "$month",
                "sortBy": {"revenue": -1},
                "output": {"revenue_rank": {"$rank": {}}},
            }
        },
        {
            "$setWindowFields": {
                "partitionBy": "$category_id",
                "sortBy": {"month": 1},
                "output": {
                    "previous_revenue": {"$shift": {"output": "$revenue", "by": -1}},
                    "previous_month": {"$shift": {"output": "$month", "by": -1}},
                },
            }
        },
        {
            "$set": {
                "change_percent": {
                    "$cond": [
                        {
                            "$and": [
                                {
                                    "$eq": [
                                        "$previous_month",
                                        {
                                            "$dateSubtract": {
                                                "startDate": "$month",
                                                "unit": "month",
                                                "amount": 1,
                                                "timezone": "Asia/Singapore",
                                            }
                                        },
                                    ]
                                },
                                {"$gt": ["$previous_revenue", 0]},
                            ]
                        },
                        {
                            "$divide": [
                                {"$multiply": [{"$subtract": ["$revenue", "$previous_revenue"]}, 100]},
                                "$previous_revenue",
                            ]
                        },
                        None,
                    ]
                },
                "month": {"$dateToString": {"date": "$month", "format": "%Y-%m-%d", "timezone": "Asia/Singapore"}},
            }
        },
        {
            "$project": {
                "_id": 0,
                "category_id": 1,
                "month": 1,
                "units": 1,
                "revenue": 1,
                "revenue_rank": 1,
                "change_percent": 1,
            }
        },
    ]
    category = category_head + category_as_written + category_tail
    # Idiomatic: the order line already carries its category (a denormalised, read-optimised document), so group by
    # category and month directly and join nothing.
    category_idiomatic = (
        category_head
        + [
            {
                "$group": {
                    "_id": {"category": "$lines.category_id", "month": month},
                    "units": {"$sum": "$lines.quantity"},
                    "revenue": {"$sum": {"$multiply": ["$lines.quantity", "$lines.unit_price"]}},
                }
            }
        ]
        + category_tail
    )
    result.append(Query("B2a", "mongo", "live", collection="orders", pipeline=category, golden="B2a"))
    result.append(Query("B2a", "mongo", "idiomatic", collection="orders", pipeline=category_idiomatic, golden="B2a"))
    recent = {**valid, "placed_at": {"$gte": start, "$lt": end}}
    stock = [
        {"$match": {"purchasable": True}},
        {
            "$lookup": {
                "from": "orders",
                "localField": "_id",
                "foreignField": "lines.product_id",
                "let": {"pid": "$_id"},
                "pipeline": [
                    {"$match": recent},
                    {"$unwind": "$lines"},
                    {"$match": {"$expr": {"$eq": ["$lines.product_id", "$$pid"]}}},
                    {
                        "$group": {
                            "_id": {"$dateTrunc": {"date": "$placed_at", "unit": "day", "timezone": "Asia/Singapore"}},
                            "units": {"$sum": "$lines.quantity"},
                        }
                    },
                ],
                "as": "sales",
            }
        },
        {
            "$set": {
                "days": {
                    "$map": {
                        "input": {"$range": [0, 28]},
                        "as": "offset",
                        "in": {
                            "$dateAdd": {
                                "startDate": start,
                                "unit": "day",
                                "amount": "$$offset",
                                "timezone": "Asia/Singapore",
                            }
                        },
                    }
                }
            }
        },
        {"$unwind": "$days"},
        {
            "$set": {
                "units": {
                    "$toDecimal": {
                        "$sum": {
                            "$map": {
                                "input": {
                                    "$filter": {"input": "$sales", "as": "s", "cond": {"$eq": ["$$s._id", "$days"]}}
                                },
                                "as": "s",
                                "in": "$$s.units",
                            }
                        }
                    }
                }
            }
        },
        {
            "$setWindowFields": {
                "partitionBy": "$_id",
                "sortBy": {"days": 1},
                "output": {
                    "daily_demand": {"$avg": "$units", "window": {"range": [-27, 0], "unit": "day"}},
                    "units_28": {"$sum": "$units", "window": {"range": [-27, 0], "unit": "day"}},
                },
            }
        },
        {"$match": {"days": day}},
        {
            "$project": {
                "_id": 0,
                "product_id": "$_id",
                "daily_demand": 1,
                "days_cover": {
                    "$cond": [
                        {"$gt": ["$units_28", 0]},
                        {"$divide": [{"$multiply": ["$stock", 28]}, "$units_28"]},
                        None,
                    ]
                },
                "replenish": {
                    "$and": [
                        {"$gt": ["$units_28", 0]},
                        {"$lt": [{"$multiply": ["$stock", 28]}, {"$multiply": ["$lead_time_days", "$units_28"]}]},
                    ]
                },
            }
        },
    ]
    result.append(Query("B2b", "mongo", "live", pipeline=stock, golden="B2b"))
    # Idiomatic: group the recent order lines by product first (one pass over a bounded date range), bring in the purchasable
    # products with `$unionWith` (an unsold product keeps zero units), and merge each product's sales with its stock and
    # lead time in one `$group` by product id. No per-product lookup.
    stock_idiomatic = [
        {"$match": recent},
        {"$unwind": "$lines"},
        {"$group": {"_id": "$lines.product_id", "units_28": {"$sum": "$lines.quantity"}}},
        {
            "$unionWith": {
                "coll": "products",
                "pipeline": [
                    {"$match": {"purchasable": True}},
                    {"$project": {"units_28": {"$literal": 0}, "stock": 1, "lead_time_days": 1, "purchasable": 1}},
                ],
            }
        },
        {
            "$group": {
                "_id": "$_id",
                "units_28": {"$sum": "$units_28"},
                "stock": {"$max": "$stock"},
                "lead_time_days": {"$max": "$lead_time_days"},
                "purchasable": {"$max": "$purchasable"},
            }
        },
        {"$match": {"purchasable": True}},  # sold products that are not purchasable carry no stock fields
        {
            "$project": {
                "_id": 0,
                "product_id": "$_id",
                "daily_demand": {"$divide": [{"$toDecimal": "$units_28"}, 28]},
                "days_cover": {
                    "$cond": [
                        {"$gt": ["$units_28", 0]},
                        {"$divide": [{"$toDecimal": {"$multiply": ["$stock", 28]}}, {"$toDecimal": "$units_28"}]},
                        None,
                    ]
                },
                "replenish": {
                    "$and": [
                        {"$gt": ["$units_28", 0]},
                        {"$lt": [{"$multiply": ["$stock", 28]}, {"$multiply": ["$lead_time_days", "$units_28"]}]},
                    ]
                },
            }
        },
    ]
    result.append(Query("B2b", "mongo", "idiomatic", collection="orders", pipeline=stock_idiomatic, golden="B2b"))
    # As first written: one correlated sub-query into `reviews` for every product.
    ratings_head = [
        {
            "$lookup": {
                "from": "reviews",
                "localField": "_id",
                "foreignField": "product_id",
                "pipeline": [
                    {"$match": {"taken_down": {"$ne": True}, "answered_at": {"$lt": end}}},
                    {"$group": {"_id": None, "count": {"$sum": 1}, "total": {"$sum": "$score"}}},
                ],
                "as": "ratings",
            }
        },
        {
            "$set": {
                "count": {"$ifNull": [{"$first": "$ratings.count"}, 0]},
                "total": {"$ifNull": [{"$first": "$ratings.total"}, 0]},
                "entities": [{"entity": "product", "identity": "$_id"}, {"entity": "seller", "identity": "$seller_id"}],
            }
        },
    ]
    ratings_tail = [
        {"$unwind": "$entities"},
        {"$group": {"_id": "$entities", "review_count": {"$sum": "$count"}, "score_sum": {"$sum": "$total"}}},
        {
            "$project": {
                "_id": 0,
                "entity": "$_id.entity",
                "entity_id": "$_id.identity",
                "review_count": 1,
                "score_sum": 1,
                "bayesian": {
                    "$cond": [
                        {"$gt": [{"$add": [stats["C"], "$review_count"]}, 0]},
                        {
                            "$divide": [
                                {"$add": [{"$multiply": [stats["C"], stats["m"]]}, "$score_sum"]},
                                {"$add": [stats["C"], "$review_count"]},
                            ]
                        },
                        Decimal128(Decimal(0)),
                    ]
                },
            }
        },
    ]
    ratings = ratings_head + ratings_tail
    # Idiomatic: one pass over the reviews grouped by product, then the products (with their seller) brought in with
    # `$unionWith` and merged by product id in one `$group`, so a product without reviews keeps zero. No per-product
    # lookup; the same product and seller roll-up follows.
    ratings_idiomatic = [
        {"$match": {"taken_down": {"$ne": True}, "answered_at": {"$lt": end}}},
        {"$group": {"_id": "$product_id", "count": {"$sum": 1}, "total": {"$sum": "$score"}}},
        {
            "$unionWith": {
                "coll": "products",
                "pipeline": [{"$project": {"count": {"$literal": 0}, "total": {"$literal": 0}, "seller_id": 1}}],
            }
        },
        {
            "$group": {
                "_id": "$_id",
                "count": {"$sum": "$count"},
                "total": {"$sum": "$total"},
                "seller_id": {"$max": "$seller_id"},
            }
        },
        {"$match": {"seller_id": {"$ne": None}}},  # reviews of a product that does not exist
        {
            "$set": {
                "entities": [
                    {"entity": "product", "identity": "$_id"},
                    {"entity": "seller", "identity": "$seller_id"},
                ]
            }
        },
    ] + ratings_tail
    result.append(Query("B2c", "mongo", "live", pipeline=ratings, golden="B2c"))
    result.append(Query("B2c", "mongo", "idiomatic", collection="reviews", pipeline=ratings_idiomatic, golden="B2c"))
    delays = [
        {"$match": {"status": "delivered", "placed_at": {"$lt": end}, "delivered_at": {"$lt": end}}},
        {
            "$set": {
                "delay": {
                    "$dateDiff": {
                        "startDate": "$estimated_delivery",
                        "endDate": "$delivered_at",
                        "unit": "day",
                        "timezone": "Asia/Singapore",
                    }
                }
            }
        },
        {
            "$lookup": {
                "from": "reviews",
                "localField": "_id",
                "foreignField": "order_id",
                "pipeline": [
                    {"$match": {"taken_down": False, "answered_at": {"$lt": end}}},
                    {"$group": {"_id": None, "score": {"$avg": {"$toDecimal": "$score"}}}},
                ],
                "as": "scores",
            }
        },
        {
            "$set": {
                "score": {"$ifNull": [{"$first": "$scores.score"}, None]},
                "bucket": {
                    "$switch": {
                        "branches": [
                            {"case": {"$lt": ["$delay", -7]}, "then": "early_over_7"},
                            {"case": {"$lte": ["$delay", 0]}, "then": "early_up_to_7_or_on_time"},
                            {"case": {"$lte": ["$delay", 7]}, "then": "late_1_to_7"},
                            {"case": {"$lte": ["$delay", 14]}, "then": "late_8_to_14"},
                        ],
                        "default": "late_over_14",
                    }
                },
            }
        },
        {
            "$group": {
                "_id": "$bucket",
                "orders": {"$sum": 1},
                "reviewed_orders": {"$sum": {"$cond": [{"$ne": ["$score", None]}, 1, 0]}},
                "average_score": {"$avg": "$score"},
            }
        },
        {"$project": {"_id": 0, "bucket": "$_id", "orders": 1, "reviewed_orders": 1, "average_score": 1}},
    ]
    result.append(Query("B2d", "mongo", "live", collection="orders", pipeline=delays, golden="B2d"))
    # Idiomatic: no per-order sub-query. Group the visible reviews by order once (an integer sum and count), add the
    # delivered orders with their delay through `$unionWith`, and merge the two kinds of document by order id in one
    # `$group`; an order with no review simply keeps a count of zero. The average is divided once per order.
    delays_idiomatic = [
        {"$match": {"taken_down": False, "answered_at": {"$lt": end}}},
        {"$group": {"_id": "$order_id", "total": {"$sum": "$score"}, "count": {"$sum": 1}}},
        {"$unionWith": {"coll": "orders", "pipeline": [delays[0], delays[1], {"$project": {"delay": 1}}]}},
        {
            "$group": {
                "_id": "$_id",
                "total": {"$sum": "$total"},
                "count": {"$sum": "$count"},
                "delay": {"$max": "$delay"},
            }
        },
        {"$match": {"delay": {"$ne": None}}},  # reviews of orders that are not delivered by the reporting date
        {
            "$set": {
                "score": {"$cond": [{"$gt": ["$count", 0]}, {"$divide": [{"$toDecimal": "$total"}, "$count"]}, None]},
                "bucket": delays[3]["$set"]["bucket"],
            }
        },
        delays[4],
        delays[5],
    ]
    result.append(Query("B2d", "mongo", "idiomatic", collection="reviews", pipeline=delays_idiomatic, golden="B2d"))
    # Maintained summaries (amendment m). PostgreSQL's daily_product_sales view is the "view" variant of B2a and B2b;
    # MongoDB gets the same summary as a collection, and both engines get a per-order delivery and score summary.
    result.append(
        Query(
            "B2d",
            "postgres",
            "summary",
            "SELECT bucket, count(*) AS orders, count(score_total) AS reviewed_orders, "
            "avg(score_total::numeric / review_count) AS average_score "
            "FROM bench_order_delivery_scores GROUP BY bucket ORDER BY bucket",
            {},
            golden="B2d",
        )
    )
    category_summary = [
        {
            "$group": {
                "_id": {
                    "category": "$category_id",
                    "month": {"$dateTrunc": {"date": "$day", "unit": "month", "timezone": "Asia/Singapore"}},
                },
                "units": {"$sum": "$units"},
                "revenue": {"$sum": "$revenue"},
            }
        }
    ] + category_tail
    result.append(Query("B2a", "mongo", "summary", collection=summaries.DAILY, pipeline=category_summary, golden="B2a"))
    stock_summary = [
        {"$match": {"day": {"$gte": start, "$lt": end}}},
        {"$group": {"_id": "$product_id", "units_28": {"$sum": "$units"}}},
    ] + stock_idiomatic[3:]  # the same union with the unsold purchasable products and the same product join
    result.append(Query("B2b", "mongo", "summary", collection=summaries.DAILY, pipeline=stock_summary, golden="B2b"))
    delays_summary = [
        {
            "$group": {
                "_id": "$bucket",
                "orders": {"$sum": 1},
                "reviewed_orders": {"$sum": {"$cond": [{"$gt": ["$count", 0]}, 1, 0]}},
                "average_score": {
                    "$avg": {"$cond": [{"$gt": ["$count", 0]}, {"$divide": [{"$toDecimal": "$total"}, "$count"]}, None]}
                },
            }
        },
        {"$project": {"_id": 0, "bucket": "$_id", "orders": 1, "reviewed_orders": 1, "average_score": 1}},
    ]
    result.append(
        Query("B2d", "mongo", "summary", collection=summaries.ORDER_SCORES, pipeline=delays_summary, golden="B2d")
    )
    # What keeping each summary current costs, measured separately for each engine.
    result += [
        Query("B2refresh", "postgres", "refresh_scores", "SELECT bench_refresh_order_delivery_scores()", {}),
        Query("B2refresh", "mongo", "refresh", collection="orders", pipeline=summaries.daily_sales_pipeline(as_of)),
        Query(
            "B2refresh",
            "mongo",
            "refresh_scores",
            collection="reviews",
            pipeline=summaries.order_scores_pipeline(as_of),
        ),
    ]
    # Deterministic driver row order makes later results comparable by plain equality, without canonicalisation.
    sorts = {
        "B2a": {"month": 1, "revenue_rank": 1, "category_id": 1},
        "B2b": {"product_id": 1},
        "B2c": {"entity": 1, "entity_id": 1},
        "B2d": {"bucket": 1},
    }
    for query in result:
        if query.engine == "mongo" and query.output in sorts:  # a refresh pipeline ends in $out and returns no rows
            query.pipeline.append({"$sort": sorts[query.output]})
    return result
