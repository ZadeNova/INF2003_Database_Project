"""The isolated app stack of the Redis experiments: switching conditions, pausing Redis, the cold-cache helper.

Only the pure rules live in redis_stats.py; everything here talks to Docker or HTTP. Like request_timing, it refuses the
project named `mercer`, a non-loopback address and any attempt to run beside a benchmark, and it never prints command
output (it can contain environment values).
"""

import http.cookiejar
import json
import os
import platform
import re
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlsplit
from urllib.request import HTTPCookieProcessor, build_opener

from benchmarks.redis_stats import ExperimentError, parse_logs
from benchmarks.request_timing import (
    ROOT,
    NoRedirect,
    TimingError,
    command,
    compose,
    ensure_no_benchmark,
    fetch,
    login_operator,
    pages_for_product,
)

# Runs inside the web container, so it uses the application's own Redis client, ACL user and key prefix. One line in,
# one line out: "trending" forgets the cached ranking, "dashboard" moves the dashboard to a version nobody has cached.
HELPER_CODE = """
import sys, time
from config import redis_store
print("ready", flush=True)
while True:
    line = sys.stdin.readline()
    if not line:
        break
    kind = line.strip()
    if kind == "trending":
        redis_store.call(lambda client: client.delete(redis_store.key("trending")))
    elif kind == "dashboard":
        redis_store.call(lambda client: client.set(redis_store.key("dashboard:version"), str(time.time_ns() // 1000)))
    print("ok", flush=True)
"""

EVENTS_CODE = """
from config import mongo
with mongo.client() as client:
    print("EVENTS", client[mongo.database_name()].events.count_documents({}))
"""

LIMITER_CODE = """
import json, time
from config import redis_store

class Unreachable(Exception):
    pass

def timed(operation, calls, failed):
    # The store fails open, so an unreachable Redis would look like a very cheap call: every call must really have reached it.
    values = []
    for _ in range(calls):
        started = time.perf_counter()
        result = operation()
        values.append((time.perf_counter() - started) * 1e6)
        if failed(result):
            raise Unreachable()
    return values

try:
    redis_store.call(lambda client: client.ping())
    ping = timed(lambda: redis_store.call(lambda client: client.ping()), CALLS, lambda r: r is not True)
    check = timed(lambda: redis_store.window_check("overhead", "probe", 1_000_000, 900), CALLS, lambda r: r is redis_store.OPEN)
    hit = timed(lambda: redis_store.window_hit("overhead", "probe", 1_000_000, 900), CALLS, lambda r: r is redis_store.OPEN or r.count < 1)
except Unreachable:
    print("LIMITER_UNREACHABLE")
else:
    redis_store.window_clear("overhead", "probe")
    print("LIMITER", json.dumps({"ping_us": ping, "window_check_us": check, "window_hit_us": hit}))
"""


LOG_CLOCK_MARGIN = timedelta(minutes=2)


