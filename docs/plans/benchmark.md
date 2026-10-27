# benchmark: Correctness-gated PostgreSQL and MongoDB comparison

status: in-progress
plan owner: Chee Long · implementer: Chee Long · Phase 3B (25 October to 1 November 2026)
· depends on: `olist-import` for harness/loaders; `catalogue`, `reviews`, `dashboard`, `checkout` for full acceptance

## Contract

**Goal and schedule.** Implement [PLAN.md section 7](../../PLAN.md#7-benchmark-protocol) after plan approval: harness,
loaders and golden fixtures after import; B1 with catalogue, B2 with reviews/dashboard, B3/B6 with checkout, B4/B5 as
available. First correctness-complete B1–B6 pass: 30 October; final measurements: 31 October–1 November. B2 depends on
28–29 October features, leaving about one day before the first pass: this is a schedule risk, not assumed readiness.

| ID | Equivalent work and correctness gate |
|---|---|
| B1 | Attribute filters on PostgreSQL EAV, JSONB with GIN, and MongoDB documents with multikey indexes; match independent golden rows |
| B2 | Headline: live PostgreSQL CTE/window query versus live MongoDB pipeline for dashboard/review aggregates. Time and report materialized-view read and `REFRESH` separately; match golden totals and rating aggregates |
| B3 | Equivalent minimal transactions: conditional stock decrement and order insert. Fifty buyers, ten units: ten successes, forty refusals, zero remaining stock, no oversell; not the full app checkout |
| B4 | Before/after indexes for B1/B2, preserving golden results: B-tree/composite/partial/GIN versus compound/multikey/partial, with plans |
| B5 | Identical loaded records: PostgreSQL `pg_relation_size`/`pg_indexes_size` after `VACUUM (ANALYZE)` and `CHECKPOINT`; MongoDB `collStats` `storageSize`/`totalIndexSize` after load. Report data/index bytes separately and note WiredTiger compression |
| B6 | Demonstrate lost update under READ COMMITTED, protection by `FOR UPDATE` and SERIALIZABLE/retry, and MongoDB write-conflict retry. Check anomaly/protected states; record throughput and retries outside the 1/10/50 timing matrix |

**Isolation and source data (BM1, BM8, BM9).** Dedicated `bench` Compose profile: `bench-db` and `bench-mongo`, using
the same pinned images as the app; MongoDB is a single-node replica set for B3/B6 transactions. `init_env.py` generates
separate `BENCH_*` credentials: the harness uses the PostgreSQL bench owner/database and a MongoDB bench user with
`readWrite` on `bench` only. App `db`/`mongo`, app grants and AGENTS.md rule 5 remain unchanged. Update README and
AGENTS.md with bench setup/commands when implemented. Derive PostgreSQL bench schema from app migrations plus
bench-only EAV/JSONB tables, so B3/B6 exercise real constraints. Load identical checksummed files, IDs, values and
attributes into both engines. The app has no `is_generated`: only bench databases carry that flag and receive
generator output. The seeded CSV/NDJSON generator (valid FKs/money; code, configuration and checksums committed, not
generated datasets) is deferred by amendment j: build it only if its condition is met. Tier 1 measures retained base Olist; scaled runs remain Tier 2
`durability`.

**Golden outputs (BM2).** An engine-independent reference implementation computes expected results from the shared
source files; commit outputs and checksums. Compare canonical rows with explicit ID tie-breaks and exact counts;
the committed output schema fixes each decimal column's scale and rounding identically for numeric and Decimal128.
Never derive the oracle from either engine or compare floating-point money.

**Measurement and evidence.** Decision d controls state and statistics; application caches are off (none in Tier 1),
while database buffers are warmed by that procedure. Disable telemetry. Driver workloads use the 1/10/50-client
matrix; B3 always retains fifty total buyers, including the fifty-client race. B5 records footprint; B6 is the
separate correctness demonstration above. Failed checks remain visible and supply no accepted timing. Capture
query plans separately (`EXPLAIN (ANALYZE, BUFFERS)`, `explain("executionStats")`) and sample `docker stats` each second.
Save dated JSON-lines results/CSV summaries under `benchmarks/results/`, with errors, retries, seeds, file/golden
checksums, commit, CPU/cores, RAM, OS, Docker version, image digests, driver/library versions and Docker Desktop VM
settings. Report ratios as headlines, absolute latency as detail, plus modelling/consistency/constraint tradeoffs.

The HTTP load script is cut (amendment j). Django `execute_wrapper`
and PyMongo `CommandListener` add database time/count to existing JSON request logs and `Server-Timing`, without
another app container. CI adds correctness-only gates as workloads and isolated bench services become available.

**Questions and expected outcomes (amendment f).** Each workload tests a Mercer design decision. The expectations
below are committed before the final runs, so the git history shows they were not written after the results; a
result that contradicts one is reported as found, with its cause, never rewritten.

| ID | Question, and the decision it tests | Expected outcome and its reason | Would surprise us | Clients | Output |
|---|---|---|---|---|---|
| B1 | Where should flexible attributes live? (specifications in MongoDB, [section 3](../../PLAN.md#3-architecture-polyglot-persistence-plus-a-benchmark-harness)) | JSONB with GIN and MongoDB are close on equality filters; EAV falls behind as a filter names more attributes (one join per attribute) and on broad filters; integer ranges need an expression B-tree in JSONB | EAV close to the others: products carry only two or three attributes each | 1/10/50 | p50 and p95 by engine and parameter set (selective to broad, one to three attributes) |
| B2 | Are analytics better as SQL or as pipelines? (dashboard in PostgreSQL with a materialized view) | PostgreSQL's live CTE/window queries lead where rows are joined; MongoDB is competitive on embedded order lines and slower where it needs `$lookup`. The materialized-view read beats both live queries by orders of magnitude, at the price of `REFRESH` and staleness | MongoDB ahead on the joined queries | 1/10/50 | Live PostgreSQL against live MongoDB per query; view read and `REFRESH` reported beside them |
| B3 | Does the last-unit race need relational transactions? (checkout in PostgreSQL) | Both engines exactly correct (10, 40, 0). PostgreSQL's conditional `UPDATE` queues on one row lock with no aborts; MongoDB aborts on write conflict and retries, so retries and p95 grow with clients | Any oversell; MongoDB with fewer retries or a lower p95 at 50 clients | 1/10/50 concurrent, 50 buyers | Outcome counts, retries and p50/p95 by concurrency |
| B4 | What does each index buy, and which index fits which query? (the indexes the app ships) | Large gains on selective B1/B2 queries, little or none on broad ones; plans change from `Seq Scan`/`COLLSCAN` to index scans | An index the planner ignores, or one that makes a query slower | 1 | Before/after ratio per index with plan excerpts, told as slow → index → fast |
| B5 | What does each data model cost on disk? (normalised tables against documents) | MongoDB smallest on disk through WiredTiger compression despite repeated field names; EAV largest (a row header per attribute); JSONB between; GIN indexes large | PostgreSQL smaller in total | none | Data and index bytes per representation, beside each engine's cache size |
| B6 | Which anomalies does each engine allow, and what does preventing them cost? (`FOR UPDATE` in checkout) | PostgreSQL READ COMMITTED loses updates in read-then-write; `FOR UPDATE` prevents them by blocking; SERIALIZABLE by aborting, with retries. MongoDB read-modify-write outside a transaction also loses updates; a transaction aborts on write conflict; atomic `$inc` avoids the read | No lost update where one is expected | separate demonstration | Anomaly reproduced or prevented, retries and throughput per strategy |

B2 times four named queries, each the same SQL text the app's feature runs (`dashboard` keeps its queries importable
for this) against an equivalent pipeline: B2a category revenue per month with `RANK()` and `LAG()`; B2b 28-day
moving-average demand per product; B2c Bayesian rating per product and per seller; B2d average score by delivery-delay
bucket. Each states whether `from_order_review` copies count, matching the app feature it mirrors (B2d skips them).

**Fair comparison (amendment g).** A rigged comparison fails the rubric's "rigorous", so each rule is stated in the
report:
- **Idiomatic models.** PostgreSQL uses the app's normalised schema plus the bench-only EAV and JSONB tables. MongoDB
  uses documents designed for these access patterns, not a port of the tables: `bench.products` (id, seller, category,
  `Decimal128` price, stock, embedded attributes), `bench.orders` (one per seller order, with embedded lines and the
  paid amount) and `bench.reviews` (as the app). Both models, and why each is idiomatic, go into `docs/DATA_MODEL.md`.
- **Equal index effort.** Each query gets the index its engine's documentation recommends; B4 shows what each adds.
- **Equal durability.** Set explicitly and record: PostgreSQL `fsync`, `synchronous_commit` and `full_page_writes`
  on; MongoDB journaling on, write concern `{w: "majority", j: true}`, transactions with read concern `snapshot`.
- **Equal work in B3.** The app's migrations put the product audit trigger, and later the restock-alert trigger, on
  stock updates, and deferred money triggers on checkouts and orders; MongoDB has no equivalent. The headline B3 keeps
  every key, foreign key and `CHECK`, writes a balanced checkout, order, line and payment, and disables only USER
  triggers on the bench tables (decision f). A second B3 run with the app's triggers on is reported separately as the
  cost of trigger-enforced audit and money invariants.
- **Stated limits.** Base Olist (about 150 MB of clean files) fits in each container's memory, so warm-cache results
  measure query execution, not disk (B5's sizes beside the cache sizes show it). Every specification attribute is generated (`has_generated_content`; about
  two or three per product over 35 keys), so B1 selectivity comes from the parameter sets, not natural data. One
  laptop, under Docker Desktop. Report where each engine wins.

**Comparison beyond speed (amendment h).** Presentation part iii grades a "rigorous comparison between the SQL and
NoSQL implementations"; speed is only part iv. The report and slides carry this matrix, each cell citing evidence in
the code or a benchmark, and a verdict for Mercer:

| Criterion | PostgreSQL evidence | MongoDB evidence |
|---|---|---|
| Data modelling | 3NF schema and ER diagram (`olist-import`) | Embedded specifications with the latest five reviews; referenced review history |
| Integrity | Composite foreign keys, `CHECK`s, deferred money triggers, partial unique index (`wishlist`) | `$jsonSchema` validators, unique `order_line_id`; cross-store references checked by the app, not the database |
| Transactions and consistency | Checkout across sellers; B3, B6 | Review summary transaction (`reviews`); needs a replica set; B3, B6 |
| Schema evolution | A migration per change | Category template versions, no validator change (`catalogue`) |
| Query expressiveness | CTEs, window functions, materialized view (`dashboard`); B2 | `$facet`, `$setWindowFields`, time-series collection with TTL (`catalogue`, `activity`); B2 |
| Security | Runtime role without DDL, `SECURITY DEFINER` functions | `readWrite` on named databases only |
| Storage and indexing | B4, B5 | B4, B5 |

**Writing each result (amendment i).** Per workload: question, expectation, measured ratio with its range, cause
(from the saved plan or `docker stats`), implication for Mercer (keep or change the decision) and limits. A script
turns `benchmarks/results/` into each output's chart or table; no figure or number is typed by hand (AGENTS.md).
`deliverables` places them: B3, B6 and the matrix in presentation part iii, B1, B2, B4 and B5 in part iv, all in the
report's results and discussion.

**Exit check.** Reproduce B1–B6, the applicable client/run matrix, plans, storage metrics, resource/provenance records
and per-request database timing on the designated machine. Check database restoration after success and failure,
and generator determinism if amendment j's condition built it. Deliberately corrupt a result or violate an invariant: the run must be recorded as failed with
no accepted timing (BM4). Each workload's expectation (amendment f) was committed before its final run; the durability
settings and trigger state (amendment g) are recorded with every result; the generated charts and tables exist for
every output; the matrix (amendment h) cites evidence for every cell. No B7, failover, backup drill or other Tier 2/3
work is included.

## Decisions

Chee Long accepted these decisions on 22 October 2026; plan approved the same day.

| ID | Accepted decision |
|---|---|
| placement | Dedicated `bench` profile, services and credentials described above (BM1) |
| a | Final runs on Chee Long's Windows laptop with Docker Desktop: plugged in, high-performance power plan, other apps closed; record specs |
| b | Each engine: 2 CPUs/2 GB, PostgreSQL `shared_buffers` 512 MB, WiredTiger cache 0.75 GB. Load client in its own limited container, limits recorded. Explicit cache settings recorded; Docker Desktop VM at least 8 GB RAM/6 CPUs |
| c | Full retained Olist base, every attribute represented in EAV and JSONB; generator deferred by amendment j; scaled runs only in Tier 2 |
| d | Seeded fixed parameter sets per workload (B1 selective to broad); one untimed warm-up pass, then five measured runs with fixed operation counts per client count. Report median across runs of per-run p50, p95 and throughput, with their ranges. Count retries separately; latency runs from first attempt to success. After mutating B3/B6 runs, restore PostgreSQL from a template database and MongoDB from NDJSON or a dump, including after failures; verify initial state before every run. Warm-up must leave that initial logical state intact; rewarm restored databases. Warm-cache measurement only |
| e | Python harness in its own container, psycopg 3/PyMongo at app versions, one thread per client, `perf_counter_ns`, no-op overhead baseline (HTTP load script cut by amendment j), raw JSON-lines output and CSV summary |

**Outcome amendments (proposed 24 October 2026; approved by Chee Long, 27 October 2026).** These fill the gap between
the method, which the contract already fixes, and what the rubric grades: analysis, conclusions, implications and a
rigorous SQL-to-NoSQL comparison ([RUBRICS.md](../../RUBRICS.md) section 5, presentation part iii).

| ID | Decision | Why |
|---|---|---|
| f | Each workload states its question, the Mercer decision it tests and an expected outcome, committed before the final runs. In B3 the headline disables USER triggers on the bench tables only, keeping keys and checks, and a second run with the app's triggers is reported separately | Results become conclusions; committing expectations first shows they were not fitted to the data. The app's audit and money triggers would otherwise charge PostgreSQL for work MongoDB never does |
| g | Fairness rules: idiomatic models, equal index effort, equal durability settings recorded explicitly, stated limits | Neither default durability nor a table-shaped MongoDB model would survive a marker's question |
| h | A comparison matrix beyond speed, with evidence per cell | Part iii is required; performance (part iv) is optional |
| i | A fixed write-up per result and generated charts and tables | Methods, results, conclusions and implications stated the same way for every workload; no hand-typed numbers |

**Scope amendment j (approved by Chee Long, 27 October 2026).** Cut the Python HTTP load script; driver-level timing
is the comparison, and per-request database timing (`execute_wrapper`, `CommandListener`, `Server-Timing`) stays.
Defer the generator: B1 runs over 34,211 products with two or three attributes each, so build the generator only if
the first correctness pass shows B1 or B4 differences inside the no-op baseline's noise. The plan owner then decides
whether a 10× run for B1, B4 and B5 moves into Tier 1; until then scaled runs stay Tier 2 (decision c). Why: neither
part earns Tier 1 marks (performance analysis is optional; the comparison is required), and both cost time the
benchmark no longer has after Phase 3A.

## Review notes

22 October 2026, independent plan review (fresh Claude Code session; planning only, nothing implemented or timed).
Checked against PLAN.md sections 7, 12 to 14, AGENTS.md, the completed olist-import plan, `compose.yaml`,
`src/docker/mongo-start.sh`, `src/docker/10-roles.sh` and `src/config/middleware.py`. The B1 to B6 list, reset after
failures, client matrix, metrics, plans, `docker stats`, driver/HTTP separation, per-request timing, provenance,
build order and both deadlines match section 7. Not ready for owner approval until the blockers are fixed.

**Blockers**
- **BM1 (Isolation and data, lines 26 to 28): bench databases have no credentials or placement.** The MongoDB app user
  has `readWrite` only on the app and `test_` databases (`mongo-start.sh`, AGENTS.md rule 5), so a `bench` database
  needs a new binding exception. State it: a dedicated bench user with `readWrite` on `bench` only, the PostgreSQL
  bench database created by the owner, and which role the harness uses. Also state whether bench runs in the app's
  `db`/`mongo` containers or in dedicated containers. Limits on the shared services would also constrain the app, and
  app data would share the buffer cache. Propose dedicated limited bench containers (a Compose profile) as an owner
  decision, and update AGENTS.md rule 5 when approved.
- **BM2 (B1 to B5, lines 19 to 23): golden outputs have no independent source.** If golden rows come from one engine,
  both engines can agree on a shared bug. Replace with: "Golden outputs are computed by a reference implementation
  over the shared source files, independent of both engines, committed with checksums. Comparisons use a canonical
  order with explicit tie-breaks, fixed decimal scale (numeric versus Decimal128) and exact counts."
- **BM3 (B2, line 20): what is timed for the materialized view is undefined.** Reading a precomputed view against a
  live MongoDB pipeline is not an equivalent workload. Specify the timed operations, for example: live CTE/window
  query versus live pipeline as the headline; materialized-view read and its `REFRESH` timed and reported
  separately; MongoDB `$merge` into a collection only if presented as the equivalent precomputed variant.

**Should fix (not blocking)**
- **BM4 (exit check, lines 46 to 49):** add a negative test: a deliberately wrong result or failed invariant is
  recorded as failed and contributes no timing, as section 7 requires.
- **BM5 (B5, line 23):** name the metrics and state: for example `pg_relation_size`/`pg_indexes_size` after
  `VACUUM (ANALYZE)` and `CHECKPOINT`; `collStats` `storageSize`/`totalIndexSize` after load. Note WiredTiger compression.
- **BM6 (line 33):** "disable caches" cannot apply to database buffer caches. Say it means application caches (none
  in Tier 1) and that buffer state is controlled by the warm-up/reset procedure in decision d.
- **BM7 (B6, line 24):** say whether B6 joins the 1/10/50 timing matrix or is a correctness demonstration that
  records throughput and retry counts only.
- **BM8 (lines 29 to 31):** the app schema has no `is_generated`; generated rows load only into bench databases, which
  carry the flag. PLAN section 14 lists "scale-up runs" under Tier 2 `durability`, so Tier 1 measures the base Olist
  volume and scaled runs remain Tier 2 unless the owner decides otherwise.
- **BM9 (line 26):** state where the bench PostgreSQL schema comes from. Propose the app migrations plus bench-only
  EAV/JSONB tables, so B3/B6 run against real constraints.

**Optional**
- Provenance (line 38): also record image digests, driver/library versions and Docker Desktop VM resource settings.
- HTTP load script (line 41): name its endpoints as features land (product list, detail, search).
- Schedule risk: B2 depends on `reviews` and `dashboard` (Phase 3A, 28 to 29 October), leaving about one day before
  the 30 October correctness pass. Record it rather than assume it.

**Owner decisions to resolve:** a (machine), b (limits), c (volumes; base versus scaled), d (request mix, warm-up,
reset/cache state, latency and error accounting, how run statistics aggregate into the reported figures), e
(tooling). New, from BM1: bench credentials and container placement.


22 October 2026, fix round: BM1–BM9, provenance/schedule risk and placement/a–e decisions applied; draft retained.

22 October 2026: approved by Chee Long (plan owner) after the fresh Claude Code re-review of the fix round.

## Implementation notes (27 October 2026)

Built the isolated bench services/credentials, unchanged-migration/import loading, typed EAV/JSONB and idiomatic
documents, independent exact golden outputs, all workloads, guarded resets, raw/summary/provenance/plan evidence,
resource sampler, CSV/SVG generation, request database timing and the optional fixture CI job. Implementation
choices are [benchmark-i1–i14](../DECISIONS.md#benchmark-implementation-27-october-2026-review-pending).

The initial [fixture pass](../../benchmarks/results/2026-10-27T233711_8b3b18d4-dirty_fixture-first-pass/summary.csv)
passed all checks. The initial [full-data attempt](../../benchmarks/results/2026-10-27T234225_8b3b18d4-dirty_full-first-pass/summary.csv)
retains its cancelled unindexed rating operation and failed plan, with no accepted timings. B4 now uses the
independent single-product rating golden for that index example; B2c still checks the complete output. Windows
terminal escapes in the initial resource stream were corrected before subsequent recorded passes; those earlier
development streams are incomplete and are not measurement evidence.

[BM4 negative evidence](../../benchmarks/results/2026-10-27T235343_8b3b18d4-dirty_bm4-negative/summary.csv)
records both a corrupted result and a violated real stock invariant as failed, with null accepted timing; its
raw evidence verifies restoration. Fixture tests also exercise restores after committed writes and forced failures,
and preserve real database constraints and injection checks. The full Django run is being completed after updating
its exact request-log field assertion for the new counters. Fresh Claude Code review remains pending.

The correctness-complete full-data pass and amendment-j trial will be linked here when completed. The target
date remains unchanged. Final measurements, hosted CI duration, owner decisions about the generator and the
comparison-matrix write-up remain outstanding. The measured Docker VM memory is below the approved minimum;
local trial results cannot be final measurements. B5 reports the agreed representations separately, whose
projected fields differ (notably full MongoDB review text versus SQL rating columns); do not infer equal-payload
total-storage claims from them. The B4 compound-index case is a fixed selective example, not the full B2 rating query.
