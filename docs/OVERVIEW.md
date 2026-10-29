# Mercer: project overview for the team

A plain-language guide to what we are building for INF2003, why, how it earns the marks, and how the work is organised.
Anyone on the team should be able to read this page and understand the whole project. It summarises: the details and
every decision live in [PLAN.md](../PLAN.md), and each workstream's contract lives in `docs/plans/`. If this page and
PLAN.md ever disagree, PLAN.md is right.

## 1. The project in one minute

**Mercer** is a small Shopee-style online marketplace. Many sellers list products; customers search, fill one cart
from several sellers and pay once; a platform operator approves sellers and keeps the platform healthy.

It runs on **real data**: about 100,000 orders placed on Olist, a Brazilian marketplace, between 2016 and 2018,
published on Kaggle. It uses **two databases on purpose**: PostgreSQL for everything involving money and stock, MongoDB
for data whose shape varies or that is read or written in bulk. A **benchmark harness** then runs the same workloads on
both databases and compares them fairly. The goal is an A, so every feature exists to show a database skill the brief
rewards ([RUBRICS.md](../RUBRICS.md)).

The app is a Django web application (HTMX for interactive pages) running in Docker, so anyone can start it with a few
commands from [README.md](../README.md).

## 2. Who uses it and what they can do

| Role | What they can do |
|---|---|
| **Customer** | Browse and search products, filter by category, price, rating and product attributes; one cart across sellers; check out once and pay (simulated: credit card, boleto, voucher or debit, no real money and no card numbers stored); track each order; cancel an order before it ships and get a refund; review each item after delivery, and edit or delete that review; wishlist sold-out items and get an alert when they are restocked; see recently viewed and trending products |
| **Seller** | Apply to sell and wait for the operator's approval; create, edit and deactivate their own products (name, price, stock, shipping fee, category, attributes, description, photo); mark their own orders shipped; see their own sales and reviews, and how many people who viewed a product went on to buy it |
| **Operator** (platform admin) | Approve, reject, suspend or reinstate sellers; take down products or reviews that break the rules; add a new attribute to a product category while the app is running, without any database migration; mark orders delivered (acting as the courier for the demo); the platform dashboard (stock planning, category performance, sellers at risk of bad reviews); the audit log of every sensitive change |

**How an order works.** As on Shopee, a cart holding products from three sellers becomes **one checkout with three
orders**, one per seller. The checkout holds the payment; each seller ships their own order; each order moves through
`placed → paid → shipped → delivered`, or `cancelled` if the customer cancels before shipping.

**Out of scope:** real payment gateways, real shipping, chat, vouchers and discounts.

## 3. The demo story

This is the path the video follows, and it touches almost every feature:

1. A customer searches with a typo ("hose nozle") and still finds the product, then narrows the results with filters
   whose counts update live. The home page shows trending products.
2. They add products from three different sellers and pay once: one checkout, three orders, stock reduced exactly.
3. Each seller logs in and ships their own order; the operator marks them delivered.
4. The customer reviews an item: the product's rating, review count and latest reviews update at once.
5. A seller restocks a sold-out product: a customer who wishlisted it gets an alert straight away.
6. The operator adds a new attribute to a category live, approves a new seller, and opens the dashboard: products that
   will run out, the best categories, and sellers whose late deliveries are causing bad reviews.
7. The benchmark results: how PostgreSQL and MongoDB compare on the same data and the same tasks.

## 4. Architecture: two databases, each with its own job

| | PostgreSQL (relational) | MongoDB (NoSQL) |
|---|---|---|
| **Holds** | Users and roles, sellers, products (name, price, stock), carts, checkouts, orders, payments, refunds, wishlist and alerts, audit log, sales analytics | Product details whose fields differ by category, category attribute templates, reviews, product photos, browsing activity |
| **Why this database** | Money and stock must never be wrong: transactions, constraints and triggers guarantee it | Shapes vary by category, reviews nest naturally and are read far more than written, activity is a high-volume stream of events |

**Each piece of data lives in exactly one database**, so nothing has to be copied or kept in sync. When a page needs
both (search, product pages, review writes, seller insights), the app asks each database for its part and combines the
answers; the report measures what that costs.

