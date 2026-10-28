"""The app's SQL text, live CTEs and equivalent pipelines with Singapore day boundaries."""
from datetime import datetime, time, timedelta
from decimal import Decimal

from bson import Decimal128

from benchmarks import db
from benchmarks.query import Query
from benchmarks.source import ZONE
from dashboard.queries import BAYESIAN_RATING, CATEGORY_PERFORMANCE, DELAY_BUCKETS, STOCK_PLANNING


def view_select():
    with db.pg() as conn:
        return conn.execute("SELECT pg_get_viewdef('daily_product_sales'::regclass, true) AS definition").fetchone()["definition"].rstrip("; \n")


def live_query(statement, definition):
    statement = statement.strip()
    prefix = "WITH daily_product_sales AS (" + definition + ")"
    return prefix + ", " + statement[5:] if statement.startswith("WITH ") else prefix + " " + statement


def queries(as_of, stats):
    end = datetime.combine(as_of + timedelta(days=1), time.min, ZONE)
    start = datetime.combine(as_of - timedelta(days=27), time.min, ZONE)
    day = datetime.combine(as_of, time.min, ZONE)
    parameters = {"as_of": as_of, "end": end, "category": None, "seller": None,
                  "C": stats["C"].to_decimal(), "m": stats["m"].to_decimal()}
    definition = view_select()
    delay = "WITH delays AS (" + DELAY_BUCKETS.strip() + """), scores AS (
      SELECT order_id, avg(score::numeric) AS score FROM reviews
      WHERE NOT taken_down AND NOT from_order_review AND answered_at < %(end)s GROUP BY order_id)
      SELECT d.bucket, count(*) AS orders, count(s.score) AS reviewed_orders, avg(s.score) AS average_score
      FROM delays d LEFT JOIN scores s ON s.order_id=d.order_id GROUP BY d.bucket ORDER BY d.bucket"""
    result = [Query("B2a", "postgres", "live", live_query(CATEGORY_PERFORMANCE, definition), parameters, golden="B2a"),
              Query("B2a", "postgres", "view", CATEGORY_PERFORMANCE, parameters, golden="B2a"),
              Query("B2b", "postgres", "live", live_query(STOCK_PLANNING, definition), parameters, golden="B2b"),
              Query("B2b", "postgres", "view", STOCK_PLANNING, parameters, golden="B2b"),
              Query("B2c", "postgres", "live", BAYESIAN_RATING, parameters, golden="B2c"),
              Query("B2d", "postgres", "live", delay, parameters, golden="B2d"),
              Query("B2refresh", "postgres", "refresh", "SELECT public.refresh_daily_product_sales()", {})]
    valid = {"placed_at": {"$lt": end}, "$or": [{"status": {"$ne": "cancelled"}}, {"cancelled_at": {"$gte": end}}]}
    month = {"$dateTrunc": {"date": "$placed_at", "unit": "month", "timezone": "Asia/Singapore"}}
    category = [{"$match": valid}, {"$unwind": "$lines"},
                {"$group": {"_id": {"product": "$lines.product_id", "month": month}, "units": {"$sum": "$lines.quantity"},
                             "revenue": {"$sum": {"$multiply": ["$lines.quantity", "$lines.unit_price"]}}}},
                {"$lookup": {"from": "products", "localField": "_id.product", "foreignField": "_id", "as": "product"}}, {"$unwind": "$product"},
                {"$group": {"_id": {"category": "$product.category_id", "month": "$_id.month"}, "units": {"$sum": "$units"}, "revenue": {"$sum": "$revenue"}}},
                {"$set": {"category_id": "$_id.category", "month": "$_id.month"}},
                {"$setWindowFields": {"partitionBy": "$month", "sortBy": {"revenue": -1}, "output": {"revenue_rank": {"$rank": {}}}}},
                {"$setWindowFields": {"partitionBy": "$category_id", "sortBy": {"month": 1}, "output": {
                    "previous_revenue": {"$shift": {"output": "$revenue", "by": -1}}, "previous_month": {"$shift": {"output": "$month", "by": -1}}}}},
                {"$set": {"change_percent": {"$cond": [{"$and": [{"$eq": ["$previous_month", {"$dateSubtract": {"startDate": "$month", "unit": "month", "amount": 1,
                           "timezone": "Asia/Singapore"}}]}, {"$gt": ["$previous_revenue", 0]}]},
                           {"$divide": [{"$multiply": [{"$subtract": ["$revenue", "$previous_revenue"]}, 100]}, "$previous_revenue"]}, None]},
                           "month": {"$dateToString": {"date": "$month", "format": "%Y-%m-%d", "timezone": "Asia/Singapore"}}}},
                {"$project": {"_id": 0, "category_id": 1, "month": 1, "units": 1, "revenue": 1, "revenue_rank": 1, "change_percent": 1}}]
    result.append(Query("B2a", "mongo", "live", collection="orders", pipeline=category, golden="B2a"))
    recent = {**valid, "placed_at": {"$gte": start, "$lt": end}}
    stock = [{"$match": {"purchasable": True}},
             {"$lookup": {"from": "orders", "localField": "_id", "foreignField": "lines.product_id", "let": {"pid": "$_id"}, "pipeline": [
                 {"$match": recent}, {"$unwind": "$lines"}, {"$match": {"$expr": {"$eq": ["$lines.product_id", "$$pid"]}}},
                 {"$group": {"_id": {"$dateTrunc": {"date": "$placed_at", "unit": "day", "timezone": "Asia/Singapore"}}, "units": {"$sum": "$lines.quantity"}}}], "as": "sales"}},
             {"$set": {"days": {"$map": {"input": {"$range": [0, 28]}, "as": "offset", "in": {
                 "$dateAdd": {"startDate": start, "unit": "day", "amount": "$$offset", "timezone": "Asia/Singapore"}}}}}},
             {"$unwind": "$days"},
             {"$set": {"units": {"$toDecimal": {"$sum": {"$map": {"input": {"$filter": {"input": "$sales", "as": "s", "cond": {"$eq": ["$$s._id", "$days"]}}},
                                                                 "as": "s", "in": "$$s.units"}}}}}},
             {"$setWindowFields": {"partitionBy": "$_id", "sortBy": {"days": 1}, "output": {
                 "daily_demand": {"$avg": "$units", "window": {"range": [-27, 0], "unit": "day"}},
                 "units_28": {"$sum": "$units", "window": {"range": [-27, 0], "unit": "day"}}}}},
             {"$match": {"days": day}},
             {"$project": {"_id": 0, "product_id": "$_id", "daily_demand": 1,
                 "days_cover": {"$cond": [{"$gt": ["$units_28", 0]}, {"$divide": [{"$multiply": ["$stock", 28]}, "$units_28"]}, None]},
                 "replenish": {"$and": [{"$gt": ["$units_28", 0]}, {"$lt": [{"$multiply": ["$stock", 28]}, {"$multiply": ["$lead_time_days", "$units_28"]}]}]}}}]
    result.append(Query("B2b", "mongo", "live", pipeline=stock, golden="B2b"))
    ratings = [{"$lookup": {"from": "reviews", "localField": "_id", "foreignField": "product_id", "pipeline": [
        {"$match": {"taken_down": {"$ne": True}, "answered_at": {"$lt": end}}},
        {"$group": {"_id": None, "count": {"$sum": 1}, "total": {"$sum": "$score"}}}], "as": "ratings"}},
        {"$set": {"count": {"$ifNull": [{"$first": "$ratings.count"}, 0]}, "total": {"$ifNull": [{"$first": "$ratings.total"}, 0]},
                  "entities": [{"entity": "product", "identity": "$_id"}, {"entity": "seller", "identity": "$seller_id"}]}},
        {"$unwind": "$entities"}, {"$group": {"_id": "$entities", "review_count": {"$sum": "$count"}, "score_sum": {"$sum": "$total"}}},
        {"$project": {"_id": 0, "entity": "$_id.entity", "entity_id": "$_id.identity", "review_count": 1, "score_sum": 1,
         "bayesian": {"$cond": [{"$gt": [{"$add": [stats["C"], "$review_count"]}, 0]},
              {"$divide": [{"$add": [{"$multiply": [stats["C"], stats["m"]]}, "$score_sum"]}, {"$add": [stats["C"], "$review_count"]}]}, Decimal128(Decimal(0))]}}}]
    result.append(Query("B2c", "mongo", "live", pipeline=ratings, golden="B2c"))
    delays = [{"$match": {"status": "delivered", "placed_at": {"$lt": end}, "delivered_at": {"$lt": end}}},
              {"$set": {"delay": {"$dateDiff": {"startDate": "$estimated_delivery", "endDate": "$delivered_at", "unit": "day", "timezone": "Asia/Singapore"}}}},
              {"$lookup": {"from": "reviews", "localField": "_id", "foreignField": "order_id", "pipeline": [
                  {"$match": {"taken_down": False, "from_order_review": False, "answered_at": {"$lt": end}}},
                  {"$group": {"_id": None, "score": {"$avg": {"$toDecimal": "$score"}}}}], "as": "scores"}},
              {"$set": {"score": {"$ifNull": [{"$first": "$scores.score"}, None]}, "bucket": {"$switch": {"branches": [
                  {"case": {"$lt": ["$delay", -7]}, "then": "early_over_7"}, {"case": {"$lte": ["$delay", 0]}, "then": "early_up_to_7_or_on_time"},
                  {"case": {"$lte": ["$delay", 7]}, "then": "late_1_to_7"}, {"case": {"$lte": ["$delay", 14]}, "then": "late_8_to_14"}], "default": "late_over_14"}}}},
              {"$group": {"_id": "$bucket", "orders": {"$sum": 1}, "reviewed_orders": {"$sum": {"$cond": [{"$ne": ["$score", None]}, 1, 0]}}, "average_score": {"$avg": "$score"}}},
              {"$project": {"_id": 0, "bucket": "$_id", "orders": 1, "reviewed_orders": 1, "average_score": 1}}]
    result.append(Query("B2d", "mongo", "live", collection="orders", pipeline=delays, golden="B2d"))
    # Deterministic driver row order makes later results comparable by plain equality, without canonicalisation.
    sorts = {"B2a": {"month": 1, "revenue_rank": 1, "category_id": 1}, "B2b": {"product_id": 1},
             "B2c": {"entity": 1, "entity_id": 1}, "B2d": {"bucket": 1}}
    for query in result:
        if query.engine == "mongo":
            query.pipeline.append({"$sort": sorts[query.output]})
    return result
