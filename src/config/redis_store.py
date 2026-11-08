"""The one module that talks to Redis (docs/plans/redis.md): cache-aside, a stampede lock, a version key and a limiter.

Redis here is a cache and a rate limiter, never a source of truth, and it **fails open**: if it is disabled, down or slow,
every function falls back to the databases (a cache miss) or allows the action (a limit). A connection failure makes the
application skip Redis for REDIS_BACKOFF_SECONDS, so a dead Redis costs at most one timeout per worker per window and
never slows each request. Values are JSON (never pickle); a value that cannot be decoded is a miss and is deleted.
Logs hold the exception class only, never its text, which may name the host.
"""

import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from math import ceil

from django.conf import settings
from django.utils import timezone

from config import redis_keys
from config.db_timing import current_timing

logger = logging.getLogger("mercer.redis")

FAILED = object()  # the call did not complete (disabled, backing off or a Redis error); not the same as "no value"
_state = {"client": None, "signature": None, "scripts": {}, "down_until": 0.0, "logged_at": 0.0}
_guard = threading.Lock()

# Sliding-window log in one atomic script, using Redis's own clock. Mode 0 only checks, 1 records an attempt if the
# window is not full (check and record are one step, so parallel attempts cannot overshoot), 2 records unconditionally.
# Blocked attempts are not recorded. The wait is until enough entries have left the window to bring the count back under
# the limit (the entry at index count - limit), which is the oldest one unless parallel requests overshot the limit.
WINDOW_SCRIPT = """
local now_parts = redis.call('TIME')
local now = tonumber(now_parts[1]) * 1000 + math.floor(tonumber(now_parts[2]) / 1000)
local window = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local mode = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
local count = redis.call('ZCARD', KEYS[1])
if mode ~= 2 and count >= limit then
  local index = math.max(count - limit, 0)
  local entry = redis.call('ZRANGE', KEYS[1], index, index, 'WITHSCORES')
  local retry = window
  if entry[2] then retry = tonumber(entry[2]) + window - now end
  if retry < 1 then retry = 1 end
  return {0, count, retry}
end
if mode ~= 0 then
  redis.call('ZADD', KEYS[1], now, ARGV[4])
  redis.call('PEXPIRE', KEYS[1], window)
  count = count + 1
end
return {1, count, 0}
"""

# The version is a microsecond timestamp that only ever increases, so a key lost to eviction or a restart can never
# bring an older version back. 'ensure' creates it when absent; 'bump' always moves it forward.
VERSION_SCRIPT = """
local now_parts = redis.call('TIME')
local now = tonumber(now_parts[1]) * 1000000 + tonumber(now_parts[2])
local current = redis.call('GET', KEYS[1])
if ARGV[1] == 'ensure' and current then return current end
local next_version = math.max(now, (tonumber(current) or 0) + 1)
local text = string.format('%.0f', next_version)
redis.call('SET', KEYS[1], text)
return text
"""

