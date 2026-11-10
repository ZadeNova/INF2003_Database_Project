# deliverables: Report, slides, video, user manual and packaging

status: approved
plan owner: Chee Long · implementers: all five members, working together · reviewer: a fresh session · phase 5
([PLAN.md section 13](../../PLAN.md#13-phases)) · depends on: every Tier 1 workstream for final acceptance;
`benchmark` final measurements for report section 6 and video part iv

**Assumes:** the application is frozen (Phase 4 closed 30 October 2026); the XSite final report template is
downloaded; the demo story in [OVERVIEW.md section 3](../OVERVIEW.md#3-the-demo-story) stays the video's spine. The
`benchmark` final measurements target 1 November with 2 to 4 November as contingency. If they slip, section 6 is
drafted from two 28 October fix-round runs: the [full-data correctness run](../../benchmarks/results/2026-10-28T225445_d6fc7e44_fix-full/summary.csv)
and the [trial measure run](../../benchmarks/results/2026-10-28T230836_d6fc7e44_fix-trial/summary.csv) for draft
ratios, labelled as a trial not run on the designated machine, and regenerated from the final run.

## Contract

**Goal.** One zip, submitted on 28 November (deadline 29 November, 23:30 Singapore time), that earns the Excellent
band for presentation (25%) and report (25%) and shows the project-quality work (40%) clearly
([RUBRICS.md section 5](../../RUBRICS.md#5-assessment-criteria)). The team writes, edits and presents together.

**In scope**

| Area | Deliverable |
|---|---|
| Report | PDF from the XSite template; at most 10 pages in Calibri (Body) 12, body tables included, excluding cover, references and appendix; outline and page budget below |
| Theory map | Appendix A: each module concept, where Mercer shows it, and the file or test that proves it |
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
- **Reviews against generated names.** The reviews are real Olist comments, but the products they were written for were anonymised, so a
  review can mention an object the generated name does not (a "curtain" under a duvet cover). The limitation to state: reviews are
  real, products are generated, and the link between them is the Olist product id. The showcase products were chosen for reviews that
  talk about delivery and service. Reviews also contain Olist's own anonymisation, such as Game of Thrones house names for shops.
- **Demo path.** The video walks the showcase products on the home page (proper names and photos), not arbitrary
  products. The showcase is demonstration data set by `seed_demo`; the clean data and checksums are untouched.
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
3. The theory map rows are checked against the module's lecture list, and each proof path exists.
4. README.md is followed on a machine other than the one the app was developed on, from an extracted `git archive`
   zip of `main` (what the packager ships), to working demo logins by 15 November; any manual fix is merged. The
   check is repeated from the final submission zip by 27 November.
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
| 4 Nov | `benchmark` final measurements closed (target 1 November); if they slip, section 6 is drafted from the fallback runs under **Assumes** |
| 7 Nov | Report sections 1 to 5 drafted; slide skeleton; material for the check-in |
| 8 Nov | Professor check-in; Tier 2 decision |
| 15 Nov | Full report draft; script frozen; first clean-machine run done |
| 18 Nov | Demo footage captured (decisions c and d) |
| 21 Nov | Voice-overs recorded (24 November is the hard limit) |
| 25 to 27 Nov | Video edit, report and video review, final pass, repeat clean-machine run, packaging |
| 28 Nov | Submit |

### Recording-day checklist

[PLAN.md section 16](../../PLAN.md#16-risks) links here. On the prepared full-data stack:

1. Run the browser suite once against it ([README Continuous integration](../../README.md#continuous-integration)).
2. Run `seed_activity`, then place a few demo purchases for the demo seller's products before filming Insights.
3. Pre-stage the demo state the script needs; preload the operator dashboard.
4. Log in from the ignored `.env`; never show a password or `.env` on screen.

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
