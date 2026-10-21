# Repository guide for coding agents

Mercer is a lean multi-seller marketplace (customers, sellers, an operator) on the real Olist dataset, built for the
INF2003 Database Systems group project (team 82, due Sunday 29 November 2026, 23:30). PostgreSQL is the system of record,
MongoDB owns product specifications, reviews and photos, and a benchmark harness compares both engines on identical data.
Django with HTMX serves the pages. The target is an A.

## Read first

- [RUBRICS.md](RUBRICS.md): what is graded. Every change should help a rubric line.
- [PLAN.md](PLAN.md): scope, tiers, **phases (section 13)**, workstreams and status (section 14). It wins over this file.
- `docs/plans/<workstream>.md`: the contract for the workstream you are working on.
- [DESIGN.md](DESIGN.md) for anything visual; `src/static/css/site.css` is its single implementation.

**Current state:** `src/` is still the earlier shoe-shop baseline. `foundation` removes its AWS parts and `olist-import`
replaces the shoe data. Do not extend shoe code; where a file contradicts PLAN.md, PLAN.md is the target.

## Phase check (before starting and before merging)

1. Find today's phase in PLAN.md section 13. The task's workstream must be in that phase or an earlier one, and its
   dependencies (section 14) must be done. If not, stop and ask instead of building ahead.
2. A plan file must exist with `status: approved` (except for small changes: typos, copy, one-line fixes).
3. Before merging, confirm the change does not break the current phase's exit check, and update the workstream's status
   in section 14.

## Architecture and ownership

Each value lives in exactly one store; nothing is copied, so no synchronisation code exists.

| Data | Store |
|---|---|
| Users and roles, sellers, products (one seller each, with price and stock), carts, checkouts (hold the payments; one order per seller), orders, order lines, payments, wishlist, analytics | PostgreSQL (latest stable, pinned by digest) |
| Product specifications (category attributes, rating summary, latest five reviews); reviews, one per order line | MongoDB (latest stable, pinned by digest), single-node replica set |
| Product photos (featured set; other products show an icon card) | MongoDB GridFS |
| Activity events (views, searches; 30-day TTL) | MongoDB time-series collection |
| Cache and rate limits (Tier 2 only) | Redis, never source of truth |

Cross-store reads are explicit and small: attribute search in MongoDB returns product ids, then PostgreSQL returns price
and stock with `WHERE id = ANY(%s)`. A review write checks the order line in PostgreSQL first.

## Rules

1. **Parameterised queries only**, in SQL and MongoDB filters. Raw SQL only where it shows a construct (checkout,
   payments, order status, wishlist, dashboard, benchmark); plain CRUD uses the Django ORM.
2. **Checkout never reads price or stock from MongoDB or Redis.**
3. **Money is exact:** `numeric(12,2)` in PostgreSQL, `Decimal128` in MongoDB. Never floats.
4. **No card numbers stored, even fake ones;** at most the last four digits.
5. **Limited privileges:** the PostgreSQL runtime role (used by `web`) has no DDL, DROP or TRUNCATE, while the owner role
   runs migrations, the import and tests; the MongoDB app user has `readWrite` on
   the app database only. Secrets come only from the git-ignored `.env`.
6. **Sellers see only their own rows:** every seller query filters by the logged-in seller, with a test proving one
   seller cannot reach another's products or orders.
7. **Uploads:** JPEG, PNG or WebP only (never SVG), at most 2 MB, re-encoded with Pillow before GridFS.
8. **Real databases in tests,** never mocks or SQLite. Each new raw-SQL path gets an injection negative test.
9. **Generated content is labelled** (names, descriptions, attributes, stock, lead times, translations) and flagged in
   the data (`has_generated_content`, `machine_translated`); rows synthesised by the scale-up generator are `is_generated`.
10. **Benchmarks** use the separate `bench` databases, identical data files and Docker limits, telemetry and caches off.
    A timing counts only if its correctness check passed.
11. **Tiers are binding:** no Tier 2 or 3 work before PLAN.md says it is earned.

## Workflow

**No plan yet:** plan, review the plan, the owner decides tradeoffs and approves, implement, review, fix, close out.
**Plan exists:** check it against the current code first, then implement, review, fix, close out.

- **One plan file per workstream** (`status:` draft, approved, in-progress, done; sections Contract, Decisions, Review
  notes; about one page). No separate tradeoff or review files.
- **Branch per workstream,** named `<workstream>/<topic>`; no direct pushes to `main`. The pull request links the plan
  and explains the change in words the author can defend in the video.
- **Reviews run in a fresh session,** ideally the other agent (Codex reviews Claude Code and the reverse), and mean
  running the tests and the plan's exit check, not only reading the diff. One fix round; leftovers become follow-ups.
- **Human gate (about 15 minutes):** the owner approves the plan, runs the demo path, checks the tests passed, and can
  explain the change in two sentences. Do not approve work you could not explain on video.
- **Commits** use the `type: summary` style, and AI-assisted ones carry a `Co-Authored-By` trailer.
- **Match the surrounding code;** do not claim results you did not run. Sub-agents only for large read-only searches.

**Close-out, before merge:** update the docs the change touched (map below); move lasting decisions into
`docs/DECISIONS.md`; add one line to `docs/AI_USE.md` (workstream, agent, what it did, reviewer); update the status in
PLAN.md section 14; delete the plan file; run `scripts/check_docs.py`.

## Documentation

Only these `.md` files exist: README.md (overview and user manual), AGENTS.md, CLAUDE.md, RUBRICS.md, PLAN.md, DESIGN.md,
CONTRIBUTIONS.md, `docs/DATA_MODEL.md`, `docs/DECISIONS.md`, `docs/AI_USE.md`, and plans in flight. A new one needs a
`docs/DECISIONS.md` entry. Each fact has one home; elsewhere, link to it.

| Change | Update |
|---|---|
| Table, column, constraint, trigger, index, collection or validator | `docs/DATA_MODEL.md` (regenerate generated parts) |
| Setup, configuration, environment variable, Compose service, port or command | README.md |
| A decision someone could later question | `docs/DECISIONS.md` |
| Scope, tier, phase, status, owner or date | PLAN.md |
| Visual tokens or components | DESIGN.md |
| A rule or command agents need | AGENTS.md |
| A member's work at a phase checkpoint | CONTRIBUTIONS.md |

**Never write by hand:** test counts, row counts, timings or benchmark tables; generate them or link to the source.
**Check (lands in `foundation`):** `scripts/check_docs.py` runs as a pre-commit hook (`git config core.hooksPath
.githooks`, once per clone) and in CI. It catches broken links and paths, unlisted `.md` files, stale generated docs and
`status: done` plans, not wrong prose, so the docs map still applies. Until it lands, check links by hand.

## Running and testing (current baseline)

Docker Desktop with Compose 2.20 or later, from the repository root:

```
python src/tools/init_env.py                                    # fresh clone only; writes src/.env
docker compose up --build                                       # app at http://127.0.0.1:8000/
docker compose run --rm web pytest -q -p no:cacheprovider /app/tests
```

The image copies `src/` at build time and mounts only `tests/`: run `docker compose build web` after changing app code.
MongoDB, the benchmark and CI commands are added here when they land.
