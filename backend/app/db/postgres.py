"""Postgres access: SQLAlchemy engine for basic CRUD, asyncpg pool for raw SQL.

Both live here so a request can reach for whichever fits. The SQLAlchemy side is for
straightforward row work; anything with CTEs, window functions, views or aggregates
goes through the asyncpg pool as parameterized SQL so the query stays readable.

Wiring only — no queries here.
"""

# TODO: async engine + sessionmaker (SQLAlchemy), asyncpg.create_pool, lifespan
#       startup/shutdown hooks, and the FastAPI dependencies that yield each.
