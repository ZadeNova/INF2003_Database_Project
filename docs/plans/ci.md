# ci: Real-database correctness, quality gates and demo-story tests

status: in-progress
plan owner: Chee Long · implementer: Chee Long · Phases 1B–4 (25 October to 4 November 2026)
· depends on: `foundation`; extend feature and benchmark checks as their workstreams land

## Contract

**Goal (CI1).** Deliver E4/E5 in [PLAN.md](../../PLAN.md). This is the sole CI contract; Phase 1B acceptance and
final workstream completion have separate exit checks. Implementation waits for fresh review and plan approval.

| Stage | Required checks and exit check |
|---|---|
| 1: Phase 1B, from 25 October | On pull requests and pushes to main: full Django suite through `migrate` with real PostgreSQL/replica-set MongoDB; analytics pipeline tests in `tools`; host Git-index and packaging tests with `--noconftest`; `check_docs.py`; fresh migrations and drift check. Exit: every check passes on real hosted runs for the reviewed revision, with PR/main run links recorded; local passes alone do not close this stage |
| 2: by Phase 3A, 28–29 October | Add Ruff, coverage gate, pip-audit and Playwright of the implemented demo story. Exit: all required jobs green on main; test/lint/coverage/audit failures fail their jobs, and a failing browser case produces useful artifacts |
| 3: after the 30 October freeze, by 4 November | Complete T8's format check: once no workstream branch has unmerged code, land one `ruff format` commit on main, then add `ruff format --check` as a required job. Exit: the format job is required and green on main |

**Jobs and fixtures (CI2–CI4).** Build the checked-out app and pinned tools environments; use repository Compose
images, authenticated databases and owner/runtime separation. Generate ephemeral values with `src/tools/init_env.py`;
wait for health checks and migrate as owner. Routine jobs import `import_olist --source tests/fixtures/olist/clean`
through `migrate`, then run `seed_demo`: no full import, translation-model download or Kaggle access. Host tests must
actually cover the Git-index tests skipped without Git in Docker. Every Compose invocation supplies a unique job/run
project name with `-p`, overriding `compose.yaml`'s hard-coded `name: mercer`; teardown targets only that same project.
Use `pull_request`, never `pull_request_target`, least-privilege permissions (`contents: read` unless justified),
actions pinned to verified commit SHAs and explicit job timeouts. No repository secrets are needed. Keep `.env`,
passwords, connection strings and interpolated configuration out of logs/artifacts. No mocks, SQLite or hidden failures.

**Quality and browser scope (CI5–CI6).** Pin coverage, Ruff, pip-audit and pytest-playwright/Playwright in a separate
`requirements-dev.txt`; leave existing pytest pins in `src/requirements.txt`. Add a pinned translation-environment
requirements file and use it in the translation build so pip-audit can check that environment as well as app/tools.
Coverage runs inside `migrate`, including management commands. Playwright drives `web` with the runtime role, never
owner credentials. Add the real demo journeys as features land: registration/approval, scoped seller CRUD/photos,
browse/filter, multi-seller checkout, lifecycle/refund, reviews, wishlist and dashboard/activity. Add B1–B6 correctness
checks with the benchmark's isolated services/credentials as available; hosted CI supplies no final benchmark timing.

Publish useful results and failure diagnostics without secrets. Document reproduction commands in README/AGENTS.md
when implemented. Until CI is operational, keep the full-suite-before-merge rule. No deployment or Tier 2/3 scope.

## Decisions

Chee Long accepted these decisions on 22 October 2026; plan approved the same day.

