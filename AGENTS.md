# Repository guide for coding agents

Mercer is a lean multi-seller marketplace on the real Olist dataset, built for the INF2003 Database Systems group project
(team 82, final submission Sunday 29 November 2026, 23:30). PostgreSQL is the system of record, MongoDB owns product
specifications and reviews, and a benchmark harness compares both engines on identical data. Django with HTMX serves
the pages.

## Read first

| File | Use it for |
|---|---|
| [RUBRICS.md](RUBRICS.md) | What is graded. The target is an A, so every change should help a rubric line |
| [PLAN.md](PLAN.md) | Scope, tiers, architecture, benchmark protocol, sub-plans, timeline. It wins over this file on scope |
| [DESIGN.md](DESIGN.md) | Visual language; `src/static/css/site.css` is its single implementation |
| `docs/plans/SP-xx-*.md` | The contract for the sub-plan you are working on (planned; written before code) |
| `docs/DECISIONS.md` | Why choices were made (planned). Add an entry for every non-obvious decision |

## Current state

The code in `src/` is still the earlier shoe-shop baseline (Django, PostgreSQL, HTMX, AWS-oriented configuration). It is
being converted: SP-01 removes the AWS parts, SP-02 replaces the shoe data with Olist. Do not extend shoe code. If a
file contradicts PLAN.md, PLAN.md describes the target and the file is waiting to be converted or deleted.

## Architecture and ownership

Each value lives in exactly one store. Nothing is copied between them, so no synchronisation code exists.

| Data | Store |
|---|---|
| Users, sellers, products, listings (price, stock), carts, orders, order lines, payments, wishlist, inventory snapshots, analytics | PostgreSQL 17 |
| Product specification documents (category-specific attributes, rating summary, latest five reviews) | MongoDB 8, single-node replica set |
| Reviews, one per order line | MongoDB |
| Cache and rate limits (Tier 2 only) | Redis; never source of truth |

Cross-store reads are explicit and small: attribute search runs in MongoDB and returns product ids, then PostgreSQL
returns price and stock with `WHERE id = ANY(%s)`. A review write checks the order line in PostgreSQL first.

## Rules

1. **Parameterised queries only**, in raw SQL and in MongoDB filters. Never build a query by string formatting.
2. **Raw SQL where it shows a construct** (checkout, payments, order status, wishlist, dashboard, benchmark paths). Plain
   CRUD stays on the Django ORM.
3. **Checkout never reads price or stock from MongoDB or Redis.** Redis never holds source-of-truth data.
4. **Money is exact:** `numeric(12,2)` in PostgreSQL, `Decimal128` in MongoDB. Never a float or the default double.
5. **No card numbers are stored, even fake ones.** At most the last four digits.
6. **Limited privileges:** the PostgreSQL application role has no DDL, DROP or TRUNCATE; the MongoDB application user
   has `readWrite` on the application database only. Root and owner credentials are used only at initialisation.
7. **Real databases in tests.** Never mocks, never SQLite. A new raw-SQL path needs an injection negative test.
8. **Secrets come from the git-ignored `.env`.** Never commit credentials or paste a resolved Compose configuration.
9. **Every generated field is labelled as generated** (names, descriptions, attributes, stock, lead times, translated
   review text), and generated rows are flagged `is_generated`.
10. **Benchmarks:** use the separate `bench` database in each engine, identical data files and Docker limits, and check
    the golden outputs first. A timing counts only if its correctness check passed. Telemetry and caches stay off during
    timed runs.
11. **Tiers are binding.** Tier 1 items are demoed, measured or shown with a query plan, and written up. Do not start a
    Tier 2 or Tier 3 item before PLAN.md says it is earned.

## How we work

- **Contract before code.** Each sub-plan in PLAN.md section 14 gets a short file in `docs/plans/` (scope, interfaces,
  tables or collections, tests, exit check) that the owner agrees before implementation starts.
- **Branch per workstream.** No direct pushes to `main`. Open a pull request, link the sub-plan, and describe what the
  change does in words the author can defend in the video.
- **Commits made with AI assistance carry a `Co-Authored-By` trailer.** Keep subjects in the `type: summary` style
  already used in the history.
- **Explainability.** Each member must be able to explain their part. Put the reasoning for non-obvious choices in
  `docs/DECISIONS.md`, not only in the code.
- **Match the surrounding code.** Follow existing naming, comment density and idiom, and DESIGN.md for anything visual.
- **Do not claim what you did not run.** Report test commands and outcomes as they actually were.

## Running and testing (current baseline)

Docker Desktop with Compose 2.20 or later is the supported environment. Run from the repository root.

```
python src/tools/init_env.py                                   # fresh clone only; writes src/.env, never overwrites
docker compose up --build                                      # app at http://127.0.0.1:8000/
docker compose run --rm web pytest -q -p no:cacheprovider /app/tests
docker compose run --rm web pytest -q -p no:cacheprovider /app/tests/test_cart.py   # one module
```

The image copies `src/` at build time and mounts only `tests/`, so run `docker compose build web` after changing
application code. Details are in [src/README.md](src/README.md) and [tests/README.md](tests/README.md). MongoDB, the
benchmark harness and CI are not in the repository yet; their commands will be added here when they land.

## Layout

`src/` Django application and Dockerfile · `tests/` pytest suite and the Locust harness in `tests/load/` · `analytics/`
dataset profiling and analytics scripts · `data/` raw and derived data with checksums · `scripts/` packaging ·
`docs/` licences now, plans, decisions, schema, setup and benchmark notes as they are written.
