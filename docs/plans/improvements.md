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
| 3 | #49, #55, #52 with #10, #57 | Integrity and the dashboard; Opus review checkpoint after | open |
| 4 | #11, #19, #21, #7, #18, #34, #8, #16 | UI and MongoDB claims | open |
| 5 | #25, #12 (Redis) | Redis, its own short plan first | open |
| 6 | #5, #13, #17 | Benchmark amendment, designated machine | open |
| 7 | #27, #33, #63 | Code-quality pass, then the full codebase review | open |
| 8 | #48 (RLS); optional #62, #42, #20 | Row-level security, settled last | open |
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
| 49 | Concurrency | [confirmed] A seller's stale edit form undoes sales: open the form at stock 8, 3 units sell, save a description fix, stock returns to 8. This is the lost-update anomaly B6 measures, inside the app ([catalogue/services.py](../../src/catalogue/services.py) copies every posted field) | Hidden expected stock and price in the form, compared under the existing row lock; refuse if they changed. Full suite | S–M | open |
| 55 | Integrity | [confirmed] The runtime role can rewrite `paid_at`, `shipped_at`, `delivered_at` and `estimated_delivery` with no audit row; the status trigger guards only `status`, and the delay analysis is computed from these columns | Extend the BEFORE UPDATE trigger to freeze lifecycle columns unless the status changes; full suite. Also a line for the #38 demo | S–M | open |
| 52 | Analytics | [measured] The delivery-delay analysis silently drops every multi-line order, because it excludes copied reviews ([dashboard/services.py](../../src/dashboard/services.py)). Copies in one order share a score and the query already groups by order, so the filter buys nothing | Remove the filter, then re-check against `verify_olist` and any figure quoted in the report. Do together with #10 | S | open |
| 10 | Backend | The operator dashboard takes several seconds: [delivery_analysis](../../src/dashboard/services.py) loads every delivered order and every order score into Python on each request, and the stock panel is paged in Python | Short design first: SQL aggregate or materialize at the source; Redis only if that is not enough | M | open |
| 57 | PostgreSQL | [measured] The stock-planning query is far slower than a plain 28-day `GROUP BY` and returns the same result; `daily_demand` is always units over 28 days, so the per-product window adds nothing. Benchmark B2 imports this query | Replace it, but keep the original for B2 or fold the change into the #5 amendment | S | open |

**Checkpoint:** an Opus 5.5 review of everything changed in batches 1–3.

## Batch 4: UI and MongoDB claims

