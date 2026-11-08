# redis: Rate limiting and two cache-aside reads

status: draft
plan owner: Erfan · implementer: Claude · reviewer: a fresh Opus 5.5 session after the build · phase 5
([PLAN.md section 13](../../PLAN.md#13-phases)) · depends on: `dashboard` and `activity`; backlog items #25 and #12 in
[improvements](improvements.md) (Batch 5)

**Purpose.** Add Redis, a key-value store, where it earns its place and say so honestly. Three uses: a security counter, an
expensive operator query, and a hot read path measured under a seeded load. At the demonstration's traffic the absolute gains
are small; the measurements show the pattern and its ratio. Redis is never a source of truth (AGENTS.md architecture table).

## Contract

| # | Use | Behaviour | Why Redis |
|---|---|---|---|
| 1 | **Rate limiting** (#25) | Failed logins are counted per username and IP, and per IP alone; review posting per user. Over the limit gives a clear "too many attempts" page with `429` and `Retry-After`. A successful login clears that username's counter. Keys hold hashes, never a raw username. | An atomic counter with an expiry is what Redis is for; the limit does not depend on traffic |
| 2 | **Dashboard cache** (#12) | The operator dashboard's data is cached per filter set until "Refresh sales history", with a version key bumped on a refresh and on a review takedown (explicit invalidation); a one-hour TTL is the safety net | The dashboard is the one genuinely heavy query (seconds of real database work) |
| 3 | **Trending cache** (#12) | The ranked ids (not the products) of the unfiltered trending aggregation are cached for 60 seconds; visibility and photos are resolved live afterwards, so a taken-down product disappears at once | The unfiltered aggregation is the largest database cost on the home and search pages once the documented synthetic events are loaded |

**Fail open.** Redis down means a cache miss (go to MongoDB or PostgreSQL) and "allowed" for rate limits, logged as
`redis.unavailable` with no data in the message. Connection and read timeouts are 200 ms, and after a failure the app skips
Redis for 30 seconds so a dead Redis never adds a timeout to every request.

**Operations.** One `redis` service in Compose, image pinned by digest, password from the ignored `.env`, internal network
only (no host port), `maxmemory` 64 MB, `volatile-lru`, persistence off. Settings `REDIS_ENABLED` (default on) and
`REDIS_URL`. With `REDIS_ENABLED=false` the code takes the database paths, so one commit is measured both ways.

**Not in scope.** Checkout, stock and carts (AGENTS.md rule 2), sessions (they stay in PostgreSQL), a sorted-set trending
leaderboard (no performance point at this traffic), caching the product page, pub/sub, queues, observability, scaled
data (parked as backlog item #72).

**Measurement.** The request-timing collector, same machine and commit, three conditions: Redis off, on with a cold cache and
on warm; pages home, search, product detail and the dashboard. A script reads the three result folders and writes a
comparison table and chart, so nothing is typed by hand. Rate limiting is a demonstration (a screen recording of the
block), not a timing.

**Tests** (real Redis, no mocks, rule 8). Limits, window expiry (short window by setting), reset on success, per-IP limit,
the `429` page, no raw username in a key; trending served from cache but a takedown applied live; dashboard invalidated by
refresh and by a review takedown; the cache-off path returns the same data; Redis unreachable gives fail-open for all three
and no slow request. CI gets a Redis service.

**Documents to update.** README (service, settings, commands, how to measure), DATA_MODEL (a "Redis keys" table: key,
value, TTL, who invalidates), DESIGN (the `429` page), AGENTS.md architecture row if needed, PLAN.md section 14.

## Decisions

| ID | Decision | Why |
|---|---|---|
| a | Three uses only: rate limiting, dashboard cache, trending cache | Each has an honest reason; nothing that touches money or stock |
| b | Fail open everywhere, with timeouts and a 30-second back-off | Availability over strictness; a cache outage must not log everyone out or slow the shop |
| c | Limits: 5 failed logins per username and IP per 15 minutes, 20 per IP per 15 minutes, 10 reviews per user per hour | Stops guessing and spraying without annoying a typo |
| d | Trending caches ids for 60 s and filters visibility live; the dashboard uses a version key | Takedowns never wait for a TTL; invalidation is explicit where the data is expensive |
| e | `maxmemory` 64 MB, `volatile-lru`, no persistence, password, internal network | Every key has a TTL; Redis can be lost without loss of data |
| f | Redis off, cold and warm measured with the existing collector on Erfan's PC | Same commit and machine; the ratio is the evidence |
| g | Values use Django's cache (pickle) over an authenticated, internal-only Redis | Simplest correct option for Decimal and date values; no untrusted writer exists |
| h | Cut: dropped if the full suite is not green by 15 November | PLAN.md condition for Tier 2 work |

## Review notes

Drafted 8 November 2026 from Erfan's decisions. Evidence for the choice of uses: with the documented 200,000 synthetic events the
unfiltered trending query was most of the home page's time, the category-filtered query was already index-fast, the
product page was cheap, and the dashboard took seconds (measured, not typed here; the collector reproduces it).
