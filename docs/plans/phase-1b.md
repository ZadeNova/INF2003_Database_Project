# phase-1b: Accepted review amendments and their canonical plans

status: done
plan owner: Chee Long · implementer: Chee Long · Phase 1B (25 October 2026)

## Contract

**Purpose.** Preserve the Phase 1B decision record, not a second implementation contract. Chee Long accepted the
amendments below on 22 October 2026. Accounts, benchmark and ci were approved on 22 October 2026;
catalogue, checkout and reviews carry only the P3 amendment and stay approved. Accepting decisions does not
authorize implementation. Accounts scope lives in [accounts.md](accounts.md); the sole
CI contract, its staged exit checks and quality decisions live in [ci.md](ci.md). Retain the `phase-1b-review` entry
in [DECISIONS.md](../DECISIONS.md#phase-1b-planning-document-22-october-2026).

## Decisions

| ID | Decision and where it now lives | Decision status |
|---|---|---|
| P1 | Pending/rejected/suspended sellers get their own status page only; [accounts](accounts.md), Roles | Accepted 22 October 2026 |
| P2 | Owner-owned SECURITY DEFINER audit triggers, direct-write revocations and runtime-role checks; [accounts](accounts.md), Shared audit boundary | Accepted 22 October 2026 |
| P3 | Narrow review-moderation audit API; shared trigger boundary in [reviews](reviews.md), [catalogue](catalogue.md), [checkout](checkout.md), linked to accounts | Accepted 22 October 2026 |
| P4 | Bound transaction-local actor and reason on every action, NULL system actor and context reset; [accounts](accounts.md) | Accepted 22 October 2026 |
| P5 | Required CI staging/exit evidence; [ci](ci.md), Contract, is the only CI authority | Accepted 22 October 2026 |
| P6 | Coverage, hosted runner/kernel validation and quality tooling policy; [ci](ci.md), Decisions | Accepted 22 October 2026 |
| P7 | Accounts date/scope and effort risk; [accounts](accounts.md) and [PLAN.md sections 12–14](../../PLAN.md#12-team-and-work-split-proposal-edit-freely) | Accepted 22 October 2026 |

## Review notes

22 October 2026: incorporates the Claude feedback supplied by Chee Long and Codex inspection of the existing account
models/views/forms/mixins, role grants, demo seeder, real-database fixtures and downstream workstream plans. This is a
planning review, not a runtime verification report. No application changes or successful database/CI checks are claimed.
The earlier feedback is not Claude's approval of this revised proposal.

22 October 2026, independent Claude Code plan review: CHANGES REQUESTED. CI was defined both here and in
ci.md, and the accounts amendments belonged in accounts.md; the fix round below resolved both. P2 and P4 were
verified on a disposable PostgreSQL database: trigger writes under the runtime role, direct audit writes refused,
and actor/reason context cleared after commit and rollback.

22 October 2026, fix round: accepted P1–P7 mapped to canonical plans; duplicate/stale CI contract removed; draft retained.

22 October 2026: all decisions applied in their canonical plans, which Chee Long approved; this record is done.
