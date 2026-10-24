# activity: Activity events in a MongoDB time-series collection (M1)

status: done
plan owner: Erfan · implementer: Chee Long · reviewer: a fresh session · estimate: 1 to 1.5 days · phase 3A (9 to 13
November) · depends on: `catalogue` (product pages, search), `checkout` (purchases for conversion)

**Assumes:** product detail and search views from `catalogue`; orders and lines from `checkout`; MongoDB 9.0 time-series
collections with `expireAfterSeconds`.

## Contract

**Goal.** Record what shoppers look at and search for, at high write volume, and turn it into recently viewed,
trending now and a views-to-purchases figure for sellers.

**In scope**

| Area | Deliverable |
|---|---|
| Collection | `events`: time-series collection (`timeField: ts`, `metaField: meta` with `type` view or search, `product_id`, `category`, `user_id` or anonymous session key), `expireAfterSeconds` = 30 days, a secondary index on `meta.product_id` and `meta.user_id`. Created by adding it to `mongo_setup` (`olist-import`) with the app user's `readWrite`; MongoDB has no separate owner |
| Writing | Product detail writes a view event; search writes a search event with the query text (trimmed, at most 100 characters). Writes use `w: 1`; a failed event write is logged and never breaks the page |
| Recently viewed | The customer's last 10 distinct products, on the home and product pages (anonymous visitors by session) |
| Trending now | Views in the last 24 hours per product, ranked with `$setWindowFields` (`$rank`), overall and per category; fills the home page slot `catalogue` left |
| Seller conversion | Seller centre "Insights": per product, views in the last 30 days (MongoDB) against units sold in the same window (PostgreSQL), joined in Python by product id |
| Demo data (decision a) | `manage.py seed_activity` writes about 200k synthetic view events over the past 30 days, spread in proportion to real sales, marked `is_generated`, so trending and conversion are not empty on camera |

**Out of scope:** recommendations; event export; personal data beyond the user id or session key.

**Tests:** a product view and a search each write one event; an event write failure does not change the page; recently
viewed returns distinct products newest first; trending ranks match a direct count; the TTL option is set to 30 days;
conversion equals views and units counted directly on a small fixture; anonymous events never carry a user id; a seller's Insights page shows only their own products (scoping, AGENTS.md rule 6).

**Exit check**
1. Browse five products as the demo customer: recently viewed lists them newest first.
2. After `seed_activity`, the home page shows trending products, and the seller centre shows views and conversion.
3. `explain("executionStats")` of the trending pipeline uses the time-series bucket index; noted for the report.
4. The full test suite passes in Docker.

## Decisions (all approved 21 October 2026)

| ID | Proposal | Why |
|---|---|---|
| a | Seed synthetic events relative to the time of seeding, labelled as generated | Olist has no browsing data, and a 30-day TTL only keeps recent events, so a fixed historical date would expire at once. This is demo data, not benchmark data, so it need not be byte-reproducible |
| b | Fire-and-forget event writes with `w: 1` | Page speed matters more than losing an occasional view event; the tradeoff is named in the report |

## Review notes

21 October 2026, cross-plan review (fresh session); findings applied: the collection joins `mongo_setup` (no MongoDB owner exists); a seller
scoping test for Insights.


24 October 2026 — Implementation notes (Codex; reviewer: pending (Claude Code)). Built the events time-series
collection with 30-day TTL and product/user/session/type/category time indexes in mongo_setup, acknowledged w:1
view/search writes with sanitized failure logging, ten distinct recently viewed products, ranked overall/category
trending in the existing catalogue slot, scoped seller Insights joining views and units over one rolling window,
and labelled relative-time seed_activity weighted by imported sales. Missing/incompatible event storage cannot
silently become a regular collection, and it never breaks catalogue rendering. Focused real-database checks passed
for writes, query trimming/injection literals, anonymous identity, windows/ties, distinct history, nonfatal failure,
TTL/index options, proportional seeding and seller scoping. Equal-view ranks retain their ties by applying the
product-ID ordering after the computed rank.

Exit check 1 passed as demo-chee-long: five browsed products appear newest first on home. Exit check 2 passed after
the default seed_activity command: labelled generated browsing appears in Trending and the demo seller's Insights
shows views and conversion. Exit check 3 passed: explain executionStats uses event_type_time in the winning
UNPACK_TS_BUCKET/IXSCAN plan; the unaltered report is .cache/phase3a/activity-trending-plan.json, for report notes.
Generated seeding and exit evidence are activity-seed.log and activity-exit.log. Desktop and 375px browser checks
covered the review histogram, Trending, dashboard and Insights, with no document overflow. The dashboard was checked
in both themes and the temporary browser session/viewport was cleaned up; visual-checks.json records the checks.

Two small integration fixes are carried on this final stacked branch: the dashboard chart now starts with the design
tokens and disables Chart.js automatic colours; repeated wishlist controls on detail/recent cards consume the server's
committed HX-Trigger state. Both controls were verified for save and remove in the real browser, including posting
from the repeated card, and server-event regression assertions were added. The previous workstream plans record
these follow-ups. These are integration corrections within the four approved features, with no new feature scope.

Exit check 4 passed after rebuilding migrate: the final full Docker suite, including the full-data dashboard check and
wishlist regression assertions, is recorded verbatim in .cache/phase3a/activity-full-suite.log. A Docker service stop
interrupted an earlier final rerun after prior complete green runs; its partial output is preserved separately as
activity-interrupted-final-suite.log and is not counted as a pass. Services were restarted and the complete suite
reran successfully. Migration drift, Django system checks, host docs/packaging checks and scripts/check_docs.py passed.
The existing container-only Git-index skips remain visible; their host equivalents passed. No functional omissions or
remaining blockers were identified. Fresh Claude Code review remains pending on all four local branches. No push,
PR or merge was performed.

24 October 2026 — Review (Claude Code; session that wrote the Codex brief, not a fresh session), finding activity R3.
Anonymous metadata held a raw Django session key. Writes and recently viewed now use the same salted_hmac hex digest
with the fixed mercer.activity.visitor salt in the existing meta.session_key field; authenticated user IDs and the
seed_activity synthetic label are unchanged. Updated the event model documentation. Tests were adjusted before code:
test_anonymous_identity_is_keyed_hash_and_histories_remain_separate checks view/search storage contains neither raw
session key, both visitors retain their own recently viewed products, and login does not inherit anonymous history.
The weighted seeding test now also asserts the unchanged synthetic label. The identity regression failed against
the previous raw-key implementation.
Rebuilt migrate and ran all of test_activity.py successfully; unaltered output is
.cache/phase3a-review/activity-R3-tests.log. No collection/index change or seeder rewrite was needed.

24 October 2026 — Review (Claude Code; session that wrote the Codex brief, not a fresh session), finding activity R5.
Team decision: keep Insights' real rolling 30-day window. The review brief reports 7,691 imported orders in that
window at review time, 114 on 25 November and none after 27 November. These are the reviewer's reported figures,
not a new measurement in this fix round. Events expire after 30 days, so an imported-date anchor cannot keep the
browsing side available. Before filming on recording day, run seed_activity and place a few demo purchases for the
seller's products. Recorded the decision, README demo step and PLAN.md recording-day dependency. No code changed;
test_insights_views_units_ratio_and_seller_scoping already checks the rolling window and passed in the R3 module run.
