# Repository guide for coding agents

Mercer is a lean multi-seller marketplace on the real Olist dataset, built for the INF2003 Database Systems group project
(team 82, final submission Sunday 29 November 2026, 23:30). PostgreSQL is the system of record, MongoDB owns product
specifications and reviews, and a benchmark harness compares both engines on identical data. Django with HTMX serves
the pages.

## Read first

| File | Use it for |
|---|---|
| [RUBRICS.md](RUBRICS.md) | What is graded. The target is an A, so every change should help a rubric line |
| [PLAN.md](PLAN.md) | Scope, tiers, architecture, benchmark protocol, workstreams, timeline. It wins over this file on scope |
| [DESIGN.md](DESIGN.md) | Visual language; `src/static/css/site.css` is its single implementation |
| `docs/plans/<workstream>.md` | The one working file for the workstream in flight: contract, decisions, review notes. Deleted at close-out (planned) |
| `docs/DECISIONS.md` | Why choices were made (planned). Add an entry for every non-obvious decision |

## Current state

The code in `src/` is still the earlier shoe-shop baseline (Django, PostgreSQL, HTMX, AWS-oriented configuration). It is
being converted: `foundation` removes the AWS parts, `olist-import` replaces the shoe data with Olist. Do not extend shoe code. If a
file contradicts PLAN.md, PLAN.md describes the target and the file is waiting to be converted or deleted.

## Architecture and ownership

Each value lives in exactly one store. Nothing is copied between them, so no synchronisation code exists.

| Data | Store |
|---|---|
| Users, sellers, products, listings (price, stock), carts, orders, order lines, payments, wishlist, inventory snapshots, analytics | PostgreSQL (latest stable, pinned by digest) |
| Product specification documents (category-specific attributes, rating summary, latest five reviews) | MongoDB (latest stable, pinned by digest), single-node replica set |
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

- **Contract before code.** Each workstream in PLAN.md section 14 gets one file, `docs/plans/<workstream>.md` (scope, interfaces,
  tables or collections, tests, exit check) that the owner approves before implementation starts. See Workflow below.
- **Branch per workstream,** named `<workstream>/<topic>`. No direct pushes to `main`. Open a pull request, link the plan, and describe what the
  change does in words the author can defend in the video.
- **Commits made with AI assistance carry a `Co-Authored-By` trailer.** Keep subjects in the `type: summary` style
  already used in the history.
- **Explainability.** Each member must be able to explain their part. Put the reasoning for non-obvious choices in
  `docs/DECISIONS.md`, not only in the code.
- **Match the surrounding code.** Follow existing naming, comment density and idiom, and DESIGN.md for anything visual.
- **Do not claim what you did not run.** Report test commands and outcomes as they actually were.

## Workflow

**No plan exists:** plan and discuss, review the plan, the owner settles tradeoffs and approves it, implement, review
the implementation, record problems and tradeoffs, fix, close out.
**A plan exists:** check it against the current code first (it may be stale), then implement, review, record, fix,
close out.

- **Plan file.** One file per workstream at `docs/plans/<workstream>.md` with a `status:` line (draft, approved, in-progress,
  done) and three sections: Contract, Decisions, Review notes. Do not create separate tradeoff, implementation or review
  files.
- **Reviews run in a fresh session**, not the one that wrote the work. Where possible use the other agent (Codex
  reviews Claude Code's work and the reverse).
- **"Review implementation" means running things:** the test suite, the plan's exit check and the rubric line the work
  is meant to earn, not only reading the diff.
- **One fix round.** Findings still open after it go into a follow-up item, not an endless loop.
- **Keep plan files to about one page.** Only plans in flight exist; progress is tracked in the status column of PLAN.md
  section 14, not in a separate index.
- **Human gates (about 15 minutes per workstream).** The owner (1) reads the Contract and Decisions and approves the plan,
  (2) runs the demo path and checks the tests passed, and (3) can explain the change in two sentences before approving.
  Agent output is a proposal, not a finished review: do not approve work you could not explain on video.
- **Skip the planning half** for small changes (typos, copy, one-line fixes).
- **Sub-agents are optional and cost more tokens overall**, because each starts without your context. Use one only for
  a large read-only search or review, never for ordinary implementation.

**Close-out (the last step of every implementation, before merge):**
1. Update the docs the change touched, using the docs map below.
2. Move lasting decisions from the plan file into `docs/DECISIONS.md`; record review findings in the pull request.
3. Add one line to `docs/AI_USE.md`: workstream, agent used, what it did, who reviewed.
4. Delete the plan file (git history keeps it).
5. Run `scripts/check_docs.py` and fix what it reports.

## Documentation

Keep the set of `.md` files small. Each fact has one home; everywhere else links to it. Do not add a new `.md` file
without an entry in `docs/DECISIONS.md`.

| File | Job |
|---|---|
| README.md | Overview and the user manual (setup, configuration, run, test, benchmark) |
| AGENTS.md, CLAUDE.md | Rules for agents |
| RUBRICS.md | The brief and rubric (fixed) |
| PLAN.md | Scope, tiers, status, owners, timeline |
| DESIGN.md | Visual language |
| docs/DATA_MODEL.md | PostgreSQL schema and MongoDB model (parts generated from the databases) |
| docs/DECISIONS.md | Decisions and tradeoffs; the source for the report's discussion |
| docs/AI_USE.md | AI-use declaration and the per-pull-request log |
| CONTRIBUTIONS.md | Contribution record for peer review |
| docs/plans/<workstream>.md | Temporary; only plans in flight |

**Docs map: what to update for which change**

| Change | Update |
|---|---|
| Table, column, constraint, trigger, index, collection or validator | `docs/DATA_MODEL.md` (regenerate the generated parts) |
| Setup, configuration, environment variable, Compose service, port or command | README.md |
| A decision someone could later question | `docs/DECISIONS.md` |
| Scope, tier, status, owner or date | PLAN.md |
| Visual tokens or components | DESIGN.md |
| A rule or command agents need | AGENTS.md |
| A merged AI-assisted pull request | `docs/AI_USE.md` |
| A member's work at a checkpoint | CONTRIBUTIONS.md |

**Never write by hand:** test counts, row counts, timings or benchmark tables. Generate them or link to the source
(`benchmarks/results/`, the schema script), so they cannot drift.

**Check (planned in `foundation`):** `scripts/check_docs.py`, run by a git pre-commit hook in `.githooks/` (enable once with
`git config core.hooksPath .githooks`) and by CI as a backstop. It fails on broken relative links, backticked file paths
that do not exist, `.md` files not in the list above, generated docs that are out of date, `status: done` plan files,
and README commands that name a missing script or Compose service. It cannot detect a paragraph that is wrong while its
links are fine, so the docs map and the review step still apply. Until it exists, check links and paths by hand.

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
