# benchmark: Correctness-gated PostgreSQL and MongoDB comparison

status: approved
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
generator output. Build and checksum-test the seeded CSV/NDJSON generator with valid FKs/money; commit its code,
configuration and checksums, not generated datasets. Tier 1 measures retained base Olist; scaled runs remain Tier 2
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

The Python HTTP script separately measures product list/detail and search as they land. Django `execute_wrapper`
and PyMongo `CommandListener` add database time/count to existing JSON request logs and `Server-Timing`, without
another app container. CI adds correctness-only gates as workloads and isolated bench services become available.

**Exit check.** Reproduce B1–B6, the applicable client/run matrix, plans, storage metrics, resource/provenance records
and driver/HTTP distinction on the designated machine. Check generator determinism and database restoration after
success and failure. Deliberately corrupt a result or violate an invariant: the run must be recorded as failed with
no accepted timing (BM4). No B7, failover, backup drill or other Tier 2/3 work is included.

## Decisions

Chee Long accepted these decisions on 22 October 2026; plan approved the same day.

| ID | Accepted decision |
|---|---|
| placement | Dedicated `bench` profile, services and credentials described above (BM1) |
| a | Final runs on Chee Long's Windows laptop with Docker Desktop: plugged in, high-performance power plan, other apps closed; record specs |
| b | Each engine: 2 CPUs/2 GB, PostgreSQL `shared_buffers` 512 MB, WiredTiger cache 0.75 GB. Load client in its own limited container, limits recorded. Explicit cache settings recorded; Docker Desktop VM at least 8 GB RAM/6 CPUs |
| c | Full retained Olist base, every attribute represented in EAV and JSONB; generator built and checksum-tested; scaled runs only in Tier 2 |
| d | Seeded fixed parameter sets per workload (B1 selective to broad); one untimed warm-up pass, then five measured runs with fixed operation counts per client count. Report median across runs of per-run p50, p95 and throughput, with their ranges. Count retries separately; latency runs from first attempt to success. After mutating B3/B6 runs, restore PostgreSQL from a template database and MongoDB from NDJSON or a dump, including after failures; verify initial state before every run. Warm-up must leave that initial logical state intact; rewarm restored databases. Warm-cache measurement only |
| e | Python harness in its own container, psycopg 3/PyMongo at app versions, one thread per client, `perf_counter_ns`, no-op overhead baseline, Python HTTP load script, raw JSON-lines output and CSV summary |

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
