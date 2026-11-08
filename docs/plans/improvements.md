# improvements: Prioritised backlog from the full-stack review

status: draft
plan owner: Erfan · implementers: per item, once settled · reviewer: Opus 5.5 session, on a large change or when Erfan asks · phase 5
([PLAN.md section 13](../../PLAN.md#13-phases)) · depends on: the frozen Tier 1 application; `benchmark` close-out

**Source.** Two reviews. On 2 November 2026: a code read and a live run of a fresh install (items 1–48). On 8 November
2026: an Opus 5.5 run of the full suite plus probe tests against the real databases (items 49–68). How to reproduce is
under Review notes.

## Contract

**Goal.** One ranked list of what to fix, measure or write before submission, judged against the
[RUBRICS.md](../../RUBRICS.md#5-assessment-criteria) Excellent bands, so the remaining weeks go where the marks are.

**How an item is settled.** Erfan is the sole approver (Chee Long is away). Erfan settles items a batch at a time,
easiest first: accept, change or drop, recorded under Decisions with the date. An item marked **approval** touches the
frozen application, a closed benchmark or an owner decision; it is settled the same way, then implemented on the
current branch under the workflow in [CLAUDE.md](../../CLAUDE.md) (a plan amendment for `benchmark`). Every fix gets a
regression test against the real databases; docs follow each change.

**Reviews.** An Opus 5.5 review after the integrity and dashboard batch (3), and a full codebase review after the
code-quality pass (7), before the freeze.

**Rules kept.** No hand-written test counts, timings, row counts or benchmark tables in the report or docs: link to
`benchmarks/results/` or regenerate (AGENTS.md, Documentation). Figures quoted by a review are re-measured when the
item is fixed.

**Freeze.** Proposed code freeze for filming: **15 November** (Erfan to confirm). Footage is due 18 November
([deliverables](deliverables.md) decision c), so nothing changed after the 15th appears in the video. After the freeze,
only bug fixes go in.

**Legend.** Effort: S (under 2 hours), M (half a day to a day), L (several days). ★ = suitable for Erfan to own.
[confirmed] = reproduced, [measured] = full-data numbers, [code] = read from the code only.

## Batches

| Batch | Items | Theme | Status |
|---|---|---|---|
| 1 | #59, #50, #61, #60, #58, #56, #2 | Tiny fixes | done 8 Nov (touched test modules pass; full suite after batch 3) |
| 2 | #53, #51, #54, #69 | Small fixes with a migration or shared helper | done 8 Nov (full suite run; four existing audit-count tests updated for the new creation row and rerun green) |
| 3 | #49, #55, #52 with #10, #57 | Integrity and the dashboard; Opus review checkpoint after | done 8 Nov (full suite green; dashboard timings re-measured on full data) |
| 4 | #11, #19, #21, #7, #18, #34, #8, #16 | UI and MongoDB claims | open |
| 5 | #25, #12 (Redis) | Redis, its own short plan first ([redis](redis.md), drafted 8 Nov) | done 8 Nov (two Opus reviews, two fix rounds, full suite green); the measurement scripts are part of Batch 6 |
| 6 | #10 step 2 (first, [plan](dashboard_summaries.md)), #5, #13, #17 | Benchmark amendment, designated machine | in progress: #10 step 2 done 9 Nov (one Opus review, one fix round, full suite green); #5, #13, #17 and the amendment tooling open |
| 6b | #71 | Full-text search on review text, both engines; only after batches 1–6 are green | open |
| 7 | #27, #33, #63, #73 | Code-quality pass and test-suite review, then the full codebase review | open |
| 8 | #48 (RLS); optional #62, #42, #20 | Row-level security, settled last | open |
| 8b | #72 | Synthetic scale runs for B1, B4, B5 and B7 (parked): code-side work, only after batches 1–8, before any report, slides or video work | parked |
| 9 | #38, #47, #70, #46, #39, #15, #41, #6, #43, #44, #26, #40, #1, #14, #3 | Demo, evidence and deliverables, alongside and after the freeze | open |
| Disclose | #29–#32, #35, #36, #64–#68 | One line each in the report's limitations | open |

## Batch 1: tiny fixes

| # | Area | Finding | Fix | Effort | Status |
|---|---|---|---|---|---|
| 59 | Search | [confirmed] A search of only spaces counts as a search and shows the capped results with the "closest matches only" notice: `searching` is decided from the raw text before Django strips it | Decide from the cleaned value | S | done |
| 50 | Search | [confirmed] Filters alone (`min_price`, `max_price`, `sort`, `rating`) are ignored on the shop home page because `searching = bool(q or category)` in [catalogue/views.py](../../src/catalogue/views.py) | Treat any filter as a search | S | done |
| 61 | Reviews | [code] A customer who edits a taken-down review is told "Review saved", but it stays hidden | Say so in the message | S | done |
| 60 | Dashboard | [measured] The latest month covers part of October but is compared with all of September, which biases the change downwards | Option A chosen: label the incomplete month "month to date" and show no change percentage for it. Done in `dashboard/services.py` and the template, not in the SQL, because benchmark B2a and its golden output run the same query | S | done |
| 58 | MongoDB | [code] `record_event` runs `listCollections` before every insert, an extra round trip on every page view and search ([activity/services.py](../../src/activity/services.py)) | Remember a successful check once per process | S | done |
| 56 | MongoDB | [measured] The operator review list scans and sorts every review in memory on each page; no index matches the newest-first sort | Add one new index `{answered_at:-1, olist_review_id:-1, order_line_id:-1}`; the tie-break keys on the product and seller indexes are deferred | S | done |
| 2 | Demo | Demo story step 1 ("hose nozle") returned no products on full data. Typo tolerance itself works | Use "garden tols", which returns results; update [OVERVIEW.md](../OVERVIEW.md#3-the-demo-story) and the script ★ | S | done (script pending in #70) |

## Batch 2: small fixes with a migration or shared helper

| # | Area | Finding | Fix | Effort | Status |
|---|---|---|---|---|---|
| 53 | Routing | [confirmed] HTTP 500 on `/operator/reviews/<20-digit id>/` (BSON integers are 8 bytes). The bigint bounds check is hand-copied into six places and URLs use unbounded `<int:>` | One `bigint` path converter and one `BIGINT_MAX` constant ([config/ids.py](../../src/config/ids.py)) used by all 20 id routes and the six hand-written checks | S | done |
| 51 | Integrity | [confirmed] A customer cannot cancel when stock is near the form maximum: the seller form allows stock up to 2³¹−1, the cancellation restock overflows the integer column, HTTP 500, no refund | Form maximum 99,999 and a database `CHECK` of 1,000,000 (`product_stock_capped`, catalogue 0003). The gap leaves room for restocks, at most 999 per cart line | S | done |
| 54 | Audit | [confirmed] Creating a product leaves no audit row: the trigger is AFTER UPDATE only, so a first price and stock are never recorded, against the plan's claim that every price and stock change is audited | An AFTER INSERT trigger writes a `product.create` audit row (catalogue 0004); [DATA_MODEL.md](../DATA_MODEL.md) updated | S | done |
| 69 | Demo | The demo story (steps 2 and 3 of [OVERVIEW.md](../OVERVIEW.md#3-the-demo-story)) has each of three sellers ship their own order, but the Opus 5.5 review reports that only one seller has a login (not yet verified; check `seed_demo` first) ★ | `seed_demo` now promotes `demo-seller`, `demo-seller-2` and `demo-seller-3`; each has two buyable products, relisted with a label only if missing. The demo passwords are now fixed and documented in the README (see Decisions) | S | done |

## Batch 3: integrity and the dashboard

| # | Area | Finding | Fix | Effort | Status |
|---|---|---|---|---|---|
| 49 | Concurrency | [confirmed] A seller's stale edit form undoes sales: open the form at stock 8, 3 units sell, save a description fix, stock returns to 8. This is the lost-update anomaly B6 measures, inside the app ([catalogue/services.py](../../src/catalogue/services.py) copies every posted field) | Option B (settled): the edit form carries the stock and price it was opened with. Under the existing row lock, a field the seller did not change keeps its live database value, so concurrent sales survive; a field the seller changed is applied only if nobody else changed it meanwhile, otherwise the save is refused with the current value shown. A save without the hidden values behaves as today. Built as settled; the hidden fields render without a label block in the shared form partial. Full suite | S–M | done |
| 55 | Integrity | [confirmed] The runtime role can rewrite `paid_at`, `shipped_at`, `delivered_at` and `estimated_delivery` with no audit row; the status trigger guards only `status`, and the delay analysis is computed from these columns | Settled: a second BEFORE UPDATE trigger on `orders_order` refuses any change to `placed_at`, `paid_at`, `shipped_at`, `delivered_at`, `cancelled_at` and `estimated_delivery` unless the status changes, and then only the destination timestamp the existing trigger sets may move. The application never writes these columns, so only a few test lines change (they get a helper that disables the guard only inside its own transaction). Migration, [DATA_MODEL.md](../DATA_MODEL.md) paragraph, full suite. Built as settled (migration `orders` 0004, `test_order_timestamps.py`). Also a line for the #38 demo | S–M | done |
| 52 | Analytics | [measured] The delivery-delay analysis silently drops every multi-line order, because it excludes copied reviews ([dashboard/services.py](../../src/dashboard/services.py)). Copies in one order share a score and the query already groups by order, so the filter buys nothing | Settled: remove the filter (it adds a few thousand reviewed orders and moves average scores by at most 0.05; the finding is unchanged), then re-check against `verify_olist` and any figure quoted in the report. Done in the same change as #10 step 1. Benchmark B2's own delay-analysis queries still exclude copied reviews, so align or document that in the #5 amendment | S | done |
| 10 | Backend | [measured] The operator dashboard takes 3.3–3.6 s on full data: [delivery_analysis](../../src/dashboard/services.py) loads every delivered order and every order score into Python on each request (about 2.1 s), and the stock panel is paged in Python | **Step 1 (settled, first):** change the MongoDB score aggregation to an integer `$sum` of scores and a count per order, divided in Python, instead of `$avg` of `$toDecimal` (the averages are identical; it removes most of the Decimal128 conversion and is faster on full data), drop the copy filter (#52), and trim the Python work; no cache and no new infrastructure. The per-order `{sum, count}` shape is also what step 2 would `$merge`. **Step 2 (design, 8 Nov, short plan before building; NoSQL order #2):** a PostgreSQL materialized view of per-order delivery delays beside a MongoDB `$merge` on-demand materialized view of per-order review scores, both refreshed by "Refresh sales history"; the Python join then reads two precomputed sets. The `$merge` output is derived from MongoDB's own reviews, so nothing is copied between stores. The same feature on both engines gives presentation part iii a like-for-like comparison. Settle in the plan: refresh after a review takedown, or accept staleness until the next refresh. Fixes #52 in the same change; #57 covers the stock panel; a Redis cache (Batch 5) only on top | M | step 1 done; step 2 done 9 Nov ([plan](dashboard_summaries.md); the MongoDB summary is rebuilt with `$out` rather than `$merge`; one Opus 5.5 review and one fix round). The before and after figures are the output of [time_dashboard_history.py](../../scripts/time_dashboard_history.py), not typed here |
| 57 | PostgreSQL | [measured] The stock-planning query is far slower than a plain 28-day `GROUP BY` and returns the same result; `daily_demand` is always units over 28 days, so the per-product window adds nothing. Benchmark B2 imports this query | Option i (settled): the app uses a new plain 28-day `GROUP BY` query; the window-function query keeps its current name for benchmark B2 until the Batch 6 amendment decides what B2 runs. Built as `STOCK_PLANNING_FAST`; a test proves it returns the same rows as the window query | S | done |

**Checkpoint:** an Opus 5.5 review of everything changed in batches 1–3.

## Batch 4: UI and MongoDB claims

**Settled 8 Nov: product names, review text and photos (Erfan).** Names were an adjective, the category label and a
hexadecimal suffix, so about 34,000 products shared only a few hundred distinct names. Chosen: **B-lite**, regenerate the names for
all 74 categories from per-category noun lists tied to each product's drawn attributes (thousands of distinct names; the
attributes, stock, lead times and every other field are byte-identical), show the old hexadecimal as a muted SKU line, then
photograph a showcase of 30 products (2 in each of the 15 main categories; 24 of them featured on the home page, so a
filter by any main category opens on pictures). Review text stays as imported (machine-translated, labelled); showcase
products are picked for readable reviews. The three demo shops get readable generated names. The benchmark is rerun on
Erfan's PC after Batch 6, so the changed clean data costs no extra rerun. The photos (#16) are delegated to a teammate.

| # | Area | Item | Why it matters | Fix | Effort | Status |
|---|---|---|---|---|---|---|
| 11 | MongoDB | `latest_reviews` is maintained on every review write ([reviews/services.py](../../src/reviews/services.py)) but never read; the product page queries `reviews` directly | The subset pattern and "a product page is one read" claim are not true | Settled 8 Nov, option A: the product page opens on the specification's `latest_reviews` (one MongoDB read; a test fails if the reviews collection is queried), and `?all=1` pages the full list from `reviews` ([queries.py](../../src/reviews/queries.py)) | S–M | done |
| 19 | UI | Review lists are mostly score-only rows, so product pages look empty | Looks empty on camera | Settled 8 Nov, option 1: the public product page shows written reviews and collapses bare star ratings into one line ("Plus 3 recent star ratings without a comment"; in the full list, the count of ratings without a comment). Operator and seller lists keep every row | S | done |
| 21 | UI | Seller insights is sorted by product id; the dashboard filter asks for a typed seller number and shows Django's empty label | Both pages appear in the demo story | Settled 8 Nov: Seller Insights sorts by views, then conversion; the dashboard category filter reads "All categories"; the typed seller number is now a "Shop" dropdown of the 50 approved shops with the most products (any other value is refused) | S | done |
| 7 | UI | Product and shop names look like identifiers (a hexadecimal suffix on every name) | Visible on every screen of the video | Settled 8 Nov: B-lite. Names regenerated from noun lists (generator, template and fixture, byte-for-byte reproduction checked), SKU line on cards, the detail page and the seller list; the showcase list and the demo shop names follow | M-L | names, shop names and the showcase loader done; photos and new products are the teammate's |
| 18 | UI | Generated-content labels appear three times per card; descriptions read like placeholder text | Clutter on every card | Settled 8 Nov: a card shows one line ("Generated name, shop and stock.") and no separate shop tag; the detail page keeps one footnote that now names the shop name; the tag stays where nothing else covers it (AGENTS.md rule 9). The description sentence is data and stays | S | done |
| 34 | Data | Some category names read oddly ("Home Appliances 2", "Construction Tools Tools") | Looks careless | Settled 8 Nov: a display-name map in [category_names.py](../../src/catalogue/category_names.py) (20 entries) shown on every page, the filter dropdowns and the dashboard; stored names, slugs and checksums unchanged | S | done |
| 8 | UI | Product page media panel: icon clipped into a corner. Fixed with CSS on 7 Nov | Looked broken | Browser-checked 8 Nov (light, dark, phone). The media tile now also fills the column height on desktop, so no empty strip sits under the image | S | done |
| 16 | UI, MongoDB | No product photos: every product shows an icon card and GridFS is empty until a seller uploads | Weak first impression; thin GridFS showcase | Seed openly licensed photos for the demo products through the GridFS upload path, labelled; reverses catalogue amendment k | M, approval | loader built 8 Nov (`seed_showcase`); the teammate supplies photos, up to 12 new products, 1 or 2 new categories and a new merchant through the committed files (see Decisions) |

## Batch 5: Redis

Settled before RLS (Decisions, 8 Nov). Needs its own short plan with trade-offs before building.

| # | Area | Item | Fix | Effort | Status |
|---|---|---|---|---|---|
| 25 | Security | No brute-force protection on login or review posting | Redis rate limiting (atomic sliding window in a Lua script) | M | done 8 Nov ([redis](redis.md)) |
| 12 | MongoDB | The unfiltered trending aggregation is the largest database cost on the home, shop and search pages | Short-lived Redis cache with explicit invalidation, measured cache on against off | S–M | done 8 Nov; the measurement runs in the benchmark programme (Batch 6 builds its tooling) |

Conditions for the plan: fix the slow dashboard query (#10) first, keep Redis off checkout and stock (rule 2), keep it
out of the B-series benchmarks (rule 10), measure cache on against off on one machine with the request-timing collector,
settle fail open or closed, `maxmemory` and eviction, real Redis in CI, and drop it if the full suite is not green by
15 November. Redis sessions, cart or stock and observability are skipped.

## Batch 6: benchmark amendment

| # | Area | Item | Fix | Effort | Status |
|---|---|---|---|---|---|
| 5 | Benchmark, MongoDB | B2 pipelines are not idiomatic: B2a joins `products` for a `category_id` the order lines already carry ([b2.py](../../benchmarks/workloads/b2.py), [load.py](../../benchmarks/load.py)); B2b–d run one correlated `$lookup` per product or order; PostgreSQL has a materialized variant and MongoDB has none | Add idiomatic and maintained-summary variants against the same golden outputs (B2's delay-analysis queries still exclude copied reviews, unlike the app since #52); keep the originals; rerun B2 only on the designated machine ★ | M, approval | open |
| 13 | Benchmark | B1 broad: the MongoDB planner chose `_id_` to avoid a sort and examined the whole product set ([plan](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/plans/B1_broad_mongo_documents.json)). Index effort in B1 is unequal: GIN plus expression B-trees against one wildcard index | Report the hinted run beside the headline and explain the planner; consider a compound wildcard index | S (report), M (rerun) | open |
| 17 | Analysis | Per-request timings differ between machines: the committed [request-timing run](../../benchmarks/results/2026-11-02T103305_b53e5d0a_request-timing/category.csv) shows a PostgreSQL-bound category page, this review did not | Rerun the collector on the recording machine after the freeze, before citing it | S | open |

## Batch 6b: full-text search on review text

| # | Area | Item | Fix | Effort | Status |
|---|---|---|---|---|---|
| 71 | MongoDB, benchmark | Full-text search on review text: a MongoDB text index against PostgreSQL `tsvector` with a GIN index, compared with query plans (PLAN.md Tier 2 `search`, E1, B7). A second same-feature comparison for the NoSQL half; the English review text already exists | Short plan first. Reviews live only in MongoDB, so the application gains MongoDB text search and the PostgreSQL side runs on the bench review copy as B7; no SQL review table in the application. Build only after batches 1–6 are green | M, approval | open |

## Batch 7: code-quality pass, then the full codebase review

| # | Finding | Status |
|---|---|---|
| 27 | Ruff selects only E, F and I. Add B, S, DJ (and SIM, C901, PLR if cheap) and fix the findings | accepted |
| 33 | Several templates are written on single very long lines; reformat | accepted |
| 63 | The `with mongo.client() as client: database = client[mongo.database_name()]` pair is repeated 27 times (add a `mongo.database()` helper). `AUDIT_LABELS` and `AUDIT_TONES` are built by four appended `.update()` blocks in [accounts/audit.py](../../src/accounts/audit.py) (one table). `moderate_product` raises `ValueError` where every other service raises `ValidationError`. `set_saved` checks purchasability twice. `purchasable_product` is `SELECT p.*`, which freezes its column list at creation. The extra Ruff rules report few findings: models without `__str__`, four over-complex functions (`checkout`, `seed_demo.handle`, `import_olist`, `reconcile`) and two nullable string fields; the one injection warning is a false positive | open |
| 73 | **Test-suite review** (Erfan, 9 Nov): read every test module and find duplicated tests (the same behaviour proved twice, in one module or across modules), tests that exist only to exist (they assert that a constant, a trivial getter or the framework behaves as written), and tests that can be merged (near-identical cases that belong in one parametrised test, or several tests of one scenario that repeat the same set-up). Merge or delete them with the full suite green before and after. Keep the tests for money, concurrency, role privileges, cross-store consistency, injection and data integrity, and the ones that proved a defect once. Widen the timing-sensitive Redis window tests that flake under a VM stall. Do it after the Batch 8 tests exist so row-level security does not add duplicates, and before the full codebase review so the reviewer sees the final suite. The report describes what the tests prove, never how many there are (AGENTS.md) | open |

## Batch 8: row-level security, settled last

| # | Item | Why it matters | Effort | Status |
|---|---|---|---|---|
| 48 | **Row-level security for sellers** (`seller-rls` in PLAN.md section 14): PostgreSQL policies so the database restricts a seller to their own products and orders. Today rule 6 is enforced only by application filters and tests; no policy exists. Needs a plan with trade-offs before building (roles, the per-request setting, owner and runtime roles, tests, benchmark isolation). Cut and disclose if not green on the full suite by the go/no-go date ★ | A database-enforced security feature the presentation criterion names; makes the "database says no" demo stronger | M–L, approval | accepted, settle last (after Redis) |
| 62 | [confirmed] A seller cannot relist a deactivated product, and many imported products are inactive. A feature, not a bug fix. Relist action using the same lock order. Optional | Seller demo only | S | open |
| 42 | **One-command start**: a script that runs `init_env`, `up`, `import_olist` and `seed_demo` in order ★ | A failed marker run costs "working". Optional | S, approval | open |
| 20 | Adding a product asks for the category twice. Only if the video films the add-product form | Visible only if filmed | S–M | open |

## Batch 8b: synthetic scale runs for the benchmark (parked)

Parked by Erfan on 8 November 2026. It is the last item of the code-side work: attempt it only when batches 1–8 are done and
green, and before any report, slides or video work (the rest of the 40% implementation line comes first). If the code side
finishes early, Erfan may pull it forward. Default is no.

| # | Area | Item | Fix | Effort | Status |
|---|---|---|---|---|---|
| 72 | Benchmark | The benchmark measures the base Olist volume only, so its attribute-filter, index and storage results show no growth with data (PLAN.md risk: "no clear difference at about 100k rows") | A seeded generator that resamples real products and their attributes (B1, B4, B5) and real review text (B7) to 3× and 10× (about 340k products and more than a million attribute and review rows), labelled `is_generated`, loaded only into throwaway bench databases, identical files for both engines, correctness against the independent reference computation before any timing counts. **Not** B2 (88% of the measured time and needs the whole order graph), B3 or B6. Run on a second night on the designated machine; reopens the 28 October decision against a generator and a scaled run | L (a day for the generator plus a benchmark night) | parked |

If it is not done, the report says so in one sentence under limitations and future work: the data is the real Olist volume,
and a scaled run was considered and left out for time.

## Batch 9: demo, evidence and deliverables

The 40% implementation line is judged on the video, slides, report and source code together, so a marker credits mainly
what those show. These items present existing work rather than add features.

| # | Priority | Item | Why it matters | Effort | Status |
|---|---|---|---|---|---|
| 1 | P0 | Report (10 pages), slides and video (10:00 maximum) do not exist; the packager refuses to build without them. [deliverables](deliverables.md): report draft by 15 Nov, footage by 18 Nov | Report and presentation are half the grade; implementation is judged through them too | L | open |
| 38 | P1 | **"The database says no" demo script**: one `psql` and `mongosh` session showing the runtime role refused `DROP` and `DELETE` on orders, an invalid status change rejected by its trigger, payments that differ from the total rejected at commit, a MongoDB document rejected by its validator, and a duplicate review rejected by the unique index ★ | Constraints, security and integrity enforced by both databases, not only by application code | S–M | open |
| 47 | P1 | **Concurrency demo**: two terminals buy the last unit of a product and one is refused; B6 already measures it. Added to the #38 script ★ | Integrity under concurrency, shown rather than described | S | open |
| 70 | P1 | **Rewrite the demo script in the brief's fixed order** (background, relational, NoSQL with comparison, performance); today the story follows the customer journey and ends with the benchmark. Folds in #38 and #47 ★ | The presentation criterion is order sensitive | S–M | open |
| 46 | P1 | **Index and plan evidence page**: two or three queries with `EXPLAIN` before and after an index, taken from the plans already saved under `benchmarks/results/` ★ | Supports "efficiency" and "complex queries" in the relational criterion | S (writing) | open |
| 39 | P1 | **Marker's tour at the top of the README**: demo logins, then for each headline feature on both databases the click that shows it, the file that implements it and the test that proves it ★ | Makes "significant implementation to both databases" visible in minutes | S | open |
| 15 | P1 | The README flow works from a clean clone, but the data import sits after the benchmark section; deliverables exit check 4 (run from the extracted zip on another machine) is still open. Reorder the README; run from the zip by 15 Nov ★ | Markers must run the app from the manual | S–M | open |
| 41 | P1 | **Diagrams as images**: the ER diagram rendered from [DATA_MODEL.md](../DATA_MODEL.md); a MongoDB model diagram (embedded against referenced, time series, GridFS); one architecture diagram of which store owns what ★ | The brief requires an ER diagram and a NoSQL data model. Reused in the report and slides | M | open |
| 6 | P0 | MongoDB's justification is not written, and the timed workloads favour PostgreSQL. Evidence exists: storage ([B5](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/report/B5.csv)), atomic single-document update ([B6](../../benchmarks/results/2026-11-02T095518_b53e5d0a_final-b3-b6/report/B6-states.csv)), embedding, migration-free schema change, GridFS, time-series TTL. Write the report and slide section ★ | Risks "implementations are not justified" | M | open |
| 43 | P2 | **Quality evidence in one place**: a link to a green CI run, the coverage report, tool-printed test counts, and the injection, isolation and concurrency tests named ★ | Turns "well tested" into evidence; supplies report section 8 | S | open |
| 44 | P2 | **Analytics depth on the delivery-delay finding**: rank correlation with a confidence interval, and distance checked as a confounder, from committed data ★ | Extra credit names "data analytics algorithms" | M | open |
| 26 | P2 | PostgreSQL-first writes log, rather than repair, a MongoDB failure. No code change: show `check_specs` in the demo; write it up as a reflection | Cross-store honesty | S | open |
| 40 | P1 | **Claims audit before submission**: check every claim in the report, slides and script against the code or a committed result file ★ | The rubric rewards "accurate" | M | open |
| 14 | QA | Reviews, wishlist, dashboard, activity and benchmark were reviewed only by the session that wrote the brief ([AI_USE.md](../AI_USE.md)). The 8 Nov Opus review covers much of this; close it after the final review | The AGENTS.md review rule | M | open |
| 3 | P0 | [CONTRIBUTIONS.md](../../CONTRIBUTIONS.md) records almost only Chee Long; Joash's student ID is missing; others are "not yet recorded". Every member records their actual work. Deferred to last by Erfan ★ | The final mark is weighted by peer review | S | open |

## Disclose in the report (no code change)

| # | Finding |
|---|---|
| 29 | MongoDB validators accept any attribute key; template types are enforced only in Django forms |
| 30 | The per-order refund rule is not a database constraint (already in [DATA_MODEL.md](../DATA_MODEL.md)) |
| 31 | Deferred money checks run per row at commit; B3 shows their cost ([summary](../../benchmarks/results/2026-11-02T095518_b53e5d0a_final-b3-b6/summary.csv)); present as a finding |
| 32 | `placed` is never written for new orders; `checkout` indexes rows by position; `seed_demo.handle` and `checkout` are long; prepare spoken explanations |
| 35 | B3 compares four normalised inserts with one embedded document; the engines' cache models differ ([memory settings](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/report/memory-settings.csv)) |
| 36 | The benchmark CI job is optional; coverage is gated on lines only |
| 64 | MongoDB validators have no length limits; Django forms bound review and description text. `mongo_setup` cannot change an existing validator under `readWrite`. Group with #29 |
| 65 | Anonymous visitors get a PostgreSQL session row on their first view or search, and nothing clears old sessions |
| 66 | Imported data has orders paid but never shipped, orders delivered after their estimate and some delivery dates in the future; a few products have reviews dated after the filming date of 18 November 2026 (imported dates are shifted into 2026; the dashboard's reporting date is 28 October 2026), so avoid those products when filming |
| 67 | If two categories define the same attribute with different types, a search across both keeps the first type and misses the other category's products ([catalogue/search.py](../../src/catalogue/search.py)) |
| 68 | The audit actor is set by the application with `set_config`, so the runtime role could record any user as the actor. Inherent to this design |
| 45 | Single dataset (Olist alone): a known slight weakness against the brief's preference for more datasets; the second dataset is dropped |

## Done and dropped

| # | Item | Outcome |
|---|---|---|
| 9 | Footer linked to the foundation mockups | done 7 Nov |
| 22 | "Live" facet counts wording | done (wording); `hx-get` live filtering dropped |
| 28 | Host Python minimum | done 7 Nov |
| 37 | Untracked `RESUME_*` notes | done |
| 4 | Email to the professors | removed by Erfan |
| 45 | A second real dataset | dropped 8 Nov |
| 23, 24 | Phone filter panel; confirmation before irreversible actions | dropped: the video is filmed at desktop width and markers will not see them |
| Observability, Redis sessions, cart or stock | | skipped: no measurable gain, or AGENTS.md rule 2 |

### Verified working, no action

Role access (redirects and 403 pages), CSRF rejection, parameterised SQL, upload validation (a disguised SVG and an
oversize file rejected, a valid PNG accepted), checkout idempotency under a double click, cross-customer order access
(404), the full Docker suite, the browser journeys on full data, Ruff, the packager's secret checks, and basic
accessibility (labels, alt text, visible focus, no horizontal scroll at phone width).

## Decisions

| # | Date | Decision (owner) | Why |
|---|---|---|---|
| 2 | 2 Nov 2026 | Erfan: remove the failing "hose nozle" example from the [OVERVIEW.md](../OVERVIEW.md#3-the-demo-story) demo story without naming a replacement | Docs only; the overview no longer promises a search that returns nothing |
| 22 | 2 Nov 2026 | Erfan: the overview now says facet counts are shown for each search, not that they update live. The `hx-get` live filtering is dropped | Docs only; matches the submit-and-reload behaviour |
| 37 | 2 Nov 2026 | Erfan: the untracked `RESUME_*` notes were deleted from the repository root | The working-tree documentation check passes again |
| 28 | 7 Nov 2026 | Erfan: keep "Python 3.8 or later". `init_env.py` and `check_docs.py` were run on 3.8 and 3.9 and pass; the README says so and that CI runs them on 3.13 only. No 3.8 CI job | Docs only; the claim was true but unverified in CI |
| 9 | 7 Nov 2026 | Erfan: remove the four mockup links from the footer; keep "System status" under a "Status" heading. The 404 page's "overview" button now goes to the home page. The routes stay because tests use them | The footer no longer sends a marker to invented figures |
| 8 | 7 Nov 2026 | Erfan: centre the category icon in the product page media frame instead of the card-corner crop | CSS only; photos are unaffected |
| all | 8 Nov 2026 | Erfan: sole approver of every item while Chee Long is away; implement on the current branch, no new branches, docs updated with each change ([CLAUDE.md](../../CLAUDE.md)). Item #4 was removed from the backlog by Erfan | Solo ownership; AGENTS.md stays unedited for Chee Long and Codex |
| 46, 47 | 8 Nov 2026 | Erfan: add the index and plan evidence page and the concurrency demo | They turn existing work into evidence the report and video can show |
| 48 | 8 Nov 2026 | Erfan: row-level security for sellers is wanted. No policy exists today (rule 6 is application-level). A plan with trade-offs comes first; cut and disclose if not green on the full suite by the go/no-go date | Database-enforced isolation; shown in the demo |
| 27, 33 | 8 Nov 2026 | Erfan: do the code-quality pass (extra Ruff rules with their findings fixed, and the long template lines reformatted) | The Excellent band names coding quality |
| 45 | 8 Nov 2026 | Erfan: drop the second dataset; Olist alone is a known slight weakness, accepted to avoid overscope | Days of work against the deadline |
| 49–55 | 8 Nov 2026 | Erfan: accept the seven confirmed correctness and integrity findings as fix-before-freeze items; re-confirm each with its probe, which becomes the regression test | Bugs in demoed paths that the existing suite misses |
| 56–63 | 8 Nov 2026 | Erfan: accept as if-cheap items (#62 optional) and fold #63 into the code-quality pass | Small, mostly performance and polish |
| 64–68 | 8 Nov 2026 | Erfan: disclose in the report rather than fix | Inherent to the design or low risk |
| 69, 70 | 8 Nov 2026 | Erfan: add the three-seller demo logins and the demo script in the brief's order | The story cannot be filmed as written |
| Redis, 48 | 8 Nov 2026 | Erfan: Redis is settled before row-level security; RLS (#48) is settled last, because it touches every seller query and the roles. Redis conditions are listed under Batch 5 | Redis is additive and adds key-value use to the NoSQL half; RLS is the riskier change |
| Batches | 8 Nov 2026 | Erfan: the backlog is organised into batches, settled a few at a time, easiest first. Batch 1 approved with option A for #60, the new index only for #56, and "garden tols" for #2 | Understand each change before it is built |
| 53, 51, 54, 69 | 8 Nov 2026 | Erfan: implement Batch 2. #51 with option A (form maximum 99,999, database ceiling 1,000,000, chosen as a logical per-listing cap); #54 agreed after the audit-size explanation (rows only on sensitive events, about 0.6 KB each); #69 with fixed, documented demo passwords (the app is never deployed), documented in the README | Recorded in `docs/DECISIONS.md` |
| 72 | 8 Nov 2026 | Erfan: park the synthetic scale benchmark (B1, B4, B5, B7 at 3x and 10x; not B2, B3, B6) as Batch 8b, after batches 1–8 and before any report, slides or video work; consider pulling it forward if the code side finishes early | The existing benchmark is already strong and half the grade is the report and presentation; a scale curve is the lowest-return item and costs a benchmark night |
| Showcase | 8 Nov 2026 | Erfan: the 30 listed products get photos; demo shop names (Paulista Watch & Gift House, Ibitinga Linen & Home, Santo Andre Beauty Studio); featured products lead category pages; the teammate adds up to 12 new products, 1 or 2 new categories and a new merchant of their own choice, through committed files; no seeded reviews for new products | The photo and product lane is data, so it reproduces on a fresh clone |
| Names review rounds | 8 Nov 2026 | Erfan: approve the fix round from the fresh Opus 5.5 review of the names change (stale benchmark goldens regenerated, `fx-source.xml` kept LF with an `-text` rule, attribute-contradicting names fixed, thin main categories widened), then a second round for three naming problems the first round introduced (repeated word in the fit suffix, operating-system suffix on non-matching nouns, power suffix on earphones; the "Portable" adjective removed where the attribute can be false). Suffixes can now be limited to named nouns. Tiny generic categories (books, music, food, party items) still repeat names on a page: accepted | Reviews found real problems in data that every benchmark run depends on (the stale goldens would have blocked the run and the optional benchmark fixture CI job) |
| 7, 16 | 8 Nov 2026 | Erfan: defer the names, review text and photos decision to Batch 4; option A is the recommendation. Teammate to add photos | Settle with the showcase set and #69 |
| NoSQL order | 8 Nov 2026 | Erfan: NoSQL work is ranked by marks per effort: (1) #11 subset read, (2) #10 with #52 as a PostgreSQL materialized view beside a MongoDB `$merge` materialized view, (3) #5 idiomatic B2, (4) #6 MongoDB justification, (5) #16 GridFS photos, (6) #71 full-text search, (7) Redis #25 and #12. Batches keep their execution order; #71 added as Batch 6b | Fix the false claim, the unfair comparison and the unwritten argument before adding features; each item must be shown in the video or report to earn credit |
| 49, 55, 52, 10, 57 | 8 Nov 2026 | Erfan: settle Batch 3 without building it yet. #49 option B (field-level merge under the row lock, following compare-and-set practice for inventory); #55 as described, a database guard on order timestamps; #52 and #10 step 1 only for now (integer sum and count, copy filter removed, no cache), the materialized-view design and Redis come later in the NoSQL order; #57 option i | Fix the demoed bugs and the measured slowness first; keep step 2 and Redis as measured follow-ups |
| Batch 3 review | 8 Nov 2026 | Erfan: approve the whole fix round from the fresh Opus 5.5 review of batches 1 to 3: refuse non-finite expected prices, correct the dashboard note and the stale docs, run `mongo_setup` and `seed_demo` locally, add privilege and concurrency tests, show hidden-field errors, treat a typed value equal to the live one as no conflict, make the test helper transactional | One fix round, as the workflow allows |
| 16 | 8 Nov 2026 | Erfan: a teammate settles and carries out #16 (photos); Erfan settles the rest of Batch 4, and other batches continue meanwhile. Open dependencies recorded for the teammate: the photos must match the product names (#7, #18) and the showcase set, they reverse catalogue amendment k, and they need a committed folder plus a licence manifest so the zip reproduces them | Photos are sourcing work that does not block the rest of the batch |
| 11, 19 | 8 Nov 2026 | Erfan: #11 option A (read the subset), #19 option 1 (written reviews, bare ratings collapsed). #7 and #16 deferred to later | Combined: page 1 is the stored latest five, so a page whose newest five are all bare ratings shows only the collapsed line and a link to the full list |
| 7, 16 | 8 Nov 2026 | Erfan: B-lite names (all 74 categories), SKU line, showcase of 30 products (15 categories x 2), readable names for the three demo shops, review text left as imported, photo rules (free-to-use sources only, JPEG/PNG/WebP up to 2 MB, at least 800 px, licence manifest, credits in the README). The #16 branch is created after the showcase list is settled; the benchmark rerun on Erfan's PC covers the regenerated data | Names affect every screen; photos must match them |
| Benchmark rerun | 8 Nov 2026 | Erfan: the whole benchmark is rerun on his desktop after Batch 8, on one clean commit: pilot, then three sessions at 50 and 10 operations per client, headline the median across sessions, pooled p95 and p99 gated by sample size, start and end baselines, old results archived and compared for unchanged workloads (benchmark amendment l). The Redis measurement protocol is part of it and `redis.md` is approved | Reproducibility across independent sessions on the machine that produces the final evidence |
| Redis review 1 | 8 Nov 2026 | Erfan: approve the whole fix round from the first fresh Opus 5.5 review of Batch 5 (Redis start-up after a restart, name-lookup timeout, look-alike username bypass, old-shaped cache entries, `Retry-After` after an overshoot, documentation, and three hardening items) | One fix round, as the workflow allows |
| Redis review 2 | 8 Nov 2026 | Erfan: approve the fix round from the second fresh Opus 5.5 review of Batch 5 (a shape number in every cached entry, lock release during a back-off, name-lookup threads, bounded username normalisation, review takedown and import invalidation, cheaper waiting, documentation) and treat it as the last one | No high-severity finding remained; a third review would meet diminishing returns |
| 10 step 2, 5, 13, 52 | 9 Nov 2026 | Erfan: #10 step 2 is built in the application (a PostgreSQL materialized view of per-order delivery delays beside a MongoDB per-order score summary, the live path kept as fallback and oracle), time-boxed to 11 Nov; the MongoDB summary is rebuilt with `$out`. For Batch 6: the headline B2b compares the plain 28-day `GROUP BY` the app runs against the equivalent simple MongoDB pipeline, with the window-function pair kept as "as first implemented" rows; B2d is aligned with the app (copied reviews included) and its indexes and golden outputs change with it; #13 is report-only (the hinted run beside the headline, the planner explained, no new index); whether the originals stay in the full matrix is decided after the pilot, if time is tight | Single owner decision; the like-for-like pair serves part iii of the presentation; aligning B2d with the app (#52) keeps the benchmark and the dashboard asking the same question |
| Dashboard summaries review | 9 Nov 2026 | Erfan: approve all recommended items from the Opus 5.5 review of #10 step 2 (no hand-written timings, a migration reversal test and a simultaneous-refresh test, a stale docstring and a status mismatch, the import empties a leftover score summary before it refreshes, and the known limits written into the plan) | Small, low-risk fixes; no correctness defects were found |
| 73 | 9 Nov 2026 | Erfan: a review of all the tests for duplicates, tests that exist only to exist and tests that can be merged, in Batch 7 (after Batch 8, before the full codebase review) | The suite is large for the application's size and slow to run; fewer, sharper tests keep the evidence and the speed |
| 18, 8, 21, 34 | 8 Nov 2026 | Erfan: settle these four first; the rest of Batch 4 is explained for him to approve | Quick UI fixes that need no further decision |

## Review notes

2 November 2026, Claude Code (Opus 5.5) for Erfan, on Erfan's Windows machine: a code read of the benchmark, both
databases, the backend, CI and templates, then a live run. The live run followed the README from a clean state
(`init_env.py`, `docker compose up --build`, `import_olist`, `verify_olist`, `seed_demo`, `seed_activity`,
`smoke_olist.py`), ran the full Docker suite and the host tests, Ruff, the browser suite
(`python -m scripts.browser_suite --env-file .env --base-url http://127.0.0.1:8000`) and the packager with placeholder
deliverables. A scripted Chromium crawl visited every page for each role at desktop and phone widths, and exploratory
scripts checked error states, uploads, focus and dark mode. All passed except the findings above. Screenshots and
logs stayed outside the repository; rerun the commands above to reproduce them.

8 November 2026, Opus 5.5 for Erfan, read-only: the full Docker suite, 17 throwaway probe tests against the real
databases, a probe of the full Olist import and an HTTP probe of the running app. Findings are #49–#68 above. It changed
no repository files, created a local `.env` and a running stack, and left its probe tests in a temporary folder; copy
them into `tests/` when fixing.

8 November 2026, fresh Opus 5.5 session for Erfan, read-only, on batches 1 to 3: the full suite, Ruff, the drift check and
`check_docs.py` passed. One real bug (a tampered `sNaN` expected price returned HTTP 500), a stale dashboard note, stale
statements about the window query and the copy rule in three docs, a missing privilege test for the timestamp guard, and
two wording errors in this file. All fixed in one round; a real concurrent save test and a migration reversibility check
were added.

Incident in the same fix round: the first version of the concurrent save test started a worker thread without MongoDB test
routing, so the save wrote to the real application database and overwrote two imported product specifications (ids 1 and
8) in the dev stack. They were restored from `data/derived/olist/clean/product_specs.ndjson` and verified; the test now
routes its thread to the test database and asserts it, and CLAUDE.md records the rule. A structural safeguard (making an
unrouted thread fail under pytest) is a possible follow-up for the code-quality pass.
