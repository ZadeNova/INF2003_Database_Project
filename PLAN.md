# INF2003 plan: Mercer, a lean marketplace on PostgreSQL and MongoDB

Revision v5, 22 October 2026. Team 82. Accelerated schedule requested by the user; implementation status is in section 14.
Final submission: **Sunday 29 November 2026, 23:30**. The proposal (4 October) was marked "a solid plan and a clear scope".
Application and benchmarks B1 to B6: **stretch target Sunday 1 November 2026**; report, slides and video remain on the
final-submission timeline (section 13).

**In one paragraph.** A lean Shopee-style marketplace (customers, sellers, an operator) on the real Olist dataset.
PostgreSQL is the system of record; MongoDB owns product specifications, reviews, photos and activity events; a benchmark
harness compares both engines on identical data and workloads. Scope is tiered: Tier 1 is the A-grade core; Tier 2
(Redis, observability, row-level security, replication and failover, full-text search, product Q&A) is earned at the
8 November checkpoint and is outside the accelerated sprint. Workstream progress is recorded in section 14.

## 1. Principles

1. **Lean.** Every Tier 1 item is demoed in the video, measured or shown with a query plan, and written up in the report.
   An item that does fewer than two of these moves down a tier.
2. **Depth over breadth.** The rubric's top band rewards significant implementation on both databases and clearly stated
   methods, results and implications, not feature count. The A is won in the analysis as much as in the code.
3. **Every member can explain their part.** Decisions and their reasons go in `docs/DECISIONS.md`, so choices made with
   coding agents become choices the team can defend in the video and in interviews.

## 2. What we are building

Three roles, as on Shopee (D14 to D18; "seller" is the one word used everywhere):

| Role | Can do |
|---|---|
| **Customer** | Browse, search and filter products from many sellers; one cart across sellers; check out once and pay with a simulated method; track each order; review each item once it is delivered; wishlist sold-out products and get a restock alert |
| **Seller** | Apply to sell (pending until the operator approves); create, edit and deactivate their own products (price, stock, specifications, photo), where restocking fires the wishlist alert; see their own orders and mark them shipped; see their own sales and reviews; a public shop page |
| **Operator** (platform admin) | Approve or suspend sellers; take down products or reviews that break the rules; manage categories and their attribute templates (the schema-evolution demo); the platform dashboard (stock planning, category performance, sellers at risk of poor reviews); the audit log; mark orders delivered, acting as the courier for the demo |

A cart with products from three sellers becomes **one checkout with three orders**, one per seller, as on Shopee. The
checkout holds the payment; each seller ships their own order.

**Out of scope:** real payment gateways, shipping integrations, chat, vouchers, a second full backend.

## 3. Architecture: polyglot persistence plus a benchmark harness

```
Browser -> Django (HTMX, Gunicorn) -+-> PostgreSQL     system of record: users, sellers, products, carts, checkouts,
                                    |                  orders, payments, refunds, wishlist, audit log, analytics
                                    +-> MongoDB         product specifications (flexible attributes), reviews,
                                                        photos (GridFS), activity events (time-series)
                                                        (single-node replica set, needed for transactions)
benchmarks/ harness -> bench-db and bench-mongo, loaded with the same clean Olist files (scaled runs in Tier 2)
Docker Compose: web, db, mongo, migrate   (+ redis, otel-lgtm in Tier 2)
  optional profiles, never part of the running app: tools (profiling, cleaning, generation, pipeline tests),
  translation (offline review translation), bench (bench-db and bench-mongo, separate credentials and limits)
```

**Latest versions.** The brief asks us to explore the latest relational and NoSQL systems, so both engines run the latest
stable release at the time `foundation` pins the images (checked, not assumed). The report shows at least one recent
feature of each (for PostgreSQL 18, for example `uuidv7()`, virtual generated columns or `RETURNING OLD/NEW`).

**Ownership by field, never copied.** No value lives in both stores in the application, so no synchronisation machinery
is needed.

| Data | Store | Why |
|---|---|---|
| Users and roles, sellers (with approval status), products (each owned by one seller, with name, price and stock), carts, checkouts, orders (one per seller per checkout), order lines, payments (on the checkout), refunds, wishlist | PostgreSQL | Money and stock need ACID, constraints and triggers |
| Daily product sales (materialized view), audit log | PostgreSQL | `dashboard` and `accounts`; reporting rebuilt on the new schema, queries ported from the old baseline |
| Product specification document (category-specific attributes, generated description, rating summary, latest five reviews), keyed by product id; category attribute templates | MongoDB | Shape varies by category |
| Activity events (product views and searches), expiring after 30 days | MongoDB time-series collection with a TTL index | Write-heavy, append-only, time-ordered |
| Reviews (one per order line, translated text, rating, seller reply in Tier 2) | MongoDB | Nested, read-heavy, aggregated |

**Cross-store reads are explicit and small:** attribute search runs in MongoDB and returns one page of product ids, then
PostgreSQL fetches price and stock with `WHERE id = ANY(%s)`; a review write checks the order line in PostgreSQL first.
Both are named in the report with their measured cost.

**Raw SQL where it shows a construct** (checkout, payments, order status, wishlist, dashboard, benchmark paths). Plain
CRUD stays on the Django ORM. Parameterised queries only, everywhere.

**Money is exact in both stores:** `numeric(12,2)` in PostgreSQL and `Decimal128` in MongoDB (never the default double),
so cross-engine results compare exactly.

**Limited-privilege users on both databases:** the PostgreSQL runtime role used by the web app cannot run DDL, DROP or
TRUNCATE, while a separate owner role runs migrations, the import and tests (foundation-g); the MongoDB application user has `readWrite` on the application database only, and
the root user is used only at initialisation. SQL-injection negative tests cover the raw-SQL paths.

## 4. Tiers

### Tier 1: the A-grade core (application and B1 to B6 target 1 November)

