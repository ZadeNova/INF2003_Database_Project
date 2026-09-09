# INF2003 Database Project

Monorepo scaffold. No application idea chosen yet — structure and config only.

| Path         | What lives there                                          |
| ------------ | --------------------------------------------------------- |
| `backend/`   | FastAPI app, SQLAlchemy Core metadata, Alembic migrations |
| `frontend/`  | React + Vite + TypeScript SPA                             |
| `benchmark/` | Go harness (pgx + mongo-driver), talks to the DBs directly |
| `etl/`       | pandas cleaning + bulk load (COPY / `insert_many`)        |
| `docs/`      | Rubric, decision log                                      |

## Run it now (local, two terminals)

```
# terminal 1 — backend
cd backend
python -m venv .venv         # macOS/Linux: python3 -m venv .venv
.venv\Scripts\activate       # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

```
# terminal 2 — frontend
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — it should say **"Backend: ok"**. That's confirmation
the React page reached the FastAPI `/health` endpoint through the Vite dev proxy.
Backend runs on :8000, frontend on :5173. Postgres/Mongo aren't needed for this —
nothing touches either database until the schema exists.

## Run it later (Docker Compose, one command)

Once the databases are wired in, this becomes the standard way to run everything:

```
cp .env.example .env
docker compose up
```

Brings up backend (:8000), frontend (:5173), Postgres, Mongo, pgAdmin (:5050), and
mongo-express (:8081) together, in the right startup order. Not required yet — the
local method above is faster while there's no database logic to test against.

Operational commands and constraints belong in [AGENTS.md](AGENTS.md) — currently a
template awaiting the project owner.
