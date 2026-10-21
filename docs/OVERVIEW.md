# Mercer: project overview for the team

A plain-language guide to what we are building for INF2003, why, and how the work is organised. It summarises; the
details and every decision live in [PLAN.md](../PLAN.md), and each workstream's contract lives in `docs/plans/`. If this
page and PLAN.md ever disagree, PLAN.md is right.

## What we are building

**Mercer** is a small Shopee-style marketplace built on a real dataset: about 100,000 orders from Olist, a Brazilian
marketplace, shared publicly on Kaggle. Many sellers list products, customers buy from several sellers in one cart, and a
platform operator keeps things running. The goal is an A, so every feature exists to show a database skill the rubric
rewards ([RUBRICS.md](../RUBRICS.md)).

| Role | What they can do |
|---|---|
| **Customer** | Browse, search and filter products; one cart across sellers; check out once and pay (simulated); track each order; cancel before it ships; review each item after delivery; wishlist sold-out items and get a restock alert; see recently viewed and trending products |
| **Seller** | Apply to sell and wait for approval; create, edit and deactivate their own products (price, stock, details, photo); ship their own orders; see their own sales, reviews and how many viewers turn into buyers |
| **Operator** (platform admin) | Approve, reject or suspend sellers; take down products or reviews; add new attributes to a category without any database migration; mark orders delivered (acting as the courier); the platform dashboard; the audit log |

Like Shopee, a cart with products from three sellers becomes **one checkout with three orders**, one per seller, so
each seller ships their own order.

**Out of scope:** real payments, real shipping, chat, vouchers.

## Why two databases, and what each one does

| | PostgreSQL (relational) | MongoDB (NoSQL) |
|---|---|---|
| Holds | Users and roles, sellers, products (price, stock), carts, checkouts, orders, payments, refunds, wishlist, audit log, sales analytics | Product details whose fields differ by category, reviews, product photos, browsing activity |
| Why | Money and stock need transactions, constraints and triggers | Flexible shapes, nested documents, fast reads, high-volume event writes |

Each piece of data lives in exactly one database, so nothing has to be kept in sync. Where a page needs both (search,
reviews, seller insights), the app asks each database for its part and combines the answers.

## The data

Olist gives us real orders, sellers, payments, delivery dates and reviews. We clean it (for example, we remove orders
whose payments do not add up) and record every removal in a **cleaning ledger**, so the report can show exactly what
changed and why. Olist removed product names, descriptions and photos for privacy, so we **generate** names and details
from templates, show icon cards instead of photos (with real stock photos for 15 featured products), and translate the
Portuguese reviews to English. Everything generated is labelled as generated, in the app and in the report. Prices are
converted to SGD, and dates are moved forward so the shop feels current.

One finding is already clear from the data: **late deliveries drive bad reviews**. Orders delivered more than a week
late average under 2 stars, against over 4 for on-time orders. The dashboard and the report build on this.

## What earns the marks

**PostgreSQL:** constraints and composite foreign keys (one seller per order is enforced by the database), triggers (order
status rules, restock alerts, audit log), a deferred constraint (payments must equal the checkout total), row locking for
the last item in stock, a materialized view and window functions for the dashboard (including a demand forecast), a
trigram index for typo-tolerant search, and two database roles so the web app cannot change the schema.

**MongoDB:** schema validation, documents that embed a rating summary and the latest reviews (one read per product
page), multi-document transactions, `$facet` search filters with live counts, aggregation pipelines, GridFS for photos,
a time-series collection with automatic expiry for browsing activity, and adding a new product attribute live, with no
migration.

**The comparison:** a benchmark harness runs the same workloads on both databases with identical data and checks that
both return the same answers before any timing counts. It covers flexible attributes, aggregations, a 50-buyer race for
10 items, indexing, storage size and isolation anomalies.

**Analytics:** a Bayesian rating (so one 5-star review does not beat a hundred 4.5-star ones), the demand forecast, and the
delivery-delay analysis.

**Quality:** tests on real databases (never mocks), end-to-end browser tests of the demo story, and continuous integration.

Scope is tiered. **Tier 1** is the A-grade core and must be finished by the 18 November freeze. **Tier 2** (Redis,
observability, row-level security, replication and failover, full-text search, product Q&A) is built only if Tier 1 is on
track at the 8 November checkpoint. No further features are being added.

## Timeline

| Phase | Dates | What happens |
|---|---|---|
| 0 Setup | 21 to 25 Oct | Repository cleaned up for INF2003; both databases running in Docker |
| 1A, 1B | 26 Oct to 1 Nov | Olist imported and cleaned; customer, seller and operator accounts |
| 2A, 2B | 2 to 8 Nov | Checkout, then the catalogue and seller tools. **8 Nov checkpoint**: the core demo works end to end |
| 3A | 9 to 13 Nov | Wishlist, dashboard, reviews, activity; continuous integration |
| 3B | 14 to 17 Nov | Benchmark: first full run |
| 4 | 18 to 22 Nov | **Feature freeze 18 Nov**; final benchmark runs; report finished |
| 5 | 23 to 29 Nov | Video and slides; **submit on 28 Nov**, a day before the 29 Nov deadline |

## Who does what

| Member | Role |
|---|---|
| **Chee Long** | Main developer: implements most of Tier 1 |
| **Erfan** | Planning and setup: PLAN.md, the workstream plans, the repository and tooling, continuous integration, observability (Tier 2) |
| **Joash, Jun Keat, Syahfariz** | Supporting developers and QA; can take a workstream if a phase runs late; section 12 of PLAN.md lists their areas |

**Everyone** presents in the video (it is graded, and names must be on screen) and writes the report section for their
part. Peer review weights the final mark, so record what you do in `CONTRIBUTIONS.md`.

## How the work is done

Most code is written with AI coding agents (Codex and Claude Code), so the process is built to keep it correct and
explainable:

1. **Plan first.** Each workstream has a one-to-two-page plan in `docs/plans/`: what to build, the decisions taken and
   why, the tests, and an exit check. Plans are approved before coding and kept afterwards as the record.
2. **Build on a branch** named after the workstream, following [AGENTS.md](../AGENTS.md), the rules every agent reads.
3. **Review in a fresh session.** The implementer asks a teammate to review the work in a new Claude Code session,
   ideally a different AI than the one that wrote it, and the review runs the tests and the exit check.
4. **Close out.** Update the docs, record decisions in `docs/DECISIONS.md`, log the AI use in `docs/AI_USE.md`, mark the
   plan done.

A few rules matter to everyone: money is always exact (never floating point), no card numbers are ever stored, tests use
real databases, secrets stay in the git-ignored `.env`, and everything generated is labelled.

## What to do now

1. Read this page, then skim [PLAN.md](../PLAN.md) sections 2 to 6.
2. Get the app running by following [README.md](../README.md) (Windows with Docker Desktop).
3. Know which part of the demo you will present, and keep `CONTRIBUTIONS.md` up to date.

## Where things are

| File | What it holds |
|---|---|
| [PLAN.md](../PLAN.md) | Full scope, decisions, phases and workstream status |
| [RUBRICS.md](../RUBRICS.md) | The brief and the marking rubric |
| [AGENTS.md](../AGENTS.md) | Rules for the coding agents and how we work |
| [README.md](../README.md) | Setup and how to run the app |
| `docs/plans/` | One plan per workstream |
| [docs/DATA_MODEL.md](DATA_MODEL.md) | The database design: ER diagram, MongoDB model |
| [docs/DECISIONS.md](DECISIONS.md) | Why things are the way they are |
