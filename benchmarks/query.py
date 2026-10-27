"""An operation opens one driver connection per worker, outside timed sections."""
from contextlib import contextmanager
from dataclasses import dataclass

from benchmarks import db


@dataclass
class Query:
    output: str
    engine: str
    variant: str
    statement: object = None
    parameters: object = None
    collection: str = "products"
    pipeline: list | None = None
    golden: str | None = None

    @contextmanager
    def open(self):
        if self.engine == "postgres":
            with db.pg() as conn:
                yield lambda: conn.execute(self.statement, self.parameters).fetchall()
        elif self.engine == "mongo":
            with db.mongo() as database:
                database.command("ping")  # Resolve/authenticate the worker's driver before starting its operation clock.
                yield lambda: list(database[self.collection].aggregate(self.pipeline, allowDiskUse=True, maxTimeMS=120_000))
        else:
            yield lambda: []

    def explain(self):
        if self.engine == "postgres":
            with db.pg() as conn:
                return conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + self.statement, self.parameters).fetchone()
        if self.engine == "mongo":
            with db.mongo() as database:
                return database.command("explain", {"aggregate": self.collection, "pipeline": self.pipeline, "cursor": {}, "allowDiskUse": True, "maxTimeMS": 120_000}, verbosity="executionStats")
        return {}
