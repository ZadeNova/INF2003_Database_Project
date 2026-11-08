# redis: Rate limiting and two cache-aside reads

status: approved
plan owner: Erfan · implementer: Claude · reviewer: a fresh Opus 5.5 session after the build · phase 5
([PLAN.md section 13](../../PLAN.md#13-phases)) · depends on: `dashboard` and `activity`; backlog items #25 and #12 in
[improvements](improvements.md) (Batch 5)

Implementation decisions and the measurement protocol settled by Erfan on 8 November 2026. The experiment runs inside the
fresh benchmark programme ([benchmark amendment l](benchmark.md#decisions)): on the same machine and commit, after the
benchmark engines are stopped.

**Purpose.** Add Redis, a key-value store, where it earns its place and say so honestly. Three uses: a security limiter, an
expensive operator query, and a hot read path measured under a seeded load. Each is built with the pattern a reviewer would
ask about (an atomic sliding window, explicit invalidation, stampede protection) so the work is more than `cache.get`. At
the demonstration's traffic the absolute gains are small; the measurements show the pattern and its ratio. Redis is never a
source of truth (AGENTS.md architecture table).

## Contract

| # | Use | Behaviour | Why Redis |
|---|---|---|---|
| 1 | **Rate limiting** (#25) | A sliding-window log in one Lua script: drop entries older than the window, count, and add the attempt only if under the limit, all atomically, using Redis's own clock. Over the limit gives a clear "too many attempts" page with `429`, `Retry-After` (from the oldest entry) and `Cache-Control: no-store`, and no re-rendered form. Blocked attempts are not recorded. Keys hold hashes, never a raw username. See "Limits" | An atomic, self-expiring counter is what Redis is for; the same writes to PostgreSQL would add WAL churn on every failed login, and an attacker could drive that load |
| 2 | **Dashboard cache** (#12) | Only the history blocks (delivery analysis, category performance, poor reviews) are cached: they depend on the fixed reporting date and change only on a refresh or a takedown. The stock planning table reads live stock and stays uncached. The cache holds computed rows (JSON), keyed by version and reporting date, so the category and shop filters do not multiply entries. Products in the poor-review list and shop names are resolved live. The page says "Served from cache, computed N minutes ago". | The dashboard is the one genuinely heavy query (seconds of real database work) |
| 3 | **Trending cache** (#12) | The top 50 ranked rows (id, views, rank, generated views) of the unfiltered trending aggregation are cached for 60 seconds, plain TTL, no lock. Visibility and photos are resolved live afterwards, so a taken-down product disappears at once; if fewer than 8 visible products remain from a full cached list the live aggregation runs. Category-filtered trending and "recently viewed" stay uncached (already index-fast, and the second is per visitor). A warm page still reads photos from MongoDB and visibility from PostgreSQL; only the aggregation is removed. | The unfiltered aggregation is the largest database cost on the home and search pages once the documented synthetic events are loaded |
| 4 | **Stampede protection** (dashboard only) | When the dashboard value is missing, one request takes a lock (`SET NX PX`, random token, released only by its owner through a Lua check), recomputes and stores it; others wait up to 5 seconds for the value and compute it themselves only if it does not appear. The lock lives 35 seconds (longer than the 30-second worker timeout), so a killed request cannot block anyone. | A cold or expired key otherwise makes every concurrent request run the heavy query at once. Trending needs no lock: at most two workers can collide on a cheap query |

**Limits** (settings, so tests use short windows). Best practice is a strict limit per account and a loose one per address,
because many people share one address behind Docker, a school or a campus network, and a low address limit would let one
person lock everyone out, markers included.

| Limit | Value | Counted |
|---|---|---|
| Logins per username and IP | 5 per 15 minutes | every attempt, before the password is checked; cleared on success |
| Failed logins per IP | 100 per 15 minutes | failures only (a success never counts); checked before, recorded after |
| Review saves per user | 10 per hour | successful saves only (not deletes, not 404s or validation errors); checked before, recorded after |

IPv4 addresses are keyed as they are and IPv6 by their /64 network. The IP is `REMOTE_ADDR` only (a forwarded header is
spoofable). Usernames are trimmed, Unicode-normalised, case-folded and cut to 150 characters before hashing, and a username
that does not exist counts like any other, so the `429` reveals nothing. Authenticated users never reach the limiter
(`LoginView` redirects them first). Known limits, to be documented: guessing one username from many addresses is not
caught (limiting per username alone would let a stranger lock a victim out), and a Redis outage or restart resets every limit.

**Fail open.** Redis down means a cache miss (go to MongoDB or PostgreSQL) and "allowed" for limits, with no fallback limiter.
Connection errors and timeouts (200 ms) trigger a 30-second back-off; out-of-memory and similar response errors only skip the
cache and do not trigger it. `redis.unavailable` is logged once per back-off window, with the exception class name only
(never its text or the address). A paused or dead Redis therefore costs at most one timeout per 30 seconds per worker.

**Operations.** One `redis` service in Compose, image pinned by digest, internal network only (no host port),
`maxmemory` 64 MB, `volatile-lru`, persistence off. Settings `REDIS_ENABLED` (strictly `true` or `false`; default on),
`REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_DB` and a key prefix; separate settings rather than a URL, because
Django's debug page hides settings named PASSWORD but would show a URL containing it. With `REDIS_ENABLED=false` the code takes
the database paths and never imports the client, so one commit is measured both ways. The bench profile and `tools` set it
to `false`.
- **Start-up script, not a command line.** An entrypoint script (like `mongo-start.sh`) writes the ACL from environment
  variables so the password never appears in `docker inspect` or `ps`. The default user is off; one application user may use
  get, set, delete, expire, scan, the sorted-set commands and `EVAL`, and may not use `FLUSHALL`, `CONFIG`, `KEYS` or the
  other dangerous commands. Resets (tests, the `clear_rate_limits` command, the measurement) scan and delete by prefix.
- **Ordering.** `web` starts without Redis (`depends_on` with `required: false`); `migrate`, which runs the tests, waits for a
  healthy Redis. `init_env.py` adds `REDIS_PASSWORD` to an existing `.env`.
- **Client.** `redis-py` only (no `django-redis`), created lazily after the worker forks. Sessions stay in PostgreSQL.

**Values and keys.** JSON, never pickle: Decimal as a string, dates as ISO, and a test proves cached and fresh data are
equal including types. A value that fails to decode, or has an old shape, is a miss and is deleted. Every key carries
`mercer:v1:`, has a TTL (the version key is the one exception and is a millisecond timestamp, not a counter, so an evicted or
restarted store can never bring back an old version), and is declared once in a registry in code (name, TTL, who invalidates).
The DATA_MODEL "Redis keys" table is checked against that registry by a test. No cached payload holds price or stock (rule 2),
and no key contains user-supplied text except as a hash.

**Invalidation happens after the change commits, never before** (bumping first would let a request cache old data under the
new version for an hour): after `refresh_sales()`, after a review takedown or restore, and at the end of `seed_showcase` and the
Olist import. A request reads the version once before computing and stores under that same version. The one-hour TTL is the
safety net.

**Not in scope.** Checkout, stock and carts (AGENTS.md rule 2), sessions, a sorted-set trending leaderboard (no performance
point at this traffic), caching the product page, registration limits, a fallback limiter, pub/sub, queues, observability,
scaled data (parked as backlog item #72).

## Tests (real Redis, no mocks, rule 8)

Redis is on in the whole suite and in CI (a Redis service with a password; `migrate` waits for it). An autouse fixture clears
the test keys before each test and refuses to run unless the database index and prefix are the test ones (`REDIS_DB=15` and
`mercer-test:` for `migrate` only), so it can never touch the application's keys.
- **Limiter:** limit and window by short setting, sliding behaviour (no burst across a boundary), `Retry-After`, reset on
  success, per-IP failures only, a limit on one username and IP not blocking another, IPv6 /64, username normalisation, no raw
  username in a key, blocked attempts not recorded, the script surviving a Redis restart, the `429` page, reviews counted on
  success only.
- **Caches:** trending served from cache but a takedown applied live; dashboard invalidated by refresh and by a review
  takedown, after commit; a cached dashboard showing a renamed product and a renamed shop; stock planning always live; a
  corrupt or old-shaped value treated as a miss; no price or stock in a payload; the cache-off path returns identical data;
  the version key surviving as a timestamp.
- **Stampede:** several threads (bodies wrapped in `mongo.using_database`) on a cold dashboard key run the computation once; a
  lock left behind expires; a lock is released only by its owner.
- **Outage:** Redis unreachable (a refused port, the suite's convention) gives fail-open for all three uses and no slow
  request; the back-off skips Redis for 30 seconds; response errors do not trigger it.

## Measurement protocol

One commit, one machine, one dataset, identical Docker limits; only `REDIS_ENABLED` and the cache state change.
`seed_activity` (seeded, 82) runs shortly before, because activity events expire after 30 days.
- **Conditions:** off; cold (Redis cleared before every timed request, so each is a miss including the cache write); warm
  (primed once); down (the Redis container paused, which exercises the real timeout and back-off, unlike a refused port).
- **Rounds:** four rounds in a seeded Latin-square order (every condition in every position once), switching conditions by
  recreating `web`; an untimed pass of at least twice the worker count per page precedes each condition so both workers and
  both databases' caches are warm.
- **Pages:** home, search and the dashboard, plus negative controls Redis does not touch (product detail and category-filtered
  trending). The controls' largest deviation from a ratio of 1 is the noise floor: no smaller effect is claimed.
- **Samples:** 150 requests per cheap page per condition per round, 15 for the dashboard. p95 is reported only with at least
  100 pooled samples and p99 only with at least 500; below that the table shows median, range and maximum, labelled. The
  dashboard therefore has no tail percentiles.
- **Per request:** server-side duration, PostgreSQL and MongoDB time and counts, and new `redis_ms` and `cache` fields in the
  request log, which the collector already joins by request id.
- **Statistics:** median, p95 and p99 where allowed; per-round paired ratios (off against warm) and their range, as the main
  evidence, because requests within a round are not independent; a pooled bootstrap interval with a fixed seed, labelled
  optimistic. Events in the trending window are recorded at the start and end of each round.
- **Gate (rule 10):** a sample counts only if its cache status matches its condition (cold a miss, warm a hit, off no Redis
  calls) and its data equals the off condition's; discrepancies are reported, not hidden. The protocol and the analysis script
  are committed before the run (`--require-clean`); a short pilot sets the sample sizes only.
- **Stampede experiment:** N simultaneous cold dashboard requests, repeated, Redis on and off; the metric is how many ran the
  query. Two workers bound the real parallelism, and the report says so.
- **Limiter overhead:** the limiter call timed on its own and reported as a cost.
- **Outputs:** a script writes the table and chart from the result folders; nothing is typed by hand. Threats to validity
  (one machine, Docker on Windows, loopback, one sequential client, synthetic events, two workers) go in the report.
- It runs alone (never beside a benchmark), after the full benchmark and before the report.

## Documents to update

README (service, settings, commands, how to measure, the `.env` rerun), DATA_MODEL (the "Redis keys" table, generated),
DESIGN (the `429` page and the cache note), AGENTS.md architecture row if needed, PLAN.md section 14, DECISIONS.

## Decisions

| ID | Decision | Why |
|---|---|---|
| a | Three uses only: rate limiting, dashboard cache, trending cache | Each has an honest reason; nothing that touches money or stock |
| b | Fail open everywhere, no fallback limiter, with timeouts and a 30-second back-off | A cache outage must not log everyone out or slow the shop; a per-worker fallback has unclear semantics |
| c | Limits: 5 per username and IP per 15 minutes, 100 failed logins per IP per 15 minutes, 10 review saves per hour | Strict per account, loose per address because many users share one (Docker, a school network); a success never counts |
| d | Trending caches ranked rows for 60 s and filters visibility live; the dashboard uses a timestamp version key and resolves products and shops live; invalidate after commit | Takedowns and renames never wait for a TTL; invalidation is explicit where the data is expensive |
| e | `maxmemory` 64 MB, `volatile-lru`, no persistence, ACL user, password, internal network, start-up script | Every key has a TTL; Redis can be lost without loss of data; least privilege as for the other stores |
| f | Redis off, cold, warm and down measured with the existing collector on Erfan's PC (protocol above), inside benchmark amendment l | Same commit and machine; the ratio is the evidence |
| g | JSON values, plain `redis-py`, no `django-redis` | No code execution from a stored value; exact Decimal and date round trips |
| h | Cut: dropped if the full suite is not green by 15 November | PLAN.md condition for Tier 2 work |
| i | Sliding-window log in a Lua script (sorted set), not a fixed-window counter | No boundary burst, exact `Retry-After`, atomic, and the honest use of a sorted set |
| j | Stampede lock on the dashboard only | Seconds of recomputation; trending is cheap and at most two workers can collide |
| k | Visible cache status on the dashboard; `cache` and `redis_ms` in the request log | The recording can show a miss then a hit; the collector can attribute time |
| l | Host, port and password settings, not a URL | The debug page would show a URL's password |
| m | Redis keys declared once in code; the DATA_MODEL table is checked against it | Nothing hand-written can drift |
| n | Redis on in the whole suite, guarded per-test clearing on a dedicated database index and prefix | Tests the real configuration; no cross-test leakage; cannot touch dev keys |
| o | Dashboard cache holds the history blocks only; stock planning stays live | A cached stock table would be up to an hour stale |
| p | The demonstration database carries the labelled `seed_activity` events | The trending cache has nothing to speed up without them; rule 9 satisfied |

## Review notes

Drafted 8 November 2026 and revised the same day after reading the dashboard, trending, login, review and Compose code with
Erfan: the trending page shows view counts and ranks, so rows (not bare ids) are cached; the dashboard result held Django
objects and live stock, so only the history blocks are cached and products are resolved live. Evidence for the choice of
uses: with the documented synthetic events the unfiltered trending query was most of the home page's time, the
category-filtered query was already index-fast, the product page was cheap, and the dashboard took seconds (measured, not
typed here; the collector reproduces it).

Defence lines for the video: why Redis and not PostgreSQL (counters with a TTL do not belong in the system of record, and the
materialized view already covers history while Redis covers the repeated read); why not an in-process cache (two workers would
disagree after an invalidation); why fail open (a cache outage must not become a shop outage); why JSON (a stored value
cannot execute); why the address limit is loose (shared networks); why no sorted-set leaderboard (no measurable gain at this
traffic, recorded as rejected) while the limiter does use one (it is the correct structure for a sliding window).
