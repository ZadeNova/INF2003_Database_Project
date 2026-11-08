# Repository guide

@AGENTS.md

Before starting a task, run the phase check in AGENTS.md against PLAN.md section 13, and check the task against
[RUBRICS.md](RUBRICS.md): the team is aiming for an A.

## Erfan's workflow (supersedes AGENTS.md "Workflow" and the plan-approval step of the phase check)

Erfan is the sole owner and approver while Chee Long is away; read "owner" and "plan owner" in AGENTS.md as Erfan.
AGENTS.md stays unedited for Chee Long and Codex. The Rules, Architecture, Documentation map and Running sections
still apply in full.

1. Discuss and plan.
2. Review the plan and state the trade-offs, with a recommendation.
3. Erfan decides. Build nothing before that.
4. Implement on the current branch.
5. Review with Opus 5.5 after a large change or when Erfan asks. It runs things, not only reads the diff.
6. Erfan reviews the findings; one fix round.

- **No new branches** unless Erfan asks. No commits or pushes unless asked. The branch-and-pull-request rule is waived.
- **Docs follow every change:** update whatever the AGENTS.md documentation map says the change touches, in the same
  pass, and run `scripts/check_docs.py`. Also update the improvements.md status and Decisions row for backlog items.
- **Checks to run:** docs and copy changes need `check_docs.py`. Changes touching schema, raw SQL, money, roles,
  uploads or concurrency also need the full Docker suite.
- **Tests that start their own threads** must wrap the thread body in `mongo.using_database(mongo_db.name)`. MongoDB test
  routing is per thread; an unrouted thread writes to the real application database (this overwrote two dev product
  specifications once, repaired from the import data).
- Skipped: the per-workstream close-out (AI_USE line, `status: done`). Lasting decisions still go in `docs/DECISIONS.md`.
- **Teammate lane (photos and demo products).** The branch `improvements/photos` is worked on by a teammate and touches only
  `data/demo_photos/**` and the `merchants`, `categories` and `products` lists of `data/demo_showcase/catalogue.json`. Claude
  does not edit those lists or the photos, and the teammate does not edit code, docs or the other parts of the file. Erfan
  merges the branch; after a merge run `seed_showcase`, `scripts/check_docs.py` and the full suite once.

