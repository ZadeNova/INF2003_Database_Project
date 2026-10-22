# Mercer: a lean marketplace on PostgreSQL and MongoDB

INF2003 Database Systems · Team 82 · Submission: Sunday 29 November 2026, 23:30 Singapore time

Mercer is a Shopee-style marketplace with customers, sellers and an operator, built on the real Olist dataset. PostgreSQL
is the system of record for money, stock and orders; MongoDB owns product specifications, reviews, photos and activity
events; a benchmark harness compares both engines on identical data. Django with HTMX serves the pages. Payments are
simulated and no personal data is used.

## Status

Phase 1A replaces the earlier dataset with a reproducible Olist pipeline, fresh marketplace schema, cross-store import,
minimum product pages and demo logins. Phase 1B adds the three roles, seller applications, the operator console and the
database-written audit log. Scope, tiers, dates and review status live in [PLAN.md](PLAN.md); contributor rules
are in [AGENTS.md](AGENTS.md), the graded outcome in [RUBRICS.md](RUBRICS.md), and the schema in
[docs/DATA_MODEL.md](docs/DATA_MODEL.md). Later application workstreams build the purchasing and operator workflows.

## Requirements

- Docker Desktop (Windows, macOS) or Docker Engine (Linux) with Compose 2.20 or later, using Linux containers. Start
  Docker Desktop first and wait until it reports the engine is running.
- Python 3.8 or later on the host, only for `src/tools/init_env.py` and the documentation check. The application runs in
  Docker. On Linux and macOS the command may be `python3`.
- Git. Free ports 8000 (the app) and 27017 (MongoDB, bound to 127.0.0.1); change `APP_PORT` or `MONGO_PORT` in `.env`.

## Set up and run (fresh clone)

From the repository root:

```sh
python src/tools/init_env.py              # 1. writes .env with random local secrets (never printed)
git config core.hooksPath .githooks       # 2. once per clone: the documentation check runs before each commit
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
mounted, but the image copies `src/` at build time, so run `docker compose build migrate` after changing application
code. Test counts are not written here; the run prints them. The app image has no Git, so its four Git-index-only
documentation tests are also run on the host with Python/pytest and Git:

```sh
python -m pytest --noconftest -q -p no:cacheprovider tests/test_check_docs.py tests/test_package_submission.py
python scripts/check_docs.py
```

The main suite and all database tests remain in Docker. The host command disables the database conftest because these
checks operate only on temporary documentation trees and submission archives.

## Configuration

`src/tools/init_env.py` creates `.env` from [.env.example](.env.example) and, run again later, adds keys a newer version
needs without changing existing ones. `.env` is git-ignored: never commit it or paste resolved Compose output.

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | At least 50 characters; generated |
| `DJANGO_DEBUG` | `true` turns debug on; off by default |
| `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated; keep `127.0.0.1` for the container health check |
| `APP_PORT`, `MONGO_PORT` | Host ports (127.0.0.1 only) |
| `POSTGRES_DB` | Database name |
| `POSTGRES_OWNER_USER`, `POSTGRES_OWNER_PASSWORD` | Owner role: owns the database; runs migrations, the importer and pytest |
| `POSTGRES_RUNTIME_USER`, `POSTGRES_RUNTIME_PASSWORD` | Runtime role used by `web`: reads and writes rows, no DDL, DROP or TRUNCATE |
| `POSTGRES_ADMIN_PASSWORD` | Bootstrap superuser, given only to the `db` service |
| `MONGO_ROOT_USER`, `MONGO_ROOT_PASSWORD` | MongoDB root, used only to initialise the replica set and users |
| `MONGO_APP_USER`, `MONGO_APP_PASSWORD`, `MONGO_DB` | Application user: `readWrite` on `MONGO_DB` and `test_<MONGO_DB>` only |
| `DEMO_CUSTOMER_PASSWORD`, `DEMO_SELLER_PASSWORD`, `DEMO_OPERATOR_PASSWORD` | Generated demo secrets; passed only to migrate for seed_demo/tests; required with no fallback |

Credentials are set up on an empty volume only: editing `.env` does not rotate an existing database password.

## Services

| Service | Role |
|---|---|
| `db` | PostgreSQL 18; creates the owner and runtime roles on first start (`src/docker/10-roles.sh`) |
| `mongo` | MongoDB 9.0 as the single-node replica set `rs0` with authentication (`src/docker/mongo-start.sh`); healthy once the set and the application user exist. The app connects with `replicaSet=rs0`; tools on the host need `directConnection=true` |
| `migrate` | Owner role: migrations, mongo_setup, import_olist, verify_olist, seed_demo and pytest; data mounted read-only |
| `web` | Django on Gunicorn as the runtime role, on 127.0.0.1 only |
| `tools` | Optional tools profile; pinned offline profiling, cleaning, generation and pipeline tests; only working directories mounted, with raw source read-only and no .env mount |
| `translation` | Optional isolated translation profile; pinned Argos package/tokenizer and CTranslate2 inference; offline at runtime, raw source read-only, no .env mount |

Both database images are pinned by digest in [compose.yaml](compose.yaml); the reasons are in
[docs/DECISIONS.md](docs/DECISIONS.md).

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
product details, registration, seller applications and the operator console work; cart, checkout, orders and the live
dashboard return 404 until their workstreams replace them. The labelled foundation design previews
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
| `/operator/audit/` | Operators | Audit log, newest first, filtered by actor and action |

Operators are never created through the web. Besides `demo-operator` from `seed_demo`, create or re-password one with
the password from `DEMO_OPERATOR_PASSWORD` (never a command-line argument, never printed); an existing account with
another role is refused:

```sh
docker compose run --rm migrate python manage.py create_operator <username>
```

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

- **`mongo` exits at start-up on Linux** with "MongoDB cannot start: Linux kernel versions 6.19 and newer ...": MongoDB
  8.0 to 9.0 refuse kernels 6.19 to 7.0.13 (MongoDB SERVER-121912) when Docker Engine shares the host kernel. Use Docker
  Desktop (its own virtual machine), a kernel older than 6.19 or 7.0.14 and later, or WSL2 on Windows.
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