class Stack:
    def __init__(self, project, base_url, env_file, source):
        address = urlsplit(base_url)
        if (
            address.scheme != "http"
            or address.hostname not in {"localhost", "127.0.0.1"}
            or address.username
            or address.password
            or address.path not in ("", "/")
            or address.query
            or address.fragment
        ):
            raise TimingError("Use an HTTP loopback base URL without credentials or a path")
        self.project, self.env_file, self.source = project, env_file, source
        self.base_url = base_url.rstrip("/")
        self.dc = compose(project, env_file)
        ports = command(self.dc + ["port", "web", "8000"])
        if (address.port or 80) not in {int(line.rsplit(":", 1)[1]) for line in ports.splitlines()}:
            raise TimingError("Base URL does not match this Compose project's web port")
        ensure_no_benchmark()

    # ------------------------------------------------------------------------------------------- docker
    def run(self, arguments, env=None):
        completed = subprocess.run(
            arguments, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False, env=env
        )
        if completed.returncode:
            raise RuntimeError("Required command failed")  # output may contain environment details; never echo it
        return completed.stdout.strip()

    def recreate_web(self, redis_enabled):
        """A fresh web container (its workers, connections and in-process state) with Redis switched on or off."""
        env = {**os.environ, "REDIS_ENABLED": "true" if redis_enabled else "false"}
        self.run(self.dc + ["up", "--detach", "--force-recreate", "--no-deps", "--wait", "web"], env=env)

    def _redis_id(self):
        identity = self.run(self.dc + ["ps", "-q", "redis"])
        if not identity:
            raise ExperimentError("The project has no running redis container")
        return identity

    def pause_redis(self):
        self.run(["docker", "pause", self._redis_id()])

    def unpause_redis(self):
        identity = self._redis_id()
        if self.run(["docker", "inspect", "--format", "{{.State.Paused}}", identity]) == "true":
            self.run(["docker", "unpause", identity])

    def logs(self, since, request_ids):
        """Wait for Docker's log collection to catch up, then return the parsed request log lines.

        Docker stamps each line with the daemon's clock, which can sit a few seconds off the host's; a `--since` equal
        to the host's start time then drops the first requests (observed: 13 of 25). Request IDs are unique, so the
        window is simply widened and the IDs select the lines."""
        logs = {}
        window = (datetime.fromisoformat(since) - LOG_CLOCK_MARGIN).isoformat()
        for _ in range(40):
            text = self.run(self.dc + ["logs", "--no-color", "--no-log-prefix", "--since", window, "web"])
            logs = parse_logs(text, request_ids)
            if request_ids <= logs.keys():
                break
            time.sleep(0.25)
        return logs

    def shell(self, code):
        return self.run(self.dc + ["exec", "-T", "web", "python", "manage.py", "shell", "-c", code])

    def events(self):
        for line in self.shell(EVENTS_CODE).splitlines():
            if line.startswith("EVENTS "):
                return int(line.split()[1])
        raise ExperimentError("Could not count the activity events")

    def limiter_timings(self, calls):
        for line in self.shell(LIMITER_CODE.replace("CALLS", str(calls))).splitlines():
            if line == "LIMITER_UNREACHABLE":
                raise ExperimentError("The limiter timing could not reach Redis; its calls would have failed open")
            if line.startswith("LIMITER "):
                return json.loads(line.split(" ", 1)[1])
        raise ExperimentError("The limiter timing printed nothing")

    # ------------------------------------------------------------------------------------------- http
    @staticmethod
    def anonymous_opener():
        """A fresh anonymous visitor; cookies are retained only by this opener."""
        return build_opener(NoRedirect(), HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def openers(self):
        anonymous = self.anonymous_opener()
        cookies = http.cookiejar.CookieJar()
        operator = build_opener(NoRedirect(), HTTPCookieProcessor(cookies))
        login_operator(operator, cookies, self.base_url, self.env_file)
        return anonymous, operator

    def pages(self, anonymous):
        row, body, _ = fetch(anonymous, self.base_url, "/products/")
        if row["status"] != 200:
            raise TimingError("Product list unavailable")
        found = pages_for_product(body, self.source)
        # The site root only redirects to the shop. The search page uses a word from the visible product's own name.
        row, detail, _ = fetch(anonymous, self.base_url, found["product_detail"])
        heading = re.search(r"<h1[^>]*>(.*?)</h1>", detail, re.S)
        words = re.findall(r"[A-Za-z]{4,}", re.sub(r"<[^>]+>", " ", heading[1])) if heading else []
        if row["status"] != 200 or not words:
            raise TimingError("The visible product has no name to search for")
        return {
            "shop": "/products/",
            "search": "/products/?q=" + quote(words[0]),
            "dashboard": "/operator/dashboard/",
            "product_detail": found["product_detail"],
            "category_trending": found["category"],
        }

    def timed_get(self, opener, page, path):
        started = time.perf_counter()
        row, body, headers = fetch(opener, self.base_url, path)
        elapsed = (time.perf_counter() - started) * 1000
        return row, body, headers, elapsed

    # ------------------------------------------------------------------------------------------- evidence
    def host(self):
        info = json.loads(command(["docker", "info", "--format", "{{json .}}"]))
        host = {
            "os": platform.platform(),
            "cpu": platform.processor(),
            "logical_cpus": os.cpu_count(),
            "python": platform.python_version(),
            "docker_version": json.loads(command(["docker", "version", "--format", "{{json .}}"])),
            "docker_vm": {key: info[key] for key in ("NCPU", "MemTotal", "OperatingSystem", "KernelVersion")},
        }
        if platform.system() == "Windows":
            host["hardware"] = json.loads(
                command(
                    [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        "@{cpu=(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors);ram=(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory} | ConvertTo-Json -Depth 4",
                    ]
                )
            )
        return host

    def commit(self):
        return command(["git", "rev-parse", "HEAD"]), bool(command(["git", "status", "--porcelain"]))


class ColdHelper:
    """A process inside the web container that clears the cached entries on request, one round trip per clear."""

    def __init__(self, stack):
        self.process = subprocess.Popen(
            stack.dc + ["exec", "-T", "web", "python", "manage.py", "shell", "-c", HELPER_CODE],
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )
        for _ in range(20):  # the shell prints its own banner first
            line = self.process.stdout.readline()
            if line.strip() == "ready":
                return
            if not line:
                break
        raise ExperimentError("The cache helper did not start")

    def clear(self, kind):
        self.process.stdin.write(kind + "\n")
        self.process.stdin.flush()
        if self.process.stdout.readline().strip() != "ok":
            raise ExperimentError("The cache helper stopped")

    def close(self):
        try:
            self.process.stdin.close()
            self.process.wait(timeout=20)
        except (OSError, subprocess.SubprocessError):
            self.process.kill()


@contextmanager
def redis_restored(stack):
    """However an experiment ends, Redis is running again and the web container is back to its normal setting."""
    try:
        yield
    finally:
        try:
            stack.unpause_redis()
        finally:
            stack.recreate_web(True)


def now_iso():
    return datetime.now(timezone.utc).isoformat()