# A lock is released only by the request that took it, never by a slow one whose lock has already expired.
RELEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
"""


def _signature():
    return (settings.REDIS_HOST, settings.REDIS_PORT, settings.REDIS_DB, settings.REDIS_USER, settings.REDIS_PASSWORD)


_resolver = ThreadPoolExecutor(max_workers=2, thread_name_prefix="redis-dns")


def _address(host, timeout):
    """The IP address of `host`, found within `timeout` seconds.

    A socket's connect timeout does not cover the name lookup, and Docker's resolver can take several seconds to give up
    on a name that is not there (a stopped Redis). The lookup runs in a helper thread so it gets the same short limit.
    """
    import redis

    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    future = _resolver.submit(socket.getaddrinfo, host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    try:
        return future.result(timeout=timeout)[0][4][0]
    except FutureTimeout:
        raise redis.TimeoutError("name lookup timed out") from None
    except OSError:
        raise redis.ConnectionError("name lookup failed") from None


def _client():
    """The client for the current settings, created on first use (after the worker forks) and never when disabled.

    It connects to the address found by `_address`; after a failure the client is dropped (see `call`), so the next
    attempt looks the name up again and follows a Redis container that came back with a new address.
    """
    signature = _signature()
    with _guard:
        if _state["signature"] != signature:
            import redis
            from redis.backoff import NoBackoff
            from redis.retry import Retry

            timeout = settings.REDIS_TIMEOUT_SECONDS
            _state["client"] = redis.Redis(
                host=_address(settings.REDIS_HOST, timeout),
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                username=settings.REDIS_USER,
                password=settings.REDIS_PASSWORD,
                socket_connect_timeout=timeout,
                socket_timeout=timeout,
                decode_responses=True,
                retry=Retry(NoBackoff(), 0),  # one attempt: a retry would add a second timeout to a failing request
            )
            _state["scripts"] = {}
            _state["signature"] = signature
        return _state["client"]


def _script(client, name, source):
    scripts = _state["scripts"]
    if name not in scripts:
        scripts[name] = client.register_script(source)
    return scripts[name]


def reset_for_tests():
    """Forget the client, the registered scripts and any back-off (tests change the settings between cases)."""
    with _guard:
        _state.update(client=None, signature=None, scripts={}, down_until=0.0, logged_at=0.0)


def _record(started_ns):
    timing = current_timing.get()
    if timing is not None:
        timing.redis_ns += time.perf_counter_ns() - started_ns
        timing.redis_commands += 1


def _log_unavailable(error):
    now = time.monotonic()
    if now - _state["logged_at"] >= settings.REDIS_BACKOFF_SECONDS:
        _state["logged_at"] = now
        logger.warning("redis.unavailable", extra={"fields": {"error": type(error).__name__}})


def call(operation, default=FAILED):
    """Run operation(client) and return its result, or `default` if Redis is disabled, backing off or failing.

    Connection failures and timeouts start the back-off; other Redis errors (out of memory, a missing script, a
    refused command) skip only this call.
    """
    if not settings.REDIS_ENABLED or time.monotonic() < _state["down_until"]:
        return default
    import redis

    started = time.perf_counter_ns()
    try:
        return operation(_client())
    except (redis.ConnectionError, redis.TimeoutError, OSError) as error:
        with _guard:
            _state["down_until"] = time.monotonic() + settings.REDIS_BACKOFF_SECONDS
            _state["signature"] = None  # drop the client: its pooled connections and address may be stale
        _log_unavailable(error)
        return default
    except redis.RedisError as error:
        _log_unavailable(error)
        return default
    finally:
        _record(started)


def available():
    return settings.REDIS_ENABLED and time.monotonic() >= _state["down_until"]


def key(suffix):
    return settings.REDIS_KEY_PREFIX + suffix


def digest(subject):
    """A keyed hash of a username or address: a key never holds the raw value, and cannot be guessed without the secret."""
    return hmac.new(settings.SECRET_KEY.encode(), subject.encode(), hashlib.sha256).hexdigest()[:32]


# JSON values -----------------------------------------------------------------------------------------------------


def _encode_default(value):
    if isinstance(value, Decimal):
        return {"__decimal__": str(value)}
    if isinstance(value, datetime):
        return {"__datetime__": value.isoformat()}
    if isinstance(value, date):
        return {"__date__": value.isoformat()}
    raise TypeError(f"Cannot cache a {type(value).__name__}")


def _decode_hook(item):
    if len(item) == 1:
        ((name, value),) = item.items()
        if name == "__decimal__":
            return Decimal(value)
        if name == "__datetime__":
            return datetime.fromisoformat(value)
        if name == "__date__":
            return date.fromisoformat(value)
    return item


def dumps(value):
    return json.dumps(value, default=_encode_default, separators=(",", ":"))


def loads(text):
    return json.loads(text, object_hook=_decode_hook)


# Cache-aside -----------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Cached:
    value: object
    status: str  # hit, miss, wait (another request computed it), down (Redis failing) or off (disabled)
    computed_at: datetime


def note_cache(status):
    timing = current_timing.get()
    if timing is not None:
        timing.cache.append(status)


def note_unavailable():
    """Record why the cache was not used (disabled or failing), for callers that skip it before looking."""
    note_cache("down" if settings.REDIS_ENABLED else "off")


def bypass(compute):
    """Compute without the cache (Redis disabled or failing) and say why, for the request log and the page."""
    status = "down" if settings.REDIS_ENABLED else "off"
    note_cache(status)
    return Cached(compute(), status, timezone.now())


def _read(full_key, valid=None):
    """(value, computed_at), or None when the entry is absent or unusable, or FAILED when Redis did not answer.

    An entry is unusable if it is not the JSON envelope this code writes or `valid(value)` says its shape is not the one
    the caller expects (a block was renamed since it was cached): it is deleted and counts as a miss, never as an error.
    """
    raw = call(lambda client: client.get(full_key))
    if raw is FAILED or raw is None:
        return raw
    try:
        envelope = loads(raw)
        value, computed_at = envelope["value"], envelope["computed_at"]
        if valid is not None and not valid(value):
            raise ValueError("unexpected shape")
        return value, computed_at
    except (ValueError, KeyError, TypeError, AttributeError):
        call(lambda client: client.delete(full_key))
        return None


def _store(full_key, value, now, ttl):
    text = dumps({"value": value, "computed_at": now})
    call(lambda client: client.set(full_key, text, ex=ttl))


def _compute_and_store(full_key, ttl, compute):
    value, now = compute(), timezone.now()
    _store(full_key, value, now, ttl)
    note_cache("miss")
    return Cached(value, "miss", now)


def cached(suffix, ttl, compute, *, lock_wait=None, valid=None):
    """Cache-aside. `compute()` runs on a miss; with `lock_wait` seconds only one request computes while others wait.

    The value must survive a JSON round trip (Decimal, date and datetime are handled; tuples come back as lists).
    `valid(value)` rejects an old-shaped entry, which is then treated as a miss.
    """
    if not settings.REDIS_ENABLED:
        return bypass(compute)
    full_key = key(suffix)
    found = _read(full_key, valid)
    if found is FAILED:
        return bypass(compute)
    if found is not None:
        note_cache("hit")
        return Cached(found[0], "hit", found[1])
    if lock_wait is None:
        return _compute_and_store(full_key, ttl, compute)
    lock_key = key("lock:" + suffix)
    token = secrets.token_hex(16)
    deadline = time.monotonic() + lock_wait
    waited = False
    while True:
        took_lock = call(lambda client: client.set(lock_key, token, nx=True, px=redis_keys.LOCK_TTL_MS))
        if took_lock is FAILED:
            return bypass(compute)
        if took_lock:
            try:
                if waited:  # the previous holder may have stored the value just before releasing the lock
                    found = _read(full_key, valid)
                    if found is not None and found is not FAILED:
                        note_cache("wait")
                        return Cached(found[0], "wait", found[1])
                return _compute_and_store(full_key, ttl, compute)
            finally:
                call(lambda client: _script(client, "release", RELEASE_SCRIPT)(keys=[lock_key], args=[token]))
        waited = True
        while time.monotonic() < deadline:  # someone else is computing: wait for the value, or for the lock to go
            time.sleep(0.05)
            found = _read(full_key, valid)
            if found is FAILED:
                return bypass(compute)
            if found is not None:
                note_cache("wait")
                return Cached(found[0], "wait", found[1])
            holder = call(lambda client: client.get(lock_key))
            if holder is FAILED:
                return bypass(compute)
            if holder is None:
                break  # released without a value (the holder failed): try to take it
        else:
            return _compute_and_store(full_key, ttl, compute)  # the holder did not finish in time: compute it here


# Dashboard version ------------------------------------------------------------------------------------------------


def dashboard_version():
    """The current version string, or None when Redis cannot be used (the caller then skips the cache)."""
    version = call(
        lambda client: _script(client, "version", VERSION_SCRIPT)(keys=[key("dashboard:version")], args=["ensure"])
    )
    return None if version is FAILED else version


def bump_dashboard():
    """Make every cached dashboard entry unreachable. Call it after the change it reflects has committed."""
    call(lambda client: _script(client, "version", VERSION_SCRIPT)(keys=[key("dashboard:version")], args=["bump"]))


# Sliding-window limiter -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Window:
    allowed: bool
    count: int
    retry_after: int  # whole seconds until an attempt would be allowed; 0 when allowed


OPEN = Window(True, 0, 0)  # what a limit says when Redis cannot be used


def _window(name, subject, limit, seconds, mode):
    token = secrets.token_hex(8)
    result = call(
        lambda client: _script(client, "window", WINDOW_SCRIPT)(
            keys=[key(f"limit:{name}:{digest(subject)}")], args=[seconds * 1000, limit, mode, token]
        )
    )
    if result is FAILED:
        return OPEN
    allowed, count, retry_ms = result
    return Window(bool(allowed), int(count), ceil(int(retry_ms) / 1000))


def window_hit(name, subject, limit, seconds):
    """Check and record one attempt atomically."""
    return _window(name, subject, limit, seconds, 1)


def window_check(name, subject, limit, seconds):
    """Check without recording."""
    return _window(name, subject, limit, seconds, 0)


def window_record(name, subject, limit, seconds):
    """Record one attempt whatever the count."""
    return _window(name, subject, limit, seconds, 2)


def window_clear(name, subject):
    call(lambda client: client.delete(key(f"limit:{name}:{digest(subject)}")))


def delete_matching(pattern_suffix):
    """Delete every key under the prefix whose remainder matches the glob pattern; returns how many were removed."""

    def run(client):
        removed = 0
        for found in client.scan_iter(match=key(pattern_suffix), count=500):
            removed += client.unlink(found)
        return removed

    removed = call(run)
    return 0 if removed is FAILED else removed
