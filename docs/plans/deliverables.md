# deliverables: Report, slides, video, user manual and packaging

status: in-progress
plan owner: Chee Long · implementers: all five members, working together · reviewer: a fresh session · phase 5
([PLAN.md section 13](../../PLAN.md#13-phases)) · depends on: every Tier 1 workstream for final acceptance;
`benchmark` final measurements for report section 6 and video part iv

**Current report boundary (12 November 2026):** the application and required November benchmark programme are
complete within scope. The [authoritative November index](benchmark.md#authoritative-november-evidence-for-report-and-slides)
supplies report figures and preserves their measured revisions; the former October trial fallback is historical.
The [reviewed report snapshot record](#report-freeze-12-november-2026) covers the restored XSite template, all ten supplied
lecture PDFs and the checked exports. Report reviewed; final submission export follows administrative completion.
Slides, video and submission acceptance remain separate. The demo story
in [OVERVIEW.md section 3](../OVERVIEW.md#3-the-demo-story) stays the video's spine.

## Contract

**Goal.** One zip, submitted on 28 November (deadline 29 November, 23:30 Singapore time), that earns the Excellent
band for presentation (25%) and report (25%) and shows the project-quality work (40%) clearly
([RUBRICS.md section 5](../../RUBRICS.md#5-assessment-criteria)). The team writes, edits and presents together.

**In scope**

| Area | Deliverable |
|---|---|
| Report | PDF from the XSite template; at most 10 pages in Calibri (Body) 12, body tables included, excluding cover, references and appendix; outline and page budget below |
| Theory map | Appendix: relevant module concepts, where Mercer uses them, and source/test evidence; distinguish theoretical reasoning, engine-provided behaviour and topics outside scope |
| Slides | `.pptx` that stands on its own (the brief: "informative enough about the project details"): architecture, core ER diagram, MongoDB data model, the comparison table, benchmark tables and demo screenshots; each presenter's name bottom-left on the slides they present |
| Video | `.mp4`, target 9:30, hard limit 10:00 at normal speed; parts i to iv in the brief's order; all five members present, with a name overlay during demo footage as well as on slides; generated content keeps its visible labels (AGENTS.md rule 9) |
| User manual | README.md reordered so a marker reads setup, data load and demo logins in sequence near the top, with a note for starting from the extracted source zip; developer, CI and benchmark material after the user sections |
| Packaging | `scripts/package_submission.py` builds the zip from a committed ref; `--check-only` passes |
| Records | CONTRIBUTIONS.md with every student ID and each member's work; a deliverables line in docs/AI_USE.md; Olist CC BY-NC-SA attribution in the report's references; every member completes the peer-review survey |

**Out of scope:** new application features (frozen); Tier 2 work, which needs its own approved plan after the
8 November check-in; editing or re-deriving benchmark numbers by hand.

### Report outline and page budget

9.25 pages budgeted, with figures inside each section's pages; 0.75 page of slack. The body carries a core ER diagram;
the full one goes in appendix B.

| # | Section | Pages |
|---|---|---:|
| 1 | Introduction: the marketplace, three roles, why two databases | 0.5 |
| 2 | Dataset and database construction: Olist, cleaning ledger, the import into both stores, generated content and its labels | 1.0 |
| 3 | Relational design: ER diagram, 3NF, constraints, triggers, roles and privileges | 1.5 |
| 4 | NoSQL design: embed against reference, validation, GridFS, time series, live schema evolution | 1.25 |
| 5 | Implementation: CRUD on both stores, checkout under concurrency, cross-store search, reviews and rating, dashboard, activity | 1.5 |
| 6 | Performance analysis: method and fairness, B1 to B6 as ratios, query plans, threats to validity | 1.75 |
| 7 | Discussion: SQL against NoSQL beyond speed; the delivery-delay finding and its implications | 0.75 |
| 8 | Testing and quality: real-database tests, browser journeys, CI gates | 0.5 |
| 9 | Reflections: changes since the proposal, limitations, future work | 0.5 |

Appendices (outside the page count): A theory map; B full ER diagram and cleaning ledger; C generated benchmark
tables; D AI use; references, including the Olist licence.

### Notes to carry into the report and video (collected during the improvements backlog)

Added 8 November 2026 on Erfan's instruction, so nothing is forgotten when the report is written.

- **Dataset framing (section 2, and the video's background part).** Olist is real, multi-table and large (orders,
  payments, deliveries, reviews, sellers, geography), which is what "appropriate and sufficient data" asks for. Say
  plainly what is real and what is generated: Olist anonymised product names, descriptions, photos and stock, so those
  are generated, labelled on every page (AGENTS.md rule 9) and flagged in the data (`has_generated_content`). Describe the
  generator and the flags as the method, not as a patch.
- **Use the scale as a strength.** The full-data benchmarks, the whole-dataset review aggregation and the 34,000-product
  search are what make B1 and B2 meaningful; a toy dataset could not show them.
- **Limitations (section 9).** One main dataset (a second was considered and dropped to protect scope); generated product
  text; machine-translated reviews with occasional odd phrasing, labelled as such; Olist category names corrected only on
  display (a display-name map), never in the stored data.
- **Security wording (section on roles and security).** Say "tenant isolation for sellers, a second layer under the seller pages" ([seller-rls](seller-rls.md)), never "the database enforces all isolation". PostgreSQL confines a seller's session to its own orders, lines, refunds and products and hides checkouts and payments; the application filters remain. State the limits: customer sessions are not confined, the owner role bypasses by design, policies limit rows not columns, and MongoDB has no equivalent, so seller-scoped reviews stay application-enforced (a point for the SQL against NoSQL comparison). The best story is the money-trigger finding: a function that runs with the caller's rights and reads a restricted table quietly stops checking.
- **Reviews against generated names.** The reviews are real Olist comments, but the products they were written for were anonymised, so a
  review can mention an object the generated name does not (a "curtain" under a duvet cover). The limitation to state: reviews are
  real, products are generated, and the link between them is the Olist product id. The showcase products were chosen for reviews that
  talk about delivery and service. Reviews also contain Olist's own anonymisation, such as Game of Thrones house names for shops.
- **Demo path.** The video walks the showcase products on the home page (proper names and photos), not arbitrary
  products. The showcase is demonstration data set by `seed_demo`; the clean data and checksums are untouched.
- **The dashboard during the demo (review round G).** Its sales-history blocks stop at the reporting date (the last
  imported day), so a purchase made on camera changes the stock column and seller Insights, never the category or
  seller-risk blocks. Do not say the dashboard updates with the demo purchase.
- **Benchmark provenance.** The 2 November run came from another machine and is superseded; the final run is on the
  designated machine named in `host.json`. Mention the earlier out-of-memory kill and the identical-limits rerun as an
  honest method note.

### Video outline (target 9:30)

| Part | Time | Covers |
|---|---|---|
| i. Background | 0:00–1:05 | The idea, three roles, Olist and its cleaning, architecture |
| ii. Relational | 1:05–3:50 | Design and constraints; checkout across sellers, shipping, cancellation; triggers; the dashboard and the delivery-delay finding |
| iii. NoSQL and comparison | 3:50–7:00 | Faceted search, live schema evolution, CRUD across both stores and GridFS, reviews, activity; the comparison table with the B3 last-unit and B6 lost-update results |
| iv. Performance | 7:00–8:45 | Method, B1, B2, B4 and B5 headline ratios with what each means, a query-plan story |
| Close | 8:45–9:30 | Testing and CI; implications; conclusions |

**Comparison table (part iii and report section 7):** flexible attributes, integrity, concurrency, schema evolution
and data modelling, each compared across PostgreSQL and MongoDB. Placement follows
[benchmark amendment i](benchmark.md#decisions): B3, B6 and this table in part iii; B1, B2, B4 and B5 in part iv.

**Exit check**
1. The report PDF is at most 10 pages excluding cover, references and appendix, in Calibri (Body) 12, on the XSite
   template. Every figure and table caption in the report, and every table and chart in the slides, names its
   generated source (benchmark report, cleaning ledger, CI run).
2. The video plays in at most 10:00 at normal speed, in the order i to iv, with every member presenting and named on
   screen.
3. The theory map rows are checked against the module's lecture list, and each evidence path exists; tests are not formal proofs of normal forms or other theoretical properties.
4. The submission includes runnable source code and data, plus README.md instructions for environment setup,
   configuration and running the application, as required by RUBRICS.md. No separate other-machine or clean-machine
   installation acceptance is required (owner amendment, 12 November 2026). This does not claim such a test occurred.
5. `scripts/package_submission.py` builds the zip from the submitted commit; `--check-only` reports no FAIL, and every
   WARN has been looked at.
6. CONTRIBUTIONS.md has every student ID and each member's work; docs/AI_USE.md has a deliverables line.
7. A fresh session reviews the report and video against the RUBRICS.md Excellent bands before submission, with one
   fix round.
8. Submitted by 28 November, with the XSite confirmation kept.

## Milestones

| Date | Milestone |
|---|---|
| 30 Oct | This plan approved |
| 4 Nov | Historical benchmark target and October fallback; superseded for report figures by the authoritative November evidence linked above |
| 7 Nov | Report sections 1 to 5 drafted; slide skeleton; material for the check-in |
| 8 Nov | Professor check-in; Tier 2 decision |
| 15 Nov | Full report draft; script frozen; user manual ready |
| 18 Nov | Demo footage captured (decisions c and d) |
| 21 Nov | Voice-overs recorded (24 November is the hard limit) |
| 25 to 27 Nov | Video edit, report and video review, final pass, user manual and packaging |
| 28 Nov | Submit |

### Recording-day checklist

[PLAN.md section 16](../../PLAN.md#16-risks) links here. On the prepared full-data stack:

1. Run the browser suite once against it ([README Continuous integration](../../README.md#continuous-integration)).
2. Run `seed_activity`, then place a few demo purchases for the demo seller's products before filming Insights.
3. Pre-stage the demo state the script needs; preload the operator dashboard.
4. Log in from the ignored `.env`; never show a password or `.env` on screen.

### Recording runbook (backlog #70, #38, #47, #26)

Added 12 November 2026. The video follows the brief's order (i background, ii relational, iii NoSQL with the
comparison, iv performance, close). The spoken script is the speaker notes of the team's slide deck: every slide's
notes start with its presenter placeholder and time slot, and carry the demo-clip cues below. Presenters are
placeholders until the team assigns names: **[Presenter 1]** slides 1–5 and 23–24, **[Presenter 2]** 6–8 and 22,
**[Presenter 3]** 9–11 and 19–21, **[Presenter 4]** 12–14, **[Presenter 5]** 15–18. These are the final 24-slide numbers: the four section-divider slides are deleted by hand in Canva (the editing tools cannot delete a page) and the page numbers already skip them. Every figure on a slide names its
source file; the benchmark figures come from the [authoritative November index](benchmark.md#authoritative-november-evidence-for-report-and-slides).

**Before filming** (once, on the full-data stack from the [README](../../README.md#load-olist-and-demo-accounts)):
`seed_activity` so Trending and Insights have data; the browser suite once; a browser at desktop width, logged out;
two terminals at the repository root. Avoid products with reviews dated after the filming date (disclosure #66 in
[improvements](improvements.md#disclose-in-the-report-no-code-change)): the showcase products on the home page are
safe to use.

| Clip | Slot | Who | What to show |
|---|---|---|---|
| R1 | after slide 7 | terminal | `database_says_no.sql` ([README](../../README.md#database-demonstrations-psql-and-mongosh)): DDL, `TRUNCATE`, money `DELETE`, audit edit, illegal status, back-dated delivery and the payment change refused at `COMMIT`; then row-level security showing only `demo-seller`'s orders and no checkouts |
| R2 | after slide 8 | a demo customer | Add one product each from Paulista Watch & Gift House (`demo-seller`), Ibitinga Linen & Home (`demo-seller-2`) and Santo Andre Beauty Studio (`demo-seller-3`), open `/cart/`, check out: one checkout, three orders; open one product to show its stock went down |
| R3 | after R2 | two terminals | `last_unit_setup.sql`, the two-terminal race (B waits, then sees stock 0, `UPDATE 0`, CHECK refusal), `last_unit_restore.sql` with its audit rows |
| — | off camera | the three sellers, `demo-operator` | Each seller ships its order from R2 (`/seller/orders/`); the operator marks them delivered (`/operator/orders/`). Needed for N3: demo customers have no imported orders |
| R4 | after slide 9 | `demo-operator` | `/operator/dashboard/`: stock-out list and seller-risk table. Do not claim the purchase changed it (sales history stops at the reporting date) |
| N1 | after slide 13 | logged out | Search `garden tols` (garden-tool products despite the typo), then pick a Tool type filter and show the counts |
| N2 | after N1 | `demo-operator`, then a garden-tools seller | `/products/operator/categories/` → Garden tools → add `water_resistant`, type Yes or no; then the seller's product form shows the field |
| N2b | right after N2, about 5 s, optional | logged out | Open the shop, choose Garden tools: the new attribute is now a filter field (`attribute_definitions` and `SearchForm` in `src/catalogue` build the filters from the category template). Existing products have no value for it yet, so its counts are zero until a seller sets one; do not claim otherwise |
| N3 | after slide 14 | the R2 customer | Review the delivered line from `/orders/`; open the product: rating and latest reviews updated |
| N4 | after N3 | logged out, then `demo-seller` | Home page Recently viewed and Trending now; `/seller/insights/` views-to-sales |
| N5 | after N4 | terminal | `database_says_no.js` (validator, score 6, duplicate review, sixth embedded review, `admin` refused), then `check_specs` |
| Q1 | slide 22, optional | browser | The green CI run on `main` linked in the slide 22 notes |

All terminal clips were rehearsed on 12 November 2026 against a full-data stack built from a `git archive` zip of
`main`; each statement was refused as described, the MongoDB script wrote nothing, and the restore put the stock
back. Raising stock from 0 in the restore fires the restock trigger, so run the restore before filming a wishlist
alert if both are shown.

## Decisions (all approved by Chee Long, 30 October 2026)

| ID | Proposal | Why |
|---|---|---|
| a | The team writes, edits and presents together, with no single report editor (closes PLAN.md open decision D2) | The work and the credit are shared equally; peer review weights the mark |
| b | The report is drafted in the XSite Word template in a shared drive, not in the repository | The template is Word; the docs rules allow no new Markdown file; only the PDF is submitted |
| c | Footage by 18 November, voice-overs by 21 November; 24 November is the hard limit | Insights is near-empty by 25 November (PLAN.md section 16). Demo purchases add only a handful of sales, not the imported history, and footage on 18 November leaves time to re-shoot |
| d | All demo footage is captured in one session on one prepared full-data stack; each presenter records their own voice-over (or face) for their part | The checklist needs one prepared stack, not five imports and five preparations. Presenters narrate footage they may not have driven, so the script names every click |
| e | If Tier 2 is earned on 8 November, it is funded from the slack: at most 0.5 page and at most 15 seconds, so the video target becomes at most 9:45 | Tier 2 never displaces graded core content, and the video keeps a margin under 10:00 |

Decision a is recorded in PLAN.md section 12 and closes open decision D2 in section 15.

## Review notes


30 October 2026, Claude Code (Opus 5.5), fresh session. Reviewed commit 490e140 against RUBRICS.md, PLAN.md
sections 4, 9, 10 and 12–16 and OVERVIEW.md sections 3 and 7. Spot-checked the theory map in the code (deferred
money triggers, the `restock_one_unseen` partial unique index, `$facet`, the time-series TTL, B6 isolation
strategies, the Bayesian update pipeline, both views) and confirmed the packager ships the Olist data;
`scripts/check_docs.py` passed. Verdict APPROVE WITH CHANGES: settle decision d against the single-stack recording checklist, move the clean-machine run earlier and run it from
`source_code.zip`, give implications more video time, add CRUD and a named comparison table, and add a proof column
to the theory map.

30 October 2026, fix round (Claude Code, the session that wrote the plan). All 15 findings applied
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
align decision c's wording with the 18 November footage date.

30 October 2026, the third review's tweaks (Claude Code, the session that wrote the plan): both applied.

30 October 2026, Claude Code (Opus 5.5), fresh session, fourth review. Reviewed commit f0bf99b: the benchmark
fallback links both 28 October runs, correctness from `fix-full` and draft ratios from the full-data `fix-trial`
measure run, and both summaries are committed. Decision c now matches decision d and the 18 and 21 November
milestones. `scripts/check_docs.py` passed. Verdict APPROVE; the plan is ready for the owner to record approval.

30 October 2026, the fourth review's cosmetic points (Claude Code, the session that wrote the plan): both applied.

30 October 2026, owner direction (Chee Long): the team does everything together and the plan stays high level.
Removed every per-person assignment (section owners, presenters, the named editor, footage capturer, assembler,
clean-machine runner); decision a now closes D2 with no single editor. The report outline
and video keep their budgets and timings without per-item detail; the draft theory-map rows and the per-part demo
and slide lists were removed and remain in commit 875a325.

30 October 2026: the video outline places B3, B6 and the comparison table in part iii and B1, B2, B4 and B5 in part
iv, as benchmark amendment i does.

30 October 2026: Chee Long approved the plan and decisions a to e.

30 October 2026, pull request review (Claude Code, fresh session): the milestones now show the plan approved on
30 October rather than 2 November, and the 4 November benchmark milestone points to the fallback runs.

31 October 2026, Claude Code (the session that wrote the brief; not a fresh session): re-checked the fix round and
approved both preparation worktrees. The documentation check passed; Chee Long authorised committing, pushing and
opening the two PRs after this approval.

### Report freeze, 12 November 2026

**Report status:** report reviewed; final submission export follows administrative completion. The checks, named freeze version and hashes below identify the historical 12 November snapshot. They do not make it an immutable final submission artifact or require a shared copy of that exact PDF before close-out. Administrative changes may require a later export, under the [owner's snapshot-status decision](../DECISIONS.md#report-terminology-and-snapshot-status-12-november-2026). The overall deliverables workstream remains in progress. The earlier five-file documentation approval and subsequent fresh Opus 5.5 seven-file approval are recorded separately below; the listed minor follow-ups were applied under the latter approval.

**Report review history and fix rounds.** The owner supplied independent Claude Code Opus report reviews: the earlier fifteen-finding review, followed by wording/layout rechecks and the report/close-out checklist. Codex applied those report corrections in the live Google Doc. That supplied report checklist accepted the B2d denominators, Redis wording and qualifications, reflection and readable repeated-header Table 3 split; it reported the two discussion headings as orphaned and the template/lecture/freeze checks as not evidenced. The Codex authoring pass refreshed the live document, explicitly checked the heading chain and verified the exports recorded below. It was the fix/check pass, not an independent review of its own edits. The repository-only housekeeping pass does not edit Google Docs.

Supplied review-text identifiers (recorded here on 12 November; not new review-execution claims):

- Attachment `44390e40-5a28-4606-bc8b-96c31f6199c6/Pasted text.txt`, SHA-256 `c3bc8c12f6880cf774ac546fac5b6632b9a871fca96270aa638c9314b110cec4`.
- Attachment `2947f129-bf35-4888-98be-f0187b6bf941/Pasted text.txt`, SHA-256 `abddf6a6dd4dc788f549d1f13364bfb87d1e8804a5e905bebcdbb931d3dee622`.

**Official template.** Inspected the actual restored `[GroupID 00x] INF2003 Projec Final Report - Template.docx`, not the presentation template; SHA-256 `9b29a3f5813aa9d3b08bbfaa07616831162fe075f945551f62a1596c25361d72`. Its five main sections, their intended content, cover fields, source-code appendix and references are covered. The report matches its A4 geometry: 1-inch left/right margins, 1 1/12-inch top/bottom margins and 0.491667-inch header/footer distances. The SIT header, footer wording/page fields, cover title and “Submitted as part of the requirement for INF2003 Database Systems” remain. Added an explicit pinned source-code link in Appendix I and restored the centred “END OF REPORT” marker. The illustrative prose, example bibliography, sample page count and placeholder labels are not report content. Calibri 12 follows RUBRICS.md rather than the template’s default Arial/example-reference styles. All five names/IDs were checked against CONTRIBUTIONS.md; actual work was not assigned or confirmed on anyone’s behalf. The template’s `<Date and Time>` placeholder does not define a deadline or freeze date, so the inherited labelled “Report date: 13 November 2026” was retained; no preparation time was invented. The named freeze below records its own actual date.

**Lecture inventory and reading.** Codex read every PDF page in the owner-supplied set: 10 readable files, 274 PDF pages, no byte-identical duplicate files. Repeated introductory/summary slides are not duplicate decks. Page references below are PDF page numbers starting at 1, not inferred calendar dates or slide labels. Diagrams and image-based examples were rendered where extraction was insufficient. The course PDFs are reference material, not redistributed source-archive contents.

| ID | Exact supplied PDF | Pages read | SHA-256 | Additional rendered diagram pages |
|---|---|---|---|---|
| L01 | INF2003 Lec01.pdf | 1–35 | `ed0e41cfd360d845c75aa906d9cec973eb1e46dc385d3a7350e2d39a3e3e1d0f` | 14, 15 |
| L02 | INF2003 Lec02.pdf | 1–46 | `7d10b00d434257bb75ada443d55e525abd5671748fd70b11a6dbac2c2b467791` | 6, 7, 12, 13, 15, 16, 17, 19, 20 |
| L03 | INF2003 Lec03.pdf | 1–43 | `05dd18eec484d07788d9c3050b0ca763a4a879380d273ab7dd1d8cb78ab5d95c` | 23, 24, 25 |
| L04 | INF2003 Lec04.pdf | 1–41 | `20ccac6420a26708c9b82ea55c6b34a4c4e286df485767f1f38fc1c1a6a155bb` | 26, 27, 28, 30, 32 |
| L05 | INF2003 Lec05.pdf | 1–36 | `5db1cc18726f1c3f82fed5be8eedddd6d76a0aeb12b73c2a7535d7bbdfabd8b5` | 7, 19, 20, 25 |
| L06 | INF2003 AY2627 T1 Lec 06 261016.pdf | 1–16 | `d20ea0e80a1f45574b1462b69f164aa3f92d3f40a0d52cac74cc9f0367a29f1e` | 6, 8, 9, 10, 11, 12, 13, 14, 15, 16 |
| L07 | INF2003 AY2627 T1 Lec 07 261021.pdf | 1–14 | `61547def2a70578d38919ab89ad6f7ca0d6cba3ca3599233d3d0dac336c15a61` | 6 |
| L08 | INF2003 AY2627 T1 Lec 08 261102.pdf | 1–14 | `e4cd29a9d6237153cd54e1db21866d95fca50105f2e6653d3507e49ffbed56ab` | 5, 6, 12, 13 |
| L09 | INF2003 AY2627 T1 Lec 09 261102.pdf | 1–14 | `913cd4c0d2aa2f254625b4a7ce2ba8de285075ebadc11dcaef1d268592e342a2` | 3, 7, 8, 12 |
| L10 | INF2003 AY2627 T1 Lec 10 261109.pdf | 1–15 | `568314f70870bdb74742bc7a1ac63814bbf19476bb9bddd9761cca4f08d24640` | 5, 7, 9, 11 |

**Traceable lecture map.** This record and report Appendix II/Table A1b connect lecture/PDF page → concept → report location → source/test evidence at `d23011e5613779bf4735884f568409d7de14e0cf`. A file’s presence is not an executed check; the cited main CI supplies revision-specific execution evidence. Normalisation uses stated functional dependencies and intentional redundancy, without a whole-schema 3NF/BCNF proof. Features that merely share vocabulary with a topic are not counted as implementations.

| Lecture / PDF pages | Concept | Report section | Verified source/test paths | Scope and interpretation |
|---|---|---|---|---|
| L01 pp. 7–16, 18–24, 26–31 | DBMS layers, schemas, keys and ACID | 2.1, 3.1–3.2 | `src/catalogue/models.py`; `src/config/privileges.py`; `tests/test_schema.py`; `tests/test_audit_privileges.py` | Database layers and enforced keys/privileges; no claim that tests prove all ACID properties. |
| L02 pp. 5–26, 33–44 | ER relationships, participation, keys, types and constraints | 3.1; Figures 2, A1–A2; Appendix I | `src/orders/models.py`; `src/catalogue/models.py`; `tests/test_schema.py` | Business cardinality is distinguished from FK enforcement; weak-entity/ISA examples are not claimed as implemented features. |
| L03 pp. 3–6, 12, 19–30, 32–41 | CRUD, joins, aggregates, NULL, views and SQL functions | 3.2; Table A1 analytical SQL row | `src/orders/services.py`; `src/dashboard/queries.py`; `src/catalogue/migrations/0001_initial.py`; `src/dashboard/migrations/0001_daily_product_sales.py`; `tests/test_dashboard.py` | Ordinary visibility view versus stored materialized summaries; RANK/LAG are extensions, not claimed as lecture examples. |
| L04 pp. 4–36 | Functional dependencies, normal forms and decomposition | 3.1; Table A1 caption | `src/catalogue/models.py`; `docs/DATA_MODEL.md`; `tests/test_schema.py` | Category separation illustrates normalisation reasoning. No complete FD closure, whole-schema 3NF/BCNF proof or decomposition algorithm is claimed; tests verify constraints only. |
| L05 pp. 6–22, 24–35 | Relational algebra, equivalent queries and execution plans | 3.2, 4.1; Appendix III plans | `src/dashboard/queries.py`; `tests/test_dashboard.py`; `benchmarks/workloads/b1.py`; `benchmarks/workloads/b4.py` | Fast/window query equivalence and retained plans illustrate less work for the same result; optimizer internals are engine-provided. Hints remain diagnostic. |
| L06 pp. 4–16 | File organisation, hash versus tree access, B+ tree operations | 3.1, 4.1; Appendix III plans | `src/config/mongo_schema.py`; `benchmarks/workloads/b4.py`; `tests/test_mongo_schema.py`; `tests/test_schema.py` | Indexes are configured and measured; tree splits/merges are engine internals. No custom B+ tree/hash-index implementation or universal index speedup is claimed. |
| L07 pp. 3–13 | Transactions, scheduling, ACID, locks, retries and recovery | 3.2–3.3, 4.1, 4.3, 5 | `src/orders/services.py`; `src/reviews/services.py`; `benchmarks/workloads/b6.py`; `tests/test_checkout_concurrency.py`; `tests/test_order_scores_maintenance.py` | Atomic checkout and MongoDB transactions have separate store boundaries. B6 is a correctness demonstration. Timed restore/failover remains optional future work; no production recovery guarantee. |
| L08 pp. 3–14 | Key-value/document models, migration choices; other NoSQL families | 3.3–3.4, 4.3 | `src/config/mongo_schema.py`; `src/config/redis_store.py`; `tests/test_mongo_schema.py`; `tests/test_dashboard_cache.py` | Validated flexible documents and disposable Redis support are implemented. Columnar/graph stores and sharding are outside scope; an ER diagram is not a graph database. |
| L09 pp. 3–14 | Hash chains, consensus, proof of work and forks | Outside scope; distinguish 2.2 checksums and 3.1 audit | `scripts/clean_olist.py`; `docs/DATA_MODEL.md`; `tests/test_audit_privileges.py` | Checksums and audit records do not implement a blockchain, consensus ledger or mining. No new feature requirement follows from this lecture. |
| L10 pp. 2–15 | ETL, OLTP/OLAP, dimensional schemas and cubes | 2.2, 3.2; 4.1 refresh/read comparison | `scripts/clean_olist.py`; `src/config/management/commands/import_olist.py`; `src/dashboard/queries.py`; `tests/test_import.py`; `tests/test_dashboard.py` | Cleaning/import is ETL and historical aggregates support analysis. A dedicated star/snowflake warehouse, OLAP cube, pivot or interactive drill-down is outside scope. |

**Artifact and verification.**

- Live report: [Google Doc](https://docs.google.com/document/d/1pjyGPMGeqvIRNAg3s2MFc5tN-PKb1Qh5RAlJWqiU27I/edit).
- Historical named Google Docs version: **Report freeze 2026-11-12 — template + 10 lectures — d23011e**; the authoring UI confirmed “Named in version history” and “Saved to Drive”. The existing version name is retained as provenance, not current final-submission status.
- Reviewed PDF snapshot (local authoring artifact, outside Git; historical filename retained): `C:/Users/limch/.codex/visualizations/2026/11/12/01a1cdc1-8a19-7a03-a867-8c1f5a8ed22b/report-template-lecture-closeout/Team82_Report_Frozen_2026-11-12.pdf`.
- PDF SHA-256: `d9a646d212320b2368e56946103e9bf4ed6d7ab103a2d9261ad60517dae0cd89`.
- Reviewed DOCX snapshot: `C:/Users/limch/.codex/visualizations/2026/11/12/01a1cdc1-8a19-7a03-a867-8c1f5a8ed22b/report-template-lecture-closeout/Team82_Report_Frozen_2026-11-12.docx`; SHA-256 `f43cc219d8a142ef7331df5f67bac4b17497d1a3b3f4b7acd7cc8328739487a7`.
- Checked 12 November 2026: 9 body pages (physical pages 2–10), 21 total. Cover, references and appendices excluded; body prose, tables and captions are Calibri 12. Every rendered PDF page and page boundary was inspected. Post-version exports rendered pixel-identically to the reviewed export.
- Exported DOCX has `keepNext=1` on “4. Discussions”, “4.1 Performance method and retained findings” and “B1 and B4 plan interpretation”. Both discussion headings and their following body open page 7; the appendix heading shares page 21 with its first source. Table 3’s existing split and repeated header remain readable.
- Literal SQL/PyMongo and all original report numerical tables are unchanged; zero accidental equation objects. The only main-body wording change explains functional-dependency design choices instead of asserting blanket 3NF. Source/test paths and named tests were checked against the pinned tree; existing diagrams and links were preserved.
- Implementation/evidence snapshot: `d23011e5613779bf4735884f568409d7de14e0cf`; [CI 43078190939](https://github.com/ZadeNova/INF2003_Database_Project/actions/runs/43078190939) completed successfully there. B1–B6 measured at `505222f41b7473260ed9f40bb3bbaf8eafa46757`; page timing at `df03cb33c12deffceb6a1d298e7a2bbbc3e0a97e`; Redis v2 at `b82ac876e9ff0fa4d3f530d81d70fa2b434c8e43`. No experiment was rerun or relabelled.
- Documentation record at the original authoring checkpoint: uncommitted work on `deliverables/report-template-lecture-closeout`, based on the snapshot above; no new commit SHA or hosted CI was claimed at that point. A final submission revision has not been selected.

**Packaging readiness, not final-package acceptance.** Inspected `scripts/package_submission.py`: the outer archive takes a report PDF, slides PPTX and video MP4 plus root-relative `source_code.zip` generated by `git archive` from an explicit committed ref. A temporary complete source archive of the report snapshot contained every one of the 65 report-cited implementation/evidence paths at its expected root-relative location. Retained benchmark/golden/data evidence bytes matched Git blobs; 44 source/documentation files had only Git’s configured CRLF conversion. The source safety checks passed for README, Compose, src and the secret-file/token checks. No excluded report evidence was found. Archive size: 192146116 bytes. The eventual submission revision must include the report close-out documentation commit, including this inventory and review record cited by Appendix II. The earlier `d23011e` archive predates these uncommitted records and does not certify their inclusion or the final submission ref.

No approved final slides PPTX, final presentation MP4 or explicitly selected submission revision was provided/found among the relevant local deliverables. Therefore no final outer submission archive was built and no final `--check-only` result is claimed. When those inputs exist, compare source/tests/benchmarks/data/scripts/analytics/Compose against the pinned report boundary, require CI on the selected ref, build the outer archive, check its nested citations and run `--check-only`. Offline source paths avoid depending on private GitHub links for evidence; final size/access arrangements still belong to submission acceptance. No permissions were changed.

**Supplied fresh documentation review.** The owner supplied a fresh Claude Code / Opus review in attachment `f93f3b7e-6ff0-41db-89d8-0a317cc0b76f/Pasted text.txt` (SHA-256 `e8cb0c14f386d89dc4c82c8e47d414f0a8359cb0f4c5770652f3de15afd5e696`), verdict **APPROVE WITH NON-BLOCKING NOTES**, with no commit blockers. It reviewed the earlier five-file uncommitted diff at `d23011e`: PLAN.md, docs/AI_USE.md, docs/plans/benchmark.md, docs/plans/deliverables.md and docs/plans/seller-rls.md. It independently checked the snapshot hashes/rendering, heading flags, font/code evidence, template/lecture inventory, cited paths, merge/CI facts and temporary archive, and ran the documentation/packaging host checks. It did not reread all lecture pages or verify the two earlier review-attachment hashes, the Google Docs named-version UI confirmation or pixel-identical export claim. These limits do not become new completed checks here.

The review required recording its outcome before commit and suggested non-blocking follow-ups. The housekeeping pass recorded the earlier approval, required the eventual submission ref to include these documentation records, repaired the seller-RLS decision link/spacing, added its documented AI-use history, recorded the owner's accepted terminology and identified the report-editing model from session metadata. The owner's later amendments confirm contributions, remove the internal installation acceptance and designate the PDF as a reviewed snapshot. The older recommendation to share that exact PDF is superseded by this snapshot-status direction. These later amendments were outside the earlier five-file approval; the resulting seven-file diff subsequently received the fresh Opus 5.5 approval recorded below.

**Separate administration:** subsequent contribution updates if needed (initial member-confirmed summaries are recorded in CONTRIBUTIONS.md); final report export after administration, submission ref/archive and rubric-required runnable source/data with setup/configuration/run instructions; slides/video completion and review; peer-review surveys; submission and receipt retention. There is no active other-machine installation acceptance or exact-historical-PDF sharing requirement.

**Attribution decision resolved (12 November 2026).** The owner confirmed reuse and approved presenting Mercer as a new
INF2003 project built on selected earlier Django components. The [decision record](../DECISIONS.md#approved-project-framing-and-reuse-attribution-12-november-2026)
contains the approved wording and concrete reused foundations. The live report now leads with the new-project framing
while retaining explicit attribution and AI disclosure. No entirely-from-scratch claim is made. Earlier review-gate
references to unresolved attribution describe the prior housekeeping scope and are historical.

**Prior authoring-pass checks (12 November 2026, Codex; historical):** `scripts/check_docs.py`, `git diff --check` and the host documentation/packaging tests passed for the earlier five-file diff. The supplied Opus review independently reran them, using a writable scratch directory for pytest. Later housekeeping checks and fresh review are recorded separately below.

### Owner amendment: installation acceptance (12 November 2026)

The owner explicitly removed the internal other-machine installation requirement and its pending admin task.
Exit check 4 now retains the rubric requirement for runnable source/data and setup/configuration/run instructions.
Earlier review notes mentioning clean-machine deadlines are historical and superseded by this amendment.
No other-machine test is claimed. See [the decision record](../DECISIONS.md#installation-acceptance-scope-12-november-2026).

### Owner confirmation: contributions and evidence terminology (12 November 2026)

Chee Long supplied the five member-confirmed contribution summaries, now recorded in CONTRIBUTIONS.md without
invented dates, finer allocations or final-artifact acceptance. As plan owner, he explicitly accepted “evidence paths”
and the clarification that tests are not formal proofs of normalisation. This accepts the corresponding theory-map
contract and exit-check wording; it adds no new test or technical deliverable.

### Repository housekeeping review gate (12 November 2026)

Branch: `deliverables/report-template-lecture-closeout`; reviewed base:
`d23011e5613779bf4735884f568409d7de14e0cf`. The reviewed uncommitted diff's SHA-256 is
`b929b5e529a96f5f29705446c74f80075a2a1eccbe0467cc5a4a6cd5e93f5306`; Codex verified an exact match before
applying the approved minor follow-ups. Its seven-file scope is CONTRIBUTIONS.md, PLAN.md, docs/AI_USE.md,
docs/DECISIONS.md, docs/plans/benchmark.md, docs/plans/deliverables.md and docs/plans/seller-rls.md. The pre-existing
member summaries are preserved. GitHub main and the recorded merged PR/CI facts were checked at the pre-review
checkpoint; the pre-commit fetch still found main at the reviewed base with no divergence or remote branch to integrate.

**Fresh Claude Code Opus 5.5 review: APPROVE WITH NON-BLOCKING NOTES; no commit blockers. The documented minor
follow-ups were applied and affected checks rerun.** The owner relayed this completed review and its delivery
permission in the final fix-round request (attachment `04f8e6a0-adcc-490e-be30-b01bffcdc245/Pasted text.txt`). This
seven-file approval includes the owner amendments and housekeeping that were outside the earlier five-file review.
The approved follow-ups remove the unsupported user-manual planning-role assignment, restore the closed Phase 4
criterion while preserving the later installation-scope amendment, restore the two 11 November decision paragraphs
with separately dated status updates, specify the SECURITY DEFINER money-check trigger functions and checkout
locking in the seller-RLS AI record, and record this review's outcome. The confirmed contribution summaries,
numerical evidence, measured revisions and snapshot hashes are unchanged.

The review explicitly permits these narrow follow-ups and the documentation commit, push and draft PR without
another broad review cycle. The owner has authorised delivery with the required AI co-author trailer, safe fetch
and divergence checks, and staged documentation checks. Google Docs, application code, benchmark results,
slides/video, final packaging/submission and the unresolved reuse decision remain outside this pass. Do not merge
or force-push; a substantive integration conflict would require stopping rather than overwriting work.

**Pre-review housekeeping checks (12 November 2026, Codex; historical):** `python scripts/check_docs.py` and
`git diff --check` passed. Host `python -m pytest --noconftest -q -p no:cacheprovider --basetemp <writable-scratch>
tests/test_check_docs.py tests/test_package_submission.py` passed with no failures or skips. The scratch directory
was under the authorised local report-housekeeping output folder. These are new executions for this pass, not copied
authoring/reviewer results. The final scope check contains only the seven Markdown files above; application, tests,
benchmark/data artifacts, scripts, analytics and Compose are unchanged. The earlier contribution diff and generated
evidence records are preserved. At that checkpoint nothing was staged, committed, pushed or merged, and no draft PR
or final package was claimed. Final fix-round and staged validation are recorded below.

**Approved minor fix round (12 November 2026, Codex):** applied only the listed follow-ups under the supplied
seven-file Opus approval. `python scripts/check_docs.py`, `git diff --check` and the affected host
documentation/packaging tests passed with a writable `--basetemp` and no failures or skips. Repository-pinned Ruff
0.17.0 ran from the authorised scratch installation: the formatting check passed and the formatter left all files
unchanged. `python scripts/check_docs.py --staged` and `git diff --cached --check` passed. The staged scope is exactly
the seven authorised Markdown files; contribution summaries, lecture rows, numerical evidence, measured revisions
and snapshot hashes are preserved. No application, test, benchmark, data or configuration file changed. These
fix-round results are separate from the historical authoring checks and do not claim final-package acceptance.
