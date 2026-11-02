# benchmark: Correctness-gated PostgreSQL and MongoDB comparison

status: done
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
matrix (B2 1/10, amendment k3); B3 always retains fifty total buyers, including the fifty-client race. B5 records footprint; B6 is the
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
| B2 | Are analytics better as SQL or as pipelines? (dashboard in PostgreSQL with a materialized view) | PostgreSQL's live CTE/window queries lead where rows are joined; MongoDB is competitive on embedded order lines and slower where it needs `$lookup`. The materialized-view read beats both live queries by orders of magnitude, at the price of `REFRESH` and staleness | MongoDB ahead on the joined queries | 1/10 (amendment k3) | Live PostgreSQL against live MongoDB per query; view read and `REFRESH` reported beside them |
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
and per-request database timing (amendment k2) on the designated machine. Check database restoration after success
and failure, and generator determinism if amendment j's condition built it. Deliberately corrupt a result or violate
an invariant: the run must be recorded as failed with no accepted timing (BM4). Each workload's expectation (amendment f) was committed before its final run; the durability
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

28 October 2026: No generator and no 10x run (Chee Long, 28 October 2026). The B2b partial index selects about 40% of products inside a pipeline dominated by the per-product $lookup, so more data would not change the finding; report it in B4 as an index that buys almost nothing.

**Final-run amendment k (proposed and approved by Chee Long, 30 October 2026).** Three gaps between the exit check and what the
runner records today.

| ID | Proposal | Why |
|---|---|---|
| k1 | **Operations per client.** Final runs use `--operations-per-client 100`, except B2 and B2-derived B4 cases (k3). After the k3 runner change, a pilot on a freshly loaded project, `--mode measure --only baseline,B1,B2 --operations-per-client 100`, times the two slowest parts of the matrix: B1 at fifty clients and B2. If the projected full run does not fit one sitting on the designated machine, fall back to 50 (B2 to 10) and state the limit in the report. B3 keeps its fifty buyers either way. The values are written to provenance (`operations_per_client`) | The default of 5 makes a one-client p95 the slowest of five samples, and leaves the one-second CPU sampling with almost nothing to attribute (the final-run follow-up in the review notes). One hundred gives each one-client p95 a hundred operations per run |
| k3 | **B2 runs at 1 and 10 clients, 20 operations per client.** The runner gains a per-workload client matrix and operation count, recorded in provenance. B4 uses one client; its B2-derived cases use the B2 count and its other cases use the default count, recorded per case under an explicit B4 matrix entry. Other workload matrices stay unchanged. The report states the B2 limit and its reason | B2 is the dashboard's analytics, not a concurrent shopper path, so fifty simultaneous copies is not a load Mercer sees. The 28 October [full-data correctness run](../../benchmarks/results/2026-10-28T225445_d6fc7e44_fix-full/runs.csv) took about 1.5, 3.5, 3.6 and 10.5 s per MongoDB B2a–B2d operation at one client: at fifty clients on two CPUs, B2d is estimated past the 120 s `maxTimeMS` and `statement_timeout`, and 100 operations would take days. At 1/10 clients and 20 operations, B2 is estimated at a few hours and inside the limits; the pilot checks both |
| k2 | **Per-request timing evidence.** A small host script, standard library only, requests a fixed page list on the full-data app stack: a category page, product list, a faceted search, a product detail and, logged in as the demo operator from `.env`, the operator dashboard. One untimed warm-up pass, then twenty sequential requests per page. It joins each response's request ID to the app's JSON request line and writes a CSV per page: median and p95 of `duration_ms`, `db_pg_ms` and `db_mongo_ms`, query and command counts, and the database share of the request. Output goes to a dated `benchmarks/results/` directory with the commit and host details; it runs after the bench runs, never alongside them, with no demo password or owner credential in its output | The exit check asks for per-request database timing on the designated machine, but the runner never records it. This evidence backs section 7's claim that the database is a minor or major share of each request, which is why engines are compared at the driver level |

