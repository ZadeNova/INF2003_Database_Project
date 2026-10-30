# deliverables: Report, slides, video, user manual and packaging

status: draft
plan owner: Chee Long · implementers: all five members (each writes and presents their part) · reviewer: a fresh
session · phase 5 ([PLAN.md section 13](../../PLAN.md#13-phases)) · depends on: every Tier 1 workstream for final
acceptance; `benchmark` final measurements for report section 6 and video part iv

**Assumes:** the application is frozen (Phase 4 closed 30 October 2026); the XSite final report template is
downloaded; the demo story in [OVERVIEW.md section 3](../OVERVIEW.md#3-the-demo-story) stays the video's spine. The
`benchmark` final measurements target 1 November with 2 to 4 November as contingency. If they slip, section 6 is
drafted from the 28 October fix round, the [full-data correctness run](../../benchmarks/results/2026-10-28T225445_d6fc7e44_fix-full/summary.csv)
and the [trial measure run](../../benchmarks/results/2026-10-28T230836_d6fc7e44_fix-trial/summary.csv) for draft
ratios, labelled as a trial not run on the designated machine, and regenerated from the final run.

## Contract

**Goal.** One zip, submitted on 28 November (deadline 29 November, 23:30 Singapore time), that earns the Excellent
band for presentation (25%) and report (25%) and shows the project-quality work (40%) clearly
([RUBRICS.md section 5](../../RUBRICS.md#5-assessment-criteria)).

**In scope**

| Area | Deliverable |
|---|---|
| Report | PDF from the XSite template; at most 10 pages in Calibri (Body) 12, body tables included, excluding cover, references and appendix; outline and page budget below |
| Theory map | Appendix A: each module concept, where Mercer shows it, and the file or test that proves it (draft below) |
| Slides | `.pptx` that stands on its own (the brief: "informative enough about the project details"): architecture, core ER diagram, MongoDB data model, the comparison table, benchmark tables and demo screenshots, not only a script skeleton; each presenter's name bottom-left on the slides they present |
| Video | `.mp4`, target 9:30, hard limit 10:00 at normal speed; parts i to iv in the brief's order; all five members present, with a name overlay during demo footage as well as on slides; generated content keeps its visible labels (AGENTS.md rule 9) |
| User manual | README.md reordered so a marker reads setup, data load and demo logins in sequence near the top, with a note for starting from the extracted source zip; developer, CI and benchmark material after the user sections; checked by the clean-machine runs below |
| Packaging | `scripts/package_submission.py` builds the zip from a committed ref; `--check-only` passes |
| Records | CONTRIBUTIONS.md with every student ID and each member's work; a deliverables line in docs/AI_USE.md; the reuse approval in writing (below); Olist CC BY-NC-SA attribution in the report's references; every member completes the peer-review survey |

**Reuse approval (carried over from Phase 0).** Phase 0's exit check required the professors' written approval of
building on our earlier module project; [AI_USE.md](../AI_USE.md) records only a verbal one. Erfan, who obtained it,
requests it in writing now and has it by the 8 November check-in; the email's sender and date are cited in AI_USE.md
and the report. The plagiarism clause carries a zero mark, so this does not wait for the end.

**Out of scope:** new application features (frozen); Tier 2 work, which needs its own approved plan after the
8 November check-in; editing or re-deriving benchmark numbers by hand.

### Report outline and page budget

9.25 pages budgeted, with figures inside each section's pages; 0.75 page of slack. The body carries a core ER diagram
(the full one goes in appendix B). Section owners are proposed (decision a).

| # | Section | Pages | Figures | Proposed owner | Material |
|---|---|---:|---|---|---|
| 1 | Introduction: the marketplace, three roles, why two databases | 0.5 | Architecture | Erfan | PLAN.md sections 2 and 3 |
| 2 | Dataset and database construction: Olist, profile, cleaning ledger, the import into both stores, generated content and its labels | 1.0 | Ledger summary table | Erfan | [DATA_MODEL.md](../DATA_MODEL.md) dataset profile and cleaning ledger |
| 3 | Relational design: core ER diagram, 3NF, constraints, triggers, deferred money checks, roles and privileges | 1.5 | Core ER diagram | Jun Keat | DATA_MODEL.md PostgreSQL sections |
| 4 | NoSQL design: embed against reference, subset pattern, `$jsonSchema`, GridFS, time series with TTL, live schema evolution | 1.25 | Document model | Joash | DATA_MODEL.md MongoDB sections |
| 5 | Implementation: CRUD on both stores (seller products, operator take-downs), checkout under concurrency, cross-store faceted search, review transactions and Bayesian rating, dashboard and forecast, activity | 1.5 | One screenshot | Chee Long | Workstream plans and their review notes |
| 6 | Performance analysis: method and fairness, B1 to B6 as ratios, query plans, threats to validity | 1.75 | Two benchmark figures | Chee Long | Generated `benchmarks/results/` reports |
| 7 | Discussion: SQL against NoSQL beyond speed (modelling, consistency, constraints, flexibility); the delivery-delay finding and its implications | 0.75 | none | Joash, Chee Long | Benchmark plan amendments f to i; dashboard |
| 8 | Testing and quality: real-database tests, injection negatives, browser journeys, CI gates | 0.5 | none | Syahfariz | [ci.md](ci.md), CI run summaries |
| 9 | Reflections: changes since the proposal, limitations, future work | 0.5 | none | All, edited by the report editor | PLAN.md section 9; Tier 2 and 3 |

Appendices (outside the page count): A theory map; B full ER diagram and cleaning ledger; C generated benchmark
tables; D AI use and the reuse disclosure; references, including the Olist licence.

### Video script (target 9:30)

Demo footage starts from a pre-staged state on the prepared stack (decision d): orders already placed for the
cancellation, two of the three seller orders already shipped, a wishlisted sold-out product.

| Part | Time | Presenter (proposed) | Live demo | Slides |
|---|---|---|---|---|
| i. Background | 0:00–1:05 | Erfan | Home page and the three role landings | Idea, roles, Olist and its cleaning ledger, architecture |
| ii. Relational | 1:05–3:50 | Jun Keat, then Chee Long | One checkout from three sellers (three orders, stock reduced); one seller ships, the operator delivers; a cancel refunds; a restock fires the wishlist alert; dashboard (about 0:30), ending on the delivery-delay finding and what it means for sellers | Core ER and 3NF; constraints and composite keys; triggers; roles and privileges |
| iii. NoSQL and comparison | 3:50–7:00 | Joash | Typo search with live facet counts; a new category attribute with no migration; a seller edits price and stock (PostgreSQL), the specification (MongoDB) and a photo (GridFS), and the operator takes a product down (0:20); a review updating the rating summary in one transaction; trending from the time series | Document model; the comparison table below |
| iv. Performance | 7:00–8:45 | Chee Long | none | Method and fairness rules; headline ratios, each with one line on what it means; one slow, index, fast plan story; B3 last-unit and B6 lost-update results |
| Close | 8:45–9:30 | Syahfariz | none | Testing and CI in one slide; implications (which store suits which job, and the delivery-delay finding); conclusions |

**Comparison table (part iii and report section 7):** flexible attributes as EAV against JSONB against documents
(B1); integrity as constraints and foreign keys against validators and unique indexes; concurrency as `FOR UPDATE` and
SERIALIZABLE against transaction retry and atomic `$inc` (B6); schema evolution as `ALTER TABLE` against a new
attribute; modelling as normalised tables against embedding and referencing. Part iv then gives the numbers.

### Theory map (draft for appendix A)

Paths are relative to the repository root.

| Module concept | Where Mercer shows it | Proof |
|---|---|---|
| ER modelling and relationship types | 1-to-many, many-to-1, many-to-many (wishlist, order lines) | ER diagram in docs/DATA_MODEL.md |
| Data types | Exact money as `numeric(12,2)` and `Decimal128`; integers, text, timestamps, booleans, JSONB | src/catalogue/models.py; src/reviews/ratings.py; docs/DATA_MODEL.md |
| Normalisation | 3NF justification; the deliberate MongoDB denormalisation (subset pattern) | docs/DATA_MODEL.md, Normalisation (3NF) |
| Integrity constraints | Keys, `CHECK`, `ON DELETE RESTRICT`, composite foreign keys such as `(order_id, seller_id)`, two deferred constraint triggers (payments and refunds against the checkout), a partial unique index | src/orders/migration_sql.py; src/wishlist/migrations/0001_wishlist_restock.py |
| Triggers | Profile-role checks; seller and order status transitions; seller, order and product audit; restock alert | src/accounts/migration_sql.py; src/orders/migration_sql.py; src/catalogue/migration_sql.py; src/wishlist/migrations/0001_wishlist_restock.py |
| Views | `purchasable_product`; the `daily_product_sales` materialized view | src/catalogue/migrations/0001_initial.py; src/dashboard/migrations/0001_daily_product_sales.py |
| Complex SQL | CTEs, window functions, aggregates in the dashboard and forecast | src/dashboard/queries.py |
| Transactions | Checkout with `FOR UPDATE` and a fixed lock order, idempotency key, compensating cancellation; B3 on both engines | src/orders/services.py; benchmarks/workloads/b3.py; tests/test_checkout.py |
| Isolation and lost updates | PostgreSQL: lost update under READ COMMITTED, `FOR UPDATE`, SERIALIZABLE with retry. MongoDB: read-modify-write, transaction retry, atomic `$inc` | benchmarks/workloads/b6.py |
| Indexing and query plans | PostgreSQL B-tree, composite, partial, GIN, trigram; MongoDB compound, multikey, wildcard, unique, partial (bench); `EXPLAIN (ANALYZE, BUFFERS)` and `explain("executionStats")`; B4 | src/catalogue/migrations/0002_product_search_audit.py; src/config/mongo_schema.py; benchmarks/load.py; benchmarks/workloads/b4.py |
| Security and least privilege | PostgreSQL owner and runtime roles; the MongoDB app user with `readWrite` on its databases only; parameterised queries with injection tests; seller scoping | src/config/privileges.py; src/docker/mongo-start.sh; tests/test_mongo_user.py; tests/test_catalogue_search.py |
| Document data model | Specifications embed the rating summary and latest five reviews; all reviews referenced | docs/DATA_MODEL.md, MongoDB |
| Schema validation and evolution | `$jsonSchema` validators; a new category attribute without a migration | src/config/mongo_schema.py |
| Aggregation | `$facet`; `$setWindowFields`; the Bayesian rating as an update pipeline built from aggregation expressions | src/catalogue/search.py; src/activity/services.py; src/reviews/ratings.py |
| MongoDB transactions and replication | A review, the rating summary and the embedded subset in one transaction on a replica set | src/reviews/services.py |
| Specialised storage | Time-series collection with TTL; GridFS | src/config/mongo_schema.py; src/catalogue/services.py |

**Exit check**
1. The report PDF is at most 10 pages excluding cover, references and appendix, in Calibri (Body) 12, on the XSite
   template. Every figure and table caption in the report, and every table and chart in the slides, names its
   generated source (benchmark report, cleaning ledger, CI run).
2. The video plays in at most 10:00 at normal speed. A part-by-part timestamp list shows the order i to iv, every
   member presenting with a name on screen, and the slide range used in each part.
3. The plan owner checks the theory map rows against the module's lecture list, and each proof path exists.
4. Syahfariz, or another member who is not the main developer, follows README.md on their own machine from an
   extracted `git archive` zip of `main` (what the packager ships) to working demo logins by 15 November, and any
   manual fix is merged. The check is repeated from the final submission zip by 27 November.
5. `scripts/package_submission.py` builds the zip from the submitted commit; `--check-only` reports no FAIL, and every
   WARN has been looked at.
6. CONTRIBUTIONS.md has every student ID and each member's work; docs/AI_USE.md has a deliverables line and cites the
   approval email's sender and date.
7. A fresh session or a teammate who did not write them reviews the report and video against the RUBRICS.md
   Excellent bands before submission, with one fix round.
8. Submitted by 28 November, with the XSite confirmation kept.

## Milestones

| Date | Milestone |
|---|---|
| 2 Nov | This plan approved; decisions a to e settled; reuse approval requested |
| 4 Nov | `benchmark` final measurements closed (target 1 November) |
| 7 Nov | Report sections 1 to 5 drafted; slide skeleton; material for the check-in |
| 8 Nov | Professor check-in; Tier 2 decision; written reuse approval in hand |
| 15 Nov | Full report draft, including sections 6 and 7; script frozen; first clean-machine run done |
| 18 Nov | Demo footage captured in one session on the prepared stack (decision d) |
| 21 Nov | Voice-overs recorded (24 November is the hard limit, decision c) |
| 25 to 27 Nov | Video edit, report and video review, final report pass, repeat clean-machine run, packaging |
| 28 Nov | Submit |

### Recording-day checklist

[PLAN.md section 16](../../PLAN.md#16-risks) links here. On the prepared full-data stack:

1. Run the browser suite once against it ([README Continuous integration](../../README.md#continuous-integration)).
2. Run `seed_activity`, then place a few demo purchases for the demo seller's products before filming Insights.
3. Pre-stage the demo state named in the video script; preload the operator dashboard.
4. Log in from the ignored `.env`; never show a password or `.env` on screen.

## Decisions (proposed, awaiting the owner)

| ID | Proposal | Why |
|---|---|---|
| a | Erfan edits and assembles the report (PLAN.md open decision D2); section owners as in the outline | One editor keeps one voice and the page count; it leaves the main developer free for the benchmark and sections 5 and 6 |
| b | The report is drafted in the XSite Word template in a shared drive, not in the repository | The template is Word; the docs rules allow no new Markdown file; only the PDF is submitted |
| c | Footage by 18 November, voice-overs by 21 November; 24 November is the hard limit | Insights is near-empty by 25 November (PLAN.md section 16). Demo purchases add only a handful of sales, not the imported history, and footage on 18 November leaves time to re-shoot |
| d | Chee Long, who holds the full-data stack, captures all demo footage in one session on it by 18 November, after the script freezes; each presenter records their own voice-over (or face) for their part; Syahfariz assembles and times the video and slides (PLAN.md section 12) | The checklist needs one prepared full-data stack. Five members each recording live demos would need five imports and five preparations. The tradeoff: presenters narrate footage they did not drive, so the script names every click |
| e | If Tier 2 is earned on 8 November, it is funded from the slack: at most 0.5 page from the 0.75 page of slack, and at most 15 seconds added to the close, so the video target becomes at most 9:45. The close and section 9 keep their budgets | Tier 2 never displaces graded core content: the close's implications and conclusions keep their 0:45, and the video keeps a margin under 10:00 |

**At close-out:** move decision a into PLAN.md section 15 (closing D2) and section 12.

## Review notes

30 October 2026, Claude Code (Opus 5.5), fresh session. Reviewed commit 490e140 against RUBRICS.md, PLAN.md
sections 4, 9, 10 and 12–16 and OVERVIEW.md sections 3 and 7. Spot-checked the theory map in the code (deferred
money triggers, the `restock_one_unseen` partial unique index, `$facet`, the time-series TTL, B6 isolation
strategies, the Bayesian update pipeline, both views) and confirmed the packager ships the Olist data;
`scripts/check_docs.py` passed. Verdict APPROVE WITH CHANGES: put a written-reuse-approval owner and date in the plan,
settle decision d against the single-stack recording checklist, move the clean-machine run earlier and run it from
`source_code.zip`, give implications more video time, add CRUD and a named comparison table, and add a proof column
to the theory map.

30 October 2026, fix round (Claude Code, the session that wrote the plan). All 15 findings applied: reuse approval
with owner and date; decision d reworked to one capture session with per-presenter voice-over; clean-machine runs by
15 and 27 November from the archive zip; video re-timed (part ii 2:45 with pre-staged state, a 0:45 close, the
delivery-delay implication in part ii, CRUD in part iii, a named comparison table); theory map with a proof column,
reworded rows and the missing constructs, its lecture-list check moved to exit check 3; exit checks made verifiable
and a review of the report and video added; standalone slides; README reorder; dates linked to PLAN.md section 13
with a benchmark fallback; the recording checklist kept here with PLAN.md section 16 linking to it; figures budgeted
per section; name overlays, generated-content labels, Olist attribution and the peer-review survey.

30 October 2026, Claude Code (Opus 5.5), fresh session, second review. Reviewed fix-round commit 7d5ba44 against the
first review's 15 findings, RUBRICS.md, PLAN.md sections 12–16 and OVERVIEW.md sections 3 and 7. Confirmed the video
(9:30) and page (9.25 + 0.75) sums and the date agreement, checked that every Proof path exists, and spot-checked the
composite foreign keys, the profile-role triggers, the MongoDB wildcard and unique indexes, B6's MongoDB strategies
and the app user's `readWrite` grant in the code; `scripts/check_docs.py` passed. Verdict APPROVE, with small edits:
cite `src/docker/mongo-start.sh` and `tests/test_mongo_user.py` for the `readWrite` scope, fund Tier 2 (decision e)
from the slack, name the footage capturer, and replace "wishlist migration" with its path.

30 October 2026, the second review's edits (Claude Code, the session that wrote the plan): all applied. The
`readWrite` and money proofs cite the grant, its test and the model; decision e takes Tier 2 from the slack (video
target at most 9:45); decision d names Chee Long, with footage captured by 18 November; the wishlist proof is a path;
PLAN.md section 16 links to decision c instead of repeating its dates; slide tables and charts name their sources;
the plan owner checks the lecture list; the benchmark fallback links its evidence.

30 October 2026, Claude Code (Opus 5.5), fresh session, third review. Reviewed commit 3b17020 against the second
review's five edits: confirmed the new proof paths and the fallback link exist, that decision e's Tier 2 budget and
the 18 and 21 November milestones are consistent with the script, page budget and PLAN.md section 16, and that the
fallback run (`fix-full`) is correctness-only, so draft ratios should come from the full-data `fix-trial` measure
run; `scripts/check_docs.py` passed. Verdict APPROVE; optional tweaks are to link `fix-trial` for draft ratios and to
align decision c's wording with the 18 November footage date. Both tweaks applied by the session that wrote the plan.
