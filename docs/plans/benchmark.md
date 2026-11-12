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
bucket. Each states whether `from_order_review` copies count, matching the app feature it mirrors (since 9 November B2d counts them, as the dashboard does).

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
| a | Final runs on Chee Long's Windows laptop with Docker Desktop: plugged in, high-performance power plan, other apps closed; record specs (the fresh run uses Erfan's desktop: amendment l1) |
| b | Each engine: 2 CPUs/2 GB, PostgreSQL `shared_buffers` 512 MB, WiredTiger cache 0.75 GB. Load client in its own limited container, limits recorded. Explicit cache settings recorded; Docker Desktop VM at least 8 GB RAM/6 CPUs |
| c | Full retained Olist base, every attribute represented in EAV and JSONB; generator deferred by amendment j; scaled runs only in Tier 2 |
| d | Seeded fixed parameter sets per workload (B1 selective to broad); one untimed warm-up pass, then five measured runs with fixed operation counts per client count. Report median across runs of per-run p50, p95 and throughput, with their ranges. Count retries separately; latency runs from first attempt to success. After mutating B3/B6 runs, restore PostgreSQL from a template database and MongoDB from NDJSON or a dump, including after failures; verify initial state before every run. Warm-up must leave that initial logical state intact; rewarm restored databases. Warm-cache measurement only |
| e | Python harness in its own container, psycopg 3/PyMongo at app versions, one thread per client, `perf_counter_ns`, no-op overhead baseline (HTTP load script cut by amendment j), raw JSON-lines output and CSV summary |

