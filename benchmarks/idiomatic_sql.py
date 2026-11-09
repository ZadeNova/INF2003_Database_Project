"""PostgreSQL's idiomatic B2 queries (amendment m, docs/plans/benchmark.md): the golden columns and nothing else.

The application's own dashboard queries also resolve names (category, shop), compute display fields and, for the delivery
buckets, a great-circle distance per order. The MongoDB pipelines return only the benchmark's columns, so the PostgreSQL
variants named `idiomatic` and `summary` ask exactly the same question: no display joins, no extra columns. Both engines
return rows in the golden key order (the MongoDB pipelines end in the same `$sort`). The application's own queries stay
as the `live`, `view`, `app` and `app_summary` variants, reported in their own table.

Written from the meaning of each question, then checked against the golden output; not changed after a timing.
"""

CATEGORY_TAIL = """
), changes AS (
    SELECT *, rank() OVER (PARTITION BY month ORDER BY revenue DESC) AS revenue_rank,
           lag(revenue) OVER (PARTITION BY category_id ORDER BY month) AS previous_revenue,
           lag(month) OVER (PARTITION BY category_id ORDER BY month) AS previous_month
    FROM monthly
)
SELECT category_id, month, units, revenue, revenue_rank,
       CASE WHEN previous_month = (month - interval '1 month')::date
            THEN (revenue - previous_revenue) * 100 / NULLIF(previous_revenue, 0) END AS change_percent
FROM changes ORDER BY month, revenue_rank, category_id
"""

# One pass over the order lines, joined to the orders (for the day and the cancellation rule) and to the product (for its
# category, which the normalised schema keeps only there), grouped by category and month.
CATEGORY_IDIOMATIC = (
    """
WITH monthly AS (
    SELECT p.category_id, date_trunc('month', o.placed_at AT TIME ZONE 'Asia/Singapore')::date AS month,
           sum(l.quantity)::bigint AS units, sum(l.quantity * l.unit_price) AS revenue
    FROM orders_orderline l JOIN orders_order o ON o.id = l.order_id
    JOIN catalogue_product p ON p.id = l.product_id
    WHERE o.placed_at < %(end)s::timestamptz
      AND (o.status <> 'cancelled' OR o.cancelled_at >= %(end)s::timestamptz)
    GROUP BY p.category_id, 2"""
    + CATEGORY_TAIL
)

# The maintained product-day summary rolled up by category and month.
CATEGORY_SUMMARY = (
    """
WITH monthly AS (
    SELECT p.category_id, date_trunc('month', d.day)::date AS month, sum(d.units)::bigint AS units,
           sum(d.revenue) AS revenue
    FROM daily_product_sales d JOIN catalogue_product p ON p.id = d.product_id
    GROUP BY p.category_id, 2"""
    + CATEGORY_TAIL
)

STOCK_SELECT = """
SELECT p.id AS product_id, COALESCE(demand.units_28, 0)::numeric / 28 AS daily_demand,
       p.stock::numeric * 28 / NULLIF(demand.units_28, 0) AS days_cover,
       (COALESCE(demand.units_28, 0) > 0
        AND p.stock::numeric * 28 < p.lead_time_days::numeric * COALESCE(demand.units_28, 0)) AS replenish
FROM purchasable_product p
LEFT JOIN ({sales}) demand ON demand.product_id = p.id
ORDER BY p.id
"""

# Units sold in the last 28 Singapore days, straight from the order lines.
STOCK_IDIOMATIC = STOCK_SELECT.format(
    sales="""
    SELECT l.product_id, sum(l.quantity) AS units_28
    FROM orders_orderline l JOIN orders_order o ON o.id = l.order_id
    WHERE o.placed_at >= %(start)s::timestamptz AND o.placed_at < %(end)s::timestamptz
      AND (o.status <> 'cancelled' OR o.cancelled_at >= %(end)s::timestamptz)
    GROUP BY l.product_id"""
)

# The same, from the maintained product-day summary.
STOCK_SUMMARY = STOCK_SELECT.format(
    sales="""
    SELECT product_id, sum(units) AS units_28 FROM daily_product_sales
    WHERE day BETWEEN %(as_of)s::date - 27 AND %(as_of)s::date GROUP BY product_id"""
)

# Delivered orders by delay bucket with the mean of the per-order mean visible score. The order table alone holds what the
# buckets need; the application's version also joins checkout, seller and customer and computes a distance.
DELAY_IDIOMATIC = """
WITH delays AS (
    SELECT o.id AS order_id,
           CASE WHEN d.delay_days < -7 THEN 'early_over_7'
                WHEN d.delay_days <= 0 THEN 'early_up_to_7_or_on_time'
                WHEN d.delay_days <= 7 THEN 'late_1_to_7'
                WHEN d.delay_days <= 14 THEN 'late_8_to_14' ELSE 'late_over_14' END AS bucket
    FROM orders_order o
    CROSS JOIN LATERAL (SELECT (o.delivered_at AT TIME ZONE 'Asia/Singapore')::date -
                               (o.estimated_delivery AT TIME ZONE 'Asia/Singapore')::date AS delay_days) d
    WHERE o.status = 'delivered' AND o.placed_at < %(end)s::timestamptz AND o.delivered_at < %(end)s::timestamptz
), scores AS (
    SELECT order_id, avg(score::numeric) AS score FROM reviews
    WHERE NOT taken_down AND answered_at < %(end)s::timestamptz GROUP BY order_id
)
SELECT d.bucket, count(*) AS orders, count(s.score) AS reviewed_orders, avg(s.score) AS average_score
FROM delays d LEFT JOIN scores s ON s.order_id = d.order_id GROUP BY d.bucket ORDER BY d.bucket
"""