| # | Item | Database content shown |
|---|---|---|
| T1 | **Olist import** replacing the shoe data, with documented cleaning rules (`olist-import`) | Real data, about 100k orders; FK integrity at import; ER diagram with the normalisation (3NF) justified, and the deliberate denormalisation in MongoDB explained (module theory) |
| T1b | **Three roles and accounts**: customer, seller, operator; seller registration and approval; operator console (approve or suspend sellers, take down products and reviews, category attribute templates, audit log) | Role-based access; seller status workflow enforced by a constraint and a transition trigger; sellers scoped to their own rows in every query |
| T2 | **Catalogue and seller shop pages**: generated English names and descriptions, product images (D10 to D12), an active catalogue of products ordered at least twice (D13), specifications in MongoDB, attribute search with **faceted filters** | Document model, `$jsonSchema` validation, multikey index; a `$facet` pipeline returns results plus counts per category, rating and attribute in one query; **live schema evolution** (a new attribute for a category with no migration, against `ALTER TABLE`) |
| T2b | **Seller product CRUD**: sellers create, edit and deactivate their own products (price, stock) in PostgreSQL, edit specifications in MongoDB and upload a photo to GridFS; the operator can take products down; deactivate instead of delete | CRUD on both databases (a brief requirement); `ON DELETE RESTRICT` protects products with order history; restocking drives the T5 trigger; an **audit trigger** records every price and stock change (who, when, before and after as JSONB) |
| T3 | **Cart across sellers, checkout split into one order per seller, simulated payment, order lifecycle** (the seller marks shipped, the operator marks delivered), **cancellation before shipping** (stock returned and a refund row recorded in one transaction) | `FOR UPDATE`, idempotency constraint, a compensating transaction for cancellation, payment rows on the checkout, deferred constraint trigger (payments equal the checkout total), status-transition trigger |
| T4 | **Per-item reviews** in MongoDB; customers can edit or delete their own review | Unique index on `order_line_id`, subset pattern, transaction (review plus rating summary), aggregation pipelines; **Bayesian average rating** for product and seller ranking, the same formula in SQL and in a pipeline (analytics algorithm) |
| T5 | **Wishlist with restock alert** | Many-to-many table, trigger |
| T6 | **Stock-planning dashboard** on Olist, with a **moving-average demand forecast** | Materialized view, CTEs, window functions (the moving-average query runs in benchmark B2; the app's dashboard uses a grouped sum since improvements #57); the same queries as aggregation pipelines in the harness |
| T6b | **Delivery delay against review score**: dashboard panel (sellers at risk of poor reviews) and a report section | Cross-store analysis: delay from PostgreSQL, score from MongoDB; the report's main implications finding |
| T6c | **Activity events** in MongoDB (M1): recently viewed for customers, trending now on the home page, views-to-purchases conversion for sellers | Time-series collection, TTL index, `$setWindowFields` ranking; the only write-heavy MongoDB workload; a second cross-store query |
| T7 | **Benchmark harness** (section 7, B1 to B6), with per-request database timing and a `docker stats` sampler | The rigorous comparison, including isolation anomalies (module theory) |
| T8 | **CI**: GitHub Actions running the suite against real PostgreSQL and MongoDB, **Playwright end-to-end tests of the demo story** (E4), `ruff` lint and format, a coverage threshold and `pip-audit` (E5) | "Well tested"; correctness gate for the benchmark |
| T9 | **Report, slides, video, user manual** | 50% of the marks |

The accelerated target covers T1 to T8 in full. T9's report, slides and video can remain pending during the sprint;
the README setup instructions and data-model documentation stay current with implementation so reviews and fresh
installs remain reproducible. Final deliverables follow section 13.

### Tier 2: earned at the 8 November checkpoint

| Item | Owner | Content |
|---|---|---|
| **Redis**: cache-aside on dashboard and reviews, rate limiting on login and review posting; cache-on against cache-off measurement | tbd | Key-value NoSQL; counts towards the rubric directly |
| **Observability**: `grafana/otel-lgtm` (OpenTelemetry collector, Tempo, Grafana in one container), OpenTelemetry instrumentation for Django, psycopg and PyMongo, one committed dashboard (section 8) | Erfan | Query spans per request, PostgreSQL against MongoDB latency; telemetry overhead measured |
| **Row-level security for sellers** (database-enforced isolation under Tier 1's app-level scoping) and a seller-scoped dashboard | tbd | Multi-tenant isolation |
| **Durability, replication and failover**: a 3-member MongoDB replica set and a PostgreSQL streaming replica; `synchronous_commit` against write concern `majority`; kill the primary on camera and show failover (E6); a timed backup and restore drill with `pg_dump`/`pg_restore` and `mongodump`/`mongorestore` (E7) | tbd | Write/durability axis promised in the proposal; replication is core module theory |
| **Full-text search** on review text: PostgreSQL `tsvector` with a GIN index against a MongoDB text index, benchmark B7 (E1) | tbd | The same feature on both engines, measured |
| **Product Q&A**: customers ask, sellers answer; answers embedded in the question document (M2) | tbd | MongoDB embedding |
| **Scale-up generator runs** to 1M+ rows, within Tier 2 `durability`; the owner decided on 28 October against building it or promoting a 10x run into Tier 1 ([benchmark-i21](docs/DECISIONS.md)) | tbd | Scale axis |
| Seller replies to reviews | tbd | |
| Showcase names and descriptions for the demo subset, written by an LLM and labelled as generated | tbd | Cosmetic |

### Tier 3: stretch, probably never

MongoDB change streams, vector search (pgvector against MongoDB `$vectorSearch`), product variants, category tree, K-means (degenerate on Olist:
about 3% of customers reorder), geospatial queries on the geolocation table (MongoDB
`2dsphere` against PostGIS), CPU and memory dashboard panels (need cAdvisor or exporters), full raw-SQL conversion.

**Cut rule.** At the 8 November checkpoint, a Tier 2 item that cannot be demoed that day is dropped. Tier 3 is not
started before the first full benchmark run exists (target 1 November).

## 5. Data: Olist, adapted

**Source:** Brazilian E-Commerce Public Dataset by Olist, CC BY-NC-SA 4.0. All nine tables are used (geolocation reduced to one point per zip prefix). Olist is
the only dataset; the ECB reference rates used for currency conversion are cited as a supporting source. Attribution and
the licence notice go in `docs/licenses/` and the report; derived data is shared under the same licence.

**Committed to the repository, so a marker needs no Kaggle account:** the raw CSVs in `data/raw/olist/` with SHA-256
checksums (check each file is under GitHub's 100 MB limit; the geolocation table is the largest), and the derived
artefacts that are slow or heavy to rebuild: the machine-translated reviews and the generated names, descriptions,
attributes, stock and lead times. The scripts that produced them are committed too, so they can be regenerated but never
have to be.

**Profile first.** A first profile ran on 21 October 2026; `analytics/profile_olist.py` (committed in `olist-import`)
reproduces it, and its output becomes the report's dataset section. What it settled:

| Question | Answer (profile, 21 Oct) | Consequence |
|---|---|---|
| Can one `product_id` be sold by several sellers? | Yes: 3.7% of products, carrying 12.8% of order lines | Shopee model (D1): every product belongs to one seller, so shared Olist products are split into one product per seller |
| Items per order | 90% of orders have one line; the same product repeats as separate lines in 6.9% of (order, product) pairs | Repeats collapse into one line with a quantity |
| Do payments sum to the order total (price plus freight)? | Compared exactly, 576 orders differ (273 by one cent, 303 by more) | All 576 are removed (R2); the deferred payment check then holds |
| Duplicate `review_id`s; empty review text | 814 duplicate ids, 547 orders with several reviews; 41% of reviews have text (about 2.8M characters) | Keep the latest review per order (removes 551); Olist review ids are not unique; translate all text once |
| Products without a category or translation | 610 without a category; 2 of 73 categories without an English name | The two translated by hand; the 610 go into an "Uncategorised" category |
| Names, descriptions, images | None in the data (only their lengths) | Generated, as planned |
| Category concentration | Top 15 categories cover 79% of order lines | Rich attribute templates for the top 15 |
| Date coverage | September 2016 to October 2018; the last full month is August 2018 | All dates shift by a fixed 426 weeks (below) |

**Cleaning rules.** The raw files are never edited. A cleaning script applies each rule before import and writes a ledger
(rule, rows removed or changed, reason) that becomes a table in the report, so every change to the real data is visible
and counted. The full rule list is in `docs/plans/olist-import.md`.

**Adaptations (all seeded, all labelled):**

| Field | Treatment |
|---|---|
| Category names | Olist's own English translation table; the two missing names translated by hand; products without a category go into "Uncategorised" |
| Product names and descriptions | Generated from templates: English category plus generated attributes |
| Product images | Every product shows an icon card (the category icon from the existing sprite, covering all 74 imported categories, plus the product name; D10) unless its seller uploaded a photo, served from MongoDB GridFS. The 15 featured stock photos (D11, D12) are dropped (catalogue amendment k) |
| Catalogue size | Seller-products in at least two distinct orders after cleaning (about 13.6k) are active and browsable; the rest (about 20k, mostly sold once in two years) are delisted: inactive, hidden from the shop, kept for order history, analytics and the benchmark (D13). Products created in the app are active |
| List price | Derived from real order prices (median per seller-owned product) |
| Shared products | Olist products sold by several sellers are split into one product per seller (32,951 become 34,448); each keeps Olist's id in a non-unique source column; counted in the cleaning ledger |
| Stock, lead time | Generated with a fixed seed |
| Category-specific attributes | Rich templates for the top 15 categories, a generic template for the rest; stored in MongoDB (and as EAV and JSONB copies for the benchmark) |
| Review text | All comments machine-translated offline once with a local model; original Portuguese kept; English labelled as machine-translated |
| Currency | Converted to SGD at **one fixed rate**: the European Central Bank reference rates (EUR/BRL and EUR/SGD cross rate) on the day `olist-import` executes. Lines rounded to the cent; checkout totals computed from the rounded lines; payments split in proportion with the rounding remainder on the largest, so they equal the total exactly. Raw BRL kept in the raw files |
| Dates | Shifted by one fixed offset of 426 weeks: 2016 to 2018 becomes November 2024 to December 2026: the last retained order is placed on 28 October 2026 and the last delivery falls on 16 December 2026, after the current date, so demo orders continue the timeline. Whole weeks keep weekdays (weekly patterns survive); the offset is a constant, never relative to today, so imports and benchmarks are reproducible. Raw files keep the original dates |
| Customers | One user per `customer_unique_id`, bulk-inserted with unusable passwords |
| Reviews | The latest review per order is kept (by answer time); reviews of orders never delivered are kept as history (R3); single-line orders map to their line; multi-line orders get a copy per line, flagged `from_order_review` |
| Freight and refunds | Each product's shipping fee is the median freight of its order lines; each imported cancelled order gets a refund row so refunds equal cancelled totals (`checkout` decisions b and c) |
| Order status | Olist's eight statuses map to ours: created → placed; approved, processing, invoiced → paid; shipped → shipped; delivered → delivered; canceled, unavailable → cancelled |
| Quantity | Repeated (order, product, seller) lines collapse into one line with a quantity |
| Sellers | The 3,095 Olist sellers become approved seller accounts with unusable passwords |
| Multi-seller orders | The 1.3% of Olist orders spanning several sellers split into one order per seller; the Olist order becomes the checkout and keeps its payments unchanged (D17) |
| Broken orders | Removed (D9, R2, R5): payments not exactly equal to price plus freight (576), no order lines (775), no payment (1), placed after August 2018 (20), delivery date contradicting the status (14), a `not_defined` payment; exact counts in the ledger |
| Geolocation | One centre point per zip prefix (about 19k of the 1M rows; 26% are exact duplicates), used for seller-to-customer distance in the delay analysis (T6b) |

**Import experience:** the importer prints progress per table, and the user manual states the expected import time and
memory on a typical laptop, so a long import never looks like a hang.

**Group accounts:** `seed_demo` creates usable logins (one customer per member, one operator, and one seller tied to a real
high-volume Olist seller so the seller pages show real products and sales).
Passwords are generated into the git-ignored `.env` by `init_env.py`. The hard-coded fallback password in
`seed_demo.py` is removed.

**Scale-up generator:** on 28 October the owner decided not to build it or promote a 10x run into Tier 1
([benchmark-i21](docs/DECISIONS.md)); it remains in Tier 2 `durability`. If earned, it would resample real Olist rows
with a seed, keep foreign keys valid, mark every row `is_generated`, and write identical CSV/NDJSON inputs for both
engines. Generated data would not be committed; the generator and an output checksum would be.

## 6. Features in detail (Tier 1)

**Checkout and orders.** One checkout per cart; it creates one order per seller. Each order moves
`placed → paid → shipped → delivered`, plus `cancelled`, and a trigger rejects invalid transitions. The seller marks their
own order shipped; the operator marks it delivered (acting as the courier), so the demo can buy, ship, deliver and review
on camera.

**Simulated payment.** A Pay button with a method picker: credit card, boleto, voucher, debit (Olist's own types). The app
writes a `payment` row (a row means money received; there is no payment status). **No card numbers are stored, even fake ones**; if card fields are shown for
realism they are format-checked in the browser and discarded (at most the last four digits are kept). Payments belong to
the checkout; a checkout may have several, and a deferred constraint trigger checks at commit that they equal the checkout
total (the sum of its orders).

**Seller scoping and uploads.** Sellers only ever read or change their own products and orders: every seller query filters
by the logged-in seller, with tests that one seller cannot reach another's rows (row-level security adds a database check
in Tier 2). Product photos: JPEG, PNG or WebP only (never SVG), at most 2 MB, re-encoded with Pillow to drop metadata,
then stored in GridFS; the old photo is removed when replaced.

**Per-item reviews.** One review per order line, enforced by a MongoDB unique index on `order_line_id`. Only the buyer of
that line, only when its order is `delivered` (checked in PostgreSQL); imported reviews of undelivered orders stay as history. Customers can edit or delete their own review.

**MongoDB data model (embed or reference, recorded in `docs/DATA_MODEL.md`).** The specification document **embeds** the
rating summary and the latest five reviews (MongoDB's subset pattern), so a product page is one read; **all** reviews
live in the `reviews` collection, **referenced** by product id, because they are unbounded. A review insert, edit or
delete updates the review, the rating summary and the embedded subset in one MongoDB transaction.

**Wishlist.** `wishlist_item` (customer, product, added_at), composite key. A trigger on stock going from zero to positive
records a restock alert shown to the customer.

**Cancellation.** A customer can cancel an order until the seller ships it. One transaction returns the stock, records a
`refund` row against the checkout and sets the status; the status trigger rejects a cancel after `shipped`. The
checkout's payments minus refunds still reconcile with its live orders.

**Activity events (M1).** Product views and searches go to a MongoDB time-series collection with a TTL index (30 days).
They drive recently viewed (per customer), trending now (views in the last 24 hours ranked with `$setWindowFields`) and a
views-to-purchases conversion figure on the seller page (views from MongoDB, purchases from PostgreSQL).

**Dashboard.** The stock-planning analytics (coverage, replenishment flags, category performance), rebuilt on the new
schema with the old baseline's queries as the starting point, with a materialized view and window functions, plus "products with poor reviews" from a MongoDB pipeline.

## 7. Benchmark protocol

**Build alongside the application.** After the `olist-import` exit checks pass and the benchmark plan is approved,
start the harness, isolated database loaders and correctness fixtures. Add B1 with `catalogue`, B2 with `reviews` and
`dashboard`, and B3/B6 with `checkout`; add B4/B5 as those workloads become available. A first correctness-complete
B1 to B6 pass is due by 30 October. Final repeated measurements run on 31 October to 1 November, after integration
and the application feature freeze. The benchmark is not left entirely to the final weekend; final acceptance still
requires the dependencies in section 14 and every check below.

**Workloads (each on identical data, each with golden outputs):**

| ID | Workload | PostgreSQL | MongoDB |
|---|---|---|---|
| B1 | Flexible attributes: filter by category-specific attributes | EAV table **and** JSONB with GIN (three-way) | Documents, multikey index |
| B2 | Aggregation: dashboard and review aggregates | Live CTE/window query; materialized-view read and REFRESH reported separately | Live aggregation pipeline |
| B3 | Last-unit race: 50 buyers, 10 units | Minimal identical operation: transaction, conditional decrement, insert order | Same: transaction, conditional `$inc`, insert order |
| B4 | Indexing: before and after for B1 and B2, told as one slow → index → fast story with plans | B-tree, composite, partial, GIN | Compound, multikey, partial |
| B5 | Storage footprint for the same data | Table and index sizes | Storage and index sizes |
| B6 | Isolation anomalies: a lost update under concurrency | Lost update under READ COMMITTED, prevented by `FOR UPDATE` and by SERIALIZABLE with retry | Write conflict and transaction retry |
| B7 (Tier 2) | Full-text search on review text (E1) | `tsvector` with a GIN index | Text index |

B3 compares **equivalent minimal operations**, not the app's full checkout (which carries idempotency and cart logic
that a minimal function would not). The app checkout is demoed, not raced.

**Correctness first.** B1/B2 match independent reference outputs computed from shared source files, with checksums,
canonical ordering, fixed decimal scales and exact counts. B3 ends with exactly 10 successes, 40 refusals, stock at 0
and no oversell. CI runs correctness checks; failed results/invariants contribute no accepted timing.

**Isolation from the app.** The dedicated `bench` Compose profile provides `bench-db` and replica-set `bench-mongo`,
with separate generated credentials and no app grant changes; [benchmark.md](docs/plans/benchmark.md) owns the setup
and measurement decisions. Every run starts from verified baseline data and resets afterwards, including failures.
Tier 1 measures base Olist; generated rows/flags stay in bench databases and scaled runs stay in Tier 2 `durability`.

**Method.**
- Identical Docker limits: 2 CPUs and 2 GB per engine; cache/client/VM settings are fixed in the benchmark plan.
- All final runs on one designated machine; CPU model, cores, RAM, OS and Docker version recorded with every result.
- Timed driver workloads: 1/10/50 clients (B2 1/10, [benchmark](docs/plans/benchmark.md) amendment k3), one untimed
  warm-up, five fixed-operation measured runs; report median per-run p50/p95/throughput and ranges, errors and
  retries. B5 records storage; B6 is a correctness demonstration outside that matrix, recording throughput/retries.
  Reset/warm-cache and latency accounting live in benchmark.md.
- Engine comparison timed **at the driver level**. The separate HTTP load script is cut ([benchmark](docs/plans/benchmark.md)
  amendment j); per-request database timing (below) shows the database share of each request.
- Query plans captured beside timings: `EXPLAIN (ANALYZE, BUFFERS)` and MongoDB `explain("executionStats")`.
- `docker stats` sampled every second during each run (CPU and memory per container).
- **Headline results as ratios** (more portable across machines), absolute milliseconds as detail.
- Telemetry and application caches off (none in Tier 1); database buffers follow the warm-up/reset procedure.
- Raw output in `benchmarks/results/`, dated, with the commit hash.

**Per-request database timing (Tier 1, no new containers):** Django's `connection.execute_wrapper` and PyMongo's
`CommandListener` record query time and count per request into the existing JSON request log and a `Server-Timing`
header (visible in browser DevTools). This shows how much of each request is database time against Django overhead,
which is the evidence for timing engines at the driver level.

**Questions, fairness and the comparison beyond speed.** Each workload answers a stated design question with an
expected outcome committed before the final runs, under explicit fairness rules (idiomatic models, equal index effort,
equal durability settings, stated limits). The report also compares data modelling, consistency guarantees,
constraint support and schema flexibility, with evidence per criterion; [benchmark.md](docs/plans/benchmark.md)
(amendments f to i) owns all three.

## 8. Observability (Tier 2, Erfan)

- One container: `grafana/otel-lgtm` (OpenTelemetry collector, Tempo, Prometheus, Grafana). Confirm the image tag and the
  instrumentation package versions in a short spike.
- OpenTelemetry instrumentation for Django, psycopg and PyMongo; spans carry the database system and operation.
- One dashboard, committed as JSON and loaded automatically: (1) p50 and p95 query latency, PostgreSQL against MongoDB, by
  operation; (2) queries per request (catches N+1); (3) slowest statements; (4) checkout transaction time with MongoDB
  retries and aborts; (5) error rate. No CPU or memory panels.
- **Overhead measurement:** the same workload with `OTEL_SDK_DISABLED=true` and with telemetry on, at least 5 runs each,
  reported as a percentage per engine (or "below measurement noise"); sampling rate recorded.
- Effort: about 1.5 to 2 days. Independent of the critical path.

## 9. Changes since the proposal (for the report)

| Proposal | Now | Reason |
|---|---|---|
| Two interchangeable back ends switched by a setting | Polyglot persistence plus a benchmark harness | Duplicating transactional data in MongoDB served no application purpose; every promised comparison still runs on identical data and workloads |
| Stock and checkout on both engines in the app | Checkout in PostgreSQL; the last-unit race on both engines in the harness | Same comparison, without a second checkout to maintain |
| Reviews linked to the products in their order | One review per order line (Shopee model) | Correct product ratings for multi-product orders |
| Merchants as stretch | Sellers are a full role in Tier 1 (register, manage their own products, ship their own orders); row-level security in Tier 2 | Makes CRUD on both databases natural to demo; matches how Shopee works |
| MongoDB change stream | Dropped (Tier 3) | No Tier 1 feature needs asynchronous processing; the rating summary is kept correct inside a MongoDB transaction instead |
| (not in proposal) | Redis, observability (Tier 2) | Added scope, earned at the checkpoint |
| (not in proposal) | Three roles, cancellation with refund, activity events, end-to-end tests (Tier 1) | Rubric and scope reviews on 21 October |

Kept as promised: Olist, CRUD on both databases, EAV against JSONB with GIN, triggers, views and materialized view
against aggregation pipelines, last-unit concurrency, indexing, the 1/10/50 protocol with correctness checks,
limited-privilege users on both databases, replica set in Compose.

## 10. Rubric map

| Rubric item | Weight | What earns it |
|---|---|---|
| Project quality and implementation | 40% | Significant work on both databases, real data, working demo, CI, tests |
| Presentation | 25% | Fixed order: background, relational, NoSQL with comparison, performance. All five present, names on screen |
| Final report | 25% | 10 pages, Calibri 12; methods, results, implications; changes since the proposal |
| Proposal | 10% | Done |
| Extra credit | n/a | Triggers (including audit), deferred constraints, materialized view, window functions, pipelines, `$facet`, transactions, analytics (Bayesian rating, forecast, delay analysis), time-series collection and TTL, end-to-end tests, observability, Redis, replication and failover, full-text search |

Performance analysis is optional in the brief, but the "rigorous comparison" (presentation part iii) and the analysis in
the top band of both the presentation and report rubrics are graded; the benchmark is how we deliver both.

## 11. Repository conversion (`foundation`, about 1.5 to 2 days; plan in `docs/plans/foundation.md`)

Fresh repo from the commands already given (no history, private). Then:

| Item | Action |
|---|---|
| `src/config/secrets.py`, boto3, `tests/test_secrets.py` | Delete; secrets from `.env`; keep the 50-character secret-key check |
| `src/certs/`, `POSTGRES_SSLROOTCERT` in `Dockerfile` | Delete |
| `src/config/database.py` | Keep optional `sslmode`; drop RDS verify-full behaviour; adjust tests |
| `HealthProbeMiddleware`, `HEALTH_PROBE_HOST`, `DJANGO_TRUST_PROXY` | Delete; keep `/health/` |
| `DJANGO_ENV` switch | Removed; one configuration with today's local values (HTTP, no HSTS, `DEBUG` off by default) |
| Request logging, DB-unavailable 503, JSON log | Keep; rename `northstar.*` loggers; becomes the home of per-request DB timing |
| `src/tools/db_bootstrap.py`, `src/docker/10-local-role.sh` | Replaced by two roles in the PostgreSQL init script: owner (migrate, import, pytest) and runtime (web, data changes only) (foundation-g) |
| Shoe code and data: `catalogue/shoes.py`, `analytics/build_shoe_dataset.py`, `data/raw/` and `data/derived/`, `src/static/models/` (3D shoes), shoe glyphs, the `CustomerSegment` model and migration | Delete in `olist-import` when the Olist import replaces them (K-means scripts go in `foundation`, decision foundation-b) |
| `tests/load/` | Deleted (foundation-h); the replacement local HTTP load script was later cut by [benchmark amendment j](docs/plans/benchmark.md#decisions) |
| `scripts/package_submission.py` | Adapt to the INF2003 zip |
| Compose | One root file, renamed; add `mongo` as a single-node replica set with a `readWrite`-only application user; latest stable PostgreSQL and MongoDB, pinned by digest |
| `.vscode/settings.json` | Cross-platform |
| `DESIGN.md` | Strip dead links and AWS text only; the full rewrite for Mercer moves to `catalogue` (decision foundation-a) |
| `AGENTS.md`, `CLAUDE.md` | Rewritten for INF2003 (done; see below) |
| Per-folder READMEs (`analytics/`, `src/`, `tests/`, `data/`) and the data dictionaries | Merge what is still true into `README.md` and `docs/DATA_MODEL.md`, delete the rest (fewer documents to keep in sync) |
| `scripts/check_docs.py`, `.githooks/pre-commit` | New: documentation checks run as a git hook and in CI (see AGENTS.md, Documentation) |

**AGENTS.md** (canonical for Codex and Claude Code; CLAUDE.md imports it): the architecture and ownership table; rules
(parameterised queries only; checkout never reads price or stock from MongoDB or Redis; Redis never holds source-of-truth
data; real databases in tests, never mocks or SQLite; no card numbers stored); the workflow (plan, review, implement,
review, record, fix, close out); the documentation rules and docs map; branch per workstream, no direct pushes to
`main`; every AI-assisted commit carries a `Co-Authored-By` trailer; how to run, test and benchmark.

**Repo layout:** `README.md` (overview and user manual), `AGENTS.md`, `CLAUDE.md`, `RUBRICS.md`, `DESIGN.md`, `compose.yaml`, `src/`, `tests/`, `analytics/`,
`data/`, `benchmarks/` (harness, `results/`), `.github/workflows/ci.yml`, `CONTRIBUTIONS.md` (one page,
updated at each checkpoint, for fair peer review), and `docs/` with `DATA_MODEL.md` (PostgreSQL schema with ER diagram, and the MongoDB model),
`DECISIONS.md`, `AI_USE.md` (including the disclosure that the codebase builds on our earlier module project), `plans/`
(one per workstream, kept after close-out as the record) and `licenses/`. Benchmark tables are generated from `benchmarks/results/`, not hand-written.

**Tests.** Most existing tests assume the shoe data. `olist-import` deletes the shoe-specific tests and writes new ones for the
Olist import and schema; every later workstream brings its own tests. Tests that check behaviour independent of the
dataset (security negatives, idempotent checkout, database unavailability) are ported rather than deleted. CI runs
against a small committed fixture subset of Olist, not the full dataset.

**Reuse of our earlier module project:** retain the disclosure in `docs/AI_USE.md` and report appendix D; written
approval is not required under [the 31 October owner decision](docs/DECISIONS.md#reuse-disclosure-31-october-2026).
The proposal does not mention the reuse.

## 12. Team and work split (proposal; edit freely)

| Member | Role | Tier 1 work |
|---|---|---|
| **Chee Long** | Main developer and plan owner | Most of Tier 1 after `foundation`: `olist-import`, `accounts`, `checkout`, `catalogue`, `wishlist`, `dashboard`, `reviews`, `activity`, `benchmark`, `ci`; owns the accounts, catalogue, checkout, reviews, benchmark, ci and Phase 1B review plans |
| **Erfan** | Planning and setup | PLAN.md and other workstream plans; the coding setup (AGENTS.md, workflow, docs check); `foundation`; Tier 2 `observability` |
| **Joash** | Supporting developer, QA | MongoDB: specifications, reviews, pipelines (his proposal role), reviewed by Erfan |
| **Jun Keat** | Supporting developer, QA | UI: catalogue, shop pages, cart and pay flow, reviews, wishlist; design standardisation; triggers with Chee Long |
| **Syahfariz** | Supporting developer, QA | Test plan and correctness gates, clean-machine run of the user manual, slides and video |

After `foundation`, Chee Long has agreed to implement most of Tier 1 (about 70 to 80%), primarily with AI assistance.
**Every GPT-authored change, including plans, documentation and tests, is reviewed in a fresh Claude Code session
before any commit.** The review runs the applicable tests and exit checks from AGENTS.md, records findings and checks
the fixes. GPT agents leave changes uncommitted for that review and commit only when the user explicitly asks after
review; there is no automatic commit or push. This is the user's review instruction of 22 October.

Every member presents in the video; `docs/OVERVIEW.md` is the plain-language guide for the team. Chee Long carries
most of the development; the supporting members' work is smaller but recorded in `CONTRIBUTIONS.md`. The team writes,
edits and presents the deliverables together, with no single report editor ([deliverables](docs/plans/deliverables.md)
decision a). Report, slides and video preparation may follow the accelerated application and benchmark sprint.

## 13. Phases

**Schedule revision, 22 October 2026.** The stretch target is the complete Tier 1 application plus validated benchmarks
B1 to B6 by **1 November**. Application feature freeze is **30 October**. **2 to 4 November** is contingency for fixes,
retests and reruns if needed; it does not change the target or justify silently cutting Tier 1 scope. The report,
slides and video are outside this accelerated target and remain due with the final submission on **29 November,
23:30 Singapore time**; the team still aims to submit on 28 November.

**Phases start on completion, not on a date (22 October 2026).** A phase may start as soon as the phase before it is
closed: its exit check has passed and its work is merged to `main`. It does not wait for its window to open. The dates
below are targets and deadlines, not start gates; finishing early moves the next phase forward. Agents use this rule
for the AGENTS.md phase check. These dates and phase assignments take precedence over older calendar dates in the
workstream plans and the team overview. Approved contracts, dependency order (section 14), real-database tests and
exit checks remain binding: within a phase, a workstream still waits for its dependencies (for example `checkout`
after `accounts`). Unfinished work can continue later, with any missed target recorded. Phases may overlap; the
benchmark can build its harness after import while final acceptance waits for its feature dependencies.
Existing effort estimates remain risk estimates, not evidence that the compressed dates are guaranteed.

| Phase | Dates | Build (Chee Long unless noted) | Write plans | Exit check |
|---|---|---|---|---|
| **0 Setup** | 21 to 22 Oct | `foundation` (Erfan; marked done in section 14) | Existing feature plans approved; prepare `benchmark` and `ci` plans | Repo runs on Linux and Windows with both databases; professors' written approval (superseded by [the 31 October owner decision](docs/DECISIONS.md#reuse-disclosure-31-october-2026)) |
| **1A Import** | 22 to 24 Oct | `olist-import` (Erfan optionally on the cleaning script) | Approve `benchmark` and `ci` plans by 24 Oct, before their implementation | Olist loaded in both databases; the ledger and money invariants reconcile; product pages and demo logins work; full import exit checks pass |
| **1B Accounts** | 25 Oct | `accounts`; start `ci` (Chee Long) after its plan is approved | none | The three roles log in; seller approval and operator controls work; CI runs the real-database checks available so far |
| **2A Checkout** | 25 to 26 Oct, after `accounts` | `checkout`; benchmark correctness cases for B3/B6 as checkout lands | none | Buy from three sellers in one checkout, ship, deliver, cancel with refund; stock, payments, permissions and retries pass their tests |
| **2B Catalogue** | 26 to 27 Oct, after `accounts` | `catalogue`; benchmark B1 cases | none | **27 Oct core-demo checkpoint:** buy, ship and deliver end to end; seller CRUD with photo upload; faceted search and schema evolution; full workstream exit checks pass |
| **3A Features** | 28 to 29 Oct | `wishlist`, `dashboard`, `reviews`, `activity`; complete `ci` (Chee Long), including Playwright demo tests and quality gates | none | Every Tier 1 application feature works end to end; CI green on `main` |
| **3B Benchmark** | 25 Oct to 1 Nov; final measurements 31 Oct to 1 Nov | Build the harness alongside features after import; load isolated `bench` databases; B1 to B6 with golden outputs, query plans, `docker stats` and per-request timing (HTTP load script cut, generator deferred: benchmark amendment j) | none; approved plan required before implementation | First correctness-complete B1 to B6 pass by 30 Oct; by **1 Nov**, applicable repeated runs at 1/10/50 clients and the separate B6 correctness demonstration, with plans, hardware/configuration and raw outputs saved on the designated machine (section 7) |
| **4 Freeze** | 30 Oct to 4 Nov | **30 Oct application feature freeze** and full integration review; fresh-install verification; fixes and affected reruns only, plus `ci` stage 3 (the deferred `ruff format` gate), with 2 to 4 Nov reserved as contingency | none | Full suite and demo pass; the manual works on a clean machine; Claude Code reviews completed before commits; unresolved failures remain visible |
| **5 Ship** | 2 to 29 Nov | Report, slides, video (all five, names on screen, under 10 minutes), final user manual and packaging; professor check-in and Tier 2 decision on 8 Nov | `deliverables`: report outline with page budget, scripted presentation and theory map appendix; Tier 2 plans only if earned | Report at 10 pages; final manual passes on a clean machine; zip checked by the packager; target submission 28 Nov (deadline 29 Nov, 23:30) |

**26 October 2026: Phase 3A exit check passed.** Every Tier 1 application feature is merged and [CI is green on main](https://github.com/ZadeNova/INF2003_Database_Project/actions/runs/40210271108).

**28 October 2026: Phase 3B first correctness-complete pass landed before the 30 October target.**
[Local full-data B1–B6 evidence](benchmarks/results/2026-10-28T000105_e23a4df4_full-correctness/summary.csv)
passes every workload and variant, with plans and restoration evidence. Fresh review and the designated-machine
final measurements remained at that checkpoint; section 14 kept the workstream in progress.

**30 October 2026: Phase 4 exit check passed.** The application is frozen. After the integration and checkout fixes
(PRs #24, #25) and CI stage 3 (PR #26), [CI is green on main](https://github.com/ZadeNova/INF2003_Database_Project/actions/runs/40906382080)
at `69d88c2`: the full suite, the smoke check, the Chromium journeys and the format gate. A fresh install from a new
clone with no `.env` and fresh volumes, following the README in its own Compose project, passed import, verification,
seeding, smoke and the browser journeys ([CI review notes](docs/plans/ci.md#review-notes)). That ran on the owner's
machine; a run on a teammate's machine stays in Phase 5's clean-machine check. Claude Code reviewed each Phase 4 change
before merge, not in fresh sessions ([CI](docs/plans/ci.md#review-notes) and [checkout](docs/plans/checkout.md#review-notes)
review notes). Phase 3B stayed open for the designated-machine final measurements, which do not change the application.

**2 November 2026: Phase 3B exit check passed on the designated machine, in the contingency window.**
The [item-by-item benchmark close-out](docs/plans/benchmark.md#designated-machine-final-and-close-out-2-november-2026)
links the repeated final measurements, the fresh B3/B6 retry after an unexpected OOM, plans, storage, resources,
[BM4 negative controls](benchmarks/results/2026-11-02T110623_b53e5d0a_final-bm4/bm4-verification.json) and
[per-request database timing](benchmarks/results/2026-11-02T103305_b53e5d0a_request-timing/requests.csv).
The original target date is unchanged. The [owner's source rule and resource observation](docs/DECISIONS.md#benchmark-designated-machine-final-and-close-out-2-november-2026)
retain the failed attempt and assign B3/B6 to the separate fresh run. Claude Code reviewed the close-out before
commit; phase closure still follows the completion/merge rule above.

**Checkpoints and completion.** If the import is not verified by 24 October, or the core demo is not working by
27 October, Chee Long and Erfan re-estimate the remaining work immediately. If a workstream overruns by more than a
day, Erfan assigns `wishlist` or `activity` to another member under its approved plan. Do not shorten database tests,
skip Claude Code review, count incorrect benchmark runs or mark a missed exit check done to preserve the date.

The 1 November target is met only when the full Tier 1 application passes its tests and demo, and B1 to B6 pass
correctness checks with the measurements required by section 7 saved reproducibly. The 8 November professor check-in
and Tier 2 cut rule remain; Tier 2 is not part of this sprint and requires its own approved plan if earned. Evidence
needed later (cleaning ledger, query plans, raw benchmark outputs and decisions) is saved as the work finishes;
writing the report and preparing slides/video can wait until the application and benchmark sprint is complete.

## 14. Workstreams (one plan file each in `docs/plans/<name>.md`, contract first, kept after close-out as the record)

The workstream name is also the branch prefix (`checkout/payment-trigger`) and the label used in chat and the video.

| Workstream | Scope | Depends on | Tier | Status |
|---|---|---|---|---|
| `foundation` | Repo conversion, AWS removal, MongoDB in Compose, latest versions pinned, docs consolidation and check | none | 1 | done |
| `olist-import` | **Olist profile, cleaning, schema (ER diagram, 3NF), import, adaptations, users** | `foundation` | 1 | done |
| `accounts` | Three roles, seller registration and approval, operator console (approve, reject, suspend or reinstate sellers, audit log) | `olist-import` | 1 | done |
| `catalogue` | Catalogue, specifications in MongoDB, faceted search, schema-evolution demo (category attribute templates), shop pages, icon cards and seller-uploaded photos in GridFS (featured stock photos dropped by amendment k), seller product CRUD with photo upload and audit trigger, `DESIGN.md` rewrite | `olist-import`, `accounts` | 1 | done |
| `checkout` | Cart across sellers, checkout split into one order per seller, simulated payment, order lifecycle (seller ships, operator delivers), cancellation with refund | `olist-import`, `accounts` | 1 | done |
| `activity` | Activity events in MongoDB: recently viewed, trending now, seller conversion (M1) | `catalogue`, `checkout` | 1 | done |
| `reviews` | Per-item reviews, Bayesian average rating | `catalogue`, `checkout`, `accounts` | 1 | done |
| `wishlist` | Wishlist and restock alerts | `catalogue`, `checkout` | 1 | done |
| `dashboard` | Stock-planning dashboard on Olist, demand forecast, delivery delay against review score | `checkout`, `accounts` | 1 | done |
| `benchmark` | Benchmark harness (B1 to B6), per-request timing, protocol (generator deferred by amendment j); build incrementally during the sprint | `olist-import` for harness/loaders; `catalogue`, `checkout`, `reviews`, `dashboard` for full acceptance | 1 | done |
| `ci` | CI and correctness gates, Playwright end-to-end tests of the demo story, `ruff`, coverage threshold, `pip-audit` (E4, E5); start 25 Oct and extend as features land | `foundation` | 1 | done |
| `deliverables` | Report (outline with a page budget; figures; theory map appendix), slides, video following the scripted demo story, user manual, packaging; report/slides/video follow the accelerated sprint | all for final acceptance; setup instructions maintained with code | 1 | ready |
| `improvements` | Prioritised backlog from the 2 and 8 November full-stack reviews (Erfan, sole approver while Chee Long is away); settled and built in batches on the current branch, see [the plan](docs/plans/improvements.md) | the frozen Tier 1 application | 1 | in progress (batches 1 to 3 built) |
| `product_photos` | Photos for 30 Olist products and a teammate's merchant with up to 12 new products, loaded from committed files by `seed_showcase`; optional 3D models as a stretch; see [the plan](docs/plans/product_photos.md) | the frozen Tier 1 application | 1 | loader built; data lane open |
| `redis` | Redis sliding-window rate limiting and two cache-aside reads (dashboard history, trending), measured off, cold, warm and down; see [the plan](docs/plans/redis.md) | `dashboard`, `activity` | 2 | built 8 Nov (limiter, trending and dashboard caches); first review fixed, second review pending; measurement scripts in Batch 6 |
| `observability` | Observability (`grafana/otel-lgtm`) | `foundation` | 2 | not started |
| `seller-rls` | Row-level security for sellers, seller-scoped dashboard | `checkout` | 2 | not started |
| `durability` | Durability benchmark, replication and failover (E6), backup and restore drill (E7), scale-up runs | `benchmark` | 2 | not started |
| `search` | Full-text search on review text, benchmark B7 (E1) | `reviews` | 2 | not started |
| `qa` | Product Q&A (M2) | `catalogue` | 2 | not started |

Status is one of: not started, planning, ready (plan approved, waiting for implementation), in progress, review, done. This column is the only progress index; update it when
a workstream changes state, and keep each plan file as short as its contract allows (about one page where possible).

**29 October 2026 checkout follow-up:** Chee Long approved Phase 4 fixes to the completed checkout contract for the
independent money-SQL review: lock order, runtime DELETE privileges and missing race coverage; document the finer
refund/line invariants. No new feature or trigger scope. The accepted workstream remains done; Claude Code reviewed
and approved the fix branch on 29 October 2026; see [the checkout review notes](docs/plans/checkout.md#review-notes).

## 15. Decisions

**Settled** (21 October 2026; reasons in the sections above and in the plan files):

- **Architecture:** polyglot persistence plus a benchmark harness; each value in one store; raw SQL only where it shows a
  construct; English throughout; latest stable PostgreSQL and MongoDB pinned by digest (D4, foundation-d, foundation-f);
  MongoDB in Compose from `foundation` (foundation-c); owner and runtime PostgreSQL roles, pytest as the owner (R1).
- **Data:** Olist is the only dataset (D8), ECB rates cited as a supporting source; shared products split per seller
  (D1); categories (D5); one geolocation point per zip prefix (D6); dates shifted 426 weeks (D7); broken orders removed,
  including all 576 payment mismatches and the 20 orders after August 2018 (D9, R2, R5); latest review per order, reviews
  of undelivered orders kept (R3); bigint ids with Olist ids as source columns (R6); cleaning in a script before import.
- **Catalogue:** every product shows an icon card (D10) unless its seller uploaded a photo, served from GridFS. The
  featured stock photos (D11/D12) are dropped (catalogue amendment k, 27 October 2026). Active catalogue = seller-products in at least two orders (D13); rich
  attribute templates for the top 15 categories.
- **Roles and orders:** customer, seller and operator in Tier 1 with row-level security in Tier 2 (D14 to D16); one
  checkout with one order per seller and payments on the checkout (D17); "seller" as the single term (D18); a custom user
  model with a role field (R7); cancellation with refund. `accounts`: one role per account, an audit log filled by
  triggers with the actor passed by `SET LOCAL`, a `rejected` seller status, operators created only by `seed_demo` or a
  command with the password from `.env`. `checkout`: one-step place and pay (orders start as `paid`), shipping fee from
  each product's median historical freight, refunds equal cancelled totals (imported cancellations get refund rows),
  whole-order cancellation as on Shopee.
- **Phase 2 and 3 plans** (approved 21 October): `catalogue` (MongoDB narrows and counts facets, PostgreSQL filters
  price, sorts and paginates; `pg_trgm` name search; PostgreSQL-first cross-store writes with a repair check; take-down
  flag), `wishlist` (partial unique index on unseen alerts; in-app only), `dashboard` (as-of the latest imported order date, excluding demo orders and later events;
  amendment a confirmed 24 October 2026; `SECURITY DEFINER` refresh; cross-store join in Python), `reviews` (Bayesian constants
  fixed at import; running sum; take-downs in `audit_log`), `activity` (seeded synthetic events; `w: 1` writes).
- **Added scope:** faceted search and schema evolution; Bayesian rating; demand forecast; delivery-delay analysis; 3NF
  justification; isolation benchmark (B6); audit trigger; activity events (M1); Playwright end-to-end tests and
  code-quality gates in `ci` (E4, E5). Tier 2: full-text search (E1), replication and failover (E6), backup and restore
  drill (E7), product Q&A (M2). The old load harness is deleted (R4); CI now starts during the accelerated sprint
  (22 October schedule revision, section 13).
- **Cross-plan review** (21 October): PostgreSQL filters first and MongoDB counts facets on those ids, "Top rated"
  sorted in the pipeline (X1); MongoDB 9.0 tests and exit checks run on Windows, where the team works, not on
  Erfan's affected Linux kernel (X2); products left without order lines are dropped (X3); the importer disables
  triggers while loading and checks the invariants with queries (X4); `taken_down` and a `purchasable_product` view
  live in `olist-import`; one idempotent `mongo_setup` command; runtime privileges granted in the first migration.
- **Deliverables:** a professor check-in at the 8 November checkpoint, a scripted demo story, a report outline with a
  page budget, and a theory map appendix. The team writes and edits the report together, with no single editor (D2,
  closed 30 October 2026 by [deliverables](docs/plans/deliverables.md) decision a).
- **No further scope additions.**

**Schedule and review revision (22 October 2026).** The user requested the full Tier 1 application and benchmarks
B1 to B6 by 1 November, with report, slides and video on the final-submission timeline. Section 13 replaces the
earlier phase dates, brings CI and benchmark development forward, and preserves all contracts and correctness gates.
Every GPT-authored change requires fresh Claude Code review before any commit (section 12). The user requested that
this revision initially remain uncommitted, then explicitly authorised committing and pushing this PLAN.md-only
revision without Claude Code review as a one-time exception on 22 October. The exception does not cover subsequent
GPT-authored work; future commits require the review and an explicit user request.

**Open:**

| ID | Question | Recommendation |
|---|---|---|
| D3 | Tier 2 owners other than observability | Decide at the 8 November checkpoint |

## 16. Risks

| Risk | Mitigation |
|---|---|
| The import (`olist-import`) slips and blocks everything | Verify the full import by 24 Oct; re-estimate immediately if it slips; Erfan can help with cleaning |
| Unfair comparison | Equivalent minimal operations, identical data files and limits, golden outputs, plans captured |
| No clear difference at about 100k rows | Driver-level timing; report differences within the baseline's noise. On 28 October the owner decided against building the generator or promoting a 10x run into Tier 1 ([benchmark-i21](docs/DECISIONS.md)); it stays Tier 2 `durability` |
| Generated fields weaken "real-world data" | Every generated field labelled; real orders, sellers, reviews and payments dominate |
| Results depend on the machine | One designated machine, hardware recorded, ratios as headline |
| Telemetry or cache skews timings | Both off during timed runs; overhead measured separately |
| One main developer: a delay or absence stalls Tier 1 | Approved feature plans let another member pick up a workstream; approve benchmark/CI plans before their code starts |
| The 1 November target compresses an already AI-assisted plan | Reassess at the 24/27 Oct checkpoints; freeze application features on 30 Oct; reserve 2 to 4 Nov for contingency; retain full Tier 1 scope and exit checks |
| Benchmark development or Claude Code review is left until the end | Build workloads alongside features and review each batch before any commit; first correctness-complete B1 to B6 pass by 30 Oct |
| Agents produce code no one can explain | `docs/DECISIONS.md`; each owner presents their part |
| Video over 10 minutes | Script by section; cut to 9:30 |
| Recording-day dependency: Insights' rolling sales window is near-empty after the imported data ends, by 25 November, and empty after 27 November | Follow [deliverables](docs/plans/deliverables.md) decision c and the [recording-day checklist](docs/plans/deliverables.md#recording-day-checklist). Keep the real rolling window because browsing events expire |
| Recording-day dependency: the dashboard takes a few seconds on the full data | Follow the [recording-day checklist](docs/plans/deliverables.md#recording-day-checklist); accept the cross-store join cost for Tier 1 and leave caching to the Tier 2 redis workstream |
| CI is incomplete while early workstreams land | Start CI on 25 Oct and complete it by 29 Oct; until then, review runs the applicable full suite in Docker before workstream commits/merges |
| MongoDB 9.0 does not start on some Linux kernels (SERVER-121912) | The team works on Windows; tests and exit checks run there (X2, foundation-m) |
| Cleaning distorts the real data | Raw files untouched; every rule counted in the import ledger; analyses re-run on the cleaned data |

## Sources checked

- Olist dataset (CC BY-NC-SA 4.0): https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
- Repeat-customer share on Olist (about 3.1%):
  https://aioconquer.aivietnam.edu.vn/posts/why-customers-never-return-the-dark-side-of-olist-s-logistics
- MongoDB Search and Vector Search for Community Edition (Tier 3 reference):
  https://www.mongodb.com/products/updates/now-ga-mongodb-search-and-vector-search-for-community-edition/