**Deferred decision (8 Nov): product names, review text and photos.** Names are an adjective, the category label and a
hexadecimal suffix, so about 34,000 products share only a few hundred distinct names; muting the suffix (#7 as
written) would leave lists of near-identical titles. English review text is a literal machine translation of
Portuguese reviews, some of them casually misspelt, and the source data itself is not corrupted. Options when settled:
(A, recommended) a showcase set of about 20 products across the three demo sellers, given labelled names, photos and
hand-checked review text in `seed_demo` (no change to the clean data, checksums or closed benchmarks); (B) regenerate
every name, which changes the clean files and needs a B1 rerun; (C) add a generated attribute to titles as a display
extra. A teammate will supply the photos (#16), which must match the names. Settle together with #69.

| # | Area | Item | Why it matters | Fix | Effort | Status |
|---|---|---|---|---|---|---|
| 11 | MongoDB | `latest_reviews` is maintained on every review write ([reviews/services.py](../../src/reviews/services.py)) but never read; the product page queries `reviews` directly | The subset pattern and "a product page is one read" claim are not true | Read the subset on the product page, or drop the claim ★ | S–M, approval | open |
| 19 | UI | Review lists are mostly score-only rows, so product pages look empty | Looks empty on camera | Text reviews first, or collapse score-only rows | S | open |
| 21 | UI | Seller insights is sorted by product id; the dashboard filter asks for a typed seller number and shows Django's empty label | Both pages appear in the demo story | Sort by views or conversion; readable filter labels | S | open |
| 7 | UI | Product and shop names look like identifiers (a hexadecimal suffix on every name) | Visible on every screen of the video | Show the suffix as a muted SKU line; regenerating names would change data checksums and benchmark provenance | M, approval | open |
| 18 | UI | Generated-content labels appear three times per card; descriptions read like placeholder text | Clutter on every card | One clear label per card (AGENTS.md rule 9) | S | open |
| 34 | Data | Some category names read oddly ("Home Appliances 2", "Construction Tools Tools") | Looks careless | Optional display mapping | S | open |
| 8 | UI | Product page media panel: icon clipped into a corner. Fixed with CSS on 7 Nov | Looked broken | Browser check of the fix is still pending (the stack is up) | S | done (unverified in browser) |
| 16 | UI, MongoDB | No product photos: every product shows an icon card and GridFS is empty until a seller uploads | Weak first impression; thin GridFS showcase | Seed openly licensed photos for the demo products through the GridFS upload path, labelled; reverses catalogue amendment k | M, approval | open |

## Batch 5: Redis

Settled before RLS (Decisions, 8 Nov). Needs its own short plan with trade-offs before building.

| # | Area | Item | Fix | Effort | Status |
|---|---|---|---|---|---|
| 25 | Security | No brute-force protection on login or review posting | Redis rate limiting (atomic counters that expire) | M | open |
| 12 | MongoDB | The unfiltered trending aggregation is the largest database cost on the home, shop and search pages | Short-lived Redis cache with explicit invalidation, measured cache on against off | S–M | open |

Conditions for the plan: fix the slow dashboard query (#10) first, keep Redis off checkout and stock (rule 2), keep it
out of the B-series benchmarks (rule 10), measure cache on against off on one machine with the request-timing collector,
settle fail open or closed, `maxmemory` and eviction, real Redis in CI, and drop it if the full suite is not green by
15 November. Redis sessions, cart or stock and observability are skipped.

## Batch 6: benchmark amendment

| # | Area | Item | Fix | Effort | Status |
|---|---|---|---|---|---|
| 5 | Benchmark, MongoDB | B2 pipelines are not idiomatic: B2a joins `products` for a `category_id` the order lines already carry ([b2.py](../../benchmarks/workloads/b2.py), [load.py](../../benchmarks/load.py)); B2b–d run one correlated `$lookup` per product or order; PostgreSQL has a materialized variant and MongoDB has none | Add idiomatic and maintained-summary variants against the same golden outputs; keep the originals; rerun B2 only on the designated machine ★ | M, approval | open |
| 13 | Benchmark | B1 broad: the MongoDB planner chose `_id_` to avoid a sort and examined the whole product set ([plan](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/plans/B1_broad_mongo_documents.json)). Index effort in B1 is unequal: GIN plus expression B-trees against one wildcard index | Report the hinted run beside the headline and explain the planner; consider a compound wildcard index | S (report), M (rerun) | open |
| 17 | Analysis | Per-request timings differ between machines: the committed [request-timing run](../../benchmarks/results/2026-11-02T103305_b53e5d0a_request-timing/category.csv) shows a PostgreSQL-bound category page, this review did not | Rerun the collector on the recording machine after the freeze, before citing it | S | open |

## Batch 7: code-quality pass, then the full codebase review

| # | Finding | Status |
|---|---|---|
| 27 | Ruff selects only E, F and I. Add B, S, DJ (and SIM, C901, PLR if cheap) and fix the findings | accepted |
| 33 | Several templates are written on single very long lines; reformat | accepted |
| 63 | The `with mongo.client() as client: database = client[mongo.database_name()]` pair is repeated 27 times (add a `mongo.database()` helper). `AUDIT_LABELS` and `AUDIT_TONES` are built by four appended `.update()` blocks in [accounts/audit.py](../../src/accounts/audit.py) (one table). `moderate_product` raises `ValueError` where every other service raises `ValidationError`. `set_saved` checks purchasability twice. `purchasable_product` is `SELECT p.*`, which freezes its column list at creation. The extra Ruff rules report few findings: models without `__str__`, four over-complex functions (`checkout`, `seed_demo.handle`, `import_olist`, `reconcile`) and two nullable string fields; the one injection warning is a false positive | open |

## Batch 8: row-level security, settled last

| # | Item | Why it matters | Effort | Status |
|---|---|---|---|---|
| 48 | **Row-level security for sellers** (`seller-rls` in PLAN.md section 14): PostgreSQL policies so the database restricts a seller to their own products and orders. Today rule 6 is enforced only by application filters and tests; no policy exists. Needs a plan with trade-offs before building (roles, the per-request setting, owner and runtime roles, tests, benchmark isolation). Cut and disclose if not green on the full suite by the go/no-go date ★ | A database-enforced security feature the presentation criterion names; makes the "database says no" demo stronger | M–L, approval | accepted, settle last (after Redis) |
| 62 | [confirmed] A seller cannot relist a deactivated product, and many imported products are inactive. A feature, not a bug fix. Relist action using the same lock order. Optional | Seller demo only | S | open |
| 42 | **One-command start**: a script that runs `init_env`, `up`, `import_olist` and `seed_demo` in order ★ | A failed marker run costs "working". Optional | S, approval | open |
| 20 | Adding a product asks for the category twice. Only if the video films the add-product form | Visible only if filmed | S–M | open |

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
| 66 | Imported data has orders paid but never shipped, orders delivered after their estimate and some delivery dates in the future; a few products have reviews dated after the dashboard's reporting date (the review's wording "after 18 November" is unverified; re-check which date it meant), so avoid them when filming |
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
| 7, 16 | 8 Nov 2026 | Erfan: defer the names, review text and photos decision to Batch 4; option A is the recommendation. Teammate to add photos | Settle with the showcase set and #69 |

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
