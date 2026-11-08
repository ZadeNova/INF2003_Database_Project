"""The Redis module against a real Redis: values, cache-aside, the stampede lock, fail-open, the ACL and the key registry.

Outages are real ones: a refused port, and a listening socket that accepts and never answers (a hung Redis).
"""

import json
import logging
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from datetime import timezone as utc_timezone
from decimal import Decimal

import pytest
import redis
from django.conf import settings as django_settings

from config import mongo, redis_keys, redis_store
from config.jsonlog import JsonFormatter


def raw():
    """A client of the same Redis, used only to look at what the code stored."""
    return redis.Redis(
        host=django_settings.REDIS_HOST,
        port=django_settings.REDIS_PORT,
        db=django_settings.REDIS_DB,
        username=django_settings.REDIS_USER,
        password=django_settings.REDIS_PASSWORD,
        decode_responses=True,
    )


def stored_keys():
    return sorted(k.removeprefix(django_settings.REDIS_KEY_PREFIX) for k in raw().scan_iter(match="*", count=500))


def pattern_regex(pattern):
    return re.compile(re.sub(r"<[^>]*>", "[^:]+", re.escape(pattern).replace("\\<", "<").replace("\\>", ">")) + "$")


def test_json_round_trip_keeps_decimals_dates_and_datetimes_exact():
    value = {
        "money": Decimal("0.10"),
        "big": Decimal("12345678901234567890.123456789"),
        "day": date(2026, 11, 8),
        "at": datetime(2026, 11, 8, 1, 2, 3, 456789, tzinfo=utc_timezone.utc),
        "rows": [{"n": None, "x": 1.5, "t": True}],
    }
    back = redis_store.loads(redis_store.dumps(value))
    assert back == value
    assert str(back["money"]) == "0.10" and type(back["money"]) is Decimal
    assert type(back["day"]) is date and back["at"].tzinfo is not None and type(back["at"]) is datetime


@pytest.mark.parametrize("unsupported", [object(), {1, 2}, b"bytes"])
def test_values_that_are_not_plain_data_are_refused_rather_than_pickled(unsupported):
    with pytest.raises(TypeError):
        redis_store.dumps({"x": unsupported})


def test_cache_aside_miss_then_hit_with_a_lifetime_and_the_computed_time():
    calls = []

    def compute():
        calls.append(1)
        return {"total": Decimal("1.50"), "days": [date(2026, 1, 2)]}

    first = redis_store.cached("unit", 30, compute)
    second = redis_store.cached("unit", 30, compute)
    assert (first.status, second.status) == ("miss", "hit") and len(calls) == 1
    assert second.value == first.value and second.computed_at == first.computed_at
    assert 0 < raw().pttl(redis_store.key("unit")) <= 30_000


@pytest.mark.parametrize("stored", ["not json {", '{"no": "envelope"}', "[1, 2]", '{"value": 1}', '"text"'])
def test_an_unreadable_or_old_shaped_value_is_a_miss_and_is_replaced(stored):
    raw().set(redis_store.key("unit"), stored)
    result = redis_store.cached("unit", 30, lambda: 7)
    assert (result.status, result.value) == ("miss", 7)
    assert redis_store.loads(raw().get(redis_store.key("unit")))["value"] == 7


def test_a_failing_computation_stores_nothing_and_releases_the_lock():
    def boom():
        raise RuntimeError("compute failed")

    with pytest.raises(RuntimeError):
        redis_store.cached("unit", 30, boom, lock_wait=1)
    assert stored_keys() == []
    started = time.monotonic()
    assert redis_store.cached("unit", 30, lambda: 1, lock_wait=1).status == "miss"
    assert time.monotonic() - started < 0.5  # it took the lock at once instead of waiting for an expiry


