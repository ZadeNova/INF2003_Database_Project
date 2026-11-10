# review_rounds: Independent review rounds F and G, run by teammates

status: approved
plan owner: Erfan · reviewers: teammates (one fresh Claude Code session per round) · analysis of the reports and every fix:
Claude Code, on Erfan's decision · phase 5 ([PLAN.md section 13](../../PLAN.md#13-phases)) · depends on: the first three
review rounds of Batch 7 in [improvements](improvements.md#batch-7-code-quality-pass-then-the-full-codebase-review)

**Purpose.** Batch 7 reviews the whole code base in rounds, each by an independent reviewer who runs things and reports to
Erfan. Rounds 1 to 3 (database layer, money and orders, connections and stores, the test suite, security and Django practice)
are done. Two rounds remain: **F** (reads and analytics: are the numbers right, at the edges, and is the benchmark's evidence
sound) and **G** (the whole system, end to end, on the fixed code). Erfan has asked teammates to run them.

## Contract

**What a reviewer does, and only this:** open one fresh Claude Code session, give it the prompt for the round (below), let it
run, and send Erfan the **final report exactly as the session wrote it**. A reviewer never edits, commits, pushes or creates a
branch, and never applies a finding, even a one-line one: Erfan decides each fix after the report has been checked, and the
fixes are made in one place so the rounds stay comparable.

**The flow (the same for every round):**

1. Erfan pushes `improvements/backlog` and gives the reviewer a **commit hash**. The commit contains this file.
2. The reviewer runs the prompt in a fresh session. The session reviews that commit, read-only, in its own Docker Compose
   project, and writes a report.
3. The reviewer sends the whole report to Erfan (paste it into a message; do not summarise or trim it).
4. Erfan pastes it to Claude Code, which verifies each finding against the code and the data (a reviewer can be wrong), ranks
   them and recommends fix, skip or disclose for each.
5. Erfan decides. Claude Code implements the approved fixes with tests, runs the full suite and commits. Erfan pushes.
6. The next round reviews the new commit.

**Order and timing.** F first, on the commit Erfan names. G only after F's fixes are committed and pushed, because G must
review the fixed code. Asked for: the F report back within two days of getting the commit; the G report at least a day before
the 15 November code freeze. Erfan can move these.

**Who and what it costs.** A round is one long session (the earlier rounds took about 14 to 27 minutes of work each and a large
amount of model usage). Rounds F and G use the reviewer's own Claude usage. They can be split between two teammates, or one
teammate can run both. Use the strongest model your plan offers (the earlier rounds used Claude Opus 5.5). Tell Erfan which model
and which person ran the session: it goes in [AI_USE](../AI_USE.md).

**Set-up (once, on the reviewer's machine).** Docker Desktop (or Docker Engine) with Compose 2.20 or later, Git, Python 3.12 or
later, Claude Code. Then:

```sh
git clone <the team repository> && cd <the clone>
git fetch --all
git checkout <COMMIT>                       # the hash Erfan gave you; a detached checkout is fine
python src/tools/init_env.py                # writes .env with random local secrets (never print it)
```

Nothing else is needed: the prompt tells the session how to start its own isolated Docker project. If the stack does not start
within about thirty minutes of trying, stop and tell Erfan; do not change any file to make it work. The review is most useful
on a machine that can import the full dataset (round F does; it needs a few GB of free disk and a few minutes).

**Safety rules the prompts repeat.** Read-only; never print `.env`; never touch any Compose project other than the session's
own (name given in the prompt); tear the project down at the end; delete any probe files the session created.

## Decisions

| # | Decision | Why |
|---|---|---|
| a | The prompts live here, in the repository, not in a private folder | Teammates must be able to run them from a clone, and the earlier rounds' known decisions travel with them |
| b | Reviewers only report; Claude Code (Erfan's session) verifies and fixes | Reviewers are sometimes wrong, and one place for fixes keeps tests, docs and commits consistent |
| c | The reviewed commit is named by Erfan in the prompt | A report is only comparable to the code it was run on |
| d | Round G runs on the code after F's fixes | Whole-system review of code that is about to change wastes the session |

## The shared brief (both rounds read this first)

You are an independent senior reviewer of "Mercer", a Django 5.2 + HTMX multi-seller marketplace (PostgreSQL = system of record,
MongoDB = specifications, reviews and photos, Redis = cache and rate limits, fails open) for a university database course. It
is graded on database design, correctness, security and robustness, code quality, test quality and a demonstration. Your job:
find real defects and real risks in your scope, by **running** things, not only reading.

**Ground rules**

- Review the commit the person who started you named (run `git rev-parse HEAD` and state it). Review the working tree as it is.
- **Read-only. Do not edit, create, move or delete any tracked file, and run no git command that changes anything** (no commit,
  checkout, stash, reset, add, push). You may create only throwaway probe tests named `tests/zz_review_<your letter>_*.py`
  (delete them before you finish) and scratch files under `.cache/review/<your letter>/` (git-ignored; delete them at the end).
  Run only your own probe files or named test modules by path. Run the whole `/app/tests` directory only if your scope says you
  may, and then add `--ignore-glob='/app/tests/zz_review_*'`.
- Another reviewer may be working at the same time on the same machine. Use only your own Compose project (name and port in
  your scope block) and never touch any other project, container or volume.
- Never print `.env`, never run `docker compose config`, never print secrets. Do not run `import_olist` against any project that
  is not yours.
- Read first: AGENTS.md (the 11 rules), RUBRICS.md, docs/DATA_MODEL.md, docs/DECISIONS.md, DESIGN.md (anything visual), and the
  plan files named in your scope.

**Known decisions: do NOT re-report these unless you can show with evidence that the reasoning is wrong**

- Seller row-level security: policies are ENABLE, not FORCE (the owner role and SECURITY DEFINER functions bypass them); the
  setting `mercer.seller_id` is session-level and fail-open when unset; it is set and released in `AnySellerMixin.dispatch`.
- Redis is never the source of truth and fails open (rate limits and caches); the benchmark connects as the owner.
- The importer and the benchmark generators insert rows directly with user triggers disabled; the application has one order
  insert path.
- Round 1 (database layer; money and orders) fixed: a lead time of at most 365 days, a NUL byte in a cancel reason, an audit
  row-history index, a key guard that makes the parent columns of the money tables read-only (`orders` 0006). Skipped or
  disclosed: direct inserts of orders are not guarded; a replayed checkout form repeats the success message; a cancel at the
  stock ceiling is not reachable from the application; redundant foreign-key indexes; blank product names at the database level;
  the policy-plan cost on bulk reads by the runtime role (#74); the runtime role can create large objects (#75). The locks
  (cart, checkout, order, product) were checked and held up.
- Round 2 (connections and stores) fixed: MongoDB connect and operation timeouts and a 5 s back-off; the shop listing and shop
  page degrade to icon cards when MongoDB is down; the dashboard cache bump ignores a Redis back-off; the web service sets
  PostgreSQL `lock_timeout` 10 s, `statement_timeout` 25 s and `idle_in_transaction_session_timeout` 60 s; stored photos are at
  most 2048 px and 2 MB. Connection methods were reviewed and kept (Django persistent connections with `CONN_MAX_AGE` 60 and
  health checks; one pooled MongoDB client per process). Disclosed: an unreferenced old photo after a failed cross-store commit
  (#76); `/health/` reports process liveness only, by design. Query counts on the small fixture were at most 11 per main page.
- Test-suite review done: the timing tests were fixed (a Docker VM's wall clock can step back about a second every 30 s, and
  Redis `TIME` follows it), the full-data test is marked `slow` and left out of the default run, duplicates were removed.
- Round 3, reviewer E (security and Django practice), fixed: every role page is `never_cache`; usernames are unique ignoring case;
  form error and help ids match `aria-describedby`; branded 400, 403 (CSRF), 413 and 500 pages; request bodies over 3 MB get a
  413. Documented, not changed: the HTTPS warnings of `check --deploy` and no Content-Security-Policy (#77); the photo cache
  window after a takedown; alerts marked seen on GET; an invalid sign-up answers 200; the operator's category-option write
  lives in a view.
- Full-text search on reviews and relisting a deactivated product are cut. Templates keep some long lines (accepted). Tests use a
  fast MD5 password hasher on purpose (tests only). Tests that start threads route MongoDB with `mongo.using_database(...)`.
- The documented limits in docs/plans/improvements.md "Disclose in the report" (#29 to #36, #64 to #68, #74 to #77). Imported
  data has odd orders (paid but never shipped, delivered after the estimate, some future delivery dates); this is disclosed.
- Ruff ignores in pyproject.toml are justified there.

**How to run.** Use YOUR OWN isolated Compose project. Linux, macOS and Windows (Git Bash) all work; under Git Bash set
`MSYS_NO_PATHCONV=1` so container paths are not rewritten. From the repository root, with `.env` already written:

```sh
export MONGO_PORT=0 APP_PORT=<your port> COMPOSE_PROJECT_NAME=<your project>
dc() { docker compose -p "$COMPOSE_PROJECT_NAME" "$@"; }
dc build migrate web
dc up --detach --wait --wait-timeout 300 db mongo redis
dc run --rm migrate
dc run --rm migrate python manage.py import_olist --source /app/tests/fixtures/olist/clean   # the small fixture
dc run --rm migrate python manage.py seed_demo
dc up --detach --wait --wait-timeout 300 web          # the runtime web service on your APP_PORT
dc run --rm migrate pytest -q -p no:cacheprovider /app/tests/<module>.py     # tests run in the `migrate` service
```

The demo logins are in the README under "Demo logins" (they are fixed and not secret). Tear your project down at the end with
`dc down --volumes`. Stopping and starting YOUR project's `mongo`, `redis` or `db` containers is allowed and is how you test
failures.

**Rules for evidence.** Report only what you checked; a finding without evidence is a guess, so label guesses "unverified". Do
not report style, formatting, naming or things Ruff already checks, and do not report the same defect twice. Prefer a failing
probe test, a command transcript or an exact reproduction over prose. Try hostile and odd input, concurrency, retries, partial
failure and a store being down or slow.

**Severity.** *blocker*: wrong money, lost or leaked data, a user reaching another user's data, account takeover, a crash on a
main path. *major*: a realistic wrong result, a missing guard the docs claim exists, a race two users can trigger, or a state
change reachable without the right permission. *minor*: unlikely, cosmetic or hardening. *note*: observation, no action.

**Output.** Your final message, nothing else, at most about 1,800 words:

1. The commit reviewed, the scope, what you ran (commands and modules), and what you could not check.
2. Findings, most severe first. For each: `ID (your letter and a number) | severity | file:line | one-sentence defect |
   evidence (the command or test and its result) | reproduced: yes/no | proposed fix and size (S/M/L)`.
3. "Assumptions about other layers": what your scope relies on that you did not verify.
4. "Checked and fine": the risky things you tried that held up.
5. Confirmation that you deleted your probe and scratch files and tore down your project.

## Round F: reads and analytics

**Paste this into a fresh Claude Code session at the repository root** (replace `<COMMIT>` with the hash Erfan gave you):

```text
You are reviewer F. Read docs/plans/review_rounds.md, the section "The shared brief" and then the section "Round F scope", in full,
and follow them exactly. Review commit <COMMIT> (state it), read-only, in your own Compose project named mercer-review-f on
APP_PORT 8042. Use Git Bash on Windows (set MSYS_NO_PATHCONV=1) or any shell on Linux or macOS. Never touch any other
project, never print .env, delete your probe and scratch files and tear your project down at the end. Your final message must
follow the output format in the shared brief. Start the full-data import first because it takes several minutes.
```

### Round F scope (letter F; project `mercer-review-f`; `APP_PORT` 8042)

Question: are the numbers the application shows correct, and do they stay correct at the edges (empty data, ties, NULLs,
rounding, time zones, the boundaries of a period), when they come from a cache, a summary or the live query, and in the
benchmark?

Read: docs/plans/dashboard.md, docs/plans/dashboard_summaries.md, docs/plans/activity.md, docs/plans/wishlist.md,
docs/plans/reviews.md, docs/plans/redis.md (the cache parts), docs/plans/benchmark.md (decisions and the correctness rules),
docs/DATA_MODEL.md (the summary views, the MongoDB `order_review_scores`, the rating summary) and the "Disclose in the report"
list in docs/plans/improvements.md. Files: `src/dashboard/`, `src/activity/`, `src/wishlist/`, `src/reviews/`,
`src/catalogue/search.py` (ranking and facets), the operator stock-planning page, `src/config/redis_store.py` only where the
dashboard cache is read or invalidated, and `benchmarks/` (the workloads, the correctness checks, `reference/compute.py`,
`golden/`, `canonical.py`, `results.py`, `report.py` and the fixture tests in `benchmarks/tests`).

Load realistic data for the numbers. In your own project, import the full cleaned dataset instead of the fixture:
`dc run --rm migrate python manage.py import_olist --source /app/data/derived/olist/clean`, then `seed_demo` and
`dc run --rm migrate python manage.py seed_activity --count 2000`. Use the small fixture for quick probes. You may run the whole
test suite once in your own project (with the ignore option above) if you need a baseline.

**A. Arithmetic and edge cases (verify with independent SQL or Python, not with the code under review)**

1. **Re-derive every dashboard number.** For the delivery-delay panel, the category block, the review blocks, the stock-planning
   table and the trending and insights panels, write your own SQL (or plain Python over the raw tables) and compare with what
   the page shows, for the live path, the summary-table path and the Redis-cached path. They must be identical; the code treats
   the live path as the oracle. Compare on full data, not only the fixture. Report any difference, however small.
2. **Rounding and types.** Every percentage, average, median, percentile and Bayesian score: which rounding, which type
   (`numeric` or float, `Decimal` or float in Python, MongoDB Decimal128), where rounding happens (once at the end, or at each
   step), half-way cases, negative values, very large and very small values, division by zero, NULL inputs, integer overflow,
   and whether a displayed number can differ from the stored one by more than the stated precision.
3. **Time.** The project's `TIME_ZONE` is Asia/Singapore; the data is Brazilian. For every date bucket (day, week, month, "last 30
   days", the reporting date `dashboard_as_of()`): which zone defines the boundary, does an order placed at 23:30 local land on
   the right day, what happens across a month end, a year end, a leap day and a daylight-saving change (Brazil had them in the
   data's years), and a period that is empty. Any place that mixes `timezone.now()` with the reporting date.
4. **Ties and ordering.** Every ranked and every paginated list (trending, top products, the "recommended" search order, seller and
   operator lists, wishlist, alerts): is the `ORDER BY` total, ending in a unique key? With ties, can a row appear on two pages or
   on none? Is the order stable between requests? Create ties on purpose (equal prices, equal view counts, equal scores).
5. **Empty and tiny data.** A new seller with no sales, a product with no reviews, a day with no events, a category with one
   product, a customer with no orders: no crash, no `NaN` or `None` shown to the user, sensible wording.
6. **Consistency between stores.** The rating summary in MongoDB (`rating`, `latest_reviews`, `platform_stats` for the Bayesian
   prior) against the reviews it summarises: create, edit, delete, take down and restore a review, and recompute the summary
   from scratch each time. Do they agree? The per-order review-score summary against the live recompute? The cached dashboard
   after a review write, a refresh and a restock? Anything that can leave a summary wrong until the next refresh without saying so?
7. **Wishlist and restock alerts.** The trigger fires once per change from 0 to a positive stock and not on other updates; alerts
   are created for the right customers only; marking alerts seen; a product deactivated or removed while saved; a customer saving
   the same product twice (a race); the alert badge count against the alerts page.
8. **Activity.** Generated and real events are labelled; the 30-day TTL and the trending window agree; a burst of views from one
   session; a view event for a deleted or hidden product; the seller-insights conversion rate (views, units, division by zero);
   no user data in events.

**B. Benchmark correctness (the benchmark is graded evidence: "a timing counts only if its correctness check passed")**

1. For each workload (B1 to B7) read the correctness check. Does it compare the two engines' results on identical inputs, with
   a tolerant comparison only where the data type really differs? Can the check pass while the result is wrong (a result compared
   with itself, an empty result matching an empty result, a count that ignores values)? In a scratch copy or a probe, make the
   query return a slightly wrong answer and confirm the check fails.
2. Is the data identical for both engines (hash or row counts compared), the seeds fixed, the caches and telemetry off as the
   rules say, warm-up and measured runs separated, outliers and failed runs recorded rather than dropped?
3. `reference/compute.py` and `golden/`: are the expected results computed independently of the code under test? Run the
   benchmark fixture tests in your own project as the README describes (the `bench` profile; use your own project name) and
   report any failure.
4. Does report generation read its numbers only from the generated result files (no hand-typed numbers), and do the tables it
   produces match the raw results? Spot-check five cells against the raw CSV.

**C. Read-path quality**

1. Every list and aggregate page on full data: the query count and the slowest query's plan (`EXPLAIN (ANALYZE, BUFFERS)` in your
   own project as the owner; as the runtime role with the seller setting where it applies). Any sequential scan of a large
   table that an index would avoid, any sort spilling to disk, any N+1. Page time at full data for the main pages, cold and warm.
2. The summary refresh: how long it takes on full data, what readers see while it runs, what happens if it fails halfway or two
   refreshes overlap, and whether the "refresh" button can be abused to cause load (rate limit, permissions).
3. Pagination of large result sets: deep pages, the cost of `COUNT(*)`, `OFFSET` with big numbers.

Do NOT review: SQL objects, triggers and policies as such (round 1), money and order logic (round 1), connections, timeouts and
store-failure behaviour (round 2), the tests (done), authorisation, CSRF, escaping and uploads (round 3, scope E).

## Round G: the whole system, end to end

**Paste this into a fresh Claude Code session at the repository root** (replace `<COMMIT>` with the hash Erfan gave you):

```text
You are reviewer G. Read docs/plans/review_rounds.md, the section "The shared brief" and then the section "Round G scope", in full,
and follow them exactly. Review commit <COMMIT> (state it), read-only, in your own Compose project named mercer-review-g on
APP_PORT 8043. Use Git Bash on Windows (set MSYS_NO_PATHCONV=1) or any shell on Linux or macOS. Never touch any other
project, never print .env, delete your probe and scratch files and tear your project down at the end. Your final message must
follow the output format in the shared brief. You may run the whole test suite once in your own project.
```

### Round G scope (letter G; project `mercer-review-g`; `APP_PORT` 8043)

Question: does the system work as a whole, on the fixed code, the way the report, slides and video will claim? Earlier rounds
reviewed layers one at a time. This round follows real journeys across all of them, hunts for what each layer assumed about the
others, and checks the claims against the rubric. It ends the review programme: Erfan's stopping rule is a round that finds
nothing above minor.

Read: RUBRICS.md (in full, line by line), PLAN.md sections 13 and 14, docs/plans/deliverables.md (the demonstration story and the
claims that will be made), docs/OVERVIEW.md, the README sections "Set up and run" and "Continuous integration", and the
"Disclose in the report" list.

**A. Journeys (run each in a real browser or with an HTTP client against your running `web` service; use the fixture data, then
`seed_demo`)**

1. **Buy and review.** An anonymous visitor browses, searches with filters, registers, adds to the cart, checks out and pays; the
   seller (approved) sees only their own order and ships it; the operator delivers it; the customer reviews it; the review shows
   on the product page, in the shop rating and in the seller's review list; the operator dashboard and the seller insights reflect
   it (including after the cache is warm); a wishlist item restocked sends the alert.
2. **Seller life cycle.** A new seller applies; the operator approves; the seller adds a product with category attributes and a
   photo, edits its price and stock, deactivates it; a customer buys it; the seller is then suspended while its session is live
   and a cart holds its product.
3. **Cancel and refund.** A customer cancels a paid order; stock returns exactly once; the refund appears in the ledger and the
   order history; the shop page, the dashboard and the alerts show consistent figures afterwards.
4. **Operator actions.** Takedown and restore of a review and of a product; seller suspend, reinstate and reject; the audit page
   shows every one of them with the right actor and reason; a customer who has the taken-down item in the cart or wishlist.
5. **Failure in the middle of a journey.** Repeat journey 1 while stopping and starting your project's `redis`, then `mongo`, then
   `db` (`dc stop <service>`, wait, `dc start <service>`) at different steps. What does the user see, is anything left half done
   (an order without its payment, a review without its order, a photo without a product), and does the system recover without
   manual repair? Note which pages must work without which store (checkout needs no MongoDB or Redis).
6. **Concurrency in a journey.** Two buyers for the last unit; a seller editing the price while a checkout is being reviewed; a
   customer cancelling while the seller ships; two browser tabs submitting the same checkout.
7. **The demonstration script.** Walk the story in docs/plans/deliverables.md step by step as the video will film it, on a fresh
   clone started with `python scripts/start.py` (read the script first and run it in your project, with your project name and
   port). Every step must work, look right (empty states, error states, both colour themes, a phone-width window) and take a
   sensible time. Report every step that fails, is slow, shows a wrong number or would embarrass the team on camera.

**B. Assumptions earlier reviewers did not verify (check each, report the verdict)**

- Only the seller views set `mercer.seller_id`; no raw SQL anywhere can reset it; the web service never connects as the owner.
- Line-level money consistency (order items equal the sum of its lines; a refund equals the cancelled order's total) is kept by the
  checkout service, because the database checks only checkout-level sums.
- The dashboard and summary refresh functions are called only from operator paths (the runtime role can call them).
- The audit actor and reason are trusted from the application's `set_config`.
- The runtime role has INSERT on `restock_alert` (for the restock trigger on cancel); `moderate_review` logs, and does not retry, a
  failed PostgreSQL commit after MongoDB has committed (`reviews-i4`): inject that failure once and confirm the log line and the
  state left behind.
- `mongo_setup` validators match `mongo_schema.py` field by field; gunicorn runs without `--preload`, so the MongoDB and Redis
  clients are created after the fork.
- The imported data loads no `placed` order without payments.
- A back button and the browser's back-forward cache after logout show no private page (real browser); a live 500 page; colour
  contrast of primary and error states against DESIGN.md.

**C. Rubric walk (the claims audit)**

For every line of RUBRICS.md write one line: the claim the project can make, the evidence a marker could be shown (a file, a test, a
benchmark result file, a page), and a verdict (`solid`, `thin: <why>`, `missing`). Be strict: a claim whose evidence is a
document with no running code, or a number typed by hand, is `thin`. This list becomes the checklist for the report and the video.

**D. Clean-clone and packaging**

On a clean clone of the commit (a second directory, a new project name): the README's set-up steps produce a working system without
undocumented steps; `scripts/check_docs.py` passes; the full test suite passes once, in your project; the eight browser journeys
pass if you can install the browser tools (`requirements-dev.txt`, `playwright install chromium`; see the README's continuous
integration section); the submission packaging commands in the README produce an archive without secrets, caches or results that
should not be shipped.

Do NOT repeat the layer reviews; use them only to choose where to look. Report a layer defect only if a journey exposed it.

## Review notes

10 November 2026, round F (reads and analytics), run by Syahfariz in one Claude Opus 5.5 session on commit `1748f2e` with the
full data. Every dashboard number matched an independent derivation on the live, summary and cached paths, and the benchmark
gate and report held up. Eight findings, none blocker or major. At Syahfariz's request the same session fixed them on
`improvements/review-f-fixes`, with a regression test for each code change. Erfan approved the report and every fix in person on 10 November (this departs
from the contract above, where the fixes are made by Erfan's session):

- F1 the refresh button no longer queues behind a running refresh ([DECISIONS](../DECISIONS.md), `refresh-no-queue`).
- F2 views count once per visitor in Trending and seller insights (`views-per-visitor`; the remaining limit is
  [improvements](improvements.md) #78).
- F3 a shop with no reviews says "No reviews yet" instead of showing the platform prior as its rating.
- F4 a customer edit keeps the imported review's source id; the effect of an edit on the dashboard history is disclosed (#79).
- F5 seller insights show units per view as a ratio, not a percentage.
- F6 the wishlist order ends in the product id.
- F7 the benchmark provenance states what telemetry is off instead of a blanket "disabled".
- F8 a note in [dashboard](dashboard.md) on which stock query the recorded index plan belongs to.

10 November 2026, round G (the whole system, end to end), run by Syahfariz in one Claude Opus 5.5 session on commit `16678bc`:
journeys on the fixture and on a clean clone started with `scripts/start.py` (full data), the full suite once, the eight
browser journeys, store outages and races. Nothing above minor, so the stopping rule is met. At Syahfariz's request, with
Erfan's approval, the same session fixed G1 to G7 on `improvements/review-g-fixes`, with a regression test for each code change:

- G1 a NUL byte in the seller's or operator's product search is ignored instead of a 500.
- G2 the audit log names the reviewed product and its shop for review decisions, and hides a price and stock line that did not change.
- G3 the demo applicant's shop is "Demo applicant shop (generated)"; `seed_demo` renames the earlier "pending approval" name.
- G4 the wishlist shows icon cards while MongoDB is down instead of a 503.
- G5 the purchase page shows a cancelled order's refund and no arrival estimate.
- G6 status badges in the phone-width audit table break only between words.
- G7 the README documents the submission packager.
- G8 (a teammate's Windows path in a shipped benchmark log) and G9 (the dashboard stops at its reporting date, so a demo
  purchase never shows there) need no code change; G9 is carried in [deliverables](deliverables.md).
