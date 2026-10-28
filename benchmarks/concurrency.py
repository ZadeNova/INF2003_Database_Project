"""Connect and validate every client before releasing a shared timed window."""
import threading
import time


class PreparedRun:
    def __init__(self, clients):
        self.connections = threading.Barrier(clients)
        self.start = threading.Barrier(clients, action=self._start)
        self.started_ns = None

    def _start(self):
        self.started_ns = time.perf_counter_ns()

    def connected(self):
        ready_at = time.time_ns()
        self.connections.wait(timeout=120)
        return ready_at

    def begin(self):
        self.start.wait(timeout=120)

    def abort(self):
        self.connections.abort()
        self.start.abort()
