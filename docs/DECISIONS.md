# Decisions

Lasting decisions someone could later question, with the reason. Scope, tiers and dates are in [PLAN.md](../PLAN.md);
this file holds the choices behind the code. Add a row when a decision is made, not when it is rediscovered.

## foundation (21 October 2026)

| ID | Decision | Why |
|---|---|---|
| foundation-a | `DESIGN.md`: strip dead links and AWS text only; the full rewrite moves to `catalogue` | The UI work decides the design |
| foundation-b | Remove the K-means scripts now; the `CustomerSegment` model goes with the `reporting` app in `olist-import` | Avoids a throwaway migration |
| foundation-c | MongoDB container, users and health check land in `foundation`, not `catalogue` | `olist-import` needs it running |
| foundation-d | Images are pinned by digest | Reproducible benchmarks |
| foundation-e | `scripts/check_docs.py` uses only the standard library and runs on the host | Works in the git hook without a virtual environment |
| foundation-f | Latest stable PostgreSQL (18) and MongoDB (9.0), checked at pin time | The brief asks for the latest systems |
| foundation-g | Two PostgreSQL roles: an owner (migrate, import, pytest) and a runtime role for `web` (rows only) | Makes AGENTS.md rule 5 true; before, the app role owned its database |
| foundation-h | Delete the old load harness; `benchmark` writes a new local load script | The old harness was built around the AWS variants and shoe sizes |
| foundation-i | `.env` and `.env.example` live at the repository root, next to the one `compose.yaml` | Compose reads `.env` from the project directory; the old location relied on `include` |
| foundation-j | pytest runs in the `migrate` service (`docker compose run --rm migrate pytest ...`), not `web` | Only the owner role may create the test database, and `web` must never hold it |
| foundation-k | The MongoDB replica set is initialised by `src/docker/mongo-start.sh` beside `mongod`, with the keyfile generated into a named volume | A bind-mounted keyfile cannot be chmod 400 on Windows; the replica set and users must be created while `mongod` already runs with the keyfile |
| foundation-l | The startup event no longer carries an `environment` field | `DJANGO_ENV` is gone, so there is only one environment |
| foundation-m | Keep MongoDB 9.0; the team develops and benchmarks on Windows with Docker Desktop, whose VM kernel is not affected by SERVER-121912 | Docker Engine on Linux shares the host kernel, and MongoDB 9.0 refuses kernels 6.19 to 7.0.13; Linux users need an older or newer kernel (README, Troubleshooting) |
| foundation-n | The role tests run against the real `mercer` database, with uniquely named probe tables that they drop | The default privileges that make the runtime role work exist only there, not in pytest's test database |
