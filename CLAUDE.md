# Repository guide

@AGENTS.md

Before starting a task, run the phase check in AGENTS.md against PLAN.md section 13 (for code workstreams), and check the task against [RUBRICS.md](RUBRICS.md):
the team is aiming for an A.

## Everyone

### Before you commit or push (every time)

Work from the latest state of the branch, so nobody overwrites or reverts a teammate's work (a stale branch once
removed docs and renumbered PLAN.md; a revert then undid good edits).

1. `git fetch`, then `git status -sb` and `git log --oneline HEAD..origin/<your-branch>`. If you are **behind**, stop:
   `git pull --rebase` (or merge), resolve conflicts, and re-read the files you changed before going on.
2. A new branch starts from the **latest** `origin/improvements/backlog` (or `origin/main` for work not on the backlog),
   after a `git fetch`: `git switch -c <workstream>/<topic> origin/improvements/backlog`. Never branch from an old branch.
3. Before the commit, read `git diff --stat` against the base: it must contain only the files you meant to change. A diff
   that deletes or renumbers content you did not touch means the branch is stale; stop and fix that first.
4. Run the checks below, commit, then fetch again before pushing. Open a pull request; no direct pushes to
   `improvements/backlog` or `main`.

### Workflow (everyone)

1. **Plan and review the plan.** Read the workstream's plan in `docs/plans/`, state the trade-offs and a recommendation,
   and get the plan owner's decision before building. Small changes (typos, copy, one-line fixes) skip this.
2. **Implement** on your own branch. Commit and push only when you are asked to or the task says so.
3. **Review.** After a large change, or when asked, run the relevant checks. A review runs things, not only reads the
   diff. Reviewers report; the author (with the plan owner) decides each finding and then fixes it. Batch 7 of the backlog
   runs several review rounds ([improvements](docs/plans/improvements.md#batch-7-code-quality-pass-then-the-full-codebase-review));
   findings are ranked Major, Medium or Minor, and rounds continue until nothing Major is left.
4. **Do not rewrite shared documents to remove content** (disclosures, decisions, section numbers) without the team's
   agreement recorded in `docs/DECISIONS.md`.

### Shared rules

- **Docs follow every change:** update whatever the AGENTS.md documentation map says the change touches, in the same
  pass, and run `scripts/check_docs.py`. Update the improvements.md status and Decisions row for backlog items.
- **Checks to run:** docs and copy changes need `check_docs.py`. Changes touching schema, raw SQL, money, roles,
  uploads or concurrency also need the full Docker suite.
- **Tests that start their own threads** must wrap the thread body in `mongo.using_database(mongo_db.name)`. MongoDB test
  routing is per thread; an unrouted thread writes to the real application database (this overwrote two dev product
  specifications once, repaired from the import data).
- Lasting decisions go in `docs/DECISIONS.md`.

### Review rounds (read-only)

A reviewer works from the latest commit of `improvements/backlog` in a detached checkout and edits, commits and pushes
nothing; the plan and prompts are in [review_rounds](docs/plans/review_rounds.md).
