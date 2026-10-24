# dashboard: Stock planning, demand forecast, category performance, delivery delay against review score

status: in-progress
plan owner: Erfan · implementer: Chee Long · reviewer: a fresh session · estimate: 2 to 3 days · phase 3A (9 to 13
November) · depends on: `olist-import`, `checkout`, `accounts` (operator console)

**Assumes:** the `olist-import` schema (orders with status and dates, lines, products with stock and lead time, sellers
with zip prefix, geolocation); MongoDB `reviews` with score, order line and seller ids. The old baseline's reporting
queries (git history before `olist-import`) are the starting point, not code to copy.

## Contract

**Amendment a (confirmed 24 October 2026 by Chee Long):** derive the as-of date from the latest imported order placed_at, excluding demo orders. This replaces the earlier request to re-confirm the fixed date.

**Goal.** The operator sees, for the whole platform, which products will run out before they can be restocked, which
categories perform best, and which sellers are at risk of poor reviews because they deliver late.

**In scope**

| Area | Deliverable |
|---|---|
| As-of date (decision a) | Every panel works "as of" the local date of the latest imported order placed_at, derived centrally from orders whose checkout has an Olist source ID; demo orders cannot move it. Events after that date are excluded. Orders placed in the demo still appear in order lists; the dashboard's history window does not silently go empty after the data ends |
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
1. As the operator, open the dashboard: every panel shows data as of the latest imported order date (the fixture uses its own date); the at-risk seller list and the
   delay table match `profile_olist.py` (bucket averages within 0.05).
2. As the demo seller, restock the flagged product `seed_demo` guarantees; refresh; its flag clears.
3. `EXPLAIN (ANALYZE, BUFFERS)` of the stock-planning query uses the view's index; the plan goes into the report notes.
4. The full test suite passes in Docker.

## Decisions (all approved 21 October 2026)

| ID | Proposal | Why |
|---|---|---|
| a | Amendment a, confirmed 24 October 2026 by Chee Long: derive the dashboard's as-of date from the latest imported order placed_at, not demo orders; exclude later events | Recording happens in late November; a "last 28 days" window would otherwise cover a month with almost no data |
| b | Refresh through a `SECURITY DEFINER` function | Keeps the runtime role free of ownership rights; a DBMS feature worth naming |
| c | Cross-store join in Python on order id, not by copying scores into PostgreSQL | Keeps "each value in one store"; the join cost is measured for the report |

## Review notes

21 October 2026, cross-plan review (fresh session); findings applied: refresh as the import's last step; `REVOKE EXECUTE … FROM PUBLIC` and a fixed
`search_path` on the definer function; non-overlapping delay buckets joined per order; injection negatives; a fixture
as-of date; the purchasable view; the demo product from `seed_demo`.


24 October 2026 — Amendment a (Chee Long): latest imported placed_at supplies the reporting date centrally; demo orders do not move it. The shifted dataset legitimately contains deliveries after that date; those deliveries and later reviews are excluded from the panels, without rewriting the import. Exit check 1 now uses the imported date, and tests use the fixture's own date.


24 October 2026 — Implementation notes (Codex; reviewer: pending (Claude Code)). Built the central imported-date
function, daily_product_sales materialized view and unique index, restricted first/concurrent refresh, importer final
refresh, zero-filled 28-day stock windows and exact replenishment threshold, category RANK/LAG table and local Chart.js
chart, delivery buckets with SQL zip-centre distance and Python review join, seller risk and MongoDB poor-review panels.
Named STOCK_PLANNING, CATEGORY_PERFORMANCE, BAYESIAN_RATING and DELAY_BUCKETS SQL remain importable. The Bayesian SQL
counterpart expects a future isolated benchmark review relation; tests provide statement-local CTE rows, and no SQL
review table or benchmark implementation was added. Its product/seller scores match hand calculations.

Exit check 1 passed on the full local data: demo-operator opened every dated/source-labelled panel; bucket averages
match the profile within tolerance and every seller risk row matches an independent calculation. Fixture panel
numbers, future order/delivery/review/cancellation exclusions and the fixed imported anchor passed their direct
calculation checks. Exit check 2 passed through the demo seller's form and operator refresh; replenishment cleared
and original stock was restored. Exit check 3 passed: EXPLAIN (ANALYZE, BUFFERS) on the named stock query with the demo
seller filter uses daily_product_sales_product_day. The unaltered plan is in .cache/phase3a/dashboard-stock-plan.json
for report notes; generated comparisons are in dashboard-exit.log and dashboard-sellers-exit.log. Exit check 4 passed:
built migrate and ran the full Docker suite, including the marked full-data profile check; exact output is saved in
.cache/phase3a/dashboard-full-suite.log. Migration drift, Django system, host docs/packaging and scripts/check_docs.py
checks passed. The existing container-only Git-index skips are visible; host equivalents passed. No contract omissions
or deviations beyond approved amendment a. The chosen risk threshold is documented in docs/DECISIONS.md. Fresh Claude
Code review and visual inspection remain pending. No push, PR or merge was performed.

24 October 2026 — Integration check on activity/events: responsive browser inspection found Chart.js default blue bars in the otherwise working dashboard. The final stacked branch disables automatic chart colours and seeds the design tokens before construction. The 375px chart and table were inspected in both themes with no document overflow or console errors. This small visual integration fix is carried by activity/events; no dashboard data or query behaviour changed.

24 October 2026 — Review (Claude Code; session that wrote the Codex brief, not a fresh session), finding dashboard R1.
The risk list included sellers with too little delivery history. The fix requires at least ten delivered orders within
the as-of window, so a small sample cannot dominate the risk list. Eligible sellers sort at risk first, then by late
share descending and seller ID; the panel states the minimum and the number excluded. Tests were added before code:
test_seller_risk_minimum_cutoff_ordering_and_excluded_panel_note proves that nine late deliveries are excluded, ten
deliveries with three late are flagged, a future delivery cannot qualify a seller, and ordering/count/note match an
independent calculation. The existing direct fixture comparison now checks eligibility and ordering too.
Rebuilt migrate and ran all of test_dashboard.py successfully, including its full-data profile comparison; unaltered
output is .cache/phase3a-review/dashboard-R1-tests.log. The new regression failed on the previous implementation.