Decision b and amendment l1 retain the planned settings as history; the owner-authorised
[11 November actual limits](#authoritative-november-evidence-for-report-and-slides) supersede their engine/VM/power
settings for the report. The index links the separate driver and application-stack configurations for each experiment.

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

**Fresh-run amendment l (proposed by Claude and approved by Erfan, 8 November 2026).** The project owner is now Erfan, the
data and the application changed after the 2 November run (regenerated names, new B2 variants, Redis, full-text search), and
the earlier run was made on another machine. The whole benchmark is therefore repeated on one clean commit, after the last
code batch, so no code change can follow it. Amendments a to k stay in force except where a row below says otherwise.

| ID | Decision | Why |
|---|---|---|
| l1 | **Machine.** The final-run machine replaces decision a's laptop. From 11 November it is Chee Long's machine (the plan was Erfan's desktop, Ryzen 7 5700X3D, 32 GB); record its specifications in the provenance, and the `--final` gate (six CPUs, 8 GiB usable) applies. The Docker VM gets 12 CPUs, 24 GB and swap off; the power plan is high performance, sleep and Windows Update are off, other heavy applications are closed, and Docker's data sits on an SSD. The container limits of decision b are unchanged (2 CPUs and 2 GB per engine and for the runner), except as l8 allows. The VM settings and the storage type go in the provenance | Spare VM resources reduce host noise and client saturation without changing what each engine is given; the large cache of this processor is stated as a difference from the laptop |
| l2 | **One clean commit, after Batch 8.** Every session runs with `--require-clean` on the same commit, and no code changes between the first session and the last | A result then describes the code that is submitted |
| l3 | **Three sessions, 50 and 10 operations per client** (B2 and its B2-derived B4 cases at 10, the rest at 50), the pilot confirming that this fits. Each session keeps the five measured runs of decision d. The headline is the median across sessions of the run-level medians; every session is kept, a session with a failure is reported and excluded from the headline with its number stated, and no session is chosen for being the best. The rule is fixed before the first session | Independent sessions say more about reproducibility than one longer run, and a rule fixed in advance cannot be tuned to the data |
| l4 | **Pooled tail percentiles.** From the raw latencies of all accepted runs and sessions, p95 is shown only with at least 100 pooled samples and p99 only with at least 500; below that the table shows the median, range and maximum, labelled "not enough data". The per-run p50 and p95 of decision d stay | With 100 operations in a run, p99 is the single slowest operation |
| l5 | **Drift controls.** The three baselines (Python no-op, `SELECT 1`, MongoDB ping) run at the start and end of every session, and a session whose end differs from its start by more than the baseline noise band is flagged. Engine order is alternated across the five measured runs if the harness change is trivial; if it is not, this is not done and the report says so | The same machine still drifts over hours (heat, background tasks, buffers); the check shows whether it did, and alternation spreads any drift across both engines |
| l6 | **Pinning pilot.** The pilot compares the baselines with and without each container pinned to its own virtual CPUs (Compose `cpuset`); the pinning is adopted for the sessions only if the spread of the baselines falls, and the choice is recorded | Under WSL2 the virtual CPUs map to host threads in a way we do not control, so the benefit is tested, not assumed |
| l7 | **Old results.** After the first fresh session is committed: tag the current commit, move the 2 November run directories into `benchmarks/results/archive/`, repair every link to them (`check_docs.py` finds breaks) and mark the 2 November close-out superseded. The archived B1, B4 and B5 ratios are compared with the fresh ones in an appendix, labelled as another machine and another build of the data | Cross-machine agreement is evidence the ratios are not a quirk of one computer; only unchanged workloads are comparable |
| l8 | **New workloads and parts.** B2 idiomatic and maintained-summary variants (#5, beside the originals), the B1 hinted run (#13) and B7 full-text search (#71, if it goes ahead) join the matrix with their own golden checks. The per-request collector (#17) and the Redis experiment (the [redis plan](redis.md)) run after the benchmark engines are stopped, never alongside. The 2 November run lost its MongoDB container to its memory limit (exit code 137): the pilot runs B2 first, and if a container is killed the memory limit is raised equally for both engines, recorded and applied to every session | A killed container wastes hours; an equal rise keeps the comparison fair |

**B2 variants and the headline rule, amendment m (Erfan, 9 November 2026; reviewed and corrected 9 and 10 November; fixed before any fresh run).** Item #5 of the
[backlog](improvements.md): B2's MongoDB pipelines were written to mirror the SQL, which a MongoDB specialist would not
write, and only PostgreSQL had a maintained summary. B2 therefore gains idiomatic and maintained-summary variants for
both engines beside the originals. [headline.py](../../benchmarks/headline.py) holds the same pairs as data and
provenance records them.

| ID | Decision | Why |
|---|---|---|
| m1 | **Variant names.** `live` and `view` are B2 as first implemented, and `app` and `app_summary` are the application's own B2b query (the plain 28-day `GROUP BY` that also resolves names and sorts for display): all four are kept, reported in their own table (`B2*-originals.csv`, no ratio) and never a headline. `idiomatic` is an engine's idiomatic computation from the source data and `summary` is its maintained summary; **both engines' `idiomatic` and `summary` variants return the golden columns and nothing else** (no display joins, no extra columns), in the golden key order | The originals show what the first implementation measured; the headline shows what each engine does when written well, and asks both the same question |
| m2 | **Headline pairs** (PostgreSQL against MongoDB): B2a live `idiomatic` against `idiomatic`, maintained `summary` against `summary`; B2b live `idiomatic` against `idiomatic`, maintained `summary` against `summary`; B2c live `live` against `idiomatic` (PostgreSQL's B2c query already returns only the golden columns); B2d live `idiomatic` against `idiomatic`, maintained `summary` against `summary`. The report prints every registered pair in `b2-headline.csv` with the ratio, a status (a pair whose row failed or is missing is listed, never dropped) and whether both rows are headline rows, and the cross-session table also requires both engines' medians to come from the same number of sessions | The rule is fixed before the data exists, so no variant is chosen for flattering a result |
| m3 | **B2c has no maintained summary on either engine**, so it has only the live pair. The two refresh costs are paired by summary: daily product sales (`refresh` on both engines) and delivery scores (`refresh_scores` on both). Both engines' `refresh_scores` recompute the delay buckets and score totals from the order and review data alone (PostgreSQL's bench view reads `orders_order` and `reviews`, not the application's richer delivery view, which resolves checkout, seller and customer rows and a distance per order and would charge it display work MongoDB never does); a test changes one delivery and requires both summaries to move, and another that the bench view does not read the application's view. Every refresh is also measured with no change to the data (PostgreSQL's concurrent refresh writes nothing when nothing differs, MongoDB's `$out` rewrites everything), which the threats to validity below state | The application maintains no rating summary of this shape in either store, and a summary's read speed is bought with its refresh cost, so both are reported together |
| m4 | **B2d is aligned with the application** (copied reviews count, as since backlog item #52): its three definitions and the two partial indexes changed, the golden outputs were regenerated, and on the full data the dashboard's buckets equal the golden output exactly | A benchmark that asks a different question from the dashboard cannot be quoted beside it |
| m5 | **Summaries.** PostgreSQL: the application's `daily_product_sales` view and a bench-only `bench_order_delivery_scores` view (delivery bucket and visible-review totals per delivered order, from the order table and the bench review copy alone). MongoDB: `daily_product_sales` and `order_delivery_scores` collections, built when the project is loaded and rebuilt with `$out`. All four count in B5's storage table | Each engine gets its own idiom for the same maintained result, at the same cut-off |
| m6 | **Idiom and its provenance.** The idiomatic pipelines group first and merge by primary key with `$unionWith` and `$group` (no per-document `$lookup`), and use integer sums with one division. They were developed with timing feedback on the full data in two iterations: the first versions of B2b, B2c and B2d still used a per-document lookup and were replaced once a preview timing showed it. Every version was checked against the golden output before it was timed, no index was added for any variant beyond the summaries. The PostgreSQL `idiomatic` and `summary` queries were added after the independent review (m8), written from the meaning of each question and checked against the golden output; they were written **after** rough preview timings of the originals had been seen, they were not changed after any timing, and the application's own queries are kept apart as originals. B2c is unchanged, because PostgreSQL's query already returned only the golden columns | The history is stated in the report, so the comparison is not read as MongoDB tuned until it won |
| m7 | **Whether the originals stay in every session** is decided after the pilot (Erfan, 9 November): they dominate the measured time, and if they are dropped from the later sessions the report says so | The pilot measures what fits in a night |
| m8 | **Changes after the independent reviews (9 and 10 November, before any fresh run).** The review found that the app's display queries gave PostgreSQL extra work the golden columns never check, so PostgreSQL gained `idiomatic` and `summary` variants for B2a, B2b and B2d that return the golden columns only (the headline pairs of m2 changed accordingly; the old pairs' queries are the originals). It also found that PostgreSQL's delivery-score refresh did not pay for recomputing the delivery side; a first fix refreshed the application's whole delivery view, which a second review showed overcharges PostgreSQL with display work, so the bench view is now built from the order and review tables alone (m3 describes the result and its tests). The per-output tables and charts mixed the originals into the comparison and are now split. The rule that both engines return the golden columns in the golden key order, and nothing else, is the symmetry the headline claims | Fixing a fairness flaw while no data exists is pre-registration; doing it afterwards would be post hoc |

**Tooling status for amendment l (9 November 2026).** l3: [sessions.py](../../benchmarks/sessions.py) applies the rule
(median across usable sessions of the run-level medians; every session kept; a session with a failed check, a nonzero
exit or a container event is excluded with its reason; sessions from different commits are reported). l4:
[pooling.py](../../benchmarks/pooling.py) pools the raw latencies and gates p95 at 100 and p99 at 500 samples; each
report has `pooled.csv`. l5: the three baselines run again at the end of every session and `drift.csv` flags a shift
beyond the noise band; engine-order alternation is **not done**, because it would interleave the five measured runs
across variants and rewrite the harness's run loop, so the report states that the same machine's drift is controlled by
the start and end baselines only. l6: [compose.pinned.yaml](../../benchmarks/compose.pinned.yaml) and `--pin` let the
pilot compare, and every result records the actual cpuset of each container. l8: the runner records each container's
state before and after and fails on an out-of-memory kill, a restart or a stop. l1: repeatable `--note KEY=VALUE`
options record the machine facts that no program can read (power plan, sleep and update settings, storage type).

Threats to validity, to be written in the report: B2's design differences that are not schema (the MongoDB daily summary stores `category_id` and the order line carries one, where PostgreSQL's views have none and join the product; MongoDB reads a precomputed `purchasable` flag through a partial index where PostgreSQL derives it through a seller join); a refresh with no change to the data (PostgreSQL's concurrent refresh writes nothing when nothing differs, MongoDB's `$out` rewrites everything); MongoDB's planner reading almost every document through an index in B2c and B2d, inspected in the pilot and not hinted after a timing; engine order not alternated; one machine under Docker on Windows; warm database buffers only; closed-loop
clients, so some queueing delay is hidden; the Olist volume fits in memory (B5's sizes show it); every attribute is generated; a
single-node replica set; a processor with a large cache; no second machine for the load generator (the clients run in a capped
container, are checked for saturation and are bracketed by the baselines).

**Collector source selection correction (11 November 2026, owner-authorised defect repair).** This scoped repair
follows the completed Phase 3B contract during Phase 5; application code and B1–B6 stay frozen. `seed_demo` now calls
`seed_showcase`, so the first product link can belong to a showcase product absent from the supplied Olist specifications.
Both HTTP collectors share `pages_for_product`: choose the first visible product with non-empty source attributes in
page order, rather than the first product link or first row in the source file. Derive its detail, category and facet
from that one specification. Refuse selection when no visible product qualifies, and keep source-category validation.
The selected paths remain in each collector's provenance. Existing evidence is preserved; this repair authorises
targeted regression tests and an untimed page-selection rehearsal, with final collection left to a separate run.

### Redis burn-in correction (11 November 2026)

Owner-authorised defect repair in the existing Phase 5 collector contract. Trending counts distinct visitors, so repeatedly
viewing the control with one anonymous cookie jar cannot overtake a seeded leader. Give each untimed control-product view
a fresh anonymous opener. Keep the ranking probe's session, cache clearing, leading-control requirement and stable-ranking
check, the existing pass size/limit, and all measured traffic and sample counts. Record the visitor policy in provenance.
Application counting and seeded data stay unchanged. This repairs the remaining Redis condition collector only; existing
B1–B6, page timing, stampede and limiter evidence remains valid. The scoped validation is host orchestration/gate tests,
real-database visitor/ranking tests and an untimed fresh-default-seeded burn-in rehearsal. Fresh Claude Code Opus review is
required before commit; the complete final Redis experiment remains a separate post-review collection.

### Redis acceptance repair (11 November 2026)

Owner-authorised collector repair in Phase 5 after the completed Redis condition run retained acceptance gaps. The
dashboard digest removed its conditional cache paragraph but retained a newline and indentation emitted inside the same
conditional. Remove that specific trailing fragment before the closing `div`; retain all other whitespace, business
values, links and rows. Digest version 2 is recorded in provenance. Existing samples and their stored digests are never
rewritten or reinterpreted, and the same-round off-reference and cache-status gates remain binding.

The separate shop/search link changes and warm miss are not explained by the retained historical evidence. Trending
uses a rolling window and its cache expires, but those mechanisms alone do not prove the causes of the old refusals.
Do not freeze the clock, edit seed events, change cache lifetimes or add measured-request priming to force acceptance.
Future legitimate refusals remain possible. Add diagnostic schema 1: public numeric product-ID strings in their exact
hashed order, catalogued once per page/digest; UTC receipt time and monotonic condition elapsed time; and the existing
untimed priming responses joined to their request logs. Missing or duplicate priming logs now stop the whole run, with no samples written. Priming stays outside measured samples and gates; HTTP timing boundaries and traffic counts are unchanged.
No HTML, credentials, cookies, CSRF tokens or visitor identities are retained.

Validation covers the real template conditional, rejected business-data mutations, exact diagnostic hash correspondence,
priming-log failures, neighbouring host checks and a separate small-fixture real-stack rehearsal. No B1–B6, page timing,
stampede, limiter or final Redis measurements are authorised by this repair. Fresh Claude Code Opus review is required
before commit; final collection remains separate, on one reviewed clean revision with the default full-data protocol.

## Review notes

12 November 2026 — Codex applied the fresh Opus re-review's two wording requests without changing measurements.
The reviewer independently verified preservation, manifests, inventory and byte-identical offline regeneration,
and reported passing documentation/diff checks and host tests. The verdict was CHANGES REQUIRED, with approval
conditional on these two fixes; no subsequent reviewer approval or repository delivery is claimed.

12 November 2026 — Fresh Claude Code Opus follow-up verdict: **APPROVE CORRECTIONS**. Both wording
fixes, preservation, normal/staged docs and diff checks, and the staged manifest passed independent review.
Measurement is complete and the documentation is ready for report and slide preparation. The owner authorised
relocating this note, committing the approved evidence, integrating latest main and opening a consolidated PR;
merge is not authorised. Repository close-out still requires successful PR checks and merge.

11 November 2026, consolidated evidence review (fresh Claude Code Opus session; supplied review of HEAD `b82ac876`
and the staged evidence). Verdict: **CHANGES REQUIRED, documentation only**. The reviewer confirmed that measurement
is complete under the existing protocol, with legitimate refusals/reduced paired coverage and no required rerun.
The supplied review reports offline normal/staged documentation and diff checks, host checks without skips, staged
hash verification, byte-identical Redis report/derived-record regeneration and cross-session table regeneration in
scratch. Those are the reviewer's checks, distinct from the original collection logs and this correction round.

The six requested corrections cover expectation-versus-finding/cause statements for B1–B6, historical supersession,
actual per-experiment limits, page-collector data-state attribution, the daily-sales refresh tie, and evidence paths
plus the thin outage-cell caveat. Codex (GPT-6.1 Sol Max) applied them in one documentation/index correction round;
fresh Opus re-review verified all six corrections and requested two wording fixes, now applied: explicitly
state that the orders-of-magnitude expectation was not met and qualify the unseeded trending state. Raw measurements and historical validation records
are unchanged. This review does not approve commit, push, PR or merge, and repository close-out is not complete.

Correction-round offline validation regenerated the cross-session tables and ran the unchanged Redis validator in a
scratch copy: derived records and Redis reports reproduced byte-identically. Source checks confirmed the refresh
range overlap, actual limits, corrected B5/B6 targets, first accepted outage requests and live-path reordering.
Normal/staged documentation and diff checks and staged-blob manifest verification are the delivery checks for these
documentation/index edits; this round runs no databases or services. Fresh Opus correction verification is complete; see the approval above.

11 November 2026, Redis acceptance repair (Codex implementation; fresh Claude Code Opus review passed).
The real-template HIT and WAIT cases reproduced the old conditional-whitespace defect before implementation.
Host collector rules and neighbours, documentation checks, Ruff formatting/lint and the real activity, dashboard and
Redis-store modules pass. A diagnostic-only small-fixture rehearsal exercised one round of off, cold, warm and down;
all its measured responses passed the unchanged gates, including full dashboard equality. The exact ordered public
link signatures reproduce their hashes; untimed priming responses remain outside the measured samples. Regression
coverage rejects changed values, links, rows and inline gaps, and missing/duplicate priming logs.
The independent reviewer reran host and real-database neighbour tests, documentation checks, lint and formatting,
performed mutation checks, and verified real-template OFF/HIT/WAIT equality with LF and CRLF line endings. Historical
report compatibility and diagnostic privacy/hash correspondence were checked. The minor finding was corrected: a
priming-log failure stops the whole experiment before samples are written. No blocking findings remained. The final
Redis run and its comparison coverage remain unvalidated; genuine shop/search drift or cache misses may still be refused.
The normal fixture CLI attempt refused page selection before any condition: the visible showcase products had no
matching source specification. That failed attempt is preserved. The bounded rehearsal discovered public fixture page
paths and called `measure()` directly; it does not validate full CLI orchestration, default source selection, seeded
rolling-window stability or full-data acceptance. Neither fixture data nor the selector was changed. No final measurement
was rerun. Historical refusals remain unchanged, and fresh Claude Code Opus review is still required before commit.

11 November 2026, Redis burn-in correction (Codex implementation; fresh Claude Code Opus review passed).
The host regression checks separate anonymous cookie jars for the control views, the retained ranking session, cache
clears and helper cleanup. Real PostgreSQL/MongoDB/Redis tests verify that one anonymous visitor's reloads count once and
distinct anonymous visitors can overtake a generated leader. The collector still requires the control to lead and the
ranking to hold still before any measured condition begins. An isolated fresh full-data import with default seeding passed
the actual burn-in; database snapshots verified the control's leadership, distinct visitors and unchanged generated events.
The host regression also rejected the previous single-visitor behaviour. No final experiment or other valid workload is
rerun here.
The independent reviewer reran host and documentation tests, lint and formatting, and performed additional mutation
checks. A separate fresh full-data/default-seeded rehearsal reproduced successful settling and verified source hashes,
control leadership, distinct visitors and unchanged generated events. No actionable findings remained. Removing the
unchanged leader callback survived the new host regression; the reviewer disclosed this coverage limitation, while the
live rehearsal verified leadership directly. The complete final Redis condition experiment still awaits its own run.

11 November 2026, collector source selection correction (Codex implementation; fresh Claude Code Opus review passed).
Host request-timing, Redis experiment and neighbouring benchmark-tooling checks pass. Regression cases cover an absent
showcase ID before source-backed products, source order differing from page order, duplicate links, empty attributes and
refusal when no visible source product qualifies. Final timing collectors were not rerun for this correction.
An untimed GET rehearsal against the existing isolated full-data request stack reproduced the showcase-first input;
the timing helper and Redis stack both chose the first eligible Olist product. Its detail, category, facet and Redis
search pages returned 200, and the listings contained the selected product. No dashboard or final experiment was run.
The independent reviewer reran the host checks, documentation validation, Ruff lint and formatting, and checked the new
regressions against the old helper to demonstrate that they detect the defect. A separate GET-only rehearsal reproduced
the old helper's failure and verified both corrected callers against the full-data stack. No actionable findings remained.
Redis trending burn-in was inspected but not run; the final Redis experiment must still verify it during its targeted
rerun. B1–B6 and the existing Redis stampede/limiter evidence are unaffected by this collector-only change.

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
worktrees. The reviewer ran Ruff format/check in the dev image,
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

### Authoritative November evidence for report and slides

Use this index, not the historical pending-status snapshots or fix handoffs in earlier result directories. Collection
and repository delivery are separate: PR #43 Redis measurement now has usable evidence for every required comparison,
with disclosed refusals and reduced coverage. The supplied fresh Opus evidence review confirms measurement completeness
and required documentation corrections only; see [review notes](#review-notes). Fresh Opus re-review verified all six corrections; its two wording follow-ups were applied and approved. Evidence delivery is complete: [PR #45](https://github.com/ZadeNova/INF2003_Database_Project/pull/45) merged into `31c1b0cbd823e3a60fff5fd47dba3d58688351dc`, and [merge CI 43058123048](https://github.com/ZadeNova/INF2003_Database_Project/actions/runs/43058123048) passed (verified 12 November 2026). Historical delivery-status snapshots below do not reopen the completed measurements.

| Evidence group | Measured revision | Actual limits | Authoritative outputs and status |
|---|---|---|---|
| B1–B6 | `505222f41b7473260ed9f40bb3bbaf8eafa46757` | [Per-session engine/runner caps and cpusets](../../benchmarks/results/overnight-2026-11-11/hardware.csv); [VM/power](../../benchmarks/results/overnight-2026-11-11/preflight.json). Engines 4 CPUs/3 GiB each; runner 2 CPUs/2 GiB; existing 10-GB/12-vCPU WSL VM, Balanced power | All three [session sources and raw evidence](../../benchmarks/results/redis-v2-2026-11-11/authoritative-evidence.csv); use the [cross-session headline](../../benchmarks/results/overnight-2026-11-11/sessions/headline.csv), [registered B2 pairs](../../benchmarks/results/overnight-2026-11-11/sessions/b2-headline.csv), and indexed per-session B5 footprint/B6 states, plans and resources. [Fresh correctness pass and restore audits](../../benchmarks/results/2026-11-11T081736_505222f4_overnight-correctness); [BM4 rejection verification](../../benchmarks/results/overnight-2026-11-11/bm4-verification.json). Valid; do not use pilots for headlines |
| Application page timing | `df03cb33c12deffceb6a1d298e7a2bbbc3e0a97e` | [Container caps](../../benchmarks/results/collectors-2026-11-11/mercer-request-collectors-containers.json), [VM](../../benchmarks/results/collectors-2026-11-11/preflight.json): database/web uncapped; Redis service 1 CPU/256 MiB, disabled for requests | [Raw joined requests and provenance](../../benchmarks/results/2026-11-11T181223_df03cb33_request-timing); [generated page summary](../../benchmarks/results/collectors-2026-11-11/page-summary.csv). Valid sequential collector immediately after import/demo seeding without seeded activity; its store split is specific to that state |
| Redis conditions | `b82ac876e9ff0fa4d3f530d81d70fa2b434c8e43` | [Application-stack configuration](../../benchmarks/results/redis-v2-2026-11-11/configuration.csv): database/web uncapped; Redis 1 CPU/256 MiB; existing VM allocation | [Raw samples, reports and chart](../../benchmarks/results/2026-11-11T220303_b82ac876_redis); [comparison usability](../../benchmarks/results/redis-v2-2026-11-11/comparison-usability.csv). Complete requested collection; all comparisons available with disclosed refusals and reduced paired coverage |
| Redis stampede | `505222f41b7473260ed9f40bb3bbaf8eafa46757` | Default application stack in the [recorded command](../../benchmarks/results/overnight-2026-11-11/commands.csv), [host/VM provenance](../../benchmarks/results/2026-11-11T171256_505222f4_redis-stampede/provenance.json); [Compose caps](../../compose.yaml) | [Original experiment](../../benchmarks/results/2026-11-11T171256_505222f4_redis-stampede/stampede.csv); [generated round summary](../../benchmarks/results/overnight-2026-11-11/stampede-summary.csv). Valid standalone evidence |
| Redis limiter | `505222f41b7473260ed9f40bb3bbaf8eafa46757` | Same default application stack and [host/VM provenance](../../benchmarks/results/2026-11-11T171256_505222f4_redis-stampede/provenance.json) as stampede; [Compose caps](../../compose.yaml) | [Measured aggregate table](../../benchmarks/results/2026-11-11T171256_505222f4_redis-stampede/limiter.csv) and original provenance. Valid; the existing tool retained aggregates rather than per-call latencies |
| Historical only: 2 November and pilots | Each original provenance retains its revision | [2 November planned/actual settings](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/provenance.json); pilot-specific settings remain in each directory | [2 November close-out and its source directories](#designated-machine-final-and-close-out-2-november-2026), [original pilot](../../benchmarks/results/2026-11-01T220402_b53e5d0a_pilot), [11 November pilot/attempt index](../../benchmarks/results/overnight-2026-11-11/attempts.csv) and [historical common cells](../../benchmarks/results/overnight-2026-11-11/historical-common-cells.csv). Superseded for report figures; preserve failures and original source rules as history |

Do not compare absolute times across B1–B6, page timing and Redis: their caps, workload and activity state differ.
The historical same-PC runs also differ in code, data and counts; they establish no causal build-speedup claim.

The [machine-readable revision map](../../benchmarks/results/redis-v2-2026-11-11/revision-map.json) explains the
separate commits: PR #41 repaired source-backed selection, PR #42 repaired distinct-visitor burn-in, and PR #43 repaired
the dashboard digest and added versioned refusal diagnostics. Application
code, data and Compose configuration are unchanged between these revisions; B1–B6, page timing, stampede and limiter
were not rerun or relabelled. Current main was fast-forwarded into `benchmark/overnight-evidence-2026-11-11` after
explicit backups and three-way reconciliation of pending documents. The collector worktree's staged tree was preserved
([integration record](../../benchmarks/results/redis-final-2026-11-11/integration-result.json)). Required prior evidence
was deliberately copied for portable repository links. Earlier staging manifests remain historical snapshots, not
inventories of the final reconciled documents.

#### Redis digest-version-2 final measurement after PR #43

The reviewed current-main revision in the table above was measured from a separate clean detached worktree. A new
`mercer-redis-digest2-final` project on loopback port 18087 received a fresh full Olist import, `seed_demo` and default
`seed_activity`. The complete default-count experiment used seed 82 and `--require-clean`; no pilot or count overrides,
TTL/clock changes, extra measured-request priming, gate bypasses or favourable-result retries were used. Other measurement
stacks were stopped. Only this task's services were stopped afterwards; its volumes and all earlier evidence remain.
The [command outcomes](../../benchmarks/results/redis-v2-2026-11-11/command-outcomes.csv) record successful preparation,
measurement and teardown. There were no operationally failed new attempts.

Actual CPU/RAM, disk and Docker limits are in the [preflight](../../benchmarks/results/redis-v2-2026-11-11/preflight.json).
The [configuration table](../../benchmarks/results/redis-v2-2026-11-11/configuration.csv) records the application-stack
limits and image identities: the existing owner-PC VM allocation was retained, not the teammate's allocation. PostgreSQL,
MongoDB and web use the default uncapped application limits inside that VM; Redis retains its configured cap. These are
separate from the earlier B1–B6 engine caps. Idle WSL file cache was released before setup with all containers stopped;
no allocation, global power, security or update setting changed. The original branch's staged evidence and the separate
collector worktree's staged tree survived [main integration](../../benchmarks/results/redis-v2-2026-11-11/integration-result.json).

**Acceptance.** The [validation record](../../benchmarks/results/redis-v2-2026-11-11/validation.json),
[condition coverage](../../benchmarks/results/redis-v2-2026-11-11/condition-coverage.csv) and
[generated comparison-usability table](../../benchmarks/results/redis-v2-2026-11-11/comparison-usability.csv) supply
counts and paired-round availability. Burn-in achieved control leadership and stable ranking. Every prescribed round,
condition and measured request was retained. Separately joined untimed records remain in
[warm-up.csv](../../benchmarks/results/2026-11-11T220303_b82ac876_redis/warm-up.csv); their IDs are disjoint from measured
samples. The strict collector joins succeeded before output, and the validator checked priming completeness, UTC and
monotonic timing consistency, and exact SHA correspondence for every public product-link signature. See
[timing and priming](../../benchmarks/results/redis-v2-2026-11-11/timing-and-priming.csv) and
[data signatures](../../benchmarks/results/2026-11-11T220303_b82ac876_redis/data-signatures.json).
Existing report tools regenerate all tables and the chart byte-identically. Digest version 2 and diagnostic schema 1
are recorded; earlier hashes were neither reinterpreted nor combined with this attempt.

**Findings and implications.** Use the generated [ratios](../../benchmarks/results/2026-11-11T220303_b82ac876_redis/ratios.csv),
[verdicts](../../benchmarks/results/2026-11-11T220303_b82ac876_redis/verdicts.csv),
[bootstrap intervals](../../benchmarks/results/2026-11-11T220303_b82ac876_redis/bootstrap.csv) and
[chart](../../benchmarks/results/2026-11-11T220303_b82ac876_redis/chart.svg) for numerical report/slide values.
Warm shop, search and dashboard comparisons exceed the measured control noise floor on accepted paired rounds.
This supports caching those repeated reads for Mercer, including dashboard history after the digest repair. Cold and
outage comparisons do not show a consistent effect beyond that noise floor; this does not establish that misses or
outages are free. Product-detail and category-trending controls do not support a universal Redis benefit.

**Refusals and limits.** The [refusal table](../../benchmarks/results/2026-11-11T220303_b82ac876_redis/refusals.csv),
[per-round refusals](../../benchmarks/results/redis-v2-2026-11-11/refusals-by-round.csv) and
[diagnosis](../../benchmarks/results/redis-v2-2026-11-11/refusal-diagnosis.json) distinguish confirmed observations from
hypotheses. Round-two shop/search public-link signatures retain the same multiset but change order: product `8914`
moves relative to neighbouring links. Those data-equality failures remain rejected. Rolling-window event expiry is a
possible mechanism, not directly proven. One measured warm search response is a confirmed cache miss; timing is
consistent with expiry, but key creation, TTL and eviction were not directly recorded. No dashboard samples are refused.
Shop/search warm and search outage comparisons have reduced paired-round coverage, losing full Williams balance.
The [shop/down round-two accepted cell](../../benchmarks/results/redis-v2-2026-11-11/condition-coverage.csv) contains
only the first 3 timed shop requests after Redis was paused, before the link order changed. Its first request pays the
configured Redis timeout, so the [raw requests](../../benchmarks/results/2026-11-11T220303_b82ac876_redis/samples.csv)
include the pause cost in this very small cell; its down/off ratio is inflated by that cost and is not a steady-state
outage estimate. The first observed reordering occurs while Redis is down and the live database path is used, which
supports a live-data change rather than a stale cached ordering; the expiry mechanism remains unproven.
The usability table exposes minimum accepted cell sizes. The approved gates permit refusals and report available paired rounds: they do not impose zero
refusals or a new minimum number of paired rounds. Every required comparison is available, with those qualifications.
Keep the report's insufficient-tail and optimistic-bootstrap labels. Sequential loopback traffic, one machine, warm
databases, synthetic activity, live rankings and worker back-off limit generalisation to production concurrency.

**Status and supersession.** All required measurement groups now have valid evidence with their recorded limitations.
This version-2 attempt supersedes earlier Redis-condition attempts for report headlines only; all historical artifacts,
failures and diagnoses below remain unchanged. B1–B6, page timing, stampede and limiter were neither rerun nor relabelled.
The main index above owns authoritative sources. Normal/staged documentation, diff, host tooling and artifact checks
are recorded in [checks.json](../../benchmarks/results/redis-v2-2026-11-11/checks.json).
That file and validation.json retain their pre-review status snapshots; the [review notes](#review-notes) own current
status. The supplied fresh Opus review confirms complete measurement and requests documentation corrections only.
Fresh Opus re-review verified all six corrections; its two wording follow-ups have been applied.
No measurement rerun is required. The earlier
[review prompt](../../benchmarks/results/redis-v2-2026-11-11/opus-review-prompt.txt) is retained as history.
Fresh Opus follow-up approved both wording fixes and report readiness. The subsequent PR #45 merge and passing
merge CI, linked in the authoritative index above, complete this evidence delivery. Final submission-package
validation is a separate deliverables acceptance check.

#### Historical superseded Redis execution and acceptance gaps after PR #42

This section records the earlier checkpoint; the version-2 measurement above resolves its dashboard blocker. It must
not supply current Redis headline figures. References to remaining work here describe that historical checkpoint.

The sole new measurement used a separate clean current-main worktree and a new `mercer-redis-report-final` project at
loopback port 18086. Full Olist import, demo seeding and default activity seeding preceded the default-count, seed-82
`--require-clean` experiment. No earlier activity was reused. The existing PC/WSL allocation was retained; default
application container limits, image identities and VM limits are in the
[configuration table](../../benchmarks/results/redis-final-2026-11-11/configuration.csv) and
[preflight](../../benchmarks/results/redis-final-2026-11-11/preflight.json). These are application-stack limits, distinct
from the driver engine caps. Benchmark/request measurement stacks were stopped. No application/benchmark code or
system allocation was changed. Only owned services were started and later stopped; all volumes and prior artifacts remain.

The repaired burn-in passed the unchanged control-leader and ranking-stability requirements. All prescribed conditions,
rounds, default sample counts and seeded order were collected; response IDs, metrics, matrices and reports validated
([validation](../../benchmarks/results/redis-final-2026-11-11/validation.json),
[coverage](../../benchmarks/results/redis-final-2026-11-11/condition-coverage.csv),
[command outcomes](../../benchmarks/results/redis-final-2026-11-11/command-outcomes.csv)). Regenerating the reports from
raw samples with the existing report code produced byte-identical outputs. Exit zero does not waive sample refusals.

**Findings and allowed uses.** The [original refusal table](../../benchmarks/results/2026-11-11T190658_eb9b39eb_redis/refusals.csv),
[refusals by round](../../benchmarks/results/redis-final-2026-11-11/refusals-by-round.csv),
[ratios](../../benchmarks/results/2026-11-11T190658_eb9b39eb_redis/ratios.csv) and
[verdicts](../../benchmarks/results/2026-11-11T190658_eb9b39eb_redis/verdicts.csv) supply all numerical values:

- Warm shop and search requests are faster in their accepted paired rounds and exceed the measured negative-control
  noise floor. These are accepted-subset findings, not complete four-round Williams comparisons: a whole round's
  warm shop/search data disagreed with its off reference. Search also had a warm cache miss. Their reduced pooled
  samples do not support every requested tail percentile; retain the generated tail labels and optimistic bootstrap labels.
- Cold-miss and outage comparisons that have accepted pairs do not show a consistent effect beyond the control noise
  floor. Search outage pairing is also incomplete. This does not prove a miss or outage costs nothing; paused Redis,
  worker back-off, sequential traffic and the observed noise limit that conclusion.
- Every warm-dashboard sample failed the data-equivalence gate. There is no accepted dashboard off/warm ratio or
  bootstrap interval. Do not infer dashboard speedup from rejected raw latencies or fill the missing bar in the chart.
  The independent earlier stampede experiment remains narrower evidence about coalesced recomputations.

**New normalization blocker.** An untimed diagnostic reproduced both recorded dashboard digest classes. The off and
warm bodies match after inter-tag whitespace normalization, but the existing digest removes the conditional cache
paragraph while retaining its extra conditional newline/indentation. The sanitized
[diagnosis](../../benchmarks/results/redis-final-2026-11-11/dashboard-digest-diagnosis.json) shows that formatting-only
mismatch; it does not retroactively accept samples or change any stored digest. A reviewed collector normalization fix
and fresh full Redis collection are required for the missing warm-dashboard comparison. No application change, gate
bypass, count reduction or identical retry was made here.

The shop/search data rejections are separate: [digest blocks](../../benchmarks/results/redis-final-2026-11-11/digest-blocks.json)
show a mid-round change followed by changed warm data. The collector retained hashes, not the HTML bodies or changed
link identities, so the exact historical link change cannot be reconstructed. A rolling trending window is a possible
cause, not a proven attribution. Keep those samples refused; future repair/review must also inspect their implications.
One machine, loopback, sequential clients, synthetic activity, two workers, warm databases, cache expiry and live ranking
changes limit generalisation. The measured effects do not establish that Redis helps every page.

**Delivery and remaining work.** All original failures below remain historical evidence: CPU-timeout pilot, MongoDB-OOM
pilot, source-selection failures and the PR #41 burn-in failure must not supply comparison headlines. BM4 remains a
separate expected rejection. The PR #42 run is a new completed execution with partial accepted comparisons, not an
unqualified successful final Redis comparison. The overall benchmark close-out is **not complete** while the dashboard
warm comparison is missing. Relevant host checks passed
([generated test record](../../benchmarks/results/redis-final-2026-11-11/host-tests.xml)); normal/staged documentation,
diff and artifact checks are retained in the current index. Fresh Claude Code review remains pending, with a
[consolidated review prompt](../../benchmarks/results/redis-final-2026-11-11/opus-review-prompt.txt).
No commit, push, consolidated PR or merge has been performed for this evidence. Current measurement completeness
and repository delivery must be assessed independently.

### Fresh driver evidence and collector blockers (11 November 2026)

Chee Long authorised this unattended rerun and machine adaptation. Codex fetched origin, verified that
`improvements/backlog` is an ancestor of `origin/main`, and fast-forwarded the clean local main to measurement commit
`505222f41b7473260ed9f40bb3bbaf8eafa46757` (PR #40). No application or benchmark source changed during the driver experiment.
Those measurements finished before the documentation branch `benchmark/overnight-evidence-2026-11-11` was created.
The supplied fresh Opus review subsequently confirmed complete measurement and requested documentation corrections;
[current review status](#review-notes) records the completed re-review and applied wording follow-ups. Nothing was committed or pushed.

**Evidence index.** The [generated validation table](../../benchmarks/results/overnight-2026-11-11/validation.csv),
[coverage matrix](../../benchmarks/results/overnight-2026-11-11/coverage.csv),
[attempts](../../benchmarks/results/overnight-2026-11-11/attempts.csv) and
[command exit statuses](../../benchmarks/results/overnight-2026-11-11/commands.csv) are the numerical record.
The [cross-session headline](../../benchmarks/results/overnight-2026-11-11/sessions/headline.csv) uses the approved
median of session medians; [session membership](../../benchmarks/results/overnight-2026-11-11/sessions/sessions.csv)
retains every session. All recorded sessions are usable; no recorded session was selected or excluded for its speed.
Per-session CSV/SVG reports, plans, storage, resource samples and checksummed compressed raw operations remain in
[session 1](../../benchmarks/results/2026-11-11T083148_505222f4_overnight-session-1),
[session 2](../../benchmarks/results/2026-11-11T112007_505222f4_overnight-session-2) and
[session 3](../../benchmarks/results/2026-11-11T141404_505222f4_overnight-session-3).

**Machine and deviations.** [Hardware and actual container limits](../../benchmarks/results/overnight-2026-11-11/hardware.csv)
and [preflight](../../benchmarks/results/overnight-2026-11-11/preflight.json) identify the Ryzen 5 5600X, host RAM,
SSD storage and the existing WSL memory allocation. The teammate's 12-CPU/24-GB VM prescription was superseded by the
owner's actual-resource authorisation: the existing 10-GB WSL limit and 12 virtual CPUs were retained, with Windows
headroom. The runner's actual usable-memory/CPU gate passed; every recorded session used `--final --require-clean`.
Both engines settled at 4 CPUs and 3 GiB with no container swap; the runner stayed at 2 CPUs and 2 GiB. PostgreSQL
shared_buffers and WiredTiger cache remained 512 MB and 0.75 GiB. The
[pinning decision](../../benchmarks/results/overnight-2026-11-11/resource-decision.json) compares relative baseline
spread and adopts disjoint cpusets. Ignored Compose overrides preserve these reversible settings; actual cpusets
are recorded even though `--pin` was omitted because its fixed file list would omit the resource override.
Balanced power and existing sleep/update/security settings were retained. At the user's later request, Steam was
closed gracefully during session 1; WSL file cache was released with engines stopped before sessions 2 and 3 loaded,
and after all work. No timed window was interrupted. This background-state change is a limitation, with no detected
start/end baseline drift. No Docker restart or unrelated project stop occurred.

The [first pilot](../../benchmarks/results/2026-11-11T022529_505222f4_pilot-b2) repeatedly timed out PostgreSQL's
B2b app variant under the original CPU cap and was deliberately stopped; its exit 137 is operator termination,
not an engine OOM. The [equal-CPU retry](../../benchmarks/results/2026-11-11T025810_505222f4_pilot-resource-b2)
passed the queries but lost MongoDB to its memory cap during repeated summary rebuilding. Both are excluded.
The [fresh memory pilot](../../benchmarks/results/2026-11-11T053250_505222f4_pilot-memory-b2) passed before resources
were settled. The [fresh full-data correctness pass](../../benchmarks/results/2026-11-11T081736_505222f4_overnight-correctness)
includes both physical restore audits. Separate
[BM4 verification](../../benchmarks/results/overnight-2026-11-11/bm4-verification.json) confirms deliberate bad results
and a violated invariant were rejected with no accepted timing. Each measurement session then reloaded again.

All applicable B1–B6 variants, originals and refresh costs were retained, with the amendment-l counts, five measured
repetitions and B3's fifty buyers. B7 stayed excluded. Engine order was not alternated, as already disclosed in l5.
Warm buffers, one Windows/WSL machine, a capped local client, generated attributes, a single-node replica set,
client-saturation/headline flags and pooled-tail sample gates remain limitations. Read each session's noise verdicts
alongside the headline flag; a statistically repeatable small difference need not exceed round-trip noise.

**Findings and implications for Mercer.** Numerical values come from the linked generators, never this prose:

- **B1:** [Cross-session attribute comparisons](../../benchmarks/results/overnight-2026-11-11/b1-comparison.csv)
  contradict the expectation that JSONB and MongoDB equality filters would be close: MongoDB is slower here. The
  expected EAV penalty is visible at one client, but often narrows to near JSONB under concurrency; consult the table's
  session ranges rather than assuming one ranking for every client count. The saved broad
  [planner-chosen plan](../../benchmarks/results/2026-11-11T141404_505222f4_overnight-session-3/plans/B1_broad_mongo_documents.json)
  scans the `_id_` index across the collection; the [attribute-hinted plan](../../benchmarks/results/2026-11-11T141404_505222f4_overnight-session-3/plans/B1_broad_mongo_documents_hinted.json)
  examines fewer documents and is faster, but remains diagnostic. That establishes the broad plan-choice cost;
  the cause of the general JSONB/MongoDB equality-filter gap is not established. MongoDB specifications remain
  justified by flexible category documents and the subset pattern; generated sparse attributes on this dataset do
  not establish a document-store search-speed advantage.
- **B2:** The expectation partly held: PostgreSQL leads the joined analytics and maintained reads reduce work, but
  expected MongoDB competitiveness on embedded order lines was contradicted. Every registered like-for-like
  [query pair](../../benchmarks/results/overnight-2026-11-11/sessions/b2-headline.csv) favours PostgreSQL here;
  the cause of the overall engine gap is not established by the [saved plans](../../benchmarks/results/2026-11-11T141404_505222f4_overnight-session-3/plans).
  Precomputation explains faster summary reads: summaries beat the live queries, but the original
  orders-of-magnitude expectation was not met; see the measured comparisons in
  [headline.csv](../../benchmarks/results/overnight-2026-11-11/sessions/headline.csv). Idiomatic queries and maintained summaries are separate from the
  original display-oriented queries. Refresh is a separate cost: daily-sales refresh is a tie at the observed
  overlapping [session ranges](../../benchmarks/results/overnight-2026-11-11/sessions/headline.csv), while delivery-score
  refresh favours PostgreSQL. This supports Mercer's PostgreSQL analytics and materialized views. Summary staleness,
  no-change refresh behaviour, precomputed MongoDB flags and category joins prevent a claim about all SQL and document workloads.
- **B3:** Both engines preserve the stock/order/payment invariants and restore their baselines
  ([states](../../benchmarks/results/2026-11-11T141404_505222f4_overnight-session-3/report/B3-states.csv)).
  The expectation held: both are correct, PostgreSQL queues without transaction retries, and MongoDB's write conflicts
  require more retries as contention rises, with higher tail latency in the [cross-session results](../../benchmarks/results/overnight-2026-11-11/sessions/headline.csv).
  The conflict/retry records support that contention mechanism; they do not isolate every component of the latency gap.
  PostgreSQL's trigger-off path has higher throughput here; trigger-on results expose the auditing cost. Mercer's
  money/stock transaction belongs in PostgreSQL; the trigger-off headline compares minimal operations and cannot
  represent the production checkout's full cost.
- **B4:** [Index comparisons](../../benchmarks/results/overnight-2026-11-11/b4-comparison.csv) show substantial gains
  from the selected SQL indexes and MongoDB attribute/review indexes, as expected for selective filters. The saved
  [before/after plans](../../benchmarks/results/2026-11-11T141404_505222f4_overnight-session-3/plans) show selective
  index paths replacing broader scans. The product-visible index changes the scan but leaves the per-product lookup
  work, and its effect is within the session noise verdicts, consistent with the expectation of little benefit
  when much of the data is still processed. Keep indexes tied to real filters and plans; do not generalise from one
  index or interpret the within-noise case as a reliable gain. Every index catalogue was restored.
- **B5:** [Storage evidence](../../benchmarks/results/overnight-2026-11-11/historical-storage.csv) exposes representation
  and index costs. The expectation partly held: EAV's attribute representation is larger than JSONB, and MongoDB's
  product footprint is smaller; GIN and the other indexes add storage. A universal MongoDB-smallest ranking cannot
  be inferred across the [unequal payloads](../../benchmarks/results/2026-11-11T141404_505222f4_overnight-session-3/report/B5.csv).
  The exact contribution of compression versus modelling/index allocation is not established by these probes.
  Embedded order lines and MongoDB review text mean these are representation-specific footprints, not equal-payload
  total-store ratios. Fresh-load probes and restore audits are retained; the linked generated table distinguishes
  historical rows from each November session.
- **B6:** [Expected and observed states](../../benchmarks/results/2026-11-11T141404_505222f4_overnight-session-3/report/B6-states.csv)
  match the expectation: naive read/modify/write loses an update in both engines, while locks/serializability and
  MongoDB transactions/atomic increments preserve the intended decrements, with retries where expected. The forced
  competing reads expose the overwrite; locking, conflict detection/retry or an atomic decrement prevents it.
  This motivates Mercer's explicit concurrency control; B6 remains a correctness demonstration, not a latency contest.
- **Application page timing:** the historical source-selection failure is preserved in the
  [original readback](../../benchmarks/results/overnight-2026-11-11/collector-blocker.json). After PR #41, the complete
  [page collector](../../benchmarks/results/2026-11-11T181223_df03cb33_request-timing) passed on its separately named
  revision. Its [generated page table](../../benchmarks/results/collectors-2026-11-11/page-summary.csv) shows that
  database work dominates category, product-list and faceted-search requests.
  The dashboard spends substantial time in both stores and also outside database calls; detail requests have a
  smaller database share. The [recorded procedure](../../benchmarks/results/collectors-2026-11-11/commands.jsonl)
  collected pages immediately after import and demo seeding, without `seed_activity`: there was no seeded activity, and trending held at most
  the collector's own single-visitor views, unlike the activity-seeded Redis experiment. Its PostgreSQL/MongoDB split is specific to that initial data state and
  must not be combined with the Redis off-condition figures. The PostgreSQL attribution difference between those
  experiments has no established cause; a planner-statistics explanation is unproven. The general claim that
  PostgreSQL dominates these pages is therefore unsupported. Database work remains a major request share in both
  experiments; optimisation should follow the relevant state. A store-split headline would need a controlled
  follow-up; it is not needed to complete the existing measurements. This is warmed, sequential HTML request timing
  with Redis disabled, excluding browser asset/render work and concurrent load.
- **Redis (historical checkpoint; superseded for condition claims by the [authoritative index](#authoritative-november-evidence-for-report-and-slides)):**
  the [stampede/limiter evidence](../../benchmarks/results/2026-11-11T171256_505222f4_redis-stampede) and
  [generated round summary](../../benchmarks/results/overnight-2026-11-11/stampede-summary.csv) show the dashboard lock
  coalescing cold recomputations and retain the measured limiter overhead. Two web workers, fixed condition order,
  loopback and one machine limit generalisation; the existing tool retains aggregates rather than individual
  stampede/limiter request latencies. The original off/cold/warm/down attempt hit the source mismatch
  ([historical failure](../../benchmarks/results/overnight-2026-11-11/redis-final-experiment.log)). The PR #41 continuation
  passed selection but failed the distinct-visitor burn-in described below. At that checkpoint no cache-condition
  speedup, bootstrap interval or cold/warm/down claim was available; PR #43's version-2 evidence now supplies those
  comparisons with the qualifications above. These app experiments ran only with benchmark engines stopped.

**Historical comparison and remaining work.** [Provenance comparison](../../benchmarks/results/overnight-2026-11-11/machine-comparison.json)
finds matching CPU and reported physical RAM, consistent with the owner's confirmation of the same PC; no unique
hardware serial was collected. These are not cross-machine results. The
[source differences](../../benchmarks/results/overnight-2026-11-11/source-differences.txt) include regenerated product
names, changed B2d goldens/semantics, new idiomatic and summary variants and later application/schema changes.
[Common B1/B4 cells](../../benchmarks/results/overnight-2026-11-11/historical-common-cells.csv) and the storage table
provide historical context only: source data, code, counts, caps and pinning differ, so they do not measure a causal
build speedup. These sessions supersede the 2 November B1–B6 driver evidence for the current build; older evidence
and all failed pilots remain in place, without archival or deletion. Fresh application timing subsequently passed on the collector-only revision below. Redis condition measurements
were blocked at that checkpoint. The historical PR #42 gaps and subsequent valid version-2 measurement are indexed above; repository delivery remains pending.
The fresh Opus re-review is complete; its two wording follow-ups have been applied ([review notes](#review-notes)). [Artifact verification](../../benchmarks/results/overnight-2026-11-11/verification.json)
passed; documentation validation is retained in
[check-docs.log](../../benchmarks/results/overnight-2026-11-11/check-docs.log).

#### Collector continuation after PR #41 (11 November 2026)

**Historical checkpoint:** PR #42 subsequently repaired this burn-in failure. Use the authoritative index above for the subsequent attempts and completed version-2 measurement.

PR #41 was fetched and verified merged into main. Both collector attempts used the clean committed revision
`df03cb33c12deffceb6a1d298e7a2bbbc3e0a97e`, in an isolated worktree. The
[revision comparison](../../benchmarks/results/collectors-2026-11-11/source-revisions.json) records that only collector
selection, tests and documentation differ from the driver/stampede revision `505222f41b7473260ed9f40bb3bbaf8eafa46757`;
application code, data and Compose configuration are unchanged. Earlier evidence retains its original commit.
No B1–B6, stampede or limiter measurement was rerun. The original uncommitted overnight documentation was reconciled
with PR #41's additions and preserved unchanged in its original checkout.

Fresh isolated full-data projects `mercer-request-collectors` and `mercer-redis-collectors` used loopback ports 18084
and 18085, the documented import and demo seeding, and default application service limits. Redis activity was seeded
with the documented defaults immediately before its attempt. The request stack stopped before Redis started; all
owned services are now stopped and volumes preserved. The existing host/WSL allocation was retained, not the
teammate's allocation. [Preflight](../../benchmarks/results/collectors-2026-11-11/preflight.json), sanitized container
snapshots and [command outcomes](../../benchmarks/results/collectors-2026-11-11/command-outcomes.csv) retain the facts.

The page run's source-backed selection, response/log joins, counts and all aggregate values were independently
recomputed using the repository's existing functions
([validation](../../benchmarks/results/collectors-2026-11-11/validation.json)). Its raw joined requests, selected
request-log records, per-page aggregates and original provenance remain in the linked result directory. The
[generated page table](../../benchmarks/results/collectors-2026-11-11/page-summary.csv) supplies the numerical findings.
The source-selection fix's prior fresh Opus review is recorded separately in the existing PR #41 notes; this evidence
handoff has not received an independent review.

**Historical blocker: Redis ranking burn-in (repaired by PR #42).** The complete default experiment was invoked with `--require-clean`,
without pilot flags or reduced counts. It exhausted the existing untimed settling procedure and rejected the run
before any timed condition. The [failed attempt](../../benchmarks/results/2026-11-11T181359_df03cb33_redis/failure.json)
and [read-only database diagnosis](../../benchmarks/results/collectors-2026-11-11/redis-failure-diagnosis.json) show
repeated views from one session but only one counted visitor for the control product, while seeded leaders have more
visitors. `settle_ranking` reuses one cookie jar; `views_per_visitor` deliberately deduplicates it. Repeating those views
cannot satisfy the required leader condition. Activity was present in the valid trending window and the collection
retained its TTL; this is not the historical showcase mismatch or an empty seed.

No timed samples, condition summaries, ratios, bootstrap intervals, verdicts or chart were produced for this failed
attempt. No gate, count, data or application/benchmark code was changed, and a deterministic identical retry was not
made. A separately reviewed burn-in fix is required, followed by only the full Redis experiment from its documented
fresh seeded state. Page timing and all earlier valid measurements need no rerun. Do not claim Redis helps every page:
its cache-condition effect is still unmeasured on this build; the earlier stampede evidence remains a narrower result.

The evidence/documentation branch is `benchmark/collector-evidence-2026-11-11`, in `.cache/collectors-final`.
Required prior evidence is included deliberately so links are portable; local orchestration and credentials are excluded.
Relevant [host checks](../../benchmarks/results/collectors-2026-11-11/host-tests.xml) passed. Current documentation and
staged-index checks are retained in the collector evidence index. Fresh Claude Code review is pending; the CLI was
not available here, so commit, push and PR creation are paused under AGENTS.md. The overall close-out remains incomplete.

### Designated-machine final and close-out (2 November 2026)

**Historical:** superseded for report figures by the [authoritative November index](#authoritative-november-evidence-for-report-and-slides).
The source-selection instruction and validation below apply to the 2 November checkpoint only.

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
