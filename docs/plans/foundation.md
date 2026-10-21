# foundation: Repo conversion, AWS removal, roles, MongoDB, docs consolidation

status: approved
owner and implementer: Erfan · estimate: 1.5 to 2 days · phase 0 (21 to 25 October)

## Contract

**Goal.** A clean local-only baseline that runs on Linux and Windows with PostgreSQL and MongoDB in Compose, real
least-privilege roles, no AWS code, a small set of docs, and a docs check that runs before every commit. No feature or
schema work (that is `olist-import` onward).

**In scope**

| Area | Change |
|---|---|
| Secrets | Delete `src/config/secrets.py`, `tests/test_secrets.py`, `tests/verify_runtime_image.py`, and boto3/botocore from `src/requirements.in` and `.txt`. Every importer of `config.secrets` changes: `src/config/settings.py` and `src/tools/db_bootstrap.py` read `os.environ` directly; `tests/test_settings.py` drops the `secrets._retrieve` patch (lines 29 and 30). Keep the 50-character secret-key check |
| Settings | One configuration with today's local values: plain HTTP, no SSL redirect, cookies not marked secure, no HSTS, no proxy header, `DEBUG` off unless `DJANGO_DEBUG=true`. Remove `DJANGO_ENV`, `DJANGO_TRUST_PROXY`, `DJANGO_HEALTH_PROBE_HOST`, `DJANGO_HSTS_SECONDS` and `HealthProbeMiddleware`. Keep `/health/`, the database-unavailable 503 and JSON request logs; rename `northstar.*` loggers to `mercer.*` |
| Database connection | `src/config/database.py`: keep optional `sslmode`; drop the RDS `verify-full` path and `POSTGRES_SSLROOTCERT` (also from `src/Dockerfile` and `.env.example`) |
| PostgreSQL roles (decision g) | Two roles, created by the PostgreSQL init script (replacing `src/docker/10-local-role.sh`): an **owner** that owns the database and runs `migrate`, the importer and pytest (which needs `CREATEDB`), and a **runtime** role for `web` with `CONNECT`, schema `USAGE`, `SELECT, INSERT, UPDATE, DELETE` on tables and `USAGE, SELECT` on sequences, granted through `ALTER DEFAULT PRIVILEGES FOR ROLE owner` so future tables are covered. The `migrate` service uses the owner's credentials, `web` the runtime's. Delete `src/tools/db_bootstrap.py` and `tests/test_db_bootstrap.py` unless something still needs them |
| Compose | One root `compose.yaml` (fold in `src/compose.yaml`) with `db`, `mongo`, `migrate`, `web`. The latest stable PostgreSQL and MongoDB releases (check the official release pages; do not assume), pinned by digest. For PostgreSQL 18 and later, check the image's data path when pinning: those images expect the volume at `/var/lib/postgresql`, and a volume at `/var/lib/postgresql/data` stops startup |
| MongoDB | Single-node replica set `rs0` with authentication. The keyfile is generated inside a container into a named volume (mode 400, owned by the mongodb user), never bind-mounted from the host, which fails on Windows. Start-up order: start `mongod` with `--replSet rs0 --keyFile`, run `rs.initiate` with host `mongo:27017`, then create the root user and the app user with `readWrite` on `mercer` and `test_mercer` only. Variables: `MONGO_ROOT_USER`, `MONGO_ROOT_PASSWORD`, `MONGO_APP_USER`, `MONGO_APP_PASSWORD`, `MONGO_DB`. The app connects with `replicaSet=rs0`; host-side tools need `directConnection=true`. Healthcheck on `rs.status()`. Add pinned `pymongo`; `check_database` reports both engines |
| `init_env.py` | Generates the new secrets (owner and runtime passwords, the `MONGO_*` values) and **adds missing keys to an existing `.env`** without changing the ones already there |
| Analytics | Delete the K-means and AWS-credential code: `analytics/segment_customers.py`, `evaluate_segments.py`, `evaluate_holdout.py`, `verify_refresh.py` (imports `config.secrets`), and `analytics/tests/test_segment_customers.py`, `test_segment_loader_integration.py`, `test_startup_credentials.py`, `test_evaluate_holdout.py`, `test_verify_refresh.py`. Remove boto3 and scikit-learn from `analytics/requirements.txt`. Keep `profile_dataset.py` (the template for `profile_olist.py`), `build_shoe_dataset.py` and `export_coverage.py` until `olist-import` removes them |
| Load harness (decision h) | Delete `tests/load/` entirely: it is built around the two AWS variants and shoe sizes and imports a missing `aws_capture`. `benchmark` writes a new local HTTP load script |
| Docs | Rewrite README.md for Mercer (overview, setup, configuration, run, test), removing the AWS deployment content and links to missing files. Merge what is still true from `src/README.md`, `tests/README.md`, `analytics/README.md` and `data/README.md`, then delete them. Fold `data/DATA_DICTIONARY.md` and `data/raw/DATA_DICTIONARY.md` into a stub `docs/DATA_MODEL.md`; delete `data/PROFILE.md` and `data/raw/README.md` (they describe the shoe data). Strip dead links and AWS text from DESIGN.md. Create `docs/DECISIONS.md`, `docs/AI_USE.md` (with the reuse disclosure and the approval citation) and `CONTRIBUTIONS.md` |
| Docs check | `scripts/check_docs.py` (standard library only) and `.githooks/pre-commit` (tries `python3`, then `python`); add `.githooks/* text eol=lf` to `.gitattributes`. It fails on broken relative links, backticked repository paths that do not exist (ignoring `<placeholders>`), `.md` files outside the AGENTS.md list (allow-list `src/static/vendor/**` and `src/static/models/CREDITS.md` until the models go), unpaired generated-section markers or markers naming a missing script, `status: done` plan files, and README commands naming a missing script or Compose service. **Generated-section convention:** `<!-- generated by <script path> -->` … `<!-- end generated -->` |
| Packaging | `scripts/package_submission.py` checks the INF2003 zip (report PDF, `.pptx`, `.mp4`, source zip) instead of the old required files |
| Misc | `.vscode/settings.json` with a cross-platform interpreter path; drop Terraform entries from `.gitignore` |

