"""Request-local driver counters. Query text, values and command bodies never enter this module."""
from contextvars import ContextVar
from dataclasses import dataclass
from time import perf_counter_ns

from pymongo.monitoring import CommandListener


@dataclass
class DatabaseTiming:
    pg_ns: int = 0
    pg_queries: int = 0
    mongo_us: int = 0
    mongo_commands: int = 0

    def fields(self):
        return {"db_pg_ms": round(self.pg_ns / 1_000_000, 3), "db_pg_queries": self.pg_queries,
                "db_mongo_ms": round(self.mongo_us / 1000, 3), "db_mongo_commands": self.mongo_commands}


current_timing = ContextVar("request_database_timing", default=None)


def time_postgres(execute, sql, params, many, context):
    started = perf_counter_ns()
    try:
        return execute(sql, params, many, context)
    finally:
        timing = current_timing.get()
        if timing is not None:
            timing.pg_ns += perf_counter_ns() - started
            timing.pg_queries += 1


class RequestCommandListener(CommandListener):
    def started(self, event):
        pass

    def succeeded(self, event):
        self._record(event.duration_micros)

    def failed(self, event):
        self._record(event.duration_micros)

    @staticmethod
    def _record(microseconds):
        timing = current_timing.get()
        if timing is not None:
            timing.mongo_us += microseconds
            timing.mongo_commands += 1


command_listener = RequestCommandListener()
