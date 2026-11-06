# Mercer: a lean marketplace on PostgreSQL and MongoDB

INF2003 Database Systems · Team 82 · Submission: Sunday 29 November 2026, 23:30 Singapore time

Mercer is a Shopee-style marketplace with customers, sellers and an operator, built on the real Olist dataset. PostgreSQL
is the system of record for money, stock and orders; MongoDB owns product specifications, reviews, photos and activity
events; a benchmark harness compares both engines on identical data. Django with HTMX serves the pages. Payments are
simulated and no personal data is used.

## Status

The Tier 1 application is complete; designated-machine benchmark evidence is recorded in the
[benchmark close-out](docs/plans/benchmark.md#designated-machine-final-and-close-out-2-november-2026). Deliverables remain.
The authoritative schedule and workstream statuses are in [PLAN.md section 13](PLAN.md#13-phases) and
[section 14](PLAN.md#14-workstreams-one-plan-file-each-in-docsplansnamemd-contract-first-kept-after-close-out-as-the-record).
Contributor rules are in [AGENTS.md](AGENTS.md), the graded outcome in [RUBRICS.md](RUBRICS.md), and the schema in
[docs/DATA_MODEL.md](docs/DATA_MODEL.md).

## Requirements

- Docker Desktop (Windows, macOS) or Docker Engine (Linux) with Compose 2.20 or later, using Linux containers. Start
  Docker Desktop first and wait until it reports the engine is running.
- Python 3.8 or later on the host, only for `src/tools/init_env.py` and the documentation check. Both were run by hand
  on 3.8 and 3.9 (they use only the standard library); CI runs them on 3.13 only. The application runs in Docker. Host
  quality and browser checks use Python 3.13 and `src/requirements-dev.txt`. On Linux and macOS the command may be `python3`.
- Git. Free ports 8000 (the app) and 27017 (MongoDB, bound to 127.0.0.1); change `APP_PORT` or `MONGO_PORT` in `.env`.

## Set up and run (fresh clone)

From the repository root:

```sh
python src/tools/init_env.py              # 1. writes .env with random local secrets (never printed)
git config core.hooksPath .githooks       # 2. once per clone: the documentation check runs before each commit
git config blame.ignoreRevsFile .git-blame-ignore-revs  # once per clone: skip the formatting commit in blame
docker compose up --build                 # 3. builds, starts PostgreSQL and MongoDB, migrates, starts the app
```

The first start takes a few minutes. When the log shows Gunicorn listening:

- Open <http://127.0.0.1:8000/>. The liveness probe is <http://127.0.0.1:8000/health/> (200, `{"status": "ok"}`).
- In another terminal, check both databases:

```sh
docker compose exec web python manage.py check_database
```

It prints `{"postgresql": "ok", "mongodb": "ok", "migrations": "applied"}`.

Stop with `docker compose down`; the databases are kept. `docker compose down --volumes` also deletes them, which is
needed once after a change to the roles or the database images because their set-up scripts run only on an empty volume.

## Tests

```sh
docker compose run --rm migrate pytest -q -p no:cacheprovider /app/tests
docker compose run --rm migrate pytest -q -p no:cacheprovider /app/tests/test_health.py
```

Tests run in the `migrate` service because it holds the PostgreSQL owner role, which pytest needs to create its test
database; `web` holds only the runtime role. The tests use the real databases, never mocks or SQLite. `tests/` is
mounted along with read-only `compose.yaml` for startup regression checks, but the image copies `src/` at build time,
so run `docker compose build migrate web` after changing application
code. `migrate` uses the dev image; `web` uses the runtime image. Test counts are not written here; the run prints them. The app image has no Git, so its four Git-index-only
documentation tests are also run on the host with Python/pytest and Git:

```sh
python -m pytest --noconftest -q -p no:cacheprovider tests/test_check_docs.py tests/test_package_submission.py
python scripts/check_docs.py
```

The main suite and all database tests remain in Docker. The host command disables the database conftest because these
checks operate only on temporary documentation trees and submission archives.

### Continuous integration

[.github/workflows/ci.yml](.github/workflows/ci.yml) runs on pull requests and pushes to `main`, with a manual
`workflow_dispatch` entry for the failure-artifact canary. It needs no repository secrets. `databases` and `browser`
use `ubuntu-22.04` with the MongoDB kernel guard; `host` and `quality` use `ubuntu-24.04`. Every job has a timeout.

| Job | Checks |
|---|---|
| `databases` | Owner migrations and drift, fixture import and demo accounts, one full Django run under coverage, then pipeline tests. Enforces 80% line coverage of src excluding migrations; retains branch data in XML/HTML reports for seven days |
| `host` | Documentation and Git-index/packaging tests; any skipped host test fails the job |
| `quality` | Ruff E/F/I lint and the 120-column format check, then audits of runtime, dev, tools and the minimal translation environment; short, owned audit exceptions are validated before use |
| `browser` | The documented HTTP smoke check of all three role landings, then one serial Chromium run against runtime-role web: registration, seller approval/upload/scoping, facets, checkout/lifecycle/refund, reviews, wishlist and analytics/activity |
| `benchmark` | Optional ruleset check on ubuntu-22.04: load the benchmark fixture, run its real-database tests and B1–B6 correctness only, retain failed checks/plans/resources and generated tables. A duration artifact records each job; this does not change the four required checks |

The [coverage wrapper](scripts/coverage_suite.py) runs the suite once with branch measurement, keeps that original
data for reports and derives a line-only report for the threshold. Unexecuted namespace files also count. The
[audit wrapper](scripts/audit_requirements.py) rejects expired exceptions and any advisory with a fix, including
an advisory whose exception was valid before a fix appeared. Exception metadata lives in
[.github/pip-audit-exceptions.toml](.github/pip-audit-exceptions.toml). The Argos file is audited without installing
its deliberately unused Torch/Stanza dependency tree.

To reproduce the CI checks from the repository root, activate a Python 3.13 virtual environment and install
`src/requirements-dev.txt`. The following commands use Bash (Git Bash on Windows). The private environment below
does not change the main stack's `.env`. `dc` always supplies the explicit isolated project and environment file.

```sh
python -m pip install --disable-pip-version-check -r src/requirements-dev.txt
mkdir -p .cache/ci-local
python - <<'PY'
import sys
sys.path.insert(0, "src")
from tools.init_env import complete_env
complete_env(".cache/ci-local/environment.env", ".env.example")
PY
export CI_ENV_FILE="$PWD/.cache/ci-local/environment.env"
export MONGO_PORT=0 APP_PORT=8011
export MSYS_NO_PATHCONV=1
dc() { docker compose --env-file "$CI_ENV_FILE" -p "$COMPOSE_PROJECT_NAME" "$@"; }
```

Database job, including coverage and pipeline tests:

```sh
export COMPOSE_PROJECT_NAME=mercer-ci-databases-local
dc build migrate
dc --profile tools build tools
dc up --detach --wait --wait-timeout 300 db mongo
dc run --rm migrate
dc run --rm migrate python manage.py makemigrations --check --dry-run
dc run --rm migrate python manage.py import_olist --source /app/tests/fixtures/olist/clean
dc run --rm migrate python manage.py seed_demo
mkdir -p coverage-reports
chmod a+rwx coverage-reports
dc run --rm --volume "$PWD/coverage-reports:/reports" migrate python /app/scripts/coverage_suite.py --output /reports
dc --profile tools run --rm tools pytest -q -rs -p no:cacheprovider analytics/tests
dc --profile tools down --volumes --remove-orphans
```

Quality and host checks need no databases:

```sh
python -m ruff check .
python -m ruff format --check .
python scripts/audit_requirements.py
python scripts/check_docs.py
CI_HOST_TEMP="$(python -c 'import tempfile; print(tempfile.mkdtemp(prefix="mcih-"))')"
python -m pytest --noconftest -q -rs -p no:cacheprovider --basetemp "$CI_HOST_TEMP" --junitxml .cache/ci-local/host.xml tests/test_check_docs.py tests/test_package_submission.py
python - <<'PY'
from xml.etree import ElementTree
suite = ElementTree.parse(".cache/ci-local/host.xml").getroot().find("testsuite")
assert int(suite.get("skipped", 0)) == 0, "Host checks must not skip"
PY
```

Keep the host test temporary repositories outside this checkout: Git would otherwise inherit its ignore rules.
The short system-temp path also avoids Windows path-length failures.

Browser job, with a fresh project. Chromium's Linux system dependencies use `--with-deps`; on Windows use
`python -m playwright install chromium`. The wrapper exports only the three demo logins to the test process,
filters database credentials, and redacts console output. Parent Django database fixtures are excluded by
`--confcutdir`; the browser subtree is excluded from the Docker Django suite.

```sh
export COMPOSE_PROJECT_NAME=mercer-ci-browser-local
dc build migrate web
dc up --detach --wait --wait-timeout 300 db mongo
dc run --rm migrate
dc run --rm migrate python manage.py import_olist --source /app/tests/fixtures/olist/clean
dc run --rm migrate python manage.py seed_demo
dc run --rm migrate python manage.py seed_activity --count 2000
dc up --detach --wait --wait-timeout 300 web
dc run --rm migrate python /app/scripts/smoke_olist.py
python -m playwright install --with-deps chromium
python -m scripts.browser_suite --env-file "$CI_ENV_FILE" --base-url "http://127.0.0.1:$APP_PORT" --output test-results
dc down --volumes --remove-orphans
```

Before filming, run this browser suite once against a fresh full-data stack using
[Load Olist and demo accounts](#load-olist-and-demo-accounts), then `seed_activity --count 2000`.

For a local artifact check, before teardown run the same browser wrapper with
`--force-browser-failure --canary-only`; a failing canary is the expected result. Normal runs leave this off.
Failures retain a trace and screenshot; passwords and authentication cookies are redacted before upload. The
workflow uploads only sanitized failure artifacts, retained for seven days. To prove hosted behavior, manually
dispatch the reviewed workflow with `force_browser_failure: true` and inspect its failed browser job's artifacts.
Local results do not replace that hosted exit check. The format gate runs in the required `quality` job; the separate
benchmark fixture job is described below and is not a required ruleset check.

## Configuration

`src/tools/init_env.py` creates `.env` from [.env.example](.env.example) and, run again later, adds keys a newer version
needs without changing existing ones. `.env` is git-ignored: never commit it or paste resolved Compose output.
After updating to the benchmark harness, rerun `python src/tools/init_env.py` even for ordinary app startup:
Compose validates required `BENCH_*` interpolation before filtering profiles, so older environments fail until completed.

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | At least 50 characters; generated |
| `DJANGO_DEBUG` | `true` turns debug on; off by default |
| `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated; keep `127.0.0.1` for the container health check |
| `APP_PORT`, `MONGO_PORT` | Host ports (127.0.0.1 only) |
| `COVERAGE_SOURCE` | Coverage source directory: defaults to src on the host; migrate sets /app to match its image layout |
| `POSTGRES_DB` | Database name |
| `POSTGRES_OWNER_USER`, `POSTGRES_OWNER_PASSWORD` | Owner role: owns the database; runs migrations, the importer and pytest |
| `POSTGRES_RUNTIME_USER`, `POSTGRES_RUNTIME_PASSWORD` | Runtime role used by `web`: reads and writes rows, no DDL, DROP or TRUNCATE |
| `POSTGRES_ADMIN_PASSWORD` | Bootstrap superuser, given only to the `db` service |
| `MONGO_ROOT_USER`, `MONGO_ROOT_PASSWORD` | MongoDB root, used only to initialise the replica set and users |
| `MONGO_APP_USER`, `MONGO_APP_PASSWORD`, `MONGO_DB` | Application user: `readWrite` on `MONGO_DB` and `test_<MONGO_DB>` only |
| `DEMO_CUSTOMER_PASSWORD`, `DEMO_SELLER_PASSWORD`, `DEMO_OPERATOR_PASSWORD` | Generated demo secrets for seeding and tests; CI exports only these login values to host browser tests, masks them, and filters database credentials; required with no fallback |
| `BENCH_DB` | Fixed `bench`; the harness refuses any other database or host |
| `BENCH_ADMIN_PASSWORD` | Isolated PostgreSQL bootstrap secret; only bench-db receives it |
| `BENCH_OWNER_USER`, `BENCH_OWNER_PASSWORD` | Separate benchmark owner, with CREATEDB and pg_checkpoint for templates/checkpoints |
| `BENCH_RUNTIME_USER`, `BENCH_RUNTIME_PASSWORD` | Separate runtime role needed by unchanged app migrations; the harness uses the owner |
| `BENCH_MONGO_ROOT_USER`, `BENCH_MONGO_ROOT_PASSWORD` | Isolated replica-set bootstrap; host runner uses docker exec for server-setting readback without exposing credentials |
| `BENCH_MONGO_USER`, `BENCH_MONGO_PASSWORD` | Separate MongoDB user with readWrite on bench only |

Credentials are set up on an empty volume only: editing `.env` does not rotate an existing database password.

## Services

| Service | Role |
|---|---|
| `db` | PostgreSQL 18; creates the owner and runtime roles on first start (`src/docker/10-roles.sh`) |
| `mongo` | MongoDB 9.0 as the single-node replica set `rs0` with authentication (`src/docker/mongo-start.sh`); healthy once the set and the application user exist. The app connects with `replicaSet=rs0`; tools on the host need `directConnection=true` |
| `migrate` | Owner role and dev image (`-app-dev`): migrations, import, seeding, pytest and coverage; data/configuration mounted read-only |
| `web` | Runtime image (`-app`) and PostgreSQL runtime role; Gunicorn on 127.0.0.1 only, without the dev tools |
| `tools` | Optional tools profile; pinned offline profiling, cleaning, generation and pipeline tests; only working directories mounted, with raw source read-only and no .env mount |
| `translation` | Optional isolated translation profile; pinned Argos package/tokenizer and CTranslate2 inference; offline at runtime, raw source read-only, no .env mount |
| `bench-db` | Optional bench profile; same PostgreSQL digest, separate roles/data, explicit durability, 512 MB shared buffers and 512 MB shared memory, no published port |
| `bench-mongo` | Optional bench profile; same MongoDB digest, separate single-node replica set and keyfile, 0.75 GiB WiredTiger cache, readWrite on bench only, no published port |
| `bench-runner` | Optional bench profile; app dev image and matching drivers, source mounts read-only and results writable; no Docker socket. Each of these three services has 2 CPUs, 2 GiB memory and no extra swap |

Both database images are pinned by digest in [compose.yaml](compose.yaml); the reasons are in
[docs/DECISIONS.md](docs/DECISIONS.md).

## Benchmark (isolated databases)

The approved [benchmark contract](docs/plans/benchmark.md) owns the method and final-run machine. Use explicit
projects; the runner rejects `mercer`. Budget at least six VM CPUs and eight GiB of Docker memory, plus initial image
downloads. Each load and correctness pass can take several minutes on a laptop; the full repeated matrix takes
longer. Actual load/run durations and peak resources are emitted in the retained console/provenance/stats evidence,
not maintained as prose estimates. Run trials with other heavy workloads stopped. The runner labels an undersized VM
and refuses `--final` there or on a dirty tree. Warm database buffers are intentional; application caches and telemetry
are disabled.

From the root (host Python 3.13, standard library only; all database drivers run in the container):

```sh
python src/tools/init_env.py
python -c "from pathlib import Path; Path('benchmarks/results').chmod(0o777)"
docker compose -p mercer-bench-local --profile bench build bench-runner
docker compose -p mercer-bench-local --profile bench up --detach --wait bench-db bench-mongo
docker compose -p mercer-bench-local --profile bench run --rm bench-runner python -m benchmarks.load --source /app/data/derived/olist/clean
python -m benchmarks.run --project mercer-bench-local --mode correctness --label first-pass
docker compose -p mercer-bench-trial --profile bench build bench-runner
docker compose -p mercer-bench-trial --profile bench up --detach --wait bench-db bench-mongo
docker compose -p mercer-bench-trial --profile bench run --rm bench-runner python -m benchmarks.load --source /app/data/derived/olist/clean
python -m benchmarks.run --project mercer-bench-trial --require-clean --mode measure --only baseline,B1,B4 --operations-per-client 5 --label trial
```

For the designated-machine run, use the [final-run checklist](#final-run-checklist-next-session) below after review.
The loader requires empty destinations; to reload, explicitly tear down only
the named benchmark project with `docker compose -p mercer-bench-local --profile bench down --volumes` and repeat.
Never remove application volumes. PostgreSQL mutation runs use bench_run cloned from bench_template; MongoDB restores
checksummed NDJSON in ignored benchmarks/results/.state. Each restored MongoDB collection is dropped and recreated
with its validator and ordered index catalogue; secondary indexes are bulk-built after inserting the documents.
Both baselines and index catalogues are checked before and after each mutation, including failed attempts.
B5 runs first and refuses any project with a nonzero restores_since_load counter. Storage probes wait for the
explicit automatic checkpoint interval plus a margin; the round-trip client needs no extra database privilege.
B4 restores the original index catalogue in a finally block.

The runner prints its dated results directory. It holds raw operations, failed checks, run-level and median/range
CSV summaries, query plans, Docker samples, source/golden hashes, host hardware, server settings, trigger state,
driver versions and container limits. All workers connect and ping before a barrier; each first result is
canonicalised against golden before a second barrier releases timing. Later results use plain fetched-row equality.
The default is five measured operations per client at 1/10/50 clients (`--operations-per-client`), except B2: it
uses 1/10 clients and twenty operations per client (`--b2-operations-per-client`, minimum five). B2refresh uses one
client with the B2 count. B4 uses one client; its B2-derived cases use the B2 count and its other cases use the
default count. Provenance records each B4 case's operation count. Each worker also validates one untimed reference
operation; B3 keeps fifty buyers. Correctness query passes stay at one client and one operation. The per-workload
matrix is recorded in provenance alongside the legacy default keys. Throughput excludes setup, initial
canonicalisation and teardown. The Python no-op
measures harness overhead; SELECT 1 and MongoDB ping provide the per-engine round-trip noise baselines.
Per-run CPU is the median of the one-second Docker runner intervals overlapping its timed window, so short runs
have coarse attribution. Runs at or above 180% runner CPU remain visible with client_saturated=true and contribute
no headline ratio; summary.csv keeps their metrics and report tables mark them as not headline. Regenerate every chart/table with
`python -m benchmarks.report benchmarks/results/<run-directory>`. Report files are CSV/SVG, with ratios and absolute
latencies; amendment-j.csv evaluates noise per B1 parameter set/client count and B4 index. Failed checks have no
accepted timing. B1 broad retains the planner-chosen MongoDB plan as the headline; documents_hinted separately
uses spec_attributes with the same golden. No scale-up generator is built; the owner decides after reading that table.
`report/memory.csv` reports median and peak memory per container for the whole run and each workload. Workload rows
include only samples whose timestamps lie in the union of that workload's `runs.csv` windows; the median is
sample-weighted, without interpolation. Whole-run rows also include setup and restoration. Untimed workloads and
windows without samples retain blank figures with an explicit status. Docker's rounded `MemUsage` makes converted
byte values approximate. `report/memory-settings.csv` records the original caps, caches and input footprint; the
footprint is populated only when local input files match every checksum in provenance. Stopped-container CPU
placeholders are skipped for CPU attribution; independently valid memory samples remain usable. These tables do
not measure memory for the same operation across engines.
New result directories are ignored while collecting evidence so subsequent runs can use the same clean commit.
After inspecting them, stage only the intended directories with `git add -f -- benchmarks/results/<run-directory>`.
Use --require-clean for recorded reruns; it refuses uncommitted source changes.

Use a different fixture project for benchmark tests:

```sh
python -c "from pathlib import Path; Path('benchmarks/results').chmod(0o777)"
docker compose -p mercer-bench-fixture --profile bench build bench-runner
docker compose -p mercer-bench-fixture --profile bench up --detach --wait bench-db bench-mongo
docker compose -p mercer-bench-fixture --profile bench run --rm bench-runner python -m benchmarks.load --source /app/fixtures/olist/clean
docker compose -p mercer-bench-fixture --profile bench run --rm bench-runner pytest -c /dev/null --rootdir=/app/benchmarks -q -p no:cacheprovider /app/benchmarks/tests
docker compose -p mercer-bench-fixture --profile bench down --volumes
docker compose -p mercer-bench-fixture --profile bench up --detach --wait bench-db bench-mongo
docker compose -p mercer-bench-fixture --profile bench run --rm bench-runner python -m benchmarks.load --source /app/fixtures/olist/clean
python -m benchmarks.run --project mercer-bench-fixture --source /app/fixtures/olist/clean --golden fixture --mode correctness --label fixture
docker compose -p mercer-bench-fixture --profile bench down --volumes
```

Regenerate independent golden CSVs with
`python -m benchmarks.reference.compute --source tests/fixtures/olist/clean --output benchmarks/golden/fixture` and
`python -m benchmarks.reference.compute --source data/derived/olist/clean --output benchmarks/golden/full`.
The reference never imports a database driver. Its committed output schema fixes decimal scales and Python
ROUND_HALF_EVEN, and its CSVs have stable LF newlines across Windows and Linux.
Tests require a freshly loaded fixture project; their restores invalidate B5's freshness counter, so the example
reloads before the separate correctness pass. The optional CI job does the same, checks the MongoDB kernel range,
and uploads only the directory printed by its current runner invocation. --only B5,B5restore on a fresh project
records a fresh footprint plus two restore cycles in storage-restores.csv. The stated storage tolerance is 10%
with a 64 KiB allocation floor per collection and metric; physical storage probes wait for automatic checkpoints.
The results-directory permission command lets the container's UID write on Linux; it affects only benchmark
evidence. The host runner creates writable run directories and replaces container-owned provenance atomically.

Requests also expose `Server-Timing: pg;dur=…, mongo;dur=…` and db_pg_ms/db_pg_queries/db_mongo_ms/db_mongo_commands
in the existing JSON request line. Counters use request-local state and never log SQL, parameters or command bodies.

### Final-run checklist (next session)

The completed designated-machine evidence and the owner's source-selection rule are recorded in the
[benchmark close-out](docs/plans/benchmark.md#designated-machine-final-and-close-out-2-november-2026).
This checklist remains the reproduction procedure.

Run on reviewed, committed, clean `main` after both preparation PRs are merged. Follow amendment k in the
[benchmark plan](docs/plans/benchmark.md#decisions): designated machine plugged in, other heavy apps stopped, Docker
VM settings checked. The commands below use dedicated projects; leave existing application projects alone.

1. **Fresh full-data load.** From the repository root, run the following. To **reload** in steps 4 and 5, repeat the
   last three commands (`down`, `up`, `load`); the loader requires empty destinations. Check the reported usable
   memory, not just Docker Desktop's allocation label: `--final` requires at least six CPUs and 8,589,934,592
   bytes (`8 * 1024**3`). An 8 GB allocation can report less usable memory; raise the allocation until this check
   meets the gate before loading or piloting.

   ```sh
   docker info --format 'CPUs={{.NCPU}} memory_bytes={{.MemTotal}}'
   python src/tools/init_env.py
   docker compose -p mercer-bench-final --profile bench build bench-runner
   docker compose -p mercer-bench-final --profile bench down --volumes
   docker compose -p mercer-bench-final --profile bench up --detach --wait bench-db bench-mongo
   docker compose -p mercer-bench-final --profile bench run --rm bench-runner python -m benchmarks.load --source /app/data/derived/olist/clean
   ```

2. **Pilot.** Keep the printed results directory. B2 uses its default 20 operations per client at 1/10 clients.

   ```sh
   python -m benchmarks.run --project mercer-bench-final --mode measure --only baseline,B1,B2 --operations-per-client 100 --label pilot
   ```

3. **Choose the counts.** Use the pilot's `host.json` duration and `runs.csv` windows to project the full run, allowing
   for the remaining workloads and reloads. Keep 100 default operations and 20 for B2 if it fits one sitting;
   otherwise choose 50 and 10 and state the limit in the report. Check for failed cells/timeouts before continuing.
   B3 always keeps fifty buyers. Retain the pilot and record the choice in the final run's provenance flags below.

4. **Reload**, then run correctness on the clean tree. B5 refuses any earlier restore, so always reload before a
   correctness run that includes B5, including a retry after a failed run.

   ```sh
   python -m benchmarks.run --project mercer-bench-final --mode correctness --require-clean --label final-correctness
   ```

5. **Reload again**, then run the final matrix. If step 3 selected the fallback, replace `100` with `50` and `20`
   with `10` in this command. Keep the printed directory and check every correctness gate.

   ```sh
   python -m benchmarks.run --project mercer-bench-final --mode measure --final --require-clean --operations-per-client 100 --b2-operations-per-client 20 --label final
   ```

6. **Per-request evidence (k2).** Finish the benchmark first and stop its engines. The timing script refuses an
   active benchmark runner and must never run alongside a benchmark. Prepare a separate full-data app stack using
   unused loopback ports; this PowerShell example reads demo credentials from the ignored `.env` in place.

   ```powershell
   docker compose -p mercer-bench-final --profile bench stop
   $env:APP_PORT = "18082"
   $env:MONGO_PORT = "0"
   docker compose -p mercer-request-final up --build --detach --wait
   docker compose -p mercer-request-final run --rm migrate python manage.py import_olist --source /app/data/derived/olist/clean
   docker compose -p mercer-request-final run --rm migrate python manage.py seed_demo > $null
   python -m benchmarks.request_timing --project mercer-request-final --base-url http://127.0.0.1:18082
   ```

   The script uses anonymous shopping requests and a separate in-memory operator session, one warm-up pass and
   twenty sequential requests per page. It joins response IDs to this project's JSON web logs and saves
   `requests.csv`, one aggregate CSV per page and `provenance.json`. The category page, facet and detail use the
   same visible product and its source category/attributes, with the chosen paths recorded. It retains no
   credentials, cookies or response bodies.
   A fixture rehearsal uses `--source tests/fixtures/olist/clean` on a separately loaded fixture app project.

7. **Regenerate tables if needed.** `benchmarks.run` already runs `benchmarks.report` for each benchmark run. Use
   this command only to regenerate its tables and charts; the k2 directory has its own CSVs and does not use the
   driver report generator.

   ```sh
   python -m benchmarks.report benchmarks/results/<run-directory>
   ```

8. **Retain the reviewed evidence.** Inspect all outputs, then explicitly stage only these run directories (replace
   each placeholder with the directory printed by its command).

   ```sh
   git add -f -- benchmarks/results/<pilot-run-directory> benchmarks/results/<correctness-run-directory> benchmarks/results/<final-run-directory> benchmarks/results/<request-timing-directory>
   ```

9. **Tear down only the two projects created here**, after the evidence is saved. In PowerShell, clear the temporary
   port overrides for subsequent work.

   ```powershell
   docker compose -p mercer-bench-final --profile bench down --volumes
   docker compose -p mercer-request-final down --volumes
   Remove-Item Env:APP_PORT, Env:MONGO_PORT
   ```

## Load Olist and demo accounts

All raw and derived inputs are included, so a fresh clone does not need Kaggle credentials or a translation model.
After the stack is healthy, run the loader as the owner:

```sh
docker compose run --rm migrate python manage.py import_olist
docker compose run --rm migrate python manage.py verify_olist
docker compose run --rm migrate python manage.py seed_demo
docker compose run --rm migrate python /app/scripts/smoke_olist.py
```

The loader verifies checksums and CSV headers, refuses non-empty destinations, creates MongoDB objects, shows progress
for each COPY/collection stage, restores USER triggers, repairs identity sequences and checks money, refunds, row counts
and ownership. MongoDB loads use bounded batch transactions with progress. Invalid inputs roll back PostgreSQL writes
and compensate the MongoDB IDs attempted by that import. A final PostgreSQL commit failure
after MongoDB commits is compensated; an unresolved connection failure may require the explicit local reset below.
`verify_olist` repeats reconciliation and the delivery-delay comparison **before seed_demo**, whose additional accounts
and labelled stock adjustments intentionally differ from the source ledger.

The approved full-import target is under ten minutes. `import_olist` prints measured duration and loader process peak
RSS in its final `Import metrics` JSON line; `verify_olist` prints the invariant and raw/imported comparison results.
Keep execution logs, timings and review evidence outside `data/` (for example, in ignored `.cache/olist-review/`), so
they do not enter the reproducible data manifests. The memory figure covers the loader process; database containers
are separate. Budget for the initial image downloads separately; import reads the already prepared local files.
Memory is bounded by COPY blocks and MongoDB batches during loading; full-data profiling/cleaning additionally holds
the source tables and needs several GB of Docker memory. A long translation is optional regeneration, not startup work.

Demo usernames are demo-chee-long, demo-erfan, demo-syahfariz, demo-jun-keat, demo-joash (customer role), demo-seller,
demo-applicant (a labelled pending seller, using DEMO_SELLER_PASSWORD) and demo-operator. Read their passwords locally from the corresponding DEMO_*_PASSWORD variables in the ignored .env;
passwords have no fallback and are never printed. The seller is linked to a real high-volume Olist seller. Two product
rows explicitly label their sold-out and low-stock/long-lead-time demo adjustments, including any relisting needed to
make them visible. Imported accounts otherwise have
unusable passwords. Rerunning `seed_demo` never resets a seller status an operator has already decided. The shop,
product details, registration, seller applications, cart, checkout, orders, reviews and the operator console work. The operator dashboard is available as described below. The labelled foundation design previews
remain available as visual samples.

Relisting labels also use retained imported order history, so rerunning `seed_demo` repairs labels omitted by an
earlier seeder even when it already set the product active.

For a fresh import, first verify the project is mercer and that its named volumes belong to this clone. The following
**deletes this project's local database data**; it leaves raw/derived repository files intact:

```sh
docker compose down --volumes
docker compose up -d --build
docker compose run --rm migrate python manage.py import_olist
```

## Accounts and the operator console

Each account has one role. After login, customers land on the shop, approved sellers on the seller centre and every
other seller on their status page; operators land on the console. Pending, rejected and suspended sellers can log in but
see only their status page. A Phase 1A database is upgraded in place by the `migrate` service on the next
`docker compose up --build`; no reset or re-import is needed.

| Path | Who | Purpose |
|---|---|---|
| `/register/` | Anyone logged out | Customer account, with an optional zip prefix, city and state |
| `/sell/apply/` | Anyone logged out | Seller application: the account and a pending seller in one transaction |
| `/account/` | Customers | Profile |
| `/seller/`, `/seller/status/` | Approved sellers; any seller | Read-only seller centre; the seller's own status and latest decision |
| `/operator/`, `/operator/sellers/<id>/` | Operators | Sellers by status; approve, reject, suspend or reinstate with a required reason (POST only) |
| `/operator/audit/` | Operators | Audit log of seller decisions, newest first, with Made by and Decision filters |

Operators are never created through the web. Besides `demo-operator` from `seed_demo`, create or re-password one with
the password from `DEMO_OPERATOR_PASSWORD` (never a command-line argument, never printed); an existing account with
another role is refused:

```sh
docker compose run --rm migrate python manage.py create_operator <username>
```

## Catalogue and seller products

After pulling catalogue changes into an existing setup, add its MongoDB indexes once (the `migrate` service runs
Django migrations only; `mongo_setup` is idempotent):

```sh
docker compose run --rm migrate python manage.py mongo_setup
```

### Catalogue browsing

The shop at `/products/` shows featured picks and categories. Search by name or choose a category, then combine
price, rating and category options. Newest, price and top-rated ordering keep filters when changing pages.
Category pages use `/products/category/<slug>/`; public shops use `/products/shops/<id>/`.
The detail page combines price and stock from PostgreSQL with descriptions, ratings and recent reviews from MongoDB.
Generated fields remain labelled. Products show category icon cards unless their seller uploaded a photo, served from
GridFS. Featured stock photos were dropped by [catalogue amendment k](docs/plans/catalogue.md).


### Seller products and category options

An approved seller opens **My products** at `/products/mine/` to create, edit or deactivate their own products.
Choose a category and load its options before filling the product form. Price, stock, shipping fee and days to ship
are required; uploads accept JPEG, PNG and WebP up to 2 MB and are re-encoded before GridFS storage. Taken-down
products show the operator's reason and cannot be edited by the seller.
Operators open **Products** at `/products/operator/` to take down or restore a product with a reason, and
**Categories** at `/products/operator/categories/` to add a category option. Existing products need no rewrite.
The audit page shows product price/stock changes and their actors alongside seller decisions.

Seller saves keep the PostgreSQL operation open until MongoDB accepts its fields. A MongoDB error rolls the SQL
change back. A rare successful MongoDB write followed by an uncertain SQL commit is logged; inspect the stores with:

```bash
docker compose run --rm migrate python manage.py check_specs
docker compose run --rm migrate python manage.py check_specs --repair
```

The repair flag removes specs whose products no longer exist, including their photos. Missing specs or category
mismatches remain reported for restoration from the source; the command does not invent missing product content.

## Browsing activity and seller insights

Product detail records a view and catalogue searches record the trimmed query, up to 100 characters. Activity writes
use MongoDB w:1 and failures are logged without breaking the page. Home and product pages show the last ten distinct
recent products for the signed-in user or anonymous browser session. The existing Trending panel shows views over
the last 24 hours, overall or in the selected category, with equal counts sharing a rank. Withdrawn products stay hidden.

For a database imported before activity landed, create the time series once before browsing. A fresh import already
runs mongo_setup. To populate the demo with labelled browsing events:

```sh
docker compose run --rm migrate python manage.py mongo_setup
docker compose run --rm migrate python manage.py seed_activity
```

The default appends synthetic views weighted by imported sales over the past 30 days relative to seeding time. Use
`--count` for a smaller demo; rerunning appends another labelled batch. Data carries is_generated and the panels say
when generated views contribute. Events expire after 30 days. Never treat this synthetic browsing as observed Olist data.

Approved sellers open `/seller/insights/` for their own products' views and non-cancelled units sold in the same rolling
30-day window. "Units per view" compares the totals; it does not identify which visitor bought an item. No views means
no ratio, and unavailable MongoDB counts are shown as unavailable while sales can still be read.

On recording day, run the seed_activity command above and place a few demo purchases for the seller's products
before filming Insights. Its rolling sales window becomes near-empty after the imported data ends. Keep the real
last-30-days window: browsing events expire, so anchoring Insights to the imported history would not preserve views.

## Operator stock planning

Open `/operator/dashboard/` as an operator. Every panel states the reporting date and its PostgreSQL/MongoDB sources.
The date is derived from the latest imported order's placed_at; demo orders cannot move it. Sales, reviews and delivery
events after that date are excluded. Inventory remains the current stock so a seller restock can clear a warning.

The stock table averages demand over 28 complete calendar dates, including zero-sale days, and flags cover shorter
than lead time. Filter it by category or seller number. Category tables show monthly revenue, units, rank and
month-on-month change; the locally bundled Chart.js chart shows the latest month's leading categories. Revenue is
item value without freight. Delivery panels join PostgreSQL delivery dates and zip-centre distances with one MongoDB
score per order, excluding copied order reviews. Seller risk requires at least ten delivered orders by the reporting
date; more than 20% late marks a seller at risk. The panel states how many smaller samples it excludes. The poor-review
panel lists products averaging at most two stars from at least five reviews.

`import_olist` refreshes daily product sales after the verified import commits. For a database imported before this
feature, press "Refresh sales history" once; migrations alone leave the materialized view unpopulated. The button
also refreshes after a restock. It uses a restricted owner-owned function, so the web role still has no direct refresh
privilege. A refresh failure after import is reported as a committed import requiring a refresh retry.

The dashboard takes a few seconds on the full data; preload `/operator/dashboard/` before filming. This is accepted
for Tier 1. Caching remains in the Tier 2 redis workstream.

Chart.js is pinned to [the upstream 4.5.1 release](https://github.com/chartjs/Chart.js/releases/tag/v4.5.1), with its
MIT licence beside the vendored distribution. Exact amounts are rendered in the tables; chart coordinates are presentation only.

## Wishlist and restock alerts

Customer product cards and detail pages have a save/remove button, including when stock is zero. `/wishlist/`
shows saved products and their current stock status. When any database update takes a saved product from zero
stock to a positive amount, PostgreSQL creates one unseen in-app alert per customer. Repeated restocks before
viewing do not create duplicate unseen alerts. This includes seller edits and checkout cancellations.

The header's Alerts badge counts your visible unseen alerts. Opening `/alerts/` marks the displayed page's alerts
seen; later restocks can notify you again. Taken-down/inactive products and suspended shops are hidden from the
wishlist, alerts and badge. Alerts stay inside Mercer; no email setup is needed.

## Reviews

Customers open a delivered order and choose "Write or edit review" beside an item. Each line has one review, which
its customer can edit or delete. Product detail has one rating block, a histogram and paginated newest-first reviews;
English machine translations are labelled and the Portuguese original is available through the language links.
Undelivered imported reviews carry a historical label. Shop ratings and Top rated sorting use the import-fixed
Bayesian prior rather than giving one five-star review the same weight as many good reviews.

Approved sellers have a read-only "My reviews" page at `/seller/reviews/`. Operators use `/operator/reviews/` to take
reviews down with a reason or restore them. Hidden reviews leave the public list, histogram and latest-five subset;
the operator's audit log records the decision. A MongoDB outage rolls back the SQL audit transaction; an uncertain
SQL commit after MongoDB succeeds is logged for reconciliation, as with catalogue cross-store writes.

## Cart, payments and orders

Customers add available products from product detail pages, change quantities or remove items at `/cart/`, and review
and choose a simulated payment method at `/checkout/`. Shipping is charged per unit. A single payment creates one
order per shop; `/orders/` lists purchases and links to each shop order's items, delivery progress and refund.
Prices and shipping must still match the review before payment; changed values send the customer back to review.
Credit cards support one to twelve instalments; boleto, voucher and debit card use one. No card details are collected.

Approved sellers use `/seller/orders/` (My orders) to mark their own paid orders shipped. Operators use
`/operator/orders/` to mark shipped orders delivered. A customer can cancel their own shop order before shipping;
its stock and full shop payment return together, with the refund visible on the order detail page.

Checkout's real-database tests, including the repeated last-unit race, can be run separately:

```sh
docker compose run --rm migrate pytest -q -p no:cacheprovider /app/tests/test_checkout.py /app/tests/test_checkout_schema.py /app/tests/test_checkout_concurrency.py /app/tests/test_checkout_views.py
```

The seller and operator order lists can filter by status and order number. Invalid filter values show a form error;
seller filters always stay within that seller's orders.

## Regenerate the data (optional)

The raw files are never edited. The preparation image pins Python by digest and pandas/NumPy/pytest versions, and has
no network access while running. Translation is a separate optional image and never part of the application image.
The exact scripts, flags and byte-level formats are documented by their --help output.

```sh
docker compose --profile tools build tools
docker compose --profile tools run --rm tools python analytics/profile_olist.py
docker compose --profile tools run --rm tools python scripts/clean_olist.py
docker compose --profile tools run --rm tools python scripts/generate_content.py
docker compose --profile tools run --rm tools python analytics/profile_olist.py --docs docs/DATA_MODEL.md
docker compose --profile tools run --rm tools python scripts/generate_content.py --checksum-root data/derived/olist
docker compose --profile tools run --rm tools pytest -q -p no:cacheprovider analytics/tests
```

The ECB execution-day reference response, its true publication date, and the BRL-to-SGD cross rate are stored in
`data/derived/olist/fx.json` and the adjacent XML. Regeneration reuses this fixed rate, not a new network quote.
The cleaning ledger accounts for every source row and explains all transformations. Generated product content uses
seed 82 and the category definitions in `data/derived/olist/templates/categories.json`. SHA-256 manifests protect raw,
clean and complete derived outputs. Pipeline tests repeat cleaning and generation on the test fixture. To check the
full dataset separately, run both stages into two directories and compare their manifests with the prepared data:

```sh
docker compose --profile tools run --rm tools python scripts/clean_olist.py --output .cache/olist-reproduce-a
docker compose --profile tools run --rm tools python scripts/generate_content.py --output .cache/olist-reproduce-a
docker compose --profile tools run --rm tools python scripts/clean_olist.py --output .cache/olist-reproduce-b
docker compose --profile tools run --rm tools python scripts/generate_content.py --output .cache/olist-reproduce-b
docker compose --profile tools run --rm tools python -c "import sys; sys.path.insert(0, 'scripts'); from olist_common import checksums; assert checksums('.cache/olist-reproduce-a', verify=True) == checksums('.cache/olist-reproduce-b', verify=True) == checksums('data/derived/olist/clean', verify=True); print('Full-data clean/generate outputs match byte for byte')"
```

To regenerate translation, download the pinned Argos pt-to-en 1.9 model once with host Python (standard library), then
run the pinned Argos 1.9.6 package loader/tokenizer and CTranslate2 backend offline in its isolated image:

```sh
python scripts/translate_reviews.py --download-model --download-only
docker compose --profile translation build translation
docker compose --profile translation run --rm translation python scripts/translate_reviews.py
```

The exact model SHA-256 and inference settings are checked against the committed translations.model.json manifest.
Only distinct title/comment strings are translated. Original Portuguese, SHA-256 text identities, English text and
machine-translation flags are stored in translations.csv. Work is atomically saved after each batch and resumes from
those hashes. The batched backend translates whole newline-separated paragraphs without the optional PyTorch/Stanza
segmenter; punctuation-only inputs that decode empty retain their original text. No online translation API is called.
The model download goes into ignored .cache, not the submission or app image. Expect the one-off translation to take
substantially longer than cleaning or import; it can be interrupted and resumed.

To rebuild the deterministic raw test subset (all real Olist rows), rerun:

```sh
docker compose --profile tools run --rm tools python scripts/make_fixture.py
docker compose --profile translation run --rm translation python scripts/translate_reviews.py --raw tests/fixtures/olist/raw --output tests/fixtures/olist/translations.csv
docker compose --profile tools run --rm tools python scripts/clean_olist.py --raw tests/fixtures/olist/raw --translations tests/fixtures/olist/translations.csv --output tests/fixtures/olist/clean
docker compose --profile tools run --rm tools python scripts/generate_content.py --output tests/fixtures/olist/clean
```

The fixture selection manifest records adversarial cases and scarce cases where the complete source contains only one
example. Pipeline tests verify the rule outcomes and two complete cleaning/generation runs byte for byte.

## Editor set-up (optional)

Docker is the supported runtime. For VS Code and Pylance to resolve imports, create a local environment once with
`python -m venv .venv` and `pip install -r src/requirements.txt` inside it, then pick `.venv` as the interpreter (VS Code
lists it automatically). `.vscode/settings.json` uses the `python` on your path and adds `src/` for project imports on
every operating system.

## Troubleshooting

- **`mongo` never becomes healthy and mongosh reports an unrecognised option:** older startup commands treated a
  leading `-` in `MONGO_ROOT_PASSWORD` as an option. The startup script and healthcheck now use attached
  `--username=...` and `--password=...` arguments; newly generated secrets also avoid a leading dash.
  With these commands a dash-leading password works as it is, so there is no need to change it. If you do change it,
  do so only on an empty MongoDB volume: credentials apply only when the volume is first created, and editing `.env`
  does not rotate an existing database user's password. Do not delete application data to resolve this error.
- **`mongo` exits at start-up on Linux** with "MongoDB cannot start: Linux kernel versions 6.19 and newer ...": MongoDB
  8.0 to 9.0 refuse kernels 6.19 to 7.0.13 (MongoDB SERVER-121912) when Docker Engine shares the host kernel. Use Docker
  Desktop (its own virtual machine), a kernel older than 6.19 or 7.0.14 and later, or WSL2 on Windows.
  Ubuntu reports every 7.0 kernel as `7.0.0-…` (for example Ubuntu 26.04), so MongoDB refuses it even when the fix is
  included (MongoDB SERVER-136848); use Docker Desktop or an Ubuntu 22.04/24.04 kernel older than 6.19 there. CI
  runs its database job on `ubuntu-22.04` for the same reason.
- **Docker "cannot find the file specified" (`dockerDesktopLinuxEngine`) on Windows:** Docker Desktop is not running.
- **Git Bash on Windows turns `/app/...` into a Windows path:** run the commands in PowerShell, or set
  `MSYS_NO_PATHCONV=1` first.
- **A variable "is missing a value"** from Compose: run `python src/tools/init_env.py`.
- **Port already in use:** change `APP_PORT` or `MONGO_PORT` in `.env`.
- **Host pytest reports Access denied for an existing pytest temp directory:** pass `--basetemp` with a new temporary
  directory outside this repository. Keep the Git-index documentation tests outside the repository's ignored folders,
  so their temporary trees do not inherit the parent repository's Git discovery.
- **Roles or database images changed after you pulled:** `docker compose down --volumes`, then start again.
- **SELinux hosts:** bind mounts carry the `:z` label already; no `chcon` is needed.

## Repository layout

```text
compose.yaml    application, databases and optional tools/translation profiles
src/            Django application (Dockerfile, requirements, docker/ set-up scripts, tools/)
tests/          pytest suite on the real databases
analytics/      Olist profiler and pipeline tests
data/           raw and derived Olist data, checksums, licences
scripts/        check_docs.py (git hook and CI), package_submission.py
docs/           DATA_MODEL.md, DECISIONS.md, AI_USE.md, licenses/, plans/ (one per workstream)
```

Where each kind of fact lives is the documentation map in [AGENTS.md](AGENTS.md#documentation).

## Team

| Name | Student ID | Role |
|---|---|---|
| LIM CHEE LONG | 2500584 | Main developer |
| MUHAMMAD ERFAN BIN MOHAN | 2500722 | Planning and setup |
| MOHAMMED SYAHFARIZ BIN EFFENDY | 2500717 | Supporting developer, QA |
| JUN KEAT LIM | 2501004 | Supporting developer, QA |
| JOASH | to add | Supporting developer, QA |

Individual contributions: [CONTRIBUTIONS.md](CONTRIBUTIONS.md). AI use: [docs/AI_USE.md](docs/AI_USE.md).