**Out of scope:** Olist data, schema and shoe code (`olist-import`); CI (`ci`, phase 3); MongoDB collections and app code
beyond the connection and health check (`catalogue`).

**Tests**
- The existing suite passes, minus deleted tests; settings, database and request-logging tests are adjusted, not deleted.
- New: the runtime role can read and write table rows but is refused `CREATE TABLE`, `DROP TABLE` and `TRUNCATE`. The
  MongoDB app user can read and write `mercer` and `test_mercer` and is refused on any other database. `init_env.py`
  adds missing keys without changing existing ones. `check_docs.py` has a unit test per rule.

**Exit check (the reviewer runs all of these)**
1. Fresh clone on Linux and on Windows: `python src/tools/init_env.py`, `git config core.hooksPath .githooks`,
   `docker compose up --build`; `/health/` returns 200 and `check_database` reports PostgreSQL and MongoDB.
2. The full test suite passes inside Docker.
3. `git grep -i -w -E "boto3|botocore|secretsmanager|terraform|fargate|ec2|AWS_[A-Z_]+" -- ':!data' ':!PLAN.md' ':!docs/plans'`
   finds nothing.
4. A commit adding a broken link to README.md is blocked by the hook.
5. `python scripts/package_submission.py --check-only` passes on a dummy zip with the four required files.
6. Every member can run step 1 from the README alone.

## Decisions (all approved 21 October 2026)

| ID | Decision | Why |
|---|---|---|
| a | `DESIGN.md`: strip dead links and AWS text only; the full rewrite moves to `catalogue` | The UI work decides the design |
| b | Remove the K-means scripts now; the `CustomerSegment` model goes with the `reporting` app in `olist-import` | Avoids a throwaway migration |
| c | MongoDB container, users and health check land here, not in `catalogue` | `olist-import` needs it running |
| d | Pin images by digest | Reproducible benchmarks |
| e | `check_docs.py` uses only the standard library and runs on the host | Works in the hook without a virtual environment |
| f | Latest stable PostgreSQL and MongoDB, checked at pin time | The brief asks for the latest systems |
| g | Two PostgreSQL roles (owner, runtime); pytest runs as the owner (R1) | Makes AGENTS.md rule 5 true; today the app role owns its database |
| h | Delete `tests/load/`; `benchmark` writes a new local load script (R4) | The old harness is AWS-specific and incomplete |

## Review notes

21 October 2026, fresh Claude Code session. All findings accepted and applied: the missing `config.secrets` importers,
the role layout (g), the MongoDB keyfile, start-up order and test database, which configuration survives, exit checks 3
and 4 (grep scope, vendored `.md` files), the README rewrite, the K-means file list, Windows line endings and Python name
in the hook, `init_env.py` adding missing keys, the PostgreSQL 18 data path, and the generated-section convention.