**Security.** The web app connects to PostgreSQL with a restricted role that can read and write data but cannot change
the schema or drop tables; a separate owner role runs migrations and the import. The MongoDB app user can only reach its
own database. Every query is parameterised, and tests try SQL injection on every hand-written query.

## 5. The data

**What Olist gives us (real):** customers, sellers, orders, order items, payments, reviews with Portuguese text, delivery
dates (promised and actual), product categories and sizes, and locations.

**What we clean (counted):** orders whose payments do not add up exactly, orders with no items or no payment, a short
tail of incomplete months, contradictory delivery dates, duplicate reviews. Every removed or changed row is recorded in
a **cleaning ledger** that becomes a table in the report, and the raw files stay untouched in the repository.

**What we adapt (labelled):** Olist hid product names, descriptions and photos to protect sellers, so we **generate**
names, descriptions and attributes from templates (rich templates for the 15 biggest categories), show an icon card for
each product unless its seller uploaded a photo. Featured stock photos are deferred by
[catalogue amendment j](plans/catalogue.md). Reviews are machine-translated to English, with the
Portuguese kept. Prices are converted to SGD at one fixed rate. All dates are moved forward by a fixed number of weeks so
the shop feels current. Products sold only once in two years are delisted (kept in the data, hidden from the shop).
**Everything generated is labelled as generated**, in the app and in the report.

**A finding already in the data:** late deliveries drive bad reviews. Orders delivered more than a week late average
under 2 stars, against over 4 for orders delivered on time. The dashboard and the report build on this.

## 6. Scope: three tiers

**Tier 1** is the A-grade core: every item must be built, tested, shown in the video and written up by the
**18 November freeze**. **Tier 2** is built only if Tier 1 is on track at the **8 November checkpoint**; anything that
cannot be demoed that day is dropped. **Tier 3** is ideas we deliberately do not build. No further features are being
added.

### Tier 1: the A-grade core

| # | Feature | What a user sees | Database techniques it shows | Workstream |
|---|---|---|---|---|
| T1 | **Olist import** | The shop full of real orders, sellers and reviews | Cleaning ledger, ER design normalised to 3NF, foreign keys checked at import, the deliberate denormalisation in MongoDB explained | `olist-import` |
| T1b | **Roles and accounts** | Separate customer, seller and operator areas; seller approval | Role-based access; a trigger enforcing the seller status workflow; an audit log written by triggers | `accounts` |
| T2 | **Catalogue and search** | Category and seller pages, typo-tolerant search, filters with live counts | Trigram index (PostgreSQL), `$facet` aggregation with live counts (MongoDB), schema validation, multikey index | `catalogue` |
| T2b | **Seller product management** | Sellers add and edit products and photos; the operator takes products down | CRUD on both databases; photos in GridFS; adding a category attribute live with no migration; an audit trigger on price and stock | `catalogue` |
| T3 | **Checkout and orders** | One cart, one payment, one order per seller; ship, deliver, cancel with refund | Row locking (`FOR UPDATE`) so two buyers never get the last item; a deferred constraint (payments must equal the total); a status-transition trigger; composite foreign keys enforcing one seller per order | `checkout` |
| T4 | **Reviews** | Review each item once after delivery; ratings update instantly; "Top rated" sorting | Unique index (one review per item); a multi-document transaction updating review and rating together; the subset pattern; a Bayesian rating | `reviews` |
| T5 | **Wishlist** | Save sold-out items; get a restock alert | A many-to-many table; a trigger; a partial unique index | `wishlist` |
| T6 | **Dashboard** | Products that will run out before they can be restocked; best categories | Materialized view; window functions (moving-average forecast, `RANK`, `LAG`); a `SECURITY DEFINER` function | `dashboard` |
| T6b | **Late deliveries against reviews** | Sellers at risk of bad reviews | A cross-database analysis: delivery delay from PostgreSQL, scores from MongoDB | `dashboard` |
| T6c | **Activity** | Recently viewed, trending now, sellers' views-to-sales | A MongoDB time-series collection with automatic 30-day expiry; window ranking | `activity` |
| T7 | **Benchmark** | Charts comparing the two databases | Same data, same tasks, correctness checked before timing; query plans from both engines | `benchmark` |
| T8 | **Quality** | Tests pass on every change | Tests on real databases (never mocks), browser tests of the demo story, code-quality and security checks, continuous integration | `ci` |
| T9 | **Deliverables** | Report, slides, video, user manual | 50% of the marks | `deliverables` |

