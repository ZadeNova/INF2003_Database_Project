# Mercer: a lean marketplace on PostgreSQL and MongoDB

INF2003 Database Systems · Team 82 · Submission: Sunday 29 November 2026, 23:30 Singapore time

Mercer is a Shopee-style marketplace with customers, sellers and an operator, built on the real Olist dataset. PostgreSQL
is the system of record for money, stock and orders; MongoDB owns product specifications, reviews, photos and activity
events; a benchmark harness compares both engines on identical data. Django with HTMX serves the pages. Payments are
simulated and no personal data is used.

## Status

The repository is being converted from an earlier shoe-shop baseline. The code in `src/` still shows the shoe shop until
`olist-import` replaces it; scope, tiers, phases and per-workstream status are in [PLAN.md](PLAN.md), the rules for
contributors and coding agents in [AGENTS.md](AGENTS.md), and what is graded in [RUBRICS.md](RUBRICS.md).

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
code. Test counts are not written here; the run prints them.

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

Credentials are set up on an empty volume only: editing `.env` does not rotate an existing database password.

## Services

| Service | Role |
|---|---|
| `db` | PostgreSQL 18; creates the owner and runtime roles on first start (`src/docker/10-roles.sh`) |
| `mongo` | MongoDB 9.0 as the single-node replica set `rs0` with authentication (`src/docker/mongo-start.sh`); healthy once the set and the application user exist. The app connects with `replicaSet=rs0`; tools on the host need `directConnection=true` |
| `migrate` | One-off job as the owner role: `manage.py migrate`. Also the service that runs pytest and the importer |
| `web` | Django on Gunicorn as the runtime role, on 127.0.0.1 only |

Both database images are pinned by digest in [compose.yaml](compose.yaml); the reasons are in
[docs/DECISIONS.md](docs/DECISIONS.md).

## Baseline demo data (shoe shop, replaced by `olist-import`)

The shop starts empty. To load the baseline dataset, build the derived files on the host (standard library only; it
reads `data/raw/` and writes `data/derived/shoes/`), then import it as the owner and refresh the dashboard:

```sh
python analytics/build_shoe_dataset.py
docker compose run --rm migrate python manage.py import_dataset --source /app/data/derived/shoes --namespace synthetic/shoes/revision-a/demo/v1
docker compose run --rm web python manage.py seed_demo --no-products
docker compose run --rm web python manage.py refresh_analytics --as-of 2026-01-02
```

`seed_demo --no-products` creates the operator `demo-operator`; its password is `DEMO_OPERATOR_PASSWORD` if set,
otherwise the fallback in `src/catalogue/management/commands/seed_demo.py`. Imported customers have unusable passwords:
to shop, register at `/register/`. The import refuses a namespace that already holds demo products, so use a fresh
database (`docker compose down --volumes`). Other commands, run as `docker compose run --rm web python manage.py <command>`:
`snapshot_inventory` and `check_database`.

`analytics/profile_dataset.py` profiles `data/raw/` with pandas (`pip install -r analytics/requirements.txt` in a
separate environment) and writes a Markdown report into `data/`, which the documentation check does not allow in the
repository: delete it after reading. `olist-import` replaces the profiler with one for Olist.

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
- **Roles or database images changed after you pulled:** `docker compose down --volumes`, then start again.
- **SELinux hosts:** bind mounts carry the `:z` label already; no `chcon` is needed.

## Repository layout

```text
compose.yaml    the four services
src/            Django application (Dockerfile, requirements, docker/ set-up scripts, tools/)
tests/          pytest suite on the real databases
analytics/      profiler and shoe-dataset builder (until olist-import)
data/           Olist and baseline datasets, checksums, licences
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