Out of scope: no HTTP load test (amendment j stays), no concurrency in k2 and no change to the B1–B6 queries or their
gates; k3 changes B2's client matrix and the operation count for B2 and its B4 cases.

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

28 October 2026, implementation review and fix-round re-check: Claude Code (the session that wrote the Codex brief,
not a fresh session) reviewed abc006c and re-checked 4a415603f88dc501f121b67e9b3a7bbfa5fb7e97. The review ran the full
Django suite, fixture tests, a fresh full-data load and B1–B6 correctness, Ruff, host tests and check_docs. The full
suite is also retained in the [implementation validation log](../../benchmarks/results/2026-10-28T001448_354f5c95_validation/full-suite.txt).
The owner reports that the re-check ran fresh fixture tests and fresh full-data correctness with B5, its restore
audit, BM4 and B1–B6: all normal checks passed, with only the deliberate BM4 failures. The fresh MongoDB B5 footprint
matched the fix-round run, and both restore cycles stayed within tolerance. Ruff, host tests and check_docs were
clean. The retained fix-round [fixture-test log](../../benchmarks/results/2026-10-28_d6fc7e44_fix-validation/benchmark-tests.txt),
[full-data checks](../../benchmarks/results/2026-10-28T225445_d6fc7e44_fix-full/summary.csv),
[fresh storage](../../benchmarks/results/2026-10-28T225445_d6fc7e44_fix-full/storage.csv),
[restore audit](../../benchmarks/results/2026-10-28T225445_d6fc7e44_fix-full/storage-restores.csv),
[BM4 failures](../../benchmarks/results/2026-10-28T230000_d6fc7e44_fix-bm4/summary.csv),
[Ruff](../../benchmarks/results/2026-10-28_d6fc7e44_fix-validation/ruff.txt),
[host tests](../../benchmarks/results/2026-10-28_d6fc7e44_fix-validation/host-tests.txt) and
[documentation check](../../benchmarks/results/2026-10-28_d6fc7e44_fix-validation/docs.txt) provide the linked evidence;
these are the committed fix-round artifacts, rather than new artifacts from the reviewer session.

The six fix-round items and outcomes were:

1. **B5 restoration history:** checksummed drop/recreate restores preserve validators, collection options and the
   exact index catalogue; fresh-state B5 and both physical restore cycles passed.
2. **Concurrent client timing:** primed connections and barriers, fixed operations per client, untimed first-result
   canonicalisation and later row equality passed; per-run CPU flags remain visible and exclude headline ratios.
3. **Amendment-j baseline:** SELECT 1 and MongoDB ping supply the per-engine round-trip noise; the Python no-op
   remains overhead only. The [generated evaluation](../../benchmarks/results/2026-10-28T230836_d6fc7e44_fix-trial/report/amendment-j.csv)
   puts B4_bench_product_visible inside noise; every B1 case and every other B4 case is outside it, subject to the
   recorded CPU/headline flags. The owner's decision is recorded above and in benchmark-i21.
4. **B1 broad planner choice:** the planner-chosen path remains headline; documents_hinted uses spec_attributes
   against the same golden, with both [plans retained](../../benchmarks/results/2026-10-28_d6fc7e44_fix-validation/b1-broad-plans.csv).
5. **Result hygiene:** fresh clean-head fixture/full/BM4/trial reruns are committed, dirty directories and the old
   coverage.json are removed, and the cited first pass is preserved with its superseded figures explained below.
6. **CI:** the optional benchmark job has the MongoDB kernel guard, a fresh fixture reload before B5, and uploads
   only its current printed run directory plus its duration; hosted outcomes belong to the PR checks.

**Final-run follow-up:** CPU is sampled once a second, so windows lasting only a few milliseconds get coarse
client_saturated flags. Use a larger --operations-per-client for the designated-machine final measurements so every
timed window spans several samples, and record the selected value in provenance. Status remains in-progress;
the designated-machine final measurements remain with the owner.