**The benchmark in detail.** Each workload runs on identical data in both databases, both must return identical answers
before a timing counts, and results are reported at 1, 10 and 50 concurrent users:

| Workload | Question it answers |
|---|---|
| B1 Flexible attributes | Filtering by category-specific fields: MongoDB documents against PostgreSQL JSONB and a classic attribute table |
| B2 Aggregation | Dashboard and review statistics: SQL views and window functions against aggregation pipelines |
| B3 Last-unit race | 50 buyers, 10 units: does either database oversell? |
| B4 Indexing | The same queries before and after indexes, with query plans |
| B5 Storage | How much space the same data takes in each |
| B6 Isolation | A "lost update" under concurrency, and how each database prevents it |

### Tier 2: earned at the 8 November checkpoint

| Feature | What it adds | Why it is worth it |
|---|---|---|
| **Redis** | Caching for the dashboard and reviews; rate limiting on login and review posting | A third kind of database (key-value), measured with the cache on and off |
| **Observability** | Traces and a Grafana dashboard of every query, PostgreSQL against MongoDB | Shows where time goes per request; industry-standard tooling (OpenTelemetry) |
| **Row-level security** | The database itself stops a seller from seeing another seller's data | Isolation enforced by PostgreSQL, not only by the app |
| **Replication and failover** | Three MongoDB nodes and a PostgreSQL replica; stop the primary on camera and watch the app keep working; a timed backup and restore | Replication is core database theory; makes the durability comparison meaningful |
| **Full-text search** | Search inside review text, PostgreSQL against MongoDB | The same feature on both engines, benchmarked |
| **Product Q&A** | Customers ask, sellers answer | A natural MongoDB embedding example |
| **Scale-up runs** | The benchmark on a million or more rows | Shows how the comparison changes with size |
| **Seller replies; showcase descriptions** | Sellers answer reviews; hand-polished text for featured products | Polish |

### Tier 3: deliberately not built

Vector or semantic search, MongoDB change streams, product variants, a category tree, customer clustering (only 3% of
Olist customers ever reorder, so clusters would be meaningless), map-based queries, CPU and memory panels, and rewriting
all code as raw SQL. Each is either too much work for the time left, adds little to the grade, or does not suit the
data.

## 7. How the project matches the brief and the rubric

**The brief's tasks** ([RUBRICS.md](../RUBRICS.md), section 3):

| Task | How we meet it |
|---|---|
| A. An application using both database types | Each database does the jobs it suits (section 4), and the benchmark repeats key functions on both |
| B. Real-world datasets | Olist, real and cleaned with a ledger; ECB exchange rates for the currency |
| C. ER diagram with 1-to-many, many-to-1, many-to-many and varied data types; a NoSQL data model | Seller → products and checkout → orders (1-to-many), order line → product (many-to-1), wishlist and order lines (many-to-many); money, integers, text, timestamps, booleans, JSON. The MongoDB model explains what is embedded and what is referenced, and why (`docs/DATA_MODEL.md`) |
| D. CRUD and complex functions | CRUD by sellers and the operator on both databases; triggers, transactions, views, pipelines, analytics |
| E. Analysis and reflection | The benchmark, the late-delivery finding, the cleaning ledger, the tradeoffs in `docs/DECISIONS.md` |

**The rubric** (group project is 50% of the module, split evenly between the relational and NoSQL sides):

