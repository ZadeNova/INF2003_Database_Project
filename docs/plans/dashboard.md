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
| Materialized view | `daily_product_sales` (product, day, units, revenue) over non-cancelled orders, with a unique index so it can be refreshed `CONCURRENTLY`. Refreshed after import and by an operator button |
| Refresh privilege (decision b) | `REFRESH MATERIALIZED VIEW` needs the owner, so a `SECURITY DEFINER` function owned by the owner role does the refresh, and the runtime role gets `EXECUTE` on that function only |
| Stock planning | Per active product: 28-day moving-average daily demand (window function over the view), days of cover = stock / demand, and a replenishment flag when cover is shorter than the lead time. Sorted by urgency, filterable by category and seller |
| Category performance | Revenue and units per category per month with `RANK()` and month-on-month change with `LAG()`, as a table and a Chart.js chart |
| Delivery delay against score (T6b) | Score by delay bucket (early, on time, late by 0 to 7, 7 to 14, more than 14 days): delay from PostgreSQL, scores from a MongoDB pipeline, joined in Python on order line id. Per seller: late-delivery share and average score, flagging sellers above a threshold as "at risk". Seller-to-customer distance from the geolocation centre points (haversine in SQL) shown beside the delay |
| Poor reviews | Products with an average score of 2 or less and at least 5 reviews, from a MongoDB aggregation pipeline |
| Page | Operator console "Dashboard" with the panels above; each panel states its as-of date and data sources |

**Out of scope:** the same aggregates as MongoDB pipelines for comparison (`benchmark`, B2); a seller-scoped dashboard
(`seller-rls`, Tier 2); caching (`redis`, Tier 2).

**Tests:** on the fixture, every panel's numbers match a direct calculation in the test; the moving average ignores
cancelled orders; the replenishment flag flips at the lead-time boundary; the runtime role can call the refresh function
but cannot run `REFRESH` directly; the delay buckets reproduce the profile's pattern on the full data (a slow test,
marked so it can be skipped locally).

**Exit check**
1. As the operator, open the dashboard: every panel shows data as of 30 October 2026; the at-risk seller list and the
   delay table match `profile_olist.py` (bucket averages within 0.05).
2. Restock a flagged product; refresh; its flag clears.
3. `EXPLAIN (ANALYZE, BUFFERS)` of the stock-planning query uses the view's index; the plan goes into the report notes.
4. The full test suite passes in Docker.

## Decisions (all approved 21 October 2026)

| ID | Proposal | Why |
|---|---|---|
| a | Pin the dashboard's as-of date to the end of the imported data (30 October 2026). **The implementer re-confirms this with the plan owner before starting** (requested 21 October) | Recording happens in late November; a "last 28 days" window would otherwise cover a month with almost no data |
| b | Refresh through a `SECURITY DEFINER` function | Keeps the runtime role free of ownership rights; a DBMS feature worth naming |
| c | Cross-store join in Python on order line id, not by copying scores into PostgreSQL | Keeps "each value in one store"; the join cost is measured for the report |

## Review notes

(empty until review)
