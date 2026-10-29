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
    hint: str | None = None
    command: str | None = None

    @contextmanager
    def open(self):
        if self.engine == "postgres":
            with db.pg() as conn:
                conn.execute("SELECT 1").fetchone()
                yield lambda: conn.execute(self.statement, self.parameters).fetchall()
        elif self.engine == "mongo":
            with db.mongo() as database:
                database.command(
                    "ping"
                )  # Resolve/authenticate the worker's driver before starting its operation clock.
                if self.command == "ping":
                    yield lambda: [{"one": int(database.command("ping")["ok"])}]
                else:
                    options = {"hint": self.hint} if self.hint else {}
                    yield lambda: list(
                        database[self.collection].aggregate(
                            self.pipeline, allowDiskUse=True, maxTimeMS=120_000, **options
                        )
                    )
        else:
            yield lambda: []

    def explain(self):
        if self.engine == "postgres":
            with db.pg() as conn:
                return conn.execute(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + self.statement, self.parameters
                ).fetchone()
        if self.engine == "mongo":
            if self.command:
                return {"round_trip_command": self.command}
            with db.mongo() as database:
                command = {
                    "aggregate": self.collection,
                    "pipeline": self.pipeline,
                    "cursor": {},
                    "allowDiskUse": True,
                    "maxTimeMS": 120_000,
                }
                if self.hint:
                    command["hint"] = self.hint
                return database.command("explain", command, verbosity="executionStats")
        return {}
