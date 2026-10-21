# foundation: Repo conversion, AWS removal, docs consolidation

status: approved
owner: Erfan · reviewer: Chee Long (other agent) · estimate: 1 to 1.5 days · window: 21 to 25 October

## Contract

**Goal.** A clean local-only baseline that runs on Linux and Windows with PostgreSQL and MongoDB in Compose, no AWS code,
a small set of docs, and a docs check that runs before every commit. No feature or schema work (that is `olist-import` onward).

**In scope**

| Area | Change |
|---|---|
| Secrets and settings | Delete `src/config/secrets.py`, `tests/test_secrets.py`, boto3 and botocore from `src/requirements.in`/`.txt`. Secrets come only from `src/.env`; keep the 50-character secret-key check. Remove the `DJANGO_ENV` local/production switch in favour of one fail-closed configuration |
| Database connection | `src/config/database.py`: keep optional `sslmode`, drop the RDS `verify-full` and `POSTGRES_SSLROOTCERT` path; remove `POSTGRES_SSLROOTCERT` from `src/Dockerfile` and `.env.example` |
| Middleware | Delete `HealthProbeMiddleware`, `DJANGO_HEALTH_PROBE_HOST`, `DJANGO_TRUST_PROXY`; keep `/health/`, the DB-unavailable 503 and JSON request logs; rename `northstar.*` loggers to `mercer.*` |
| Roles | Keep the owner/application split in `src/tools/db_bootstrap.py` and `src/docker/10-local-role.sh`; drop RDS-only parts |
| Compose | One root `compose.yaml` (fold in `src/compose.yaml`). Add `mongo` (single-node replica set, root user only at init, application user with `readWrite` on the app database only). Use the latest stable PostgreSQL and MongoDB releases (check the official release pages; do not assume) and pin every image by digest. Add `pymongo`; `check_database` reports both engines |
| Analytics | Delete the AWS credential path (`analytics/tests/test_startup_credentials.py` and the production branch it tests) and the K-means segmentation scripts (Tier 3 per PLAN.md) |
| Load harness | Keep the Locust core for local HTTP runs (`locustfile.py`, `common.py`, `accounts.py`, local parts of `analyze.py`, `run.py`); delete the EC2/Fargate, kill and `aws_capture` parts and their self-tests; drop boto3 |
| Docs | Merge what is still true from `src/README.md`, `tests/README.md`, `tests/load/README.md`, `analytics/README.md`, `data/README.md` into `README.md`; delete the rest. Fold `data/DATA_DICTIONARY.md` and `data/raw/DATA_DICTIONARY.md` into a stub `docs/DATA_MODEL.md`. Remove dead links and AWS text from `DESIGN.md`. Create `docs/DECISIONS.md` and `docs/AI_USE.md` (with the reuse disclosure and approval citation) |
| Docs check | `scripts/check_docs.py` (standard library only) and `.githooks/pre-commit`, as specified in AGENTS.md, Documentation. Setup line `git config core.hooksPath .githooks` in README |
| Packaging | `scripts/package_submission.py` checks the INF2003 zip (report PDF, `.pptx`, `.mp4`, source zip) instead of the old required files |
| Misc | `.vscode/settings.json` cross-platform interpreter path; drop Terraform entries from `.gitignore` |

**Out of scope:** Olist data, schema changes, shoe code and shoe tests (`olist-import`); CI workflow (`ci`, which will also run
`check_docs.py`); any MongoDB collections or app code beyond the connection and health check (`catalogue`).

**Tests**
- Existing suite passes, minus deleted AWS tests. Settings, database and request-logging tests are adjusted, not deleted.
- New: MongoDB application user can read and write the app database and is refused on another database and on
  `dropDatabase`. `check_docs.py` has unit tests (broken link, missing path, unlisted `.md`, `status: done` plan).

**Exit check (the reviewer runs all of these)**
1. Fresh clone on Linux and on Windows: `python src/tools/init_env.py`, `git config core.hooksPath .githooks`,
   `docker compose up --build`; `/health/` returns 200 and `check_database` reports PostgreSQL and MongoDB.
2. Full test suite passes inside Docker.
3. `git grep -i -E "boto3|botocore|secretsmanager|AWS_|terraform|fargate|ec2"` finds nothing outside PLAN.md history notes.
4. A commit with a deliberately broken link in README is blocked by the hook.
5. `python scripts/package_submission.py --check-only` passes on a dummy zip with the four required files.
6. Every member can run step 1 from the README alone.

## Decisions (all approved 21 October 2026)

| ID | Proposal | Why |
|---|---|---|
| foundation-a | `DESIGN.md`: strip dead links and AWS text only; the full rewrite moves to `catalogue` (UI) | Keeps `foundation` to about a day; the UI work decides the design |
| foundation-b | Remove the K-means scripts now; remove the `CustomerSegment` model and migration in `olist-import` with the schema reset | Avoids a throwaway migration now |
| foundation-c | MongoDB container, users and health check land here, not in `catalogue` | CI and `olist-import` need it running; no collections yet |
| foundation-d | Pin images by digest (PLAN.md D4) | Reproducible benchmarks |
| foundation-e | `check_docs.py` uses only the standard library and runs on the host | Works in the hook without a virtual environment, for both agents |
| foundation-f | Latest stable PostgreSQL and MongoDB, checked at pin time | The brief asks for the latest systems; the report shows a recent feature of each |

## Review notes

(empty until review)