def test_concurrent_requests_on_a_cold_key_compute_once_and_the_rest_wait(mongo_db):
    computed = []

    def compute():
        computed.append(1)
        time.sleep(0.6)
        return {"answer": Decimal("42.00")}

    def request(_):
        with mongo.using_database(mongo_db.name):
            return redis_store.cached("unit", 30, compute, lock_wait=5)

    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(request, range(6)))
    assert len(computed) == 1
    statuses = sorted(result.status for result in results)
    assert statuses.count("miss") == 1 and set(statuses) <= {"miss", "wait", "hit"} and "wait" in statuses
    assert {result.value["answer"] for result in results} == {Decimal("42.00")}


def test_a_stale_lock_expires_and_a_waiting_request_falls_back_to_computing():
    client = raw()
    lock = redis_store.key("lock:unit")
    client.set(lock, "someone-else", px=300)
    started = time.monotonic()
    result = redis_store.cached("unit", 30, lambda: "computed here", lock_wait=0.1)
    assert (result.status, result.value) == ("miss", "computed here") and time.monotonic() - started < 1
    time.sleep(0.4)
    assert client.get(lock) is None  # it expired by itself
    client.delete(redis_store.key("unit"))
    started = time.monotonic()
    assert redis_store.cached("unit", 30, lambda: "again", lock_wait=5).status == "miss"
    assert time.monotonic() - started < 1


def test_a_lock_is_released_only_by_its_owner():
    client = raw()
    lock = redis_store.key("lock:unit")
    client.set(lock, "mine", px=5000)
    release = redis_store._script(redis_store._client(), "release", redis_store.RELEASE_SCRIPT)
    assert release(keys=[lock], args=["theirs"]) == 0 and client.get(lock) == "mine"
    assert release(keys=[lock], args=["mine"]) == 1 and client.get(lock) is None


def test_the_version_only_moves_forward_and_survives_repeated_ensures():
    first = redis_store.dashboard_version()
    assert redis_store.dashboard_version() == first  # ensure never changes an existing version
    redis_store.bump_dashboard()
    second = redis_store.dashboard_version()
    redis_store.bump_dashboard()
    redis_store.bump_dashboard()
    third = redis_store.dashboard_version()
    assert int(first) < int(second) < int(third)
    assert raw().pttl(redis_store.key("dashboard:version")) == -1  # the one key without an expiry


def test_a_lost_version_key_never_brings_an_old_version_back():
    redis_store.bump_dashboard()
    old = redis_store.dashboard_version()
    raw().delete(redis_store.key("dashboard:version"))  # as if it had been evicted or Redis had restarted
    assert int(redis_store.dashboard_version()) > int(old)


def test_disabled_redis_never_connects_and_every_lookup_computes(settings):
    settings.REDIS_ENABLED = False
    redis_store.reset_for_tests()
    calls = []
    for _ in range(2):
        result = redis_store.cached("unit", 30, lambda: calls.append(1) or "value")
        assert result.status == "off"
    assert len(calls) == 2 and redis_store._state["client"] is None
    assert redis_store.window_hit("login", "x", 1, 60).allowed and redis_store.window_hit("login", "x", 1, 60).allowed
    assert redis_store.dashboard_version() is None and redis_store.delete_matching("*") == 0
    settings.REDIS_ENABLED = True
    assert stored_keys() == []  # nothing was written while it was off


@pytest.fixture
def unreachable(settings):
    settings.REDIS_PORT = 1  # nothing listens here: the connection is refused
    redis_store.reset_for_tests()


def test_everything_fails_open_when_redis_is_unreachable(unreachable):
    started = time.monotonic()
    first = redis_store.window_hit("login", "x", 1, 60)
    second = redis_store.window_hit("login", "x", 1, 60)
    assert first.allowed and second.allowed  # no limit can be enforced, so none is
    assert redis_store.dashboard_version() is None
    calls = []
    result = redis_store.cached("unit", 30, lambda: calls.append(1) or "live")
    assert (result.status, result.value) == ("down", "live") and calls == [1]
    assert redis_store.delete_matching("*") == 0
    assert time.monotonic() - started < 1


