# dashboard: Stock planning, demand forecast, category performance, delivery delay against review score

status: approved
plan owner: Erfan · implementer: Chee Long · reviewer: a fresh session · estimate: 2 to 3 days · phase 3A (9 to 13
November) · depends on: `olist-import`, `checkout`, `accounts` (operator console)

**Assumes:** the `olist-import` schema (orders with status and dates, lines, products with stock and lead time, sellers
with zip prefix, geolocation); MongoDB `reviews` with score, order line and seller ids. The old baseline's reporting
queries (git history before `olist-import`) are the starting point, not code to copy.

## Contract

**Before starting:** ask the plan owner (Erfan) to re-confirm decision a, the as-of date.

**Goal.** The operator sees, for the whole platform, which products will run out before they can be restocked, which
categories perform best, and which sellers are at risk of poor reviews because they deliver late.

**In scope**

| Area | Deliverable |
|---|---|
| As-of date (decision a) | Every panel works "as of" a date: by default the last day of imported data (30 October 2026), set in one setting. Orders placed in the demo still appear in order lists; the dashboard's history window does not silently go empty after the data ends |
| Materialized view | `daily_product_sales` (product, day, units, revenue) over non-cancelled orders, with a unique index so it can be refreshed `CONCURRENTLY`. Refreshed as the last step of `import_olist` (this plan appends that step; migrate alone leaves it empty) and by an operator button |
| Refresh privilege (decision b) | `REFRESH MATERIALIZED VIEW` needs the owner, so a `SECURITY DEFINER` function owned by the owner role does the refresh, with `SET search_path = public, pg_temp`; the migration `REVOKE`s `EXECUTE` from `PUBLIC` (functions are executable by everyone by default) and grants it to the runtime role only |
| Stock planning | Per product in the `purchasable_product` view: 28-day moving-average daily demand (window function over the view), days of cover = stock / demand, and a replenishment flag when cover is shorter than the lead time. Sorted by urgency, filterable by category and seller |
| Category performance | Revenue and units per category per month with `RANK()` and month-on-month change with `LAG()`, as a table and a Chart.js chart |
| Delivery delay against score (T6b) | Score by delay bucket, half-open so none overlap: early by more than 7 days, early by up to 7 days or on time, late by up to 7, 7 to 14 and more than 14 days. Delay from PostgreSQL per order; one score per order from a MongoDB pipeline (copies flagged `from_order_review` skipped), joined in Python on order id. Per seller: late-delivery share and average score, flagging sellers above a threshold as "at risk". Seller-to-customer distance from the geolocation centre points (haversine in SQL) shown beside the delay |
| Poor reviews | Products with an average score of 2 or less and at least 5 reviews, from a MongoDB aggregation pipeline |
| Page | Operator console "Dashboard" with the panels above; each panel states its as-of date and data sources |

**Out of scope:** the same aggregates as MongoDB pipelines for comparison (`benchmark`, B2); a seller-scoped dashboard
(`seller-rls`, Tier 2); caching (`redis`, Tier 2).

**Tests:** on the fixture, with its own as-of date, every panel's numbers match a direct calculation in the test; injection negatives on every raw-SQL filter (category, seller, dates); the moving average ignores
cancelled orders; the replenishment flag flips at the lead-time boundary; the runtime role can call the refresh function
but cannot run `REFRESH` directly; the delay buckets reproduce the profile's pattern on the full data (a slow test,
marked so it can be skipped locally).

**Exit check**
1. As the operator, open the dashboard: every panel shows data as of 30 October 2026; the at-risk seller list and the
   delay table match `profile_olist.py` (bucket averages within 0.05).
2. As the demo seller, restock the flagged product `seed_demo` guarantees; refresh; its flag clears.
3. `EXPLAIN (ANALYZE, BUFFERS)` of the stock-planning query uses the view's index; the plan goes into the report notes.
4. The full test suite passes in Docker.

## Decisions (all approved 21 October 2026)

| ID | Proposal | Why |
|---|---|---|
| a | Pin the dashboard's as-of date to the end of the imported data (30 October 2026). **The implementer re-confirms this with the plan owner before starting** (requested 21 October) | Recording happens in late November; a "last 28 days" window would otherwise cover a month with almost no data |
| b | Refresh through a `SECURITY DEFINER` function | Keeps the runtime role free of ownership rights; a DBMS feature worth naming |
| c | Cross-store join in Python on order id, not by copying scores into PostgreSQL | Keeps "each value in one store"; the join cost is measured for the report |

## Review notes

21 October 2026, cross-plan review (fresh session); findings applied: refresh as the import's last step; `REVOKE EXECUTE … FROM PUBLIC` and a fixed
`search_path` on the definer function; non-overlapping delay buckets joined per order; injection negatives; a fixture
as-of date; the purchasable view; the demo product from `seed_demo`.