| ID | Accepted decision |
|---|---|
| a | GitHub Actions on `pull_request` and pushes to main. Stage 1 jobs required from Phase 1B; Stage 2 jobs added at 3A. Branch protection requires a PR and passing checks, blocks force pushes, and requires no GitHub approvals: fresh Claude Code review is the review gate |
| b | GitHub-hosted runners pinned by name, never `latest`: the `databases` job on `ubuntu-22.04` (kernel 6.8), the `host` job on `ubuntu-24.04` (amended 22 October 2026, below); print the kernel and fail clearly for versions 6.19 through 7.0.13 inclusive (DECISIONS foundation-m). Use self-hosted only if MongoDB fails on the hosted runner; never skip real MongoDB checks. For a private repository, confirm the owner account's available included minutes before the first hosted run; budget recommendation below |
| c | Measure baseline first; enforce 80% line coverage of `src/` excluding migrations. Report branch coverage without enforcing it. Money, role and concurrency tests remain mandatory regardless of percentage |
| d | Ruff lint only during the sprint: E, F, I; line length matches existing code. The `ruff format` gate is deferred, not dropped: stage 3 adds it after the 30 October feature freeze and by 4 November, completing PLAN.md T8 |
| e | pip-audit fails on any advisory with an available fix. Exceptions file records advisory ID, reason, owner and expiry at most two weeks away; do not suppress failures silently |
| f | Chromium only, Python `pytest-playwright`, one serial job; keep trace and screenshot on failure for seven days |
| full-data | Full import, `verify_olist` and full determinism check on `workflow_dispatch` and main pushes touching `data/`, `scripts/` or the importer; separate from routine PR jobs. Run manually if hosted memory is insufficient; record the evidence rather than claiming hosted success |

