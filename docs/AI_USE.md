# AI use

## Reuse of our earlier module project

Mercer's codebase builds on a project the same team made for an earlier module: the Django application shell, the
accounts, cart and orders code and the request logging. The shoe-shop and AWS parts are removed
by `foundation` and `olist-import`; the rest is converted to the marketplace described in [PLAN.md](../PLAN.md).

**Approval from the INF2003 professors:** confirmed with them by Erfan; no written reference is recorded here.

## How AI is used

Coding agents (Claude Code and Codex) plan and implement workstreams under the rules in [AGENTS.md](../AGENTS.md). A
person approves each plan and runs the demo path; a fresh session, ideally the other agent, reviews the change by
running its tests and exit check. Every AI-assisted commit carries a `Co-Authored-By` trailer.

## Log

One line per workstream, added at close-out.

| Workstream | Agent | What it did | Reviewer |
|---|---|---|---|
| foundation | Claude Code (Sonnet 5.5) | Removed AWS and K-means code; two PostgreSQL roles; MongoDB replica set in Compose; docs consolidation and `scripts/check_docs.py`; packager | Claude Code (fresh session): Windows exit-check run, see `docs/plans/foundation.md` |
| olist-import | Codex | Implemented Olist preparation, translation and generated content; marketplace schema and cross-store import; demo pages, tests and review fixes | Claude Code (fresh independent session): review and fix-round verification completed; see [the workstream review notes](plans/olist-import.md#review-notes) |
| accounts | Claude Code; Sol | Claude Code implemented roles, seller approval, the operator console and the trigger-written audit log; Sol drafted the plain-language wording, which Claude Code checked and finished (`0421fb4`) | Codex independently reviewed the implementation with one fix round (AR1 closed); Claude Code checked and finished the display amendment; see [review notes](plans/accounts.md#review-notes) |
| ci stage 1 | Claude Code | Implemented the stage 1 real-database, pipeline, documentation and host Git-index/packaging workflow | Codex: independent implementation review approved; local reproduction passed, hosted PR and main runs passed; see [review notes](plans/ci.md#review-notes) |
| ci startup correction | Codex | Fixed dash-leading mongosh credentials, rejected dash-leading new secrets, added regression checks and troubleshooting guidance (ci-i9) | Fresh Claude Code review: APPROVE, no blockers; Claude Code fix round CS1–CS3; hosted PR/main runs pending; see [review notes](plans/ci.md#review-notes) |
| checkout | Codex | Implemented additive cart/lifecycle/money enforcement, PostgreSQL split checkout, scoped order pages and real-database/injection/concurrency checks; preserved local command evidence | Fresh Claude Code review: APPROVE, no blockers; Claude Code fix round CK1–CK5 and the catalogue integration; merged in PR #9; see [review notes](plans/checkout.md#review-notes) |
| catalogue | Codex | Implemented shop/search/facets, scoped seller CRUD and GridFS uploads, product audit, operator moderation and live category options; ran real-database and full-data checks with saved plans | Fresh Claude Code review: no blockers; Claude Code fix round CG1–CG6, CG8, CG9 and the checkout integration; merged in PR #10; see [review notes](plans/catalogue.md#review-notes) |
| catalogue amendments f/j | Codex | Recorded the approved stock-photo deferral; rewrote the Mercer design system and CSS, added removable filter chips, and checked responsive layouts, contrast and the existing GridFS upload flow | Claude Code review: CHANGES REQUESTED, no blockers; Claude Code fix round DG1-DG3 (DG4 local data; DG5-DG6 optional); Chee Long approved the design on 23 October 2026; see [review notes](plans/catalogue.md#review-notes) |

| reviews | Codex | Implemented per-line reviews, transactional summaries and Bayesian ranking, moderation audit, scoped pages and real-database checks | Claude Code (the session that wrote the Codex brief; not a fresh session) |
| wishlist | Codex | Implemented composite-key saves, trigger-created restock alerts, unseen uniqueness, scoped HTMX pages and cancellation/raw-update checks | Claude Code (the session that wrote the Codex brief; not a fresh session) |
| dashboard | Codex | Recorded amendment a; implemented materialized sales, restricted refresh, named analytical SQL, as-of panels and independent database checks | Claude Code (the session that wrote the Codex brief; not a fresh session) |
| activity | Codex | Implemented time-series setup, best-effort events, recent/trending panels, scoped seller conversion, labelled weighted seeding, responsive browser checks, chart palette and repeated-wishlist-control integration fixes and real-database checks | Claude Code (the session that wrote the Codex brief; not a fresh session) |
| ci stage 2 | Codex | Added a separate dev image, line-only coverage gate with branch reports, Ruff cleanup, strict dependency audits and expiring exceptions, serial browser journeys and redacted failure artifacts; local validation recorded in the CI plan | Claude Code (APPROVE, 46731ad) |
| ci hosted evidence | Codex | Published and merged the reviewed stage 2 change, verified hosted PR/main checks and forced-canary artifact redaction, and recorded Phase 3A exit evidence | scripts/check_docs.py (docs-only review) |
| benchmark | Codex | Implemented isolated loaders, golden outputs, B1–B6, request timing and evidence; addressed the authorised storage/timing/baseline/results/CI fix round, reran affected checks and collected fresh committed-head correctness/BM4/trial evidence | Claude Code (the session that wrote the Codex brief; not a fresh session) |
