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
