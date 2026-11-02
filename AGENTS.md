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

**Current state:** The Tier 1 application is frozen. The
[benchmark close-out](docs/plans/benchmark.md#designated-machine-final-and-close-out-2-november-2026) records the
designated-machine evidence; [PLAN.md section 14](PLAN.md#14-workstreams-one-plan-file-each-in-docsplansnamemd-contract-first-kept-after-close-out-as-the-record)
is the progress index. Deliverables remain.

## Phase check (before starting and before merging)

1. Find the current phase in PLAN.md section 13: a phase is open once the phase before it is closed (exit check
   passed, work merged to `main`), whatever the date. The task's workstream must be in an open phase, and its
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
| Seller-uploaded product photos (other products show an icon card) | MongoDB GridFS |
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
   the app database and its `test_` database only. Secrets come only from the git-ignored `.env`.
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
  and explains the change in words the author can defend in the video. A human team member may override this (for
  example a docs-only change pushed straight to `main`) by saying so; agents never skip the branch and pull request on
  their own, and never push without being asked.
- **Reviews run in a fresh session,** ideally the other agent (Codex reviews Claude Code and the reverse), and mean
  running things, not only reading the diff. One fix round; leftovers become follow-ups. Run what the change warrants:

  | Change | Review runs |
  |---|---|
  | Small: docs, copy, typos, a one-line fix | `scripts/check_docs.py`, plus the touched module's tests if code changed |
  | Medium: inside one workstream, no schema, raw SQL, money, roles, uploads or concurrency | The touched test modules and their neighbours |
  | Workstream merge, or any change to schema, migrations, raw SQL, money, roles, uploads or concurrency | The full suite in Docker and the plan's exit checks |

  Fix rounds rerun only the affected tests; the full suite runs once more before merging. Until CI exists (phase 3),
  the full suite before a workstream merge is the only safety net, so it is never skipped there.
- **Who reviews:** the implementer asks a teammate to run the review in a fresh Claude Code session (Codex work is
  reviewed by Claude Code). The plan owner approves plans before implementation; there is no separate human gate.
- **Commits** use the `type: summary` style, and AI-assisted ones carry a `Co-Authored-By` trailer.
- **Match the surrounding code;** do not claim results you did not run. Sub-agents only for large read-only searches.

**Close-out, before merge:** update the docs the change touched (map below); move lasting decisions into
`docs/DECISIONS.md`; add one line to `docs/AI_USE.md` (workstream, agent, what it did, reviewer); update the status in
PLAN.md section 14; set the plan file to `status: done` and keep it as the record (decisions and review notes); run
`scripts/check_docs.py`.

## Documentation

Only these `.md` files exist: README.md (overview and user manual), AGENTS.md, CLAUDE.md, RUBRICS.md, PLAN.md, DESIGN.md,
CONTRIBUTIONS.md, `docs/DATA_MODEL.md`, `docs/DECISIONS.md`, `docs/AI_USE.md`, `docs/OVERVIEW.md` (plain-language team guide), and one plan per workstream in `docs/plans/` (kept after
close-out). A new one needs a
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
**Check:** `scripts/check_docs.py` runs as a pre-commit hook (`git config core.hooksPath .githooks`, once per clone) and in
CI. It catches broken links and paths, unlisted `.md` files, unpaired generated-section markers, plan files without a valid status line and
README commands naming a missing script or service, not wrong prose, so the docs map still applies.

## Running and testing

Run `python -m ruff format .` before committing; CI checks formatting at 120 columns.

Docker Desktop (or Docker Engine) with Compose 2.20 or later, from the repository root:

```
python src/tools/init_env.py                                    # writes .env, or adds keys a newer version needs
docker compose up --build                                       # app at http://127.0.0.1:8000/
docker compose build migrate web                               # rebuild dev runner and runtime web
docker compose run --rm migrate pytest -q -p no:cacheprovider /app/tests
docker compose run --rm migrate pytest -q -p no:cacheprovider /app/tests/test_settings.py   # one module
docker compose --profile tools run --rm tools pytest -q -p no:cacheprovider analytics/tests
python -m pytest --noconftest -q -p no:cacheprovider tests/test_check_docs.py tests/test_package_submission.py tests/test_request_timing.py
```

Tests run in the `migrate` service because it holds the PostgreSQL owner role, which pytest needs to create its test
database; `web` holds only the runtime role. The image copies `src/` at build time and `migrate` mounts `tests/`: run
`docker compose build migrate web` after changing app code. `migrate` targets the dev stage and its own `-app-dev`
image; `web` targets runtime and its `-app` image. Existing pytest pins stay in requirements.txt; additional quality
and browser tools live in requirements-dev.txt.

Benchmark commands use explicitly isolated projects and the bench profile. Run init_env.py again after updating;
Compose requires the new BENCH_* keys even when that profile is off. See the [README benchmark procedure](README.md#benchmark-isolated-databases)
for full-data loading, measurements and teardown. The fixture tests use their own fixture-loaded project:

```
docker compose -p mercer-bench-fixture --profile bench run --rm bench-runner pytest -c /dev/null --rootdir=/app/benchmarks -q -p no:cacheprovider /app/benchmarks/tests
python -m benchmarks.run --project mercer-bench-local --mode correctness --label first-pass
python -m benchmarks.run --project mercer-bench-local --mode measure --only baseline,B1,B4 --label trial
python -m benchmarks.request_timing --project mercer-request-final --base-url http://127.0.0.1:18082
python -m benchmarks.report benchmarks/results/<run-directory>
```

The benchmark fixture CI job is optional in the ruleset; its duration and all failures are retained as artifacts.
Benchmark tests require a freshly loaded fixture project. Reload before a correctness run that includes B5,
because B5 refuses any earlier restore. Recorded reruns use --require-clean; generated run directories are ignored
until explicitly staged with `git add -f -- benchmarks/results/<run-directory>`. See the README for per-client
operation counts (including `--b2-operations-per-client`), the storage checkpoint wait, round-trip baselines and
client CPU flags. The [final-run checklist](README.md#final-run-checklist-next-session) covers reloads and the separate
per-request collector; never run that collector alongside a benchmark.

CI (`.github/workflows/ci.yml`, stages 1–3 of [ci](docs/plans/ci.md)) runs these checks on every pull request and push to
`main`: build, migrate as owner, the drift check, the fixture import and `seed_demo`, the full suite, the pipeline tests,
the host Git-index/packaging tests (which must not skip), `scripts/check_docs.py`, Ruff E/F/I, dependency audit and
serial Chromium journeys. The full suite runs once through scripts/coverage_suite.py: branch reports are retained,
but only line coverage is gated at 80%. Include namespace files; omit migrations and the external repository mounts.
Browser tests drive runtime web only. Use `python -m scripts.browser_suite --env-file <private env> --base-url
http://127.0.0.1:<port>` after importing and seeding an isolated project. It exports demo logins only; never pass
owner credentials to browser tests. Trace/screenshot capture is failure-only, with redaction before upload. The
manual failure canary is opt-in; a hosted failed run and useful artifacts are still an exit check.
To reproduce a run locally, use
the README's "Continuous integration" commands; they use their own Compose project (`-p`), never `mercer`, so teardown
cannot touch your data. Do not print `.env` or `docker compose config` in CI. The required quality job also checks
Ruff formatting at 120 columns.