| Rubric line | Weight | What the Excellent band asks | How we earn it |
|---|---|---|---|
| Project quality and implementation | 40% | Interesting, innovative, accurate, useful; appropriate data; significant work on **both** databases; algorithms; excellent code | A complete three-role marketplace on real data; balanced advanced work on both databases (T1 to T6c); Bayesian rating, forecast and delay analysis; tests, browser tests and CI (T8) |
| Presentation (video and slides) | 25% | Clear and logical; methods, results and conclusions stated; implications discussed | The demo story (section 3) in the required order below; benchmark charts; the late-delivery implications |
| Final report | 25% | Clear and comprehensive; implementation details and analysis | 10 pages written per feature as it finishes; the ER diagram, cleaning ledger, benchmark results and decisions as material |
| Proposal | 10% | Done | Marked "a solid plan and a clear scope" |
| Extra credit | bonus | Innovative ideas, advanced technologies and interfaces, advanced SQL and NoSQL features, analytics | Triggers, deferred constraints, materialized view, window functions, `$facet`, time-series collections, transactions on both engines, live schema evolution, the analytics, and Tier 2 if earned |

**The video's required order** (the brief makes it order-sensitive):

| Part | What we show |
|---|---|
| i. Background | The marketplace idea, the three roles, the Olist data and how it was cleaned |
| ii. Relational database | The ER design, constraints and triggers, checkout under concurrency, the dashboard, security roles |
| iii. NoSQL database and comparison | The document model, faceted search, reviews with transactions, live schema evolution, activity; then the comparison with PostgreSQL |
| iv. Performance analysis | The benchmark results, query plans and what they mean |

## 8. Timeline

The authoritative schedule is [PLAN.md section 13](../PLAN.md#13-phases). Application features freeze on
30 October, with final benchmark runs on 31 October to 1 November and contingency for fixes and retests on
2 to 4 November. The professor check-in and Tier 2 decision are on 8 November. We aim to submit on 28 November;
the deadline is 29 November 2026 at 23:30 Singapore time.

## 9. Who does what

| Member | Role |
|---|---|
| **Chee Long** | Main developer: implements most of Tier 1 |
| **Erfan** | Planning and setup: PLAN.md, the workstream plans, the repository and tooling, continuous integration, observability (Tier 2) |
| **Joash, Jun Keat, Syahfariz** | Supporting developers and QA; can take a workstream if a phase runs late; PLAN.md section 12 lists their areas |

**Everyone** presents in the video (it is graded, and names must be on screen) and writes the report section for their
part. Peer review weights the final mark, so record what you do in `CONTRIBUTIONS.md`.

## 10. How the work is done

Most code is written with AI coding agents (Codex and Claude Code), so the process is built to keep it correct and
explainable:

1. **Plan first.** Each workstream has a plan in `docs/plans/`: what to build, the decisions taken and why, the tests,
   and an exit check. Plans are reviewed and approved before coding, and kept afterwards as the record.
2. **Build on a branch** named after the workstream, following [AGENTS.md](../AGENTS.md), the rules every agent reads.
3. **Review in a fresh session.** The implementer asks a teammate to review the work in a new Claude Code session,
   ideally a different AI than the one that wrote it; the review runs the tests and the exit check.
4. **Close out.** Update the docs, record decisions in `docs/DECISIONS.md`, log the AI use in `docs/AI_USE.md`, mark the
   plan done.

A few rules matter to everyone: money is always exact (never floating point), no card numbers are ever stored, tests use
real databases, secrets stay in the git-ignored `.env`, and everything generated is labelled.

## 11. What to do now

1. Read this page, then skim [PLAN.md](../PLAN.md) sections 2 to 7.
2. Get the app running by following [README.md](../README.md) (Windows with Docker Desktop).
3. Know which part of the demo and the video you will present, and keep `CONTRIBUTIONS.md` up to date.

## 12. Where things are

| File | What it holds |
|---|---|
| [PLAN.md](../PLAN.md) | Full scope, decisions, phases and workstream status |
| [RUBRICS.md](../RUBRICS.md) | The brief and the marking rubric |
| [AGENTS.md](../AGENTS.md) | Rules for the coding agents and how we work |
| [README.md](../README.md) | Setup and how to run the app |
| `docs/plans/` | One plan per workstream |
| [docs/DATA_MODEL.md](DATA_MODEL.md) | The database design: ER diagram, MongoDB model |
| [docs/DECISIONS.md](DECISIONS.md) | Why things are the way they are |
