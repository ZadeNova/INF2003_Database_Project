# dashboard_summaries: Delivery and score summaries in both engines

status: done
plan owner: Erfan · implementer: Claude · reviewer: a fresh Opus 5.5 session after the build · phase 5
([PLAN.md section 13](../../PLAN.md#13-phases)) · depends on: `dashboard`, `reviews`; backlog item #10 step 2 in
[improvements](improvements.md) (built first in Batch 6)

Settled by Erfan on 9 November 2026. Time-box: tests green by the end of Wednesday 11 November, otherwise the in-app wiring
is dropped and the same summaries become benchmark-only variants (see Fallback).

**Purpose.** The delivery-delay panel joins two stores per request: delivery rows from PostgreSQL and per-order review
scores from MongoDB. Step 1 of #10 made the MongoDB side one integer `$group`. Step 2 maintains each side as a precomputed
summary, with the same feature built in the idiom of each engine: a PostgreSQL **materialized view** beside a MongoDB
**on-demand materialized view** (rebuilt with `$out`). It gives the NoSQL comparison a like-for-like pair, a demonstrable MongoDB
aggregation feature, and the maintained-summary variants of benchmark B2 (#5) without writing them twice. It is an
optimisation, not new data: the live path stays as the fallback and the test oracle.

## Contract

| # | Part | Behaviour |
|---|---|---|
| 1 | **PostgreSQL view** | `order_delivery_summary` in the `dashboard` app, one row per delivered order up to the reporting date (`dashboard_as_of()`): order, seller, delay days, bucket, distance in km and the reporting date. Shop names are not stored (they are read live). A unique index on the order makes `REFRESH MATERIALIZED VIEW CONCURRENTLY` possible. The refresh runs in a `SECURITY DEFINER` function with a pinned `search_path`, under the existing advisory lock, granted only to the runtime role; the runtime role gets `SELECT`. Built in a new migration |
| 2 | **MongoDB summary** | Collection `order_review_scores`, one document per order that has visible scores: the integer `total` and `count` of those scores up to the reporting date, and the reporting date as an ISO string. A strict `$jsonSchema` validator in `mongo_schema.py` like the other collections; only the `_id` index. Derived from MongoDB's own reviews, so nothing is copied between stores |
| 3 | **Bulk refresh** | "Refresh sales history" and the Olist import refresh both summaries in one PostgreSQL transaction: the two views, then one aggregation over the reviews ending in `$out`. `$out` replaces the collection atomically and keeps its validator and indexes, so a reader sees the old summary or the new one and a refused result leaves the old one in place; an order whose visible reviews are gone simply is not in the new result. If the MongoDB step fails the views roll back. The Redis version bump follows the commit as today. *Changed from the first draft (`$merge` with a run stamp and a sweep): a full rebuild rewrites every document, which `$merge` measured slower than `$out` on the full data, and `$out` needs no stamp, sweep or interleaving guard* |
| 4 | **Per-order recompute** | Every review write that can change a historical score recomputes that one order's summary inside the same MongoDB transaction: operator takedown and restore ([reviews/services.py](../../src/reviews/services.py) `moderate_review`) and customer edit and delete (`write_review`). It reads the order's few reviews and replaces one document ("recompute, do not increment", so it cannot drift). A rolled-back transaction leaves the summary unchanged. `$out` and `$merge` cannot run inside a transaction (verified in the spike: error 263), so the per-order change reads and replaces one document instead; it deletes the document when no visible review is left |
| 5 | **Read path** | `delivery_analysis` reads the view and the collection and does the same Python join as today. The result is the same shape, so the cached blocks do not change (the Redis shape number stays unless the structure does) |
| 6 | **Fallback and oracle** | The current live path stays. The dashboard uses it when either summary is missing, or the two carry different reporting dates (for example after a half-failed refresh). Tests assert both paths return identical blocks |

## Best practices applied

- PostgreSQL: a materialized view for a read-heavy derived set, refreshed concurrently so readers keep the previous
  snapshot; refresh through a narrow definer function, never DDL rights for the runtime role; the view stores facts, not
  display text; parameterised SQL only.
- MongoDB: an on-demand materialized view rebuilt with `$out` (atomic replace; `$merge` is for incremental updates and was measured slower for a full rebuild), a schema validator,
  idempotent per-order recompute inside the same transaction as the review write, majority write concern and snapshot
  read concern through the existing `_transact` helper; no embedded copy of PostgreSQL data.
- Both: the summary is rebuildable from its source at any time; a stale or missing summary degrades to the live path.

## Tests

Summary path equals live path on the imported fixture (the main test); takedown, restore, customer edit and customer delete
each leave the summary equal to the live result; a rolled-back review transaction leaves it unchanged; a summary with a
mismatched reporting date falls back to the live path; a refresh drops orders whose reviews are gone and a refused rebuild leaves the old summary; the runtime role can
refresh but has no DDL; the migration is reversible and the drift check passes; existing dashboard and cache tests updated.
Full Docker suite before the review.

## Measurement

The committed script [time_dashboard_history.py](../../scripts/time_dashboard_history.py) times the cold dashboard history on
the full data through the live path and the summary path, alternating within each round, and prints the median, minimum and
maximum, whether the two results are identical, and the duration of a full refresh. Figures are quoted only as its output,
with the machine they came from (never typed into a document). If the summary path is not measurably faster, the
value is the demonstration and the benchmark pairing; Erfan is told before the build continues past the spike.

## Order of work

1. Spike: confirm the `$merge`/`$out` and transaction behaviour on the real MongoDB, and time a prototype against the live path.
2. This plan finalised, Decisions row. 3. PostgreSQL migration, function, grants, import hook. 4. MongoDB validator, bulk
refresh, per-order recompute on all review paths. 5. Read path and fallback. 6. Tests and the full suite. 7. Opus review,
one fix round. 8. Docs: DATA_MODEL, README, DECISIONS, PLAN, improvements; `scripts/check_docs.py`.

## Fallback

If the tests are not green by the end of 11 November, the application wiring (items 3 to 6) is dropped. The view definition
and the `$out` pipeline move into the benchmark as the maintained-summary variants of B2 and the app stays as it is.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Review changes | Recompute the affected order's summary in the same MongoDB transaction, on takedown, restore, edit and delete | A takedown must show on the dashboard at once; incrementing could drift |
| Live path | Kept as fallback and test oracle | Graceful degradation and a permanent correctness check |
| Plan file | This file | The backlog row required a short plan first |

## Known limits

- A bulk refresh that overlaps a review takedown can write the pre-takedown value over the freshly recomputed document.
  Both are operator actions and the overlap is short; the next refresh corrects it.
- A refresh's `$out` waits for review transactions in flight, because each reads the summary's reporting date first.
  Review writes are short and rare.
- The reporting-date check cannot see a summary that is stale at the same date. Every writer of `reviews` (the import and
  the two review services) is covered, and the import empties a leftover summary before it refreshes.

## Review notes

9 November 2026, a fresh Opus 5.5 session for Erfan, running things against the real stack: the targeted test modules, the
migration drift check, scratch tests of the edge cases (a delivery exactly at the cut-off, the Singapore boundary, null
geolocation, a missing reporting date), the privileges of the application's PostgreSQL and MongoDB users, MongoDB
unreachable during a refresh, and the committed timing script. It found no correctness defect: the summary path matched
the source on every case and on the full data. Findings, all approved by Erfan and fixed in one round:

- Timings had been typed into three places (the plan, the Decisions row and a docstring); they are now qualitative, and
  the measured figures are the output of [time_dashboard_history.py](../../scripts/time_dashboard_history.py).
- The tests the plan promised for migration reversal and simultaneous refreshes were missing; both were added.
- A docstring still named `$merge`, and PLAN.md and this file disagreed on status.
- A truncate-style reset followed by a failed post-import refresh could leave a stale summary that the date check would
  trust; the import now empties the score summary before it refreshes.
- Confirmed and accepted, now under "Known limits": a bulk refresh overlapping a takedown can write the older value, and
  a refresh waits for review transactions in flight.

Also verified outside the review: the benchmark loader builds both summaries in the isolated bench databases, the
benchmark fixture tests pass, and the benchmark correctness mode passes on the fixture; the full Docker suite is green
after the fix round (counts are printed by the run, never typed here).