31 October 2026, Codex: implemented amendment k3 (B2 1/10 clients with its own operation count and provenance) and
k2 (standard-library request/log timing collector, host tests and fixture rehearsal), plus the README final-run
checklist. Host tests, freshly loaded fixture bench tests, the B2-only fixture measurement and the fixture app
request-timing rehearsal passed; fixture evidence stays ignored and unstaged. The pilot and designated-machine
final runs remain with Chee Long; benchmark stays in progress in PLAN.md section 14.

31 October 2026, Claude Code (the session that wrote the brief; not a fresh session): reviewed both preparation
worktrees and approved the reuse-decision documentation. The reviewer ran Ruff format/check in the dev image,
check_docs, host tests and freshly loaded fixture benchmark tests; all passed. Codex's fix round gives B2-derived
B4 cases the B2 count and records B4's one-client matrix and per-case counts, clarifies automatic report generation,
repairs README wording and records the reviewer accurately. Chee Long chose a category page instead of the home
redirect for k2 on 31 October; the plan, collector, tests and checklist now use it. Codex reran Ruff format/check
in the dev image, the affected B2/B4 fixture integration cases in both modes, the timing host tests and the fixture
category collector; all passed. Documentation checks passed in both worktrees, fixture projects were torn down,
and all changes remain uncommitted.

31 October 2026, Claude Code (the session that wrote the brief; not a fresh session): re-checked the fix round and
approved both preparation worktrees. The reviewer reported that documentation checks, host tests, Ruff format/check
and the affected fixture benchmark tests passed. Chee Long authorised committing, pushing and opening the two PRs;
the pilot and full-data runs remain for the next session.

