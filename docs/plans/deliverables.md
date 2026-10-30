# deliverables: Report, slides, video, user manual and packaging

status: draft
plan owner: Chee Long · implementers: all five members (each writes and presents their part) · reviewer: a fresh
session · phase 5 (30 October to 28 November) · depends on: every Tier 1 workstream for final acceptance; `benchmark`
final measurements for report section 6 and video part iv

**Assumes:** the application is frozen (Phase 4 closed 30 October 2026); the XSite final report template is
downloaded; the demo story in [OVERVIEW.md section 3](../OVERVIEW.md#3-the-demo-story) stays the video's spine; the
`benchmark` workstream closes its designated-machine measurements by 4 November.

## Contract

**Goal.** One zip, submitted on 28 November (deadline 29 November, 23:30 Singapore time), that earns the Excellent
band for presentation (25%) and report (25%) and shows the project-quality work (40%) clearly
([RUBRICS.md section 5](../../RUBRICS.md#5-assessment-criteria)).

**In scope**

| Area | Deliverable |
|---|---|
| Report | PDF from the XSite template; at most 10 pages in Calibri (Body) 12, excluding cover, references and appendix; outline and page budget below |
| Theory map | Appendix A of the report: each module concept, where Mercer shows it, and the file or test that proves it (draft rows below) |
| Slides | `.pptx` following the script below; each presenter's name bottom-left on the slides they present |
| Video | `.mp4`, target 9:30, hard limit 10:00 at normal speed; parts i to iv in the brief's order; all five members present with names on screen |
| User manual | README.md; final pass after a clean-machine run on a teammate's machine (not the main developer's) |
| Packaging | `scripts/package_submission.py` builds the zip from a committed ref; `--check-only` passes |
| Records | CONTRIBUTIONS.md complete for peer review (including Joash's student ID); docs/AI_USE.md complete; the professors' reuse approval obtained in writing and cited |

**Out of scope:** new application features (frozen); Tier 2 work, which needs its own approved plan after the
8 November check-in; editing or re-deriving benchmark numbers by hand.

### Report outline and page budget

Nine pages budgeted, one page of slack for figures. Section owners are proposed (decision a).

| # | Section | Pages | Proposed owner | Material |
|---|---|---:|---|---|
| 1 | Introduction: the marketplace, three roles, why two databases | 0.5 | Erfan | PLAN.md sections 2 and 3 |
| 2 | Dataset: Olist, profile, cleaning rules and ledger, generated content and its labels | 1.0 | Erfan | [DATA_MODEL.md](../DATA_MODEL.md) dataset profile and cleaning ledger |
| 3 | Relational design: ER diagram, 3NF, constraints, triggers, deferred payment check, roles and privileges | 1.5 | Jun Keat | DATA_MODEL.md PostgreSQL sections |
| 4 | NoSQL design: embed against reference, subset pattern, `$jsonSchema`, GridFS, time series with TTL, live schema evolution | 1.25 | Joash | DATA_MODEL.md MongoDB sections |
| 5 | Implementation: checkout under concurrency, cross-store faceted search, review transactions and Bayesian rating, dashboard and forecast, activity | 1.5 | Chee Long | Workstream plans and their review notes |
| 6 | Performance analysis: method and fairness, B1 to B6 as ratios, query plans, threats to validity | 1.75 | Chee Long | Generated `benchmarks/results/` reports |
| 7 | Discussion: SQL against NoSQL beyond speed (modelling, consistency, constraints, flexibility); the delivery-delay finding and its implications | 0.75 | Joash, Chee Long | Benchmark plan amendments f to i; dashboard |
| 8 | Testing and quality: real-database tests, injection negatives, browser journeys, CI gates | 0.25 | Syahfariz | [ci.md](ci.md), CI run summaries |
| 9 | Reflections: changes since the proposal, limitations, future work | 0.5 | All, edited by the report editor | PLAN.md section 9; Tier 2 and 3 |

Appendices (outside the page count): A theory map; B full cleaning ledger; C generated benchmark tables; D AI use and
the reuse disclosure; references.

### Video script (target 9:30)

| Part | Time | Presenter (proposed) | Shows |
|---|---|---|---|
| i. Background | 0:00–1:15 | Erfan | The idea, the three roles, Olist and its cleaning ledger, the two-store architecture |
| ii. Relational | 1:15–4:15 | Jun Keat, then Chee Long | ER and 3NF; buy from three sellers in one checkout; seller ships, operator delivers, a cancel refunds; status, audit and restock triggers (wishlist alert); roles and privileges; dashboard with materialized view, window functions and forecast |
| iii. NoSQL and comparison | 4:15–7:15 | Joash | Typo search and live facet counts; a new category attribute with no migration; a review updating the rating summary in one transaction; a seller photo in GridFS; trending from the time series; the comparison table |
| iv. Performance | 7:15–9:00 | Chee Long | Method and fairness rules; headline ratios; one slow, index, fast plan story; B3 last-unit and B6 lost-update results |
| Close | 9:00–9:30 | Syahfariz | Testing and CI in one slide; the delivery-delay implication; conclusions |

### Theory map (draft rows for appendix A)

| Module concept | Where Mercer shows it |
|---|---|
| ER modelling and relationship types | ER diagram: 1-to-many, many-to-1, many-to-many (wishlist, order lines) |
| Normalisation | 3NF justification in DATA_MODEL.md; the deliberate MongoDB denormalisation |
| Integrity constraints | Keys, `CHECK`, `ON DELETE RESTRICT`, the deferred payment constraint trigger, partial unique index |
| Triggers | Status transition, audit, restock alert |
| Views | `purchasable_product`; the dashboard's materialized view |
| Complex SQL | CTEs, window functions, aggregates in the dashboard and forecast |
| Transactions and concurrency | `FOR UPDATE` checkout, idempotency, compensating cancellation; B3 and B6 |
| Isolation levels | Lost update under READ COMMITTED; SERIALIZABLE with retry (B6) |
| Indexing and query plans | B-tree, composite, partial, GIN, trigram; `EXPLAIN (ANALYZE, BUFFERS)`; B4 |
| Security | Owner and runtime roles, parameterised queries, injection tests, seller scoping |
| Document data model | Specifications, reviews, embed against reference, subset pattern |
| Schema validation and evolution | `$jsonSchema`; a new attribute without a migration |
| Aggregation | `$facet`, `$setWindowFields`, the Bayesian rating pipeline |
| MongoDB transactions and replication | Review writes in one transaction on a replica set |
| Specialised collections | Time series with TTL; GridFS |

The owner checks these rows against the module's lecture list before the appendix is written (decision e).

**Exit check**
1. The report PDF is at most 10 pages excluding cover, references and appendix, in Calibri (Body) 12, on the XSite
   template. Every figure and number traces to a generated source: benchmark reports, the cleaning ledger, CI output.
2. The video plays in at most 10:00 at normal speed, parts in order, all five members presenting with names on screen.
   The slides match it.
3. A teammate other than the main developer follows README.md on their own machine from a fresh clone to working demo
   logins, and any manual fix is merged.
4. `scripts/package_submission.py` builds the zip from the submitted commit; `--check-only` reports no FAIL, and every
   WARN has been looked at.
5. CONTRIBUTIONS.md and docs/AI_USE.md are complete; the reuse approval is cited in writing.
6. Submitted by 28 November, with the XSite confirmation kept.

## Milestones

| Date | Milestone |
|---|---|
| 2 Nov | This plan approved; decisions a to e settled |
| 4 Nov | `benchmark` final measurements closed |
| 7 Nov | Report sections 1 to 5 drafted; slide skeleton; material for the check-in |
| 8 Nov | Professor check-in; Tier 2 decision |
| 15 Nov | Full report draft, including sections 6 and 7; script frozen |
| 24 Nov | Video recorded (hard limit, decision c) |
| 25 to 27 Nov | Video edit, final report pass, clean-machine run, packaging |
| 28 Nov | Submit |

**Recording-day checklist:** run the browser suite once against the full-data stack ([README Continuous
integration](../../README.md#continuous-integration)); run `seed_activity`; place a few demo purchases for the demo
seller's products before filming Insights; preload the operator dashboard; log in from the ignored `.env` and never
show a password or `.env` on screen.

## Decisions (proposed, awaiting the owner)

| ID | Proposal | Why |
|---|---|---|
| a | Erfan edits and assembles the report (PLAN.md open decision D2); section owners as in the outline | One editor keeps one voice and the page count; it leaves the main developer free for the benchmark and sections 5 and 6 |
| b | The report is drafted in the XSite Word template in a shared drive, not in the repository | The template is Word; the docs rules allow no new Markdown file; only the PDF is submitted |
| c | Record the video by 24 November | The seller Insights window is near-empty by 25 November and empty after 27 November (PLAN.md section 16) |
| d | Each presenter records their own segment with voice-over; Syahfariz assembles and times the video and slides (PLAN.md section 12) | Parallel recording; one person owns the 9:30 target |
| e | The theory map rows are confirmed against the module's lecture list before writing | The draft rows come from the project, not from the syllabus |
| f | If Tier 2 is earned on 8 November, it gets at most half a page in section 9 and 30 seconds in the close | The outline and script stay stable; Tier 2 never displaces graded core content |

## Review notes
