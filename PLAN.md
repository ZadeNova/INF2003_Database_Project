# INF2003 plan: Mercer, a lean marketplace on PostgreSQL and MongoDB

Draft v4, 21 October 2026. Team 82. Status: **for the team to edit**. Nothing here is implemented yet.
Final submission: **Sunday 29 November 2026, 23:30**. The proposal (4 October) was marked "a solid plan and a clear scope".

**In one paragraph.** A lean Shopee-style marketplace (customers, sellers, an operator) on the real Olist dataset.
PostgreSQL is the system of record; MongoDB owns product specifications, reviews, photos and activity events; a benchmark
harness compares both engines on identical data and workloads. Scope is tiered: Tier 1 is the A-grade core; Tier 2
(Redis, observability, row-level security, replication and failover, full-text search, product Q&A) is earned at the
8 November checkpoint. The first workstreams are `foundation` (repo conversion) and `olist-import`.

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
                                    |                  orders, payments, wishlist, inventory, analytics
                                    +-> MongoDB         product specifications (flexible attributes), reviews,
                                                        photos (GridFS), activity events (time-series)
                                                        (single-node replica set, needed for transactions)
benchmarks/ harness -> both engines, loaded with the same clean Olist files (and scale-up files)
Docker Compose: web, db, mongo, migrate   (+ redis, otel-lgtm in Tier 2)
```

**Latest versions.** The brief asks us to explore the latest relational and NoSQL systems, so both engines run the latest
stable release at the time `foundation` pins the images (checked, not assumed). The report shows at least one recent
feature of each (for PostgreSQL 18, for example `uuidv7()`, virtual generated columns or `RETURNING OLD/NEW`).

**Ownership by field, never copied.** No value lives in both stores in the application, so no synchronisation machinery
is needed.

| Data | Store | Why |
|---|---|---|
| Users and roles, sellers (with approval status), products (each owned by one seller, with name, price and stock), carts, checkouts, orders (one per seller per checkout), order lines, payments (on the checkout), refunds, wishlist | PostgreSQL | Money and stock need ACID, constraints and triggers |
| Inventory snapshots, analytics runs, daily sales | PostgreSQL | Rebuilt on the new schema in `dashboard` (queries ported from the old baseline) |
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

### Tier 1: the A-grade core (done by the 18 November freeze)

| # | Item | Database content shown |
|---|---|---|
| T1 | **Olist import** replacing the shoe data, with documented cleaning rules (`olist-import`) | Real data, about 100k orders; FK integrity at import; ER diagram with the normalisation (3NF) justified, and the deliberate denormalisation in MongoDB explained (module theory) |
| T1b | **Three roles and accounts**: customer, seller, operator; seller registration and approval; operator console (approve or suspend sellers, take down products and reviews, category attribute templates, audit log) | Role-based access; seller status workflow enforced by a constraint and a transition trigger; sellers scoped to their own rows in every query |
| T2 | **Catalogue and seller shop pages**: generated English names and descriptions, product images (D10 to D12), an active catalogue of products ordered at least twice (D13), specifications in MongoDB, attribute search with **faceted filters** | Document model, `$jsonSchema` validation, multikey index; a `$facet` pipeline returns results plus counts per category, rating and attribute in one query; **live schema evolution** (a new attribute for a category with no migration, against `ALTER TABLE`) |
| T2b | **Seller product CRUD**: sellers create, edit and deactivate their own products (price, stock) in PostgreSQL, edit specifications in MongoDB and upload a photo to GridFS; the operator can take products down; deactivate instead of delete | CRUD on both databases (a brief requirement); `ON DELETE RESTRICT` protects products with order history; restocking drives the T5 trigger; an **audit trigger** records every price and stock change (who, when, before and after as JSONB) |
| T3 | **Cart across sellers, checkout split into one order per seller, simulated payment, order lifecycle** (the seller marks shipped, the operator marks delivered), **cancellation before shipping** (stock returned and a refund row recorded in one transaction) | `FOR UPDATE`, idempotency constraint, a compensating transaction for cancellation, payment rows on the checkout, deferred constraint trigger (payments equal the checkout total), status-transition trigger |
| T4 | **Per-item reviews** in MongoDB; customers can edit or delete their own review | Unique index on `order_line_id`, subset pattern, transaction (review plus rating summary), aggregation pipelines; **Bayesian average rating** for product and seller ranking, the same formula in SQL and in a pipeline (analytics algorithm) |
| T5 | **Wishlist with restock alert** | Many-to-many table, trigger |
| T6 | **Stock-planning dashboard** on Olist, with a **moving-average demand forecast** | Materialized view, CTEs, window functions; the same queries as aggregation pipelines in the harness |
| T6b | **Delivery delay against review score**: dashboard panel (sellers at risk of poor reviews) and a report section | Cross-store analysis: delay from PostgreSQL, score from MongoDB; the report's main implications finding |
| T6c | **Activity events** in MongoDB (M1): recently viewed for customers, trending now on the home page, views-to-purchases conversion for sellers | Time-series collection, TTL index, `$setWindowFields` ranking; the only write-heavy MongoDB workload; a second cross-store query |
| T7 | **Benchmark harness** (section 7, B1 to B6), with per-request database timing and a `docker stats` sampler | The rigorous comparison, including isolation anomalies (module theory) |
| T8 | **CI**: GitHub Actions running the suite against real PostgreSQL and MongoDB, **Playwright end-to-end tests of the demo story** (E4), `ruff` lint and format, a coverage threshold and `pip-audit` (E5) | "Well tested"; correctness gate for the benchmark |
| T9 | **Report, slides, video, user manual** | 50% of the marks |

### Tier 2: earned at the 8 November checkpoint

| Item | Owner | Content |
|---|---|---|
| **Redis**: cache-aside on dashboard and reviews, rate limiting on login and review posting; cache-on against cache-off measurement | tbd | Key-value NoSQL; counts towards the rubric directly |
| **Observability**: `grafana/otel-lgtm` (OpenTelemetry collector, Tempo, Grafana in one container), OpenTelemetry instrumentation for Django, psycopg and PyMongo, one committed dashboard (section 8) | Erfan | Query spans per request, PostgreSQL against MongoDB latency; telemetry overhead measured |
| **Row-level security for sellers** (database-enforced isolation under Tier 1's app-level scoping) and a seller-scoped dashboard | tbd | Multi-tenant isolation |
| **Durability, replication and failover**: a 3-member MongoDB replica set and a PostgreSQL streaming replica; `synchronous_commit` against write concern `majority`; kill the primary on camera and show failover (E6); a timed backup and restore drill with `pg_dump`/`pg_restore` and `mongodump`/`mongorestore` (E7) | tbd | Write/durability axis promised in the proposal; replication is core module theory |
| **Full-text search** on review text: PostgreSQL `tsvector` with a GIN index against a MongoDB text index, benchmark B7 (E1) | tbd | The same feature on both engines, measured |
| **Product Q&A**: customers ask, sellers answer; answers embedded in the question document (M2) | tbd | MongoDB embedding |
| **Scale-up generator runs** to 1M+ rows (promoted to Tier 1 if the 8 November numbers show no clear difference) | tbd | Scale axis |
| Seller replies to reviews | tbd | |
| Showcase names and descriptions for the demo subset, written by an LLM and labelled as generated | tbd | Cosmetic |

### Tier 3: stretch, probably never

MongoDB change streams, vector search (pgvector against MongoDB `$vectorSearch`), product variants, category tree, K-means (degenerate on Olist:
about 3% of customers reorder), geospatial queries on the geolocation table (MongoDB
`2dsphere` against PostGIS), CPU and memory dashboard panels (need cAdvisor or exporters), full raw-SQL conversion.

**Cut rule.** At the 8 November checkpoint, a Tier 2 item that cannot be demoed that day is dropped. Tier 3 is not
started before the first full benchmark run exists (target 17 November).

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
| Product images | Every product: an icon card (the category's icon from the existing sprite, extended to cover all 73 categories, plus the product name), drawn at render time with no stored file (D10). Featured set: the best seller in each of the top 15 categories gets an openly licensed stock photo matching its generated name, labelled as illustrative; source files and a manifest (file, product, source URL, author, licence) are committed, and the importer loads them into MongoDB GridFS (D11, D12). The same rule extends to the top 3 per category (45 photos) if time allows |
| Catalogue size | Seller-products in at least two distinct orders after cleaning (about 13.6k) are active and browsable; the rest (about 20k, mostly sold once in two years) are delisted: inactive, hidden from the shop, kept for order history, analytics and the benchmark (D13). Products created in the app are active |
| List price | Derived from real order prices (median per seller-owned product) |
| Shared products | Olist products sold by several sellers are split into one product per seller (32,951 become 34,448); each keeps Olist's id in a non-unique source column; counted in the cleaning ledger |
| Stock, lead time | Generated with a fixed seed |
| Category-specific attributes | Rich templates for the top 15 categories, a generic template for the rest; stored in MongoDB (and as EAV and JSONB copies for the benchmark) |
| Review text | All comments machine-translated offline once with a local model; original Portuguese kept; English labelled as machine-translated |
| Currency | Converted to SGD at **one fixed rate**: the European Central Bank reference rates (EUR/BRL and EUR/SGD cross rate) on the day `olist-import` executes. Lines rounded to the cent; checkout totals computed from the rounded lines; payments split in proportion with the rounding remainder on the largest, so they equal the total exactly. Raw BRL kept in the raw files |
| Dates | Shifted by one fixed offset of 426 weeks: 2016 to 2018 becomes November 2024 to 30 October 2026, so demo orders continue the timeline. Whole weeks keep weekdays (weekly patterns survive); the offset is a constant, never relative to today, so imports and benchmarks are reproducible. Raw files keep the original dates |
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

**Scale-up generator** (Python, same codebase as the importer): resamples real Olist rows with a seed, keeps foreign keys
valid, marks every row `is_generated`, and writes CSV for PostgreSQL `COPY` and NDJSON for `mongoimport`, so both engines
load byte-identical data. Generated data is not committed; the generator and an output checksum are.

## 6. Features in detail (Tier 1)

**Checkout and orders.** One checkout per cart; it creates one order per seller. Each order moves
`placed → paid → shipped → delivered`, plus `cancelled`, and a trigger rejects invalid transitions. The seller marks their
own order shipped; the operator marks it delivered (acting as the courier), so the demo can buy, ship, deliver and review
on camera.

**Simulated payment.** A Pay button with a method picker: credit card, boleto, voucher, debit (Olist's own types). The app
writes a `payment` row with status `paid`. **No card numbers are stored, even fake ones**; if card fields are shown for
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

**Workloads (each on identical data, each with golden outputs):**

| ID | Workload | PostgreSQL | MongoDB |
|---|---|---|---|
| B1 | Flexible attributes: filter by category-specific attributes | EAV table **and** JSONB with GIN (three-way) | Documents, multikey index |
| B2 | Aggregation: dashboard and review aggregates | Materialized view, CTEs, window functions | Aggregation pipeline |
| B3 | Last-unit race: 50 buyers, 10 units | Minimal identical operation: transaction, conditional decrement, insert order | Same: transaction, conditional `$inc`, insert order |
| B4 | Indexing: before and after for B1 and B2, told as one slow → index → fast story with plans | B-tree, composite, partial, GIN | Compound, multikey, partial |
| B5 | Storage footprint for the same data | Table and index sizes | Storage and index sizes |
| B6 | Isolation anomalies: a lost update under concurrency | Lost update under READ COMMITTED, prevented by `FOR UPDATE` and by SERIALIZABLE with retry | Write conflict and transaction retry |
| B7 (Tier 2) | Full-text search on review text (E1) | `tsvector` with a GIN index | Text index |

B3 compares **equivalent minimal operations**, not the app's full checkout (which carries idempotency and cart logic
that a minimal function would not). The app checkout is demoed, not raced.

**Correctness first.** Both engines must return identical result rows for B1 and B2, and B3 must end with exactly 10
successes, 40 refusals, stock at 0 and no oversell. These checks run in CI; a timing counts only if its check passed.

**Isolation from the app.** The harness uses its own databases (a `bench` database in each engine), never the
application's. Every run starts from the same loaded state and is **reset to that original state afterwards**, so runs
do not affect each other or the demo data.

**Method.**
- Identical Docker limits for both engines (for example 2 CPUs and 2 GB each).
- All final runs on one designated machine; CPU model, cores, RAM, OS and Docker version recorded with every result.
- 1, 10 and 50 concurrent clients; warm-up; at least 5 runs; p50, p95, throughput, errors, MongoDB retries.
- Engine comparison timed **at the driver level**; HTTP end-to-end timings reported separately, from a new local load
  script written in `benchmark` (the old AWS harness is deleted in `foundation`).
- Query plans captured beside timings: `EXPLAIN (ANALYZE, BUFFERS)` and MongoDB `explain("executionStats")`.
- `docker stats` sampled every second during each run (CPU and memory per container).
- **Headline results as ratios** (more portable across machines), absolute milliseconds as detail.
- Telemetry and caches off during timed runs.
- Raw output in `benchmarks/results/`, dated, with the commit hash.

**Per-request database timing (Tier 1, no new containers):** Django's `connection.execute_wrapper` and PyMongo's
`CommandListener` record query time and count per request into the existing JSON request log and a `Server-Timing`
header (visible in browser DevTools). This shows how much of each request is database time against Django overhead,
which is the evidence for timing engines at the driver level.

**The comparison is not only speed.** The report also compares data modelling, consistency guarantees, constraint
support and schema flexibility.

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
| `tests/load/` | Delete; `benchmark` writes a new local load script (foundation-h) |
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
`data/`, `benchmarks/` (harness, generator, `results/`), `.github/workflows/ci.yml`, `CONTRIBUTIONS.md` (one page,
updated at each checkpoint, for fair peer review), and `docs/` with `DATA_MODEL.md` (PostgreSQL schema with ER diagram, and the MongoDB model),
`DECISIONS.md`, `AI_USE.md` (including the disclosure that the codebase builds on our earlier module project), `plans/`
(only plans in flight) and `licenses/`. Benchmark tables are generated from `benchmarks/results/`, not hand-written.

**Tests.** Most existing tests assume the shoe data. `olist-import` deletes the shoe-specific tests and writes new ones for the
Olist import and schema; every later workstream brings its own tests. Tests that check behaviour independent of the
dataset (security negatives, idempotent checkout, database unavailability) are ported rather than deleted. CI runs
against a small committed fixture subset of Olist, not the full dataset.

**Professors' approval of building on our earlier module project:** keep it in writing and cite it in `docs/AI_USE.md`
and the report. The proposal does not mention the reuse.

## 12. Team and work split (proposal; edit freely)

| Member | Role | Tier 1 work |
|---|---|---|
| **Chee Long** | Main developer | Most of Tier 1 after `foundation`: `olist-import`, `accounts`, `checkout`, `catalogue`, `wishlist`, `dashboard`, `reviews`, `activity`, `benchmark` |
| **Erfan** | Planning and setup | PLAN.md and the workstream plans; the coding setup (AGENTS.md, workflow, docs check); `foundation`; `ci` (phase 3); Tier 2 `observability` |
| **Joash** | Supporting developer, QA | MongoDB: specifications, reviews, pipelines (his proposal role), reviewed by Erfan |
| **Jun Keat** | Supporting developer, QA | UI: catalogue, shop pages, cart and pay flow, reviews, wishlist; design standardisation; triggers with Chee Long |
| **Syahfariz** | Supporting developer, QA | Test plan and correctness gates, clean-machine run of the user manual, slides and video |

After `foundation`, Chee Long has agreed to implement most of Tier 1 (about 70 to 80%). Each other member still owns the
human gates of at least one workstream and presents it. Chee Long carries most of the development; the supporting members' work is smaller but recorded in
`CONTRIBUTIONS.md`. Report: shared, each owner writes the section for their work as it finishes; one editor assembles
it (to decide).

## 13. Phases

Agents check every task against this table (AGENTS.md, Phase check): a workstream is built only in its phase or later.

| Phase | Dates | Build (Chee Long unless noted) | Write plans | Exit check |
|---|---|---|---|---|
| **0 Setup** | 21 to 25 Oct | `foundation` (Erfan) | `accounts`, `checkout`; review of the `foundation` and `olist-import` plans (done 21 Oct) | Repo runs on Linux and Windows with both databases; professors' written approval |
| **1A Import** | 26 to 30 Oct | `olist-import` (Erfan optionally on the cleaning script) | `catalogue` | Olist loaded in both databases; the ledger reconciles; product pages render |
| **1B Accounts** | 31 Oct to 1 Nov | `accounts` | `wishlist`, `dashboard` | The three roles log in; seller approval works |
| **2A Checkout** | 2 to 4 Nov | `checkout` | `reviews`, `activity` | Buy from three sellers in one checkout, ship, deliver, cancel with refund |
| **2B Catalogue** | 5 to 8 Nov | `catalogue` | `benchmark`, `ci`, `observability`; `deliverables`: report outline with a page budget and the scripted demo story | **8 Nov checkpoint** (book a 15-minute check-in with the professors to show the demo): buy, ship and deliver work end to end; seller CRUD with photo upload; faceted search; cut rule applied and recorded |
| **3A Features** | 9 to 13 Nov | `wishlist`, `dashboard`, `reviews`, `activity`; `ci` (Erfan); surviving Tier 2 in parallel (likely `observability`, Erfan) | Tier 2 plans if earned | Every Tier 1 feature works end to end; CI green on `main` |
| **3B Benchmark** | 14 to 17 Nov | `benchmark`: harness, the clean Olist files loaded into the `bench` databases, workloads B1 to B6 with golden outputs, query plans, `docker stats` sampling, per-request timing, the new local HTTP load script | none | **First full benchmark run by 17 Nov** on the designated machine, every correctness check passing; each owner drafts their report section |
| **4 Freeze** | 18 to 22 Nov | **Feature freeze 18 Nov**; final benchmark runs (at least 5 per workload) and the report's results tables; the theory map appendix; bug fixes only | none | Report at 10 pages; the manual passes on a clean machine |
| **5 Ship** | 23 to 29 Nov | Video (all five, names on screen, under 10 minutes), slides, packaging | none | Zip checked by the packager; submitted 28 Nov, a day early (deadline 29 Nov, 23:30) |

The phases run one after another because one developer builds most of Tier 1, and they leave no slack before the
freeze (decided 21 October: keep all of Tier 1 with Chee Long). If a phase overruns by more than a day, Erfan assigns
`wishlist` or `activity` to another member, each with its own plan file.

## 14. Workstreams (one plan file each in `docs/plans/<name>.md`, contract first, deleted at close-out)

The workstream name is also the branch prefix (`checkout/payment-trigger`) and the label used in chat and the video.

| Workstream | Scope | Depends on | Tier | Status |
|---|---|---|---|---|
| `foundation` | Repo conversion, AWS removal, MongoDB in Compose, latest versions pinned, docs consolidation and check | none | 1 | review |
| `olist-import` | **Olist profile, cleaning, schema (ER diagram, 3NF), import, adaptations, users** | `foundation` | 1 | ready |
| `accounts` | Three roles, seller registration and approval, operator console (approve or suspend sellers, take-downs, audit log) | `olist-import` | 1 | ready |
| `catalogue` | Catalogue, specifications in MongoDB, faceted search, schema-evolution demo (category attribute templates), shop pages, icon cards and featured photos in GridFS, seller product CRUD with photo upload and audit trigger, `DESIGN.md` rewrite | `olist-import`, `accounts` | 1 | ready |
| `checkout` | Cart across sellers, checkout split into one order per seller, simulated payment, order lifecycle (seller ships, operator delivers), cancellation with refund | `olist-import`, `accounts` | 1 | ready |
| `activity` | Activity events in MongoDB: recently viewed, trending now, seller conversion (M1) | `catalogue`, `checkout` | 1 | ready |
| `reviews` | Per-item reviews, Bayesian average rating | `catalogue`, `checkout` | 1 | ready |
| `wishlist` | Wishlist and restock alerts | `catalogue`, `checkout` | 1 | ready |
| `dashboard` | Stock-planning dashboard on Olist, demand forecast, delivery delay against review score | `checkout`, `accounts` | 1 | ready |
| `benchmark` | Benchmark harness (B1 to B6), generator, per-request timing, protocol | `catalogue`, `reviews`, `dashboard` | 1 | not started |
| `ci` | CI and correctness gates, Playwright end-to-end tests of the demo story, `ruff`, coverage threshold, `pip-audit` (E4, E5); built in phase 3 once the features are in | `foundation` | 1 | not started |
| `deliverables` | Report (outline with a page budget in phase 2; figures; theory map appendix), slides, video following the scripted demo story, user manual, packaging | all | 1 | not started |
| `redis` | Redis cache-aside and rate limiting | `dashboard` | 2 | not started |
| `observability` | Observability (`grafana/otel-lgtm`) | `foundation` | 2 | not started |
| `seller-rls` | Row-level security for sellers, seller-scoped dashboard | `checkout` | 2 | not started |
| `durability` | Durability benchmark, replication and failover (E6), backup and restore drill (E7), scale-up runs | `benchmark` | 2 | not started |
| `search` | Full-text search on review text, benchmark B7 (E1) | `reviews` | 2 | not started |
| `qa` | Product Q&A (M2) | `catalogue` | 2 | not started |

Status is one of: not started, planning, ready (plan approved, waiting for implementation), in progress, review, done. This column is the only progress index; update it when
a workstream changes state, and keep each plan file as short as its contract allows (about one page where possible).

## 15. Decisions

**Settled** (21 October 2026; reasons in the sections above and in the plan files):

- **Architecture:** polyglot persistence plus a benchmark harness; each value in one store; raw SQL only where it shows a
  construct; English throughout; latest stable PostgreSQL and MongoDB pinned by digest (D4, foundation-d, foundation-f);
  MongoDB in Compose from `foundation` (foundation-c); owner and runtime PostgreSQL roles, pytest as the owner (R1).
- **Data:** Olist is the only dataset (D8), ECB rates cited as a supporting source; shared products split per seller
  (D1); categories (D5); one geolocation point per zip prefix (D6); dates shifted 426 weeks (D7); broken orders removed,
  including all 576 payment mismatches and the 20 orders after August 2018 (D9, R2, R5); latest review per order, reviews
  of undelivered orders kept (R3); bigint ids with Olist ids as source columns (R6); cleaning in a script before import.
- **Catalogue:** icon cards for every product (D10); illustrative stock photos for the best seller in each of the top 15
  categories (D11) in GridFS (D12); active catalogue = seller-products in at least two orders (D13); rich attribute
  templates for the top 15 categories.
- **Roles and orders:** customer, seller and operator in Tier 1 with row-level security in Tier 2 (D14 to D16); one
  checkout with one order per seller and payments on the checkout (D17); "seller" as the single term (D18); a custom user
  model with a role field (R7); cancellation with refund. `accounts`: one role per account, an audit log filled by
  triggers with the actor passed by `SET LOCAL`, a `rejected` seller status, operators created only by `seed_demo` or a
  command with the password from `.env`. `checkout`: one-step place and pay (orders start as `paid`), shipping fee from
  each product's median historical freight, refunds equal cancelled totals (imported cancellations get refund rows),
  whole-order cancellation as on Shopee.
- **Phase 2 and 3 plans** (approved 21 October): `catalogue` (MongoDB narrows and counts facets, PostgreSQL filters
  price, sorts and paginates; `pg_trgm` name search; PostgreSQL-first cross-store writes with a repair check; take-down
  flag), `wishlist` (partial unique index on unseen alerts; in-app only), `dashboard` (as-of 30 October 2026, to
  re-confirm before implementation; `SECURITY DEFINER` refresh; cross-store join in Python), `reviews` (Bayesian constants
  fixed at import; running sum; take-downs in `audit_log`), `activity` (seeded synthetic events; `w: 1` writes).
- **Added scope:** faceted search and schema evolution; Bayesian rating; demand forecast; delivery-delay analysis; 3NF
  justification; isolation benchmark (B6); audit trigger; activity events (M1); Playwright end-to-end tests and
  code-quality gates in `ci` (E4, E5). Tier 2: full-text search (E1), replication and failover (E6), backup and restore
  drill (E7), product Q&A (M2). The old load harness is deleted (R4); CI is built in phase 3.
- **Deliverables:** a professor check-in at the 8 November checkpoint, a scripted demo story, a report outline with a
  page budget, and a theory map appendix.
- **No further scope additions.**

**Open:**

| ID | Question | Recommendation |
|---|---|---|
| D2 | Report editor | One person assembles; everyone writes their section |
| D3 | Tier 2 owners other than observability | Decide at the 8 November checkpoint |

## 16. Risks

| Risk | Mitigation |
|---|---|
| The import (`olist-import`) slips and blocks everything | First plan; two people; simplify the existing machinery instead of porting all of it |
| Unfair comparison | Equivalent minimal operations, identical data files and limits, golden outputs, plans captured |
| No clear difference at about 100k rows | Driver-level timing; the scale-up generator promotes to Tier 1 at the checkpoint |
| Generated fields weaken "real-world data" | Every generated field labelled; real orders, sellers, reviews and payments dominate |
| Results depend on the machine | One designated machine, hardware recorded, ratios as headline |
| Telemetry or cache skews timings | Both off during timed runs; overhead measured separately |
| One main developer: a delay or absence stalls Tier 1 | Plans written one phase ahead; any member can pick up a workstream from its plan file |
| No slack before the 18 November freeze | A phase more than a day late moves `wishlist` or `activity` to another member (section 13) |
| Agents produce code no one can explain | `docs/DECISIONS.md`; each owner presents their part |
| Video over 10 minutes | Script by section; cut to 9:30 |
| Reuse approval only verbal | Written confirmation, cited |
| No CI until phase 3 | The review step runs the full test suite in Docker before every merge |
| Cleaning distorts the real data | Raw files untouched; every rule counted in the import ledger; analyses re-run on the cleaned data |

## Sources checked

- Olist dataset (CC BY-NC-SA 4.0): https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
- Repeat-customer share on Olist (about 3.1%):
  https://aioconquer.aivietnam.edu.vn/posts/why-customers-never-return-the-dark-side-of-olist-s-logistics
- MongoDB Search and Vector Search for Community Edition (Tier 3 reference):
  https://www.mongodb.com/products/updates/now-ga-mongodb-search-and-vector-search-for-community-edition/