def listening_socket():
    """A port that accepts connections in the kernel and never answers, like a hung Redis."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(8)
    return server, server.getsockname()[1]


def test_a_hung_redis_costs_one_timeout_then_is_skipped_for_the_backoff(settings):
    server, port = listening_socket()  # accepts connections in the kernel but never answers
    try:
        settings.REDIS_PORT = port
        settings.REDIS_HOST = "127.0.0.1"
        redis_store.reset_for_tests()
        started = time.monotonic()
        assert redis_store.window_hit("login", "x", 1, 60).allowed
        first = time.monotonic() - started
        assert 0.15 < first < 1.5  # the 200 ms timeout, not seconds
        started = time.monotonic()
        for _ in range(20):
            assert redis_store.window_hit("login", "x", 1, 60).allowed
        assert time.monotonic() - started < 0.1  # skipped: no connection was tried
    finally:
        server.close()


def test_during_the_backoff_no_connection_is_attempted_even_to_a_working_server(unreachable, settings):
    assert redis_store.window_hit("login", "x", 1, 60).allowed  # fails once and starts the back-off
    server, port = listening_socket()
    try:
        settings.REDIS_PORT = port
        settings.REDIS_HOST = "127.0.0.1"
        for _ in range(5):
            redis_store.window_hit("login", "x", 1, 60)
        server.settimeout(0.3)
        with pytest.raises(socket.timeout):
            server.accept()
    finally:
        server.close()


def test_redis_is_used_again_when_the_backoff_ends(settings):
    real_port = settings.REDIS_PORT
    settings.REDIS_BACKOFF_SECONDS = 1.5
    settings.REDIS_PORT = 1
    redis_store.reset_for_tests()
    assert redis_store.window_hit("login", "x", 1, 60).allowed  # fails and starts the back-off
    settings.REDIS_PORT = real_port
    first, second = redis_store.window_hit("login", "y", 1, 60), redis_store.window_hit("login", "y", 1, 60)
    assert first.allowed and second.allowed  # still skipping Redis, so a limit of one is not enforced
    time.sleep(1.6)
    assert redis_store.window_hit("login", "y", 1, 60).allowed
    assert not redis_store.window_hit("login", "y", 1, 60).allowed  # Redis is back and counting


def test_a_refused_command_does_not_start_the_backoff():
    assert redis_store.call(lambda client: client.flushall(), default="refused") == "refused"
    assert redis_store._state["down_until"] == 0.0
    assert not redis_store.window_hit("login", "x", 0, 60).allowed  # Redis is still in use


def test_an_outage_is_logged_once_per_window_with_the_exception_class_only(unreachable):
    logger = logging.getLogger("mercer.redis")
    records = []

    class Collect(logging.Handler):
        def emit(self, record):
            records.append(JsonFormatter().format(record))

    handler = Collect()
    logger.addHandler(handler)
    try:
        for _ in range(5):
            redis_store.window_hit("login", "x", 1, 60)
    finally:
        logger.removeHandler(handler)
    assert len(records) == 1
    line = json.loads(records[0])
    assert line["message"] == "redis.unavailable" and line["error"] == "ConnectionError"
    assert "refused" not in records[0] and django_settings.REDIS_PASSWORD not in records[0]  # no error text, no secret


def test_the_application_user_can_do_only_what_the_application_needs():
    client = raw()
    for command in (("FLUSHALL",), ("FLUSHDB",), ("CONFIG", "GET", "maxmemory"), ("KEYS", "*"), ("SCRIPT", "FLUSH")):
        with pytest.raises(redis.exceptions.NoPermissionError):
            client.execute_command(*command)
    with pytest.raises(redis.exceptions.NoPermissionError):
        client.set("outside-the-prefix", "x")  # keys must start with mercer
    client.set(redis_store.key("acl"), "x", ex=5)
    assert client.get(redis_store.key("acl")) == "x"


def test_every_key_the_code_writes_matches_the_registry(mongo_db):
    redis_store.window_hit("login", "a|1.1.1.1", 5, 60)
    redis_store.window_record("login_ip", "1.1.1.1", 5, 60)
    redis_store.window_record("review", "7", 5, 60)
    redis_store.cached("trending", redis_keys.TRENDING_TTL_SECONDS, lambda: [])
    version = redis_store.dashboard_version()
    redis_store.cached(f"dashboard:{version}:2026-11-08", 60, lambda: {}, lock_wait=1)
    raw().set(redis_store.key(f"lock:dashboard:{version}:2026-11-08"), "token", px=1000)
    keys = stored_keys()
    expressions = [pattern_regex(key.pattern) for key in redis_keys.KEYS]
    assert len(keys) == 7
    for found in keys:
        assert sum(bool(expression.match(found)) for expression in expressions) == 1, found
    assert not any("a|1.1.1.1" in found or "1.1.1.1" in found for found in keys)  # hashed, never raw


def test_registry_lifetimes_are_the_ones_the_code_stores():
    redis_store.cached("trending", redis_keys.TRENDING_TTL_SECONDS, lambda: [])
    assert 0 < raw().pttl(redis_store.key("trending")) <= redis_keys.TRENDING_TTL_SECONDS * 1000
    assert redis_keys.BY_NAME["trending"].ttl_seconds == 60
    assert redis_keys.BY_NAME["dashboard"].ttl_seconds == 3600
    assert redis_keys.BY_NAME["dashboard_lock"].ttl_seconds * 1000 == redis_keys.LOCK_TTL_MS


def test_a_host_name_that_does_not_resolve_costs_one_short_wait_and_is_looked_up_again_later(settings):
    settings.REDIS_HOST = "no-such-redis-host.invalid"
    redis_store.reset_for_tests()
    started = time.monotonic()
    assert redis_store.window_hit("login", "x", 1, 60).allowed
    assert time.monotonic() - started < 1  # the lookup has the same short limit as a connection
    assert redis_store._state["signature"] is None  # the client was dropped: the next attempt resolves the name again
    started = time.monotonic()
    assert redis_store.window_hit("login", "x", 1, 60).allowed
    assert time.monotonic() - started < 0.05  # backing off


def test_an_address_given_as_an_ip_needs_no_lookup(settings):
    settings.REDIS_HOST = "127.0.0.1"
    redis_store.reset_for_tests()
    assert redis_store._address("127.0.0.1", 0.2) == "127.0.0.1" and redis_store._address("::1", 0.2) == "::1"
    assert redis_store._address("localhost", 1) in {"127.0.0.1", "::1"}


@pytest.mark.parametrize("rejects", [lambda value: "new" in value, lambda value: value["new"] is not None])
def test_an_entry_the_caller_no_longer_understands_is_a_miss_even_if_checking_it_raises(rejects):
    envelope = redis_store.dumps({"value": {"old": 1}, "computed_at": datetime(2026, 1, 1, tzinfo=utc_timezone.utc)})
    raw().set(redis_store.key("unit"), envelope, ex=60)
    result = redis_store.cached("unit", 30, lambda: {"new": 2}, valid=rejects)
    assert (result.status, result.value) == ("miss", {"new": 2})
    assert redis_store.cached("unit", 30, lambda: {"new": 3}, valid=rejects).value == {"new": 2}  # now stored, so a hit


def test_a_waiting_request_takes_the_lock_over_when_the_holder_fails(mongo_db):
    def holder():
        def boom():
            time.sleep(0.5)
            raise RuntimeError("the holder failed")

        with mongo.using_database(mongo_db.name), pytest.raises(RuntimeError):
            redis_store.cached("unit", 30, boom, lock_wait=5)

    def waiter():
        with mongo.using_database(mongo_db.name):
            time.sleep(0.15)  # let the holder take the lock first
            started = time.monotonic()
            result = redis_store.cached("unit", 30, lambda: "recomputed", lock_wait=5)
            return result, time.monotonic() - started

    with ThreadPoolExecutor(2) as pool:
        failed, waited = pool.submit(holder), pool.submit(waiter)
        failed.result()
        result, elapsed = waited.result()
    assert (result.status, result.value) == ("miss", "recomputed")
    assert elapsed < 2  # it took over soon after the lock was released, not after the full wait
