# Repository guide

@AGENTS.md

Before starting a task, run the phase check in AGENTS.md against PLAN.md section 13 (for code workstreams; a branch with
its own allocated plan, listed below, follows that plan instead), and check the task against [RUBRICS.md](RUBRICS.md):
the team is aiming for an A.

## Everyone

### Workflow

1. **Plan and review the plan.** Read the workstream's plan in `docs/plans/`, state the trade-offs and a recommendation,
   and get the plan owner's decision before building. Small changes (typos, copy, one-line fixes) skip this.
2. **Implement** on your current branch. Do not create branches, commit or push unless your owner asks.
3. **Review.** After a large change, or when asked, run the relevant checks. A review runs things, not only reads the
   diff. One fix round; leftovers become follow-ups.

### Shared rules

- **Docs follow every change:** update whatever the AGENTS.md documentation map says the change touches, in the same
  pass, and run `scripts/check_docs.py`.
- **Checks to run:** docs and copy changes need `check_docs.py`. Changes touching schema, raw SQL, money, roles,
  uploads or concurrency also need the full Docker suite.
- **Tests that start their own threads** must wrap the thread body in `mongo.using_database(mongo_db.name)`. MongoDB test
  routing is per thread; an unrouted thread writes to the real application database (this overwrote two dev product
  specifications once, repaired from the import data).
- Lasting decisions go in `docs/DECISIONS.md`.

### Branches with an allocated plan

If your branch is listed here, follow its plan and edit only the files the plan allows. Ignore the "Owner only"
section below.

| Branch | Plan | Files you may edit |
|---|---|---|
| `improvements/photos` | [product_photos](docs/plans/product_photos.md), section "Teammate instructions" | `data/demo_photos/**` and the `merchants`, `categories` and `products` lists of `data/demo_showcase/catalogue.json` |

## Owner only (Erfan, on `improvements/backlog`)

**Applies only when working for Erfan on `improvements/backlog`. Ignore on any other branch.**

Erfan is the sole owner and approver while Chee Long is away; read "owner" and "plan owner" in AGENTS.md as Erfan.
AGENTS.md stays unedited for Chee Long and Codex. The Rules, Architecture, Documentation map and Running sections
still apply in full. This section supersedes AGENTS.md "Workflow" and the plan-approval step of the phase check.

1. Discuss and plan.
2. Review the plan and state the trade-offs, with a recommendation.
3. Erfan decides. Build nothing before that.
4. Implement on the current branch (`improvements/backlog`).
5. Review with Opus 5.5 after a large change or when Erfan asks. It runs things, not only reads the diff.
6. Erfan reviews the findings; one fix round.

- **No new branches** unless Erfan asks. No commits or pushes unless asked. The branch-and-pull-request rule is waived.
- Also update the improvements.md status and Decisions row for backlog items.
- Skipped: the per-workstream close-out (AI_USE line, `status: done`).
- Do not edit the files of a branch listed in "Branches with an allocated plan" while that branch is open. After
  merging one, run `seed_showcase`, `scripts/check_docs.py` and the full suite once.