**Budget recommendation requested 22 October (amount pending confirmation).** Plan for at most 2,000 standard Linux
runner-minutes/month, capped by the owner's remaining included allowance across repositories, with $0 paid overage.
Confirm the account plan/remaining allowance and configure spending controls before hosted runs; this docs change
does not alter billing. GitHub Free includes 2,000 minutes; other plans/usage can change the available balance
([included usage](https://docs.github.com/en/billing/reference/product-usage-included),
[budget controls](https://docs.github.com/en/billing/how-tos/set-up-budgets)).

## Review notes

22 October 2026, independent plan review (fresh Claude Code session; planning only, nothing implemented or run in
CI). Checked against PLAN.md sections 12 to 14, AGENTS.md, the completed olist-import plan, `compose.yaml`,
`src/requirements.txt`, `scripts/translation.Dockerfile` and DECISIONS foundation-m. Real PostgreSQL and authenticated
replica-set MongoDB, no mocks or SQLite, the full Django suite through `migrate`, pipeline tests, host Git-index tests,
`check_docs.py`, Ruff, coverage, pip-audit and incremental Playwright are all covered. Start date and 3A target match
section 13. Not ready for owner approval until the blocker is fixed.

**Blocker**
- **CI1 (Required checks and exit check, lines 19 to 23 and 36 to 40): no Phase 1B stage.** The exit check needs lint,
  coverage and audit at once, but PLAN.md section 13 makes 1B "CI runs the real-database checks available so far" and
  completes the quality gates in 3A. Define two stages, each with its own exit check: stage 1 (Phase 1B): on pull
  requests and pushes to `main`, the full real-database suite, pipeline tests, host Git-index and packaging tests and
  `check_docs.py` pass on a real hosted run; stage 2 (Phase 3A): Ruff, the coverage gate, pip-audit and Playwright.
  The draft `phase-1b.md` section 7 also defines CI staging with an 80% proposal against decision c's 85%. Keep one
  home: this plan is the CI contract, and phase-1b.md should point here.

**Should fix (not blocking)**
- **CI2 (lines 25 to 28): test data is unstated.** Specify that routine jobs import the committed fixture
  (`import_olist --source` the fixture's clean folder) and run `seed_demo`, with no full import, translation model or
  Kaggle access. Whether full-data determinism or import runs in CI (for example on `main` only) is an owner choice.
- **CI3 (line 16, decision b): isolation is not mechanised.** `compose.yaml` hard-codes `name: mercer`. A job on a
  shared self-hosted machine could otherwise remove a developer's volumes. Require a unique Compose project name per
  job (`-p`) and teardown limited to that project.
- **CI4 (lines 13 to 17): workflow security is missing.** Add: `pull_request` (never `pull_request_target`),
  least-privilege `permissions`, actions pinned to commit SHAs, job timeouts, and no repository secrets needed
  (`init_env.py` generates ephemeral values).
- **CI5 (lines 22 to 23, decision d):** pytest and pytest-django are already in `src/requirements.txt`, so "keep test
  tools out of the runtime dependency set" contradicts current practice. Decide whether coverage, Ruff and Playwright
  go in a separate requirements file or image target, and whether the existing pytest pins move.
- **CI6 (line 22):** the translation environment pins packages inline in `scripts/translation.Dockerfile`, with no
  requirements file to audit. Add one or audit the built image.

**Optional**
- Decision b: pin an explicit runner image (for example `ubuntu-24.04`, not `latest`) and add a step that prints the
  kernel and fails clearly in the 6.19 to 7.0.13 range that foundation-m records for MongoDB 9.0.
- Say that Playwright drives `web` under the runtime role, and that coverage runs inside `migrate`, where the tests
  run, with management commands included.
- Benchmark correctness gates depend on the bench database credentials raised in the benchmark review (BM1).

**Owner decisions to resolve:** a (provider, triggers, required checks, branch protection), b (runner and OS), c
(coverage threshold and denominator, reconciled with phase-1b.md's 80%), d (Ruff rules, formatting gate, dependency
layout), e (pip-audit exception policy), f (browser matrix, job parallelism, artifact retention). New, from CI2:
whether full-data checks run in CI.


22 October 2026, fix round: CI1–CI6, a–f/full-data decisions and requested minutes-budget recommendation applied; draft retained.

22 October 2026: approved by Chee Long (plan owner) after the fresh Claude Code re-review of the fix round.

22 October 2026, independent Codex implementation review of `e3c7d2c`: **APPROVE; no CR findings.** Verified the
Action release SHAs through GitHub's API, PR/main triggers, read-only permissions, pinned runner, timeouts, secret
masking, project isolation and all stage 1 checks. Extracted kernel-guard boundary checks passed; the host skip guard
passed the real report and rejected a report with a skipped case. The isolated `mercer-ci-review` reproduction passed
fresh migrations, drift, fixture import, demo seeding, the full Django suite, pipeline tests and host Git-index/
packaging tests in a temporary pinned Python environment. Generated secret values were absent from database logs.
Teardown removed only the review project's containers, network and volumes; the original `mercer` volume metadata
and running container identities were unchanged. Removed the worktree's generated `.env`. Commands and actual
results are in the review chat. Hosted PR/main evidence is still required to close stage 1; stages 2 and 3 remain.

22 October 2026, decision b amended by Chee Long: the main run after PR #4 failed the kernel guard on
`7.0.0-1017-azure`. ubuntu-24.04 image 20261021 moves to that kernel, and MongoDB 9.0 refuses every Ubuntu 7.0 kernel
because Ubuntu reports them as 7.0.0 (SERVER-136848, open); no MongoDB release fixes SERVER-121912. The `databases`
job moves to hosted `ubuntu-22.04` (kernel 6.8, which that release cannot exceed); `host` stays on `ubuntu-24.04`.
Real MongoDB checks still run on hosted runners; self-hosted remains the fallback.

22 October 2026, hosted stage 1 exit verification (Codex): the [PR #4 run](https://github.com/ZadeNova/INF2003_Database_Project/actions/runs/39793132301)
passed, but the [main run after PR #4](https://github.com/ZadeNova/INF2003_Database_Project/actions/runs/39794200058)
failed before database setup because the kernel guard rejected `7.0.0-1017-azure`. After decision b's runner fix,
the [runner-kernel PR #5 run](https://github.com/ZadeNova/INF2003_Database_Project/actions/runs/39796588676) and
[main run after PR #5](https://github.com/ZadeNova/INF2003_Database_Project/actions/runs/39798217952) passed;
their database logs printed `6.8.0-1070-azure`. The [accounts PR #6 run](https://github.com/ZadeNova/INF2003_Database_Project/actions/runs/39801783027)
and [main run after PR #6](https://github.com/ZadeNova/INF2003_Database_Project/actions/runs/39803121613) also passed
both jobs. **CI stage 1's exit check passed on GitHub.** Stages 2 and 3 remain; the CI workstream stays in progress.
