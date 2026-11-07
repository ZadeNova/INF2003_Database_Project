"""Named analytical SQL. Values are bound; B2 can reuse these definitions without copying formulas.

BAYESIAN_RATING is the SQL counterpart over the benchmark's review copy. There is deliberately no SQL
reviews table in the application. Its execution tests supply a statement-local CTE, never a stored copy.
"""

STOCK_PLANNING = """
SELECT p.id AS product_id, p.name, p.stock, p.lead_time_days, p.seller_id, c.name_en AS category,
       s.shop_name, demand.daily_demand,
       p.stock::numeric * 28 / NULLIF(demand.units_28, 0) AS days_cover,
       (demand.units_28 > 0 AND p.stock::numeric * 28 < p.lead_time_days::numeric * demand.units_28) AS replenish
FROM purchasable_product p
JOIN catalogue_category c ON c.id = p.category_id
JOIN accounts_seller s ON s.id = p.seller_id
CROSS JOIN LATERAL (
    SELECT daily_demand, units_28 FROM (
        SELECT days.day::date AS day,
               avg(COALESCE(sales.units, 0)::numeric) OVER (
                   ORDER BY days.day ROWS BETWEEN 27 PRECEDING AND CURRENT ROW) AS daily_demand,
               sum(COALESCE(sales.units, 0)) OVER (
                   ORDER BY days.day ROWS BETWEEN 27 PRECEDING AND CURRENT ROW) AS units_28
        FROM generate_series(%(as_of)s::date - 27, %(as_of)s::date, interval '1 day') days(day)
        LEFT JOIN daily_product_sales sales ON sales.product_id = p.id AND sales.day = days.day::date
    ) rolling WHERE day = %(as_of)s::date
) demand
WHERE (%(category)s::bigint IS NULL OR p.category_id = %(category)s::bigint)
  AND (%(seller)s::bigint IS NULL OR p.seller_id = %(seller)s::bigint)
ORDER BY replenish DESC, days_cover ASC NULLS LAST, p.id
"""

# What the dashboard runs: the same result as STOCK_PLANNING from one grouped sum over the last 28 days, instead of a
# 28-row window per product (an order of magnitude slower on the full data). STOCK_PLANNING stays for benchmark B2.
STOCK_PLANNING_FAST = """
SELECT p.id AS product_id, p.name, p.stock, p.lead_time_days, p.seller_id, c.name_en AS category,
       s.shop_name, COALESCE(demand.units_28, 0)::numeric / 28 AS daily_demand,
       p.stock::numeric * 28 / NULLIF(demand.units_28, 0) AS days_cover,
       (COALESCE(demand.units_28, 0) > 0
        AND p.stock::numeric * 28 < p.lead_time_days::numeric * COALESCE(demand.units_28, 0)) AS replenish
FROM purchasable_product p
JOIN catalogue_category c ON c.id = p.category_id
JOIN accounts_seller s ON s.id = p.seller_id
LEFT JOIN (
    SELECT product_id, sum(units) AS units_28 FROM daily_product_sales
    WHERE day BETWEEN %(as_of)s::date - 27 AND %(as_of)s::date GROUP BY product_id
) demand ON demand.product_id = p.id
WHERE (%(category)s::bigint IS NULL OR p.category_id = %(category)s::bigint)
  AND (%(seller)s::bigint IS NULL OR p.seller_id = %(seller)s::bigint)
ORDER BY replenish DESC, days_cover ASC NULLS LAST, p.id
"""

CATEGORY_PERFORMANCE = """
WITH monthly AS (
    SELECT p.category_id, c.name_en AS category, date_trunc('month', d.day)::date AS month,
           sum(d.units)::bigint AS units, sum(d.revenue) AS revenue
    FROM daily_product_sales d JOIN catalogue_product p ON p.id = d.product_id
    JOIN catalogue_category c ON c.id = p.category_id
    WHERE d.day <= %(as_of)s::date
    GROUP BY p.category_id, c.name_en, date_trunc('month', d.day)::date
), changes AS (
    SELECT *, rank() OVER (PARTITION BY month ORDER BY revenue DESC) AS revenue_rank,
           lag(revenue) OVER (PARTITION BY category_id ORDER BY month) AS previous_revenue,
           lag(month) OVER (PARTITION BY category_id ORDER BY month) AS previous_month
    FROM monthly
)
SELECT *, CASE WHEN previous_month = (month - interval '1 month')::date
               THEN (revenue - previous_revenue) * 100 / NULLIF(previous_revenue, 0) END AS change_percent
FROM changes ORDER BY month DESC, revenue_rank, category_id
"""

BAYESIAN_RATING = """
SELECT CASE WHEN grouping(p.id) = 0 THEN 'product' ELSE 'seller' END AS entity,
       CASE WHEN grouping(p.id) = 0 THEN p.id ELSE p.seller_id END AS entity_id,
       count(r.score) AS review_count, COALESCE(sum(r.score), 0) AS score_sum,
       COALESCE((%(C)s::numeric * %(m)s::numeric + COALESCE(sum(r.score), 0)) /
           NULLIF(%(C)s::numeric + count(r.score), 0), 0) AS bayesian
FROM catalogue_product p LEFT JOIN reviews r ON r.product_id = p.id
    AND NOT COALESCE(r.taken_down, false) AND r.answered_at < %(end)s::timestamptz
GROUP BY GROUPING SETS ((p.id), (p.seller_id))
ORDER BY entity, entity_id
"""

DELAY_BUCKETS = """
WITH deliveries AS (
    SELECT o.id AS order_id, o.checkout_id, o.seller_id,
           (o.delivered_at AT TIME ZONE 'Asia/Singapore')::date -
               (o.estimated_delivery AT TIME ZONE 'Asia/Singapore')::date AS delay_days,
           s.shop_name,
           CASE WHEN sg.zip_prefix IS NULL OR cg.zip_prefix IS NULL THEN NULL ELSE
               6371 * 2 * asin(sqrt(least(1.0, greatest(0.0,
                   power(sin(radians((cg.latitude - sg.latitude)::double precision) / 2), 2) +
                   cos(radians(sg.latitude::double precision)) * cos(radians(cg.latitude::double precision)) *
                   power(sin(radians((cg.longitude - sg.longitude)::double precision) / 2), 2)))))
           END AS distance_km
    FROM orders_order o JOIN orders_checkout ch ON ch.id = o.checkout_id
    JOIN accounts_seller s ON s.id = o.seller_id
    JOIN accounts_customerprofile cp ON cp.user_id = ch.customer_id
    LEFT JOIN accounts_geolocation sg ON sg.zip_prefix = s.zip_prefix
    LEFT JOIN accounts_geolocation cg ON cg.zip_prefix = cp.zip_prefix
    WHERE o.status = 'delivered' AND o.placed_at < %(end)s::timestamptz
      AND o.delivered_at < %(end)s::timestamptz
)
SELECT *, CASE WHEN delay_days < -7 THEN 'early_over_7'
               WHEN delay_days <= 0 THEN 'early_up_to_7_or_on_time'
               WHEN delay_days <= 7 THEN 'late_1_to_7'
               WHEN delay_days <= 14 THEN 'late_8_to_14' ELSE 'late_over_14' END AS bucket
FROM deliveries ORDER BY order_id
"""
