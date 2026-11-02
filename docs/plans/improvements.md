# improvements: Prioritised backlog from the full-stack review

status: draft
plan owner: Erfan · implementers: per item, once settled · reviewer: a fresh session · phase 5
([PLAN.md section 13](../../PLAN.md#13-phases)) · depends on: the frozen Tier 1 application; `benchmark` close-out

**Source.** A review on 2 November 2026 of the code (read) and the running application (a fresh install that followed
the README on a second machine, the full Olist import, the full Docker suite, the project's browser journeys against
full data, and a role-by-role browser crawl at desktop and phone widths). No benchmark was run. How to reproduce is
under Review notes.

## Contract

**Goal.** One ranked list of what to fix, measure or write before submission, judged against the
[RUBRICS.md](../../RUBRICS.md#5-assessment-criteria) Excellent bands, so the team spends the remaining weeks where
the marks are.

**How an item is settled.** Erfan settles each item with the owner (Chee Long) before any work starts: accept,
change or drop, recorded under Decisions with the date. An item marked **approval** touches the frozen application, a
closed benchmark or an owner decision. It needs that sign-off, then a branch and pull request under
[AGENTS.md](../../AGENTS.md) (a plan amendment for `benchmark`). Docs-only items follow the small-change rule.

**Rules kept.** No hand-written test counts, timings or benchmark tables in the report or docs: link to
`benchmarks/results/` or regenerate (AGENTS.md, Documentation). Tier 2 work starts only after the 8 November check-in.

**Legend.** Effort: S (under 2 hours), M (half a day to a day), L (several days). ★ = suitable for Erfan to own.

## Backlog

### P0: blocks the grade

| # | Area | Item | Why it matters | Fix | Effort | Status |
|---|---|---|---|---|---|---|
| 1 | Deliverables | Report (10 pages), slides and video (10:00 maximum) do not exist; the packager refuses to build without them | Report and presentation are half the grade; implementation is judged through them too | [deliverables](deliverables.md) milestones: report draft by 15 Nov, footage by 18 Nov | L | open |
| 2 | Demo | Demo story step 1 ("hose nozle") returns no products on full data: no generated name contains "hose" or "nozzle". Typo tolerance itself works ("garden tols") | It opens the video | Choose a query that exists; update [OVERVIEW.md](../OVERVIEW.md#3-the-demo-story) and the script ★ | S | open |
| 3 | Peer review | [CONTRIBUTIONS.md](../../CONTRIBUTIONS.md) records almost only Chee Long; Joash's student ID is missing; others are "not yet recorded" | The final mark is weighted by peer review | Every member records their actual work ★ | S | open |
| 4 | Integrity | Reuse of the earlier module project has no written confirmation from the professors ([AI_USE.md](../AI_USE.md)) | The brief zeroes plagiarism and fails "total copy of existing code" | Email the professors and keep the reply ★ | S | open |
| 5 | Benchmark, MongoDB | B2 pipelines are not idiomatic: B2a joins `products` for a `category_id` the order lines already carry ([b2.py](../../benchmarks/workloads/b2.py), [load.py](../../benchmarks/load.py)); B2b–d run one correlated `$lookup` per product or order; PostgreSQL has a materialized variant and MongoDB has none | The aggregation headline is partly an artifact; "rigorous comparison" is graded | Add idiomatic and maintained-summary variants against the same golden outputs; keep the originals; rerun B2 only on the designated machine ★ | M, approval | open |
| 6 | Analysis | MongoDB's justification is not written, and the timed workloads favour PostgreSQL | Risks "implementations are not justified". Evidence exists: storage ([B5](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/report/B5.csv)), atomic single-document update ([B6](../../benchmarks/results/2026-11-02T095518_b53e5d0a_final-b3-b6/report/B6-states.csv)), embedding, migration-free schema change, GridFS, time-series TTL | Write the report and slide section ★ | M | open |

### P1: credibility, accuracy, demo quality

| # | Area | Item | Why it matters | Fix | Effort | Status |
|---|---|---|---|---|---|---|
| 7 | UI | Product and shop names look like identifiers (a hexadecimal suffix on every name) | Visible on every screen of the video | Display-level change; regenerating names would change data checksums and benchmark provenance | M, approval | open |
| 8 | UI | Product page media panel: a large empty box with the category icon clipped into its corner, in both themes | Looks broken | Override the card crop (`.tile__glyph` in [site.css](../../src/static/css/site.css)) for the detail panel ★ | S, approval | open |
| 9 | UI | The footer on every page links to the foundation mockups, including a statistics page of invented figures ([base.html](../../src/templates/base.html)) | A marker will click it | Remove the footer section or the routes ★ | S, approval | open |
| 10 | Backend | The operator dashboard takes several seconds: [delivery_analysis](../../src/dashboard/services.py) loads every delivered order and every order score into Python on each request, and the stock panel is paged in Python | Visible on camera; "efficiency" is named in the brief | Decide: materialize at the source, or cache (Redis decision 1) | M | open |
| 11 | MongoDB | `latest_reviews` is maintained on every review write ([reviews/services.py](../../src/reviews/services.py)) but never read; the product page queries `reviews` directly | The subset pattern and "a product page is one read" claim are not true | Read the subset on the product page, or drop the claim ★ | S–M, approval | open |
| 12 | MongoDB | The unfiltered trending aggregation is the largest database cost on the home, shop and search pages; the category-filtered version is far cheaper | Paid on almost every page | Short-lived cache (Redis) or a better index ★ | S–M | open |
| 13 | Benchmark | B1 broad: the MongoDB planner chose `_id_` to avoid a sort and examined the whole product set ([plan](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/plans/B1_broad_mongo_documents.json)). Index effort in B1 is unequal: GIN plus expression B-trees against one wildcard index | Fairness challenge from any marker who knows MongoDB | Report the hinted run beside the headline and explain the planner; consider a compound wildcard index | S (report), M (rerun) | open |
| 14 | QA | Reviews, wishlist, dashboard, activity and benchmark were reviewed only by the session that wrote the brief ([AI_USE.md](../AI_USE.md)) | The AGENTS.md review rule is unmet | Fresh-session reviews, dashboard and reviews first ★ | M | open |
| 15 | User manual | The README flow works from a clean clone, but the data import sits after the benchmark section; deliverables exit check 4 (run from the extracted zip on another machine) is still open | Markers must run the app from the manual | Reorder the README; run from the zip by 15 Nov ★ | S–M | open |
| 16 | UI, MongoDB | No product photos: every product shows an icon card and GridFS is empty until a seller uploads | Weak first impression; thin GridFS showcase | Seed openly licensed photos for the demo products through the GridFS upload path, labelled; reverses catalogue amendment k | M, approval | open |
| 17 | Analysis | Per-request timings differ between machines: the committed [request-timing run](../../benchmarks/results/2026-11-02T103305_b53e5d0a_request-timing/category.csv) shows a PostgreSQL-bound category page, this review did not | Quoting either unverified is risky | Rerun the collector on the recording machine before citing it | S | open |

### P2: polish and engineering rigour

| # | Area | Item | Fix | Effort | Status |
|---|---|---|---|---|---|
| 18 | UI | Generated-content labels appear three times per card; descriptions read like placeholder text | One clear label per card (AGENTS.md rule 9) | S | open |
| 19 | UI | Review lists are mostly score-only rows, so product pages look empty | Text reviews first, or collapse score-only rows | S | open |
| 20 | UI | Adding a product asks for the category twice | Merge the selectors or load the options automatically | S–M | open |
| 21 | UI | Seller insights is sorted by product id; the dashboard filter asks for a typed seller number and shows Django's empty label | Sort by views or conversion; readable filter labels | S | open |
| 22 | UI | Facet counts refresh on submit, but the overview says "live"; HTMX is used only for cart and wishlist | Fix the wording, or `hx-get` on the filter form | S / M | open |
| 23 | UI | On a phone the filter form fills the first screen | Collapsible filter panel | S | open |
| 24 | UI | No confirmation before irreversible actions (cancel with refund, deactivate, suspend) | Confirmation step | S | open |
| 25 | Security | No brute-force protection on login or review posting | Redis rate limiting (Tier 2) | M | open |
| 26 | Cross-store | PostgreSQL-first writes log, rather than repair, a MongoDB failure | No code change: show `check_specs` in the demo; write it up as a reflection | S | open |
| 27 | CI | Ruff selects only E, F and I | Add B, S and DJ; fix the findings | M | open |
| 28 | CI, docs | The README claims host Python 3.8 or later; CI tests host scripts only on 3.13 | State the real minimum, or test it | S | open |

### P3: disclose or leave

| # | Area | Item | Action | Status |
|---|---|---|---|---|
| 29 | MongoDB | Validators accept any attribute key; template types are enforced only in Django forms | Disclose in the report | open |
| 30 | PostgreSQL | The per-order refund rule is not a database constraint | Already documented in [DATA_MODEL.md](../DATA_MODEL.md) | open |
| 31 | PostgreSQL | Deferred money checks run per row at commit; B3 shows their cost ([summary](../../benchmarks/results/2026-11-02T095518_b53e5d0a_final-b3-b6/summary.csv)) | Present as a finding | open |
| 32 | Backend | `placed` is never written for new orders; `checkout` indexes rows by position; `seed_demo.handle` and `checkout` are long | Leave money code alone; prepare explanations | open |
| 33 | Code quality | Several templates are written on single very long lines | Optional reformat | open |
| 34 | Data | Some category names read oddly ("Home Appliances 2", "Construction Tools Tools") | Optional display mapping | open |
| 35 | Benchmark | B3 compares four normalised inserts with one embedded document; the engines' cache models differ ([memory settings](../../benchmarks/results/2026-11-02T004351_b53e5d0a_final/report/memory-settings.csv)) | State as design; disclose | open |
| 36 | CI | The benchmark job is optional; coverage is gated on lines only | State in the report | open |
| 37 | Repository | Untracked `RESUME_*` notes in the repository root | Do not commit them | open |

### Tier 2: only if earned on 8 November

| Item | Position |
|---|---|
| Redis, narrow scope | Rate limiting (#25), dashboard cache (#10), trending cache (#12). Settle first: fix or cache; key and invalidation; fail open or closed for rate limits; on/off measurement protocol; `maxmemory` and eviction; real Redis in CI; the 15-second and half-page budget ([deliverables](deliverables.md) decision e); documentation touched |
| Redis sessions, cart or stock | Skip: no measurable gain, or AGENTS.md rule 2 |
| Observability | Skip or keep minimal; per-request timing already exists |

### Verified working, no action

Role access (redirects and 403 pages), CSRF rejection, parameterised SQL, upload validation (a disguised SVG and an
oversize file rejected, a valid PNG accepted), checkout idempotency under a double click, cross-customer order access
(404), the full Docker suite, the browser journeys on full data, Ruff, the packager's secret checks, and basic
accessibility (labels, alt text, visible focus, no horizontal scroll at phone width).

### Suggested sequence

1. To 8 Nov: #2, #3, #4; draft #6; get decisions on #7–#9, #11 and #16; settle the Redis questions; start #14.
2. To 15 Nov: #5 and #13; #10 and #12 (or Redis); #15; report sections 1–5; the rest of P1.
3. To 18 Nov (footage): P2 interface items, so the recording shows them.
4. Then: report sections 6–9, slides, video edit, packaging.

## Decisions

| # | Date | Decision (owner) | Why |
|---|---|---|---|
| | | | |

## Review notes

2 November 2026, Claude Code (Opus 5.5) for Erfan, on Erfan's Windows machine: a code read of the benchmark, both
databases, the backend, CI and templates, then a live run. The live run followed the README from a clean state
(`init_env.py`, `docker compose up --build`, `import_olist`, `verify_olist`, `seed_demo`, `seed_activity`,
`smoke_olist.py`), ran the full Docker suite and the host tests, Ruff, the browser suite
(`python -m scripts.browser_suite --env-file .env --base-url http://127.0.0.1:8000`) and the packager with placeholder
deliverables. A scripted Chromium crawl visited every page for each role at desktop and phone widths, and exploratory
scripts checked error states, uploads, focus and dark mode. All passed except the findings above. Screenshots and
logs stayed outside the repository; rerun the commands above to reproduce them.