31 October 2026, owner-requested CI follow-up (Codex): [PR #33's Django job](https://github.com/ZadeNova/INF2003_Database_Project/actions/runs/41170847257/job/124448283477) stopped at collection because the app image has no benchmarks package; the timing test module now uses pytest.importorskip and qualified helper calls so it skips in that image while the host job still requires its tests to run without skips.

### Designated-machine final and close-out (2 November 2026)

Chee Long directed the final run and this close-out on the designated Windows PC. All six retained directories
identify the clean measurement commit `b53e5d0`; the BM4 controls were captured before any close-out source edit.
The [owner decisions](../DECISIONS.md#benchmark-designated-machine-final-and-close-out-2-november-2026) record the
trimmed pilot, count choice, source rule and unexpected resource observation.

The [pilot provenance](../../benchmarks/results/2026-11-01T220402_b53e5d0a_pilot/provenance.json) records B2 at five
operations per client while the default remained one hundred. The owner trimmed only the pilot to obtain a timely
projection; it supplies no final headline. The [script-generated count decision](../../benchmarks/results/2026-11-01T220402_b53e5d0a_pilot/count-decision.json)
uses every B1/B2 warm-up and measured window and the owner's multiplier/remaining-work allowances. It selects
100/default and 20/B2 because that projection fits the target; the final provenance records those counts.

The [full final](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/host.json) exited unsuccessfully after an
**unexpected** MongoDB out-of-memory kill. Its [failure capture](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/failure.json),
[Docker state](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/failure-docker-state.txt) and
[failed summary rows](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/summary.csv) remain visible. The owner
used the single infrastructure retry for a fresh full-data load and a separate
[final B3/B6 run](../../benchmarks/results/2026-11-02T095518_b53e5d0a_final-b3-b6/provenance.json), at the same commit,
machine and limits. **Use B3 and B6 entirely from final-b3-b6; use every other final comparison output from final.**
Keep all original B3/B6 records, including failures, as history rather than combining them into the final sample.
The generated [source-selection table](../../benchmarks/results/2026-11-02T110623_b53e5d0a_final-bm4/final-source-selection.csv)
identifies the source directory for each selected cell and checks that none includes a failed run.

The interrupted raw file is now `raw.jsonl.gz`. Its [compression manifest](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/raw-compression.json)
records the original size/hash, method, date and reason, and verifies the decompressed payload against the original
before removal of the uncompressed file. Provenance was not edited. Close-out skips nonnumeric stopped-container
CPU samples, reannotates the failed run and regenerates its report. The other driver reports were regenerated with
the same memory-table generator; [generation metadata](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/report/generation.json)
records the post-processing code hashes and unchanged measurement fields/provenance. The generated
[full-run memory table](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/report/memory.csv) and
[fresh B3/B6 memory table](../../benchmarks/results/2026-11-02T095518_b53e5d0a_final-b3-b6/report/memory.csv) replace
the exploratory cache-only memory section as the citable figures. The observation and its limitations are in the
owner decision; it was not a controlled memory test.

Exit-check evidence, item by item:

| Exit-check item | Retained evidence |
|---|---|
| Independent golden outputs and B1/B2 equivalence | [Full correctness checks](../../benchmarks/results/2026-11-02T002948_b53e5d0a_final-correctness/report/checks.csv), [final checks](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/report/checks.csv) and [source/golden hashes](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/provenance.json) |
| Applicable client/run matrix and operation counts | [Final runs](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/runs.csv), [final workload matrix](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/provenance.json), and [authoritative B3/B6 runs](../../benchmarks/results/2026-11-02T095518_b53e5d0a_final-b3-b6/runs.csv) |
| B3 outcomes and separate B6 demonstrations | [Fresh B3 outcomes/restoration](../../benchmarks/results/2026-11-02T095518_b53e5d0a_final-b3-b6/report/B3-states.csv) and [B6 expected/observed states](../../benchmarks/results/2026-11-02T095518_b53e5d0a_final-b3-b6/report/B6-states.csv) |
| Plans and storage metrics | [Final query plans](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/plans), [B4 ratios/ranges](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/report/ratios.csv), and [fresh B5 footprint](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/report/B5.csv); the contract's representation limits still apply |
| Hardware, limits, durability, trigger policy and resources | [Original host](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/host.json), [original settings](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/provenance.json), [fresh-run host](../../benchmarks/results/2026-11-02T095518_b53e5d0a_final-b3-b6/host.json), and [generated settings/input footprint](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/report/memory-settings.csv) |
| Restoration after success and deliberate failure | [B3/B6 check records](../../benchmarks/results/2026-11-02T095518_b53e5d0a_final-b3-b6/report/checks.csv) and [BM4 restoration evidence](../../benchmarks/results/2026-11-02T110623_b53e5d0a_final-bm4/bm4-verification.json); OOM recovery used a full reload, recorded by the fresh run's initial state/provenance |
| BM4 rejects incorrect results and violated invariants | [Both expected failed rows](../../benchmarks/results/2026-11-02T110623_b53e5d0a_final-bm4/summary.csv), [raw/no-accepted-timing verification](../../benchmarks/results/2026-11-02T110623_b53e5d0a_final-bm4/bm4-verification.json) and [run provenance](../../benchmarks/results/2026-11-02T110623_b53e5d0a_final-bm4/provenance.json); the nonzero exit is expected for these controls |
| Per-request database timing, collected after benchmarks stopped | [Joined requests](../../benchmarks/results/2026-11-02T103305_b53e5d0a_request-timing/requests.csv), [per-page aggregates](../../benchmarks/results/2026-11-02T103305_b53e5d0a_request-timing) and [collector provenance](../../benchmarks/results/2026-11-02T103305_b53e5d0a_request-timing/provenance.json) |
| Precommitted expectations, fairness and evidence per matrix criterion | Amendment f above remains unchanged; [final matrix evidence](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/report/matrix-evidence.csv), provenance and the authoritative B3/B6 state files support amendments g/h |
| Generated charts/tables and visible limitations | [Final report](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/report), [B3/B6 report](../../benchmarks/results/2026-11-02T095518_b53e5d0a_final-b3-b6/report), [BM4 report](../../benchmarks/results/2026-11-02T110623_b53e5d0a_final-bm4/report) and [CPU/noise verdicts](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/report/amendment-j.csv); saturation flags remain visible and excluded from headlines |
| Generator condition and tier boundary | Amendment j's owner decision remains no generator/no scaled run, so generator determinism is not applicable. No B7, failover, backup drill or other Tier 2/3 work was added |
| Close-out code/documentation checks | [Generated validation record](../../benchmarks/results/2026-11-02T110623_b53e5d0a_final-bm4/closeout-validation.json) records real Ruff, host, fresh-fixture and full-Docker-suite results |

The validation record retains the initial host-test failure from temporary repositories placed inside the ignored
checkout and the passing invocation using an external temporary directory. It also retains an initial failure of
the existing MongoDB storage-repeatability assertion and the passing fixture suite after a full reload, with code
and tolerance unchanged. The underlying physical-storage variability remains visible for review.

Codex prepared this close-out uncommitted on `benchmark/close-out`. Claude Code reviewed it before commit, in the
session that wrote the brief (not a fresh one). The review read the code and documentation diff; scanned every staged
file for `.env` secret values (none); confirmed that no staged file exceeds 50 MB, that the final-source selection
takes B3 and B6 only from final-b3-b6 with no failed cell, and that both BM4 rows record failed with no accepted
timing; regenerated the final and final-b3-b6 reports from copies, byte-identical to the staged files; and reran the
host, packaging, request-timing and reporting tests with no skips. It found no defect. The only fix was this wording:
the documentation had still said that the review was pending. Ruff and the Docker suites were not rerun here; the
cited validation record and CI cover them.

## Implementation notes (27–28 October 2026)

The isolated services, checksummed loader and independent golden outputs, B1–B6, request timing and generated
CSV/SVG evidence are implemented. Decisions are in [benchmark-i1–i21](../DECISIONS.md#benchmark-implementation-27-october-2026-review-pending).

**28 October 2026: the first correctness-complete full-data pass landed before the 30 October target.**
The [cited first pass](../../benchmarks/results/2026-10-28T000105_e23a4df4_full-correctness/summary.csv) remains the
historical correctness record. Its B5 MongoDB figures are superseded: delete/reinsert restoration retained
WiredTiger free space, so they depended on restoration history. The [old trial](../../benchmarks/results/2026-10-28T001329_354f5c95_trial/summary.csv)
is superseded for timing/noise analysis: connection preparation and repeated canonicalisation overlapped other
clients' timed operations, and a Python no-op measured harness overhead rather than database round-trip noise.
Retained directories containing -dirty and the old validation coverage.json were removed; Git history preserves them.

### Authorised fix round (28 October 2026)

Claude Code (the session that wrote the Codex brief, not a fresh session) reviewed abc006c by running the full Django suite, migration drift, fixture and
fresh full-data correctness including BM4, Ruff, host tests and documentation checks. Correctness gates, independent
golden outputs, logical restores and PostgreSQL B4 plans passed. The requested fixes concern storage state, client
measurement, the amendment-j baseline, a hinted broad-query comparison, result hygiene and CI artifacts/kernel guard.

MongoDB restoration now drops/recreates each mutated collection with its checksummed validator and ordered index
catalogue, inserts documents before bulk-building secondary indexes and verifies digest/options/index equality.
Persistent restore state prevents B5 from measuring after any restore. B5 executes before mutations; physical probes
wait for an automatic checkpoint after a load/restore. Two-cycle storage checks use the stated allocation tolerance.

Every client connects and pings before a readiness barrier. Each first result is canonicalised against golden before
a shared timing barrier; later fetched rows are checked by equality. Counts are fixed per client, with B3's original
buyer count retained. The Python no-op remains an overhead baseline; SELECT 1 and MongoDB ping supply the engine
round-trip noise baselines. Per-run CPU attribution and client_saturated flags keep constrained client results visible
without headline ratios. B1 broad keeps its planner choice; documents_hinted separately shows spec_attributes.

The requested reruns used clean commit d6fc7e44 in separate freshly loaded projects:

- [Full-data correctness](../../benchmarks/results/2026-10-28T225445_d6fc7e44_fix-full/summary.csv), including the
  [fresh footprint](../../benchmarks/results/2026-10-28T225445_d6fc7e44_fix-full/storage.csv) and
  [two-restore physical audit](../../benchmarks/results/2026-10-28T225445_d6fc7e44_fix-full/storage-restores.csv).
- [Fixture correctness](../../benchmarks/results/2026-10-28T225800_d6fc7e44_fix-fixture/summary.csv).
- [BM4](../../benchmarks/results/2026-10-28T230000_d6fc7e44_fix-bm4/summary.csv): both deliberate failures were retained
  with no accepted timing.
- [Trial](../../benchmarks/results/2026-10-28T230836_d6fc7e44_fix-trial/summary.csv), with no prior mutating run;
  [amendment-j evaluation](../../benchmarks/results/2026-10-28T230836_d6fc7e44_fix-trial/report/amendment-j.csv)
  identifies the engine round-trip baseline, gap, threshold and noise/headline flags for each comparison.

All requested workload variants passed their correctness gates; use the generated
[variant status](../../benchmarks/results/2026-10-28_d6fc7e44_fix-validation/variant-status.csv) and
[run index](../../benchmarks/results/2026-10-28_d6fc7e44_fix-validation/run-index.csv) for the complete record.
The product-visible B4 comparison falls inside the trial's noise threshold. Read every amendment-j verdict alongside
its headline flag: the [saturated summary rows](../../benchmarks/results/2026-10-28_d6fc7e44_fix-validation/client-saturated.csv)
remain visible, with [individual run CPU evidence](../../benchmarks/results/2026-10-28_d6fc7e44_fix-validation/client-saturated-runs.csv).
One-second sampling gives coarse attribution for short windows, including neighbouring preparation work; saturation
in any accepted run excludes the summary row from headline ratios. The owner's amendment-j decision above closes
the generator and 10x-run question.
The [broad-query plan comparison](../../benchmarks/results/2026-10-28_d6fc7e44_fix-validation/b1-broad-plans.csv)
records the full-data planner's _id_ scan and the hinted spec_attributes scan separately, against identical golden rows.
The [generated handoff](../../benchmarks/results/2026-10-28_d6fc7e44_fix-validation/handoff.txt) includes exact affected-test
results, fresh storage, per-variant status and the retained limitations. Raw evidence checksums, operation counts,
barriers and correctness/timing gates were [audited](../../benchmarks/results/2026-10-28_d6fc7e44_fix-validation/evidence-checks.txt).
The CI job now checks the kernel, reloads after mutating tests and uploads only the current printed run directory.
The 28 October PLAN.md date line and original target dates stay unchanged. Claude Code re-checked the fix round as
recorded above; hosted outcomes belong to the PR checks. At that checkpoint the designated-machine final measurements
were still pending; their completed evidence is recorded in the close-out above. No generator, scaled run,
HTTP load script, Tier 2/3 work or CI formatter stage is included. Machine memory remains the owner's setting.
B5 reports the agreed representations separately: MongoDB reviews include text while SQL bench reviews contain
the analytical columns. These are not equal-payload total-storage claims.

30 October 2026, pull request review of amendment k (Claude Code, fresh session): k1's pilot covered only baseline and
B1, while the committed full-data run shows MongoDB B2 about ten times slower per operation at one client, so the
pilot could not project the matrix. Chee Long chose B2 at 1/10 clients with 20 operations per client (k3); the pilot
now includes B2 and runs after the k3 runner change.
