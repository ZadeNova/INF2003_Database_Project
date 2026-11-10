"""Every Redis key the application uses, declared once (docs/plans/redis.md). Pure data: no Django, no Redis.

The "Redis keys" table in docs/DATA_MODEL.md is generated from KEYS by scripts/redis_keys_doc.py, and a test fails if
the two differ. Every key carries the prefix from the REDIS_KEY_PREFIX setting and has an expiry except the version key.
Values are JSON (never pickle); each cached entry also carries a shape number, and an entry that cannot be decoded or has
another shape number is a cache miss.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RedisKey:
    name: str
    pattern: str  # after the prefix; <...> is filled in by the code
    kind: str
    ttl: str  # as written in the table
    invalidated_by: str
    purpose: str
    ttl_seconds: int | None = None  # the fixed lifetime the code uses, when there is one


TRENDING_TTL_SECONDS = 60
DASHBOARD_TTL_SECONDS = 60 * 60
LOCK_TTL_MS = 35_000  # longer than the 30 second worker timeout, so a killed request cannot block anyone

KEYS = (
    RedisKey(
        "login_attempts",
        "limit:login:<hmac>",
        "sorted set of attempt times",
        "the window set in `RATE_LIMITS`, renewed on each attempt",
        "a successful login by that username from that address; `clear_rate_limits`",
        'Sign-in attempts by one username from one address (limit: `RATE_LIMITS["login"]`)',
    ),
    RedisKey(
        "login_failures_by_address",
        "limit:login_ip:<hmac>",
        "sorted set of failure times",
        "the window set in `RATE_LIMITS`, renewed on each failure",
        "`clear_rate_limits`",
        'Failed sign-ins from one address (limit: `RATE_LIMITS["login_ip"]`; a success never counts)',
    ),
    RedisKey(
        "review_saves",
        "limit:review:<hmac>",
        "sorted set of save times",
        "the window set in `RATE_LIMITS`, renewed on each save",
        "`clear_rate_limits`",
        'Review saves by one customer (limit: `RATE_LIMITS["review"]`)',
    ),
    RedisKey(
        "trending",
        "trending",
        "JSON: the top ranked rows of the unfiltered trending aggregation",
        "60 seconds",
        "the expiry only; visibility and photos are read live",
        "The largest database cost on the home and search pages",
        TRENDING_TTL_SECONDS,
    ),
    RedisKey(
        "dashboard_version",
        "dashboard:version",
        "string: a microsecond timestamp",
        "none (the one key without an expiry)",
        'replaced by a newer timestamp after "Refresh sales history" (the Olist import runs it) and after a review '
        "takedown or restore",
        "Makes every older dashboard entry unreachable; a timestamp, so a lost key can never revive an old version",
    ),
    RedisKey(
        "dashboard",
        "dashboard:<version>:<reporting date>",
        "JSON: the delivery, category, seller and poor-review blocks",
        "1 hour",
        "a new version key; the expiry is the safety net",
        "The history blocks of the operator dashboard (stock planning is always live)",
        DASHBOARD_TTL_SECONDS,
    ),
    RedisKey(
        "dashboard_lock",
        "lock:dashboard:<version>:<reporting date>",
        "string: the owner's random token",
        "35 seconds",
        "released by its owner, or the expiry",
        "One request recomputes a missing dashboard entry while the others wait",
        LOCK_TTL_MS // 1000,
    ),
)

BY_NAME = {key.name: key for key in KEYS}


def render_table():
    """The DATA_MODEL table, exactly as it must appear between the generated-section markers."""
    lines = [
        "| Key (after the prefix) | Value | Lifetime | Cleared by | Purpose |",
        "|---|---|---|---|---|",
    ]
    for key in KEYS:
        lines.append(f"| `{key.pattern}` | {key.kind} | {key.ttl} | {key.invalidated_by} | {key.purpose} |")
    return "\n".join(lines)
