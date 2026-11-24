# ci: Real-database correctness, quality gates and demo-story tests

status: done
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

23 October 2026, Codex startup correction (ci-i9), requested in the owner's handoff: attached mongosh credential
arguments in the startup script and healthcheck; retry newly generated secrets that start with `-`, retaining
existing `.env` values. Regression checks cover generated secret size/alphabet, existing credentials, and both
command forms. `migrate` mounts `compose.yaml` read-only so the same checks run inside Docker. README troubleshooting
explains the difference between empty-volume setup and existing credentials. Phase check: this is stage 1
maintenance, dependent on the completed foundation; stages 2 and 3 remain outside this change.
Fresh Claude Code review and hosted verification are pending; the owner requested all changes remain uncommitted.

Local implementation verification used the isolated Compose project `mercer-ci-password-dash`, an ephemeral MongoDB
host port, and deliberately dash-leading root username and password supplied through the process environment.
Fresh-volume startup and restart with the same credentials both became healthy; owner-role migrations passed.
The full Django suite through `migrate` passed, including the new startup/secret regression checks; only the
Git-index tests skipped in the Git-free app image. Host documentation/Git-index/packaging tests ran without skips
and passed, as did `scripts/check_docs.py`. Command outputs are in the
implementation chat; this evidence does not replace the independent review or hosted PR/main checks.

23 October 2026, independent fresh Claude Code review of the uncommitted ci-i9 change (on `6a5f874`): **APPROVE, no
blockers.** Phase check: stage 1 maintenance of the in-progress `ci` workstream; `foundation` is done. Checks used a
separate project (`-p mercer-review-dash` with a matching `COMPOSE_PROJECT_NAME`, `MONGO_PORT=0`) and process-environment
overrides in which the root username, root password and application password all began with `-`. A fresh volume
became healthy; Docker stored the healthcheck with variable names, so `$$` escaping holds. Owner migrations, the drift
check, the fixture import, `seed_demo` and the full suite passed through `migrate`; only the Git-index tests skipped.
Restarting on the populated volume became healthy again. The old `-u`/`-p` form, run in the same container with the same
password, reproduced the CI error ("unrecognized option"), and the application user authenticated with its dash-leading
password. Wrong passwords shaped like `--eval`, `-p`, `--`, `a=b=c` and a leading space failed authentication, not
argument parsing; users created with `12345`, `true` and `-1e5` authenticated, so values stay strings. With a changed
root password on the populated volume, the healthcheck command failed authentication, as the README says (no
rotation). Host documentation/Git-index/packaging tests passed without skips (with a short `--basetemp`; a long one
made `git add` fail on Windows), as did `scripts/check_docs.py` and `git diff --check`. Mutation runs on a scratch copy
showed the new tests fail when the retry loop is removed, when either startup call returns to `-u`/`-p`,
`--password VALUE` or `-p"$X"`, or when the healthcheck uses `-u`/`-p` or a single `$`. The `compose.yaml` mount is
appropriate: it holds only variable references, is read-only, is limited to `migrate`, and without it the test fails
loudly instead of skipping.
**Optional:** CS1, the source-text test (`tests/test_init_env.py:62`) compares `shlex` tokens, so dropping the double
quotes still passes; harmless for generated secrets, but a hand-set password with spaces would then break. Asserting the
raw quoted substring would close it. CS2, README Troubleshooting (`README.md:341`) reads as if changing a dash-leading
password were required; after the fix it is optional. CS3, at commit, drop "implementation awaiting review" from the
DECISIONS heading (`docs/DECISIONS.md:43`). Not caused by this change: the `0o600` assertion in
`test_a_missing_env_is_created_private_with_generated_secrets` cannot pass on a Windows host; it passes in Docker.
Hosted PR and main runs remain pending until the owner pushes.

23 October 2026, fix round (Claude Code, at Chee Long's request), still uncommitted: CS1 adds raw-text assertions for
the quoted `--username="..."`/`--password="..."` arguments in both the startup script and the healthcheck; the
unquoted mutations that previously passed now fail. CS2 says a dash-leading password works as it is, and any change
belongs on an empty volume only. CS3 drops "implementation awaiting review" from the DECISIONS heading.
`tests/test_init_env.py` passed in Docker (separate project `mercer-review-cs`, since removed), and
`scripts/check_docs.py` and `git diff --check` passed. Pre-merge run on the fixed tree, following the README's
continuous-integration commands in the separate project `mercer-review-final` (since removed): build, owner
migrations, the drift check, the fixture import, `seed_demo`, the full suite (only the Git-index tests skipped) and
the pipeline tests all passed; the host Git-index/packaging tests passed without skips.

25 October 2026 — Implementation notes (Codex; reviewer: pending (Claude Code)). Stage 2 is implemented on
ci/stage-2-quality-browser from the merged Phase 3A main. Added a separately tagged dev image for migrate, pinned
development dependencies, Ruff E/F/I configuration and the required import/statement/name corrections, a single
coverage run with a line-only gate and original branch artifacts, strict audits with expiring exception metadata,
and serial Chromium journeys against runtime web. Browser tests are excluded from Django collection and do not
inherit its owner database fixtures. Demo passwords and authentication cookies are redacted from retained traces
and console output; upload is conditional on successful sanitization.

The baseline was measured before application lint changes, using real PostgreSQL and replica-set MongoDB in the
isolated mercer-ci2-baseline-20261024 project. Its original branch data is retained; the unexecuted namespace helper
tools/collect_static.py is included in the complete source denominator. The final configuration includes namespace
files from the outset. Gate policy tests use real CoverageData and exercise a fully covered line report whose
combined branch percentage is below the threshold, plus a failing line report and exception expiry/fix guards.

Chee Long approved one scope amendment on 25 October: upgrade only translation setuptools to the verified fixed
release, since the unchanged pin failed on advisories with fixes. Other translation pins and Argos --no-deps remain
as specified. The exception file remains empty. Decisions ci-i10–ci-i16 record the implementation choices.

The fixture exposes only two established public shops. The checkout journey creates a third shop through the real
application/approval/product UI, so it does not depend on the photo journey running first. Each journey uses its own
new account/order where possible; stock and visible-alert preconditions are established through the UI. The canary
is normal on ordinary runs and deliberately fails only with the explicit flag. Local results and elapsed job times
are generated below from the reproduction logs; this is not hosted stage 2 acceptance. PR/main required jobs and a
hosted forced-failure run with useful artifacts still await review/push. Stage 3 and benchmark checks are deferred;
ci and PLAN.md section 14 remain in progress. No push, PR, merge, billing or repository-setting change was made.

<!-- stage-2-local-results:start -->
Local verification below was generated from the saved command outputs and JSON timing records on 25 October 2026.
Evidence is retained in the ignored .cache/ci-stage2 folder for the fresh local review.

| Check | Observed output or generated metric |
|---|---|
| Before-change baseline | `624 passed, 4 skipped in 433.30s (0:07:13)`; complete src line coverage **93.36%** |
| Final full suite, one coverage run | `635 passed, 4 skipped in 387.46s (0:06:27)` |
| Line-only gate | **93.33%**, 2729/2924 statements covered; threshold passed |
| Branch report, informational | **83.28%**, 533/640 branches covered; original XML/HTML retained |
| Pipeline | `39 passed in 2.98s` |
| Chromium normal run | `8 passed in 41.07s` |
| Forced canary, expected exit 1 | `1 failed, 7 deselected in 2.19s`; 1 valid trace ZIP and 1 PNG screenshot; generated-secret scan passed |
| Ruff | `All checks passed!` |
| Host tests | `28 passed in 2.82s`; `host tests: 28 run, 0 skipped` |
| Documentation | `check_docs: ok` |
| Workflow validation | actionlint exited 0 with no findings |
| Translation image | Build and offline Argos/CTranslate2/SentencePiece import check passed with the approved setuptools pin |

Dependency audit output (the extra Argos file covers its intentionally separate no-deps installation):

```text
src\requirements.txt: 17 dependencies, 0 advisories, 0 with fixes
src\requirements-dev.txt: 51 dependencies, 0 advisories, 0 with fixes
analytics\requirements.txt: 11 dependencies, 0 advisories, 0 with fixes
scripts\translation-requirements.txt: 6 dependencies, 0 advisories, 0 with fixes
scripts\translation-argos-requirements.txt: 1 dependencies, 0 advisories, 0 with fixes
```

| Local job reproduction | Elapsed seconds, including setup | Workflow timeout (minutes) |
|---|---:|---:|
| databases | 428.44 | 45 |
| host | 38.36 | 10 |
| quality | 122.43 | 15 |
| browser | 173.80 | 25 |

These local job reproductions total 12.72 minutes. The browser measurement includes an extra local
forced-canary invocation and artifact inspection; an ordinary workflow run omits that invocation. Measurements used
Windows Python 3.13.7, Linux Docker databases, warm image-build caches, fresh host virtual environments and a fresh
Chromium download. Windows installed Chromium without Linux-only system dependencies; the hosted workflow uses
--with-deps on Ubuntu. Checkout, hosted runner setup and artifact-upload time are not measured. These are local
observations, not hosted duration or billing claims; the owner budget remains at most 2,000 Linux runner-minutes.

The first host harness attempt reported `9 failed, 19 passed in 2.97s` because its temporary trees were under the ignored
.cache directory and inherited the parent Git repository. Rerunning unchanged tests with a short system-temp
directory outside the checkout produced the final host result above. README now uses that setup. The four
Git-index-only skips in the Git-free migrate image are covered by the zero-skip host run.

Fresh owner migrations, drift checking, fixture import, seed_demo and seed_activity completed successfully.
Runtime-image inspection confirmed the added dev tools are absent. Both final Compose projects were torn down,
including their volumes; the mercer project was not used. Earlier development browser failures were corrected
before the fresh final run. No test was weakened or skipped to obtain these results.

Still pending: fresh Claude Code review, then owner-authorized PR/main hosted runs and a hosted forced browser
failure whose artifact is inspected. Stage 2 acceptance remains open until those hosted checks pass. The owner
must require these job names: Django suite, migrations and pipeline tests (real PostgreSQL and MongoDB);
Documentation check and host Git-index/packaging tests; Python lint and dependency audit; Chromium demo story
(runtime web). Repository protection and billing were not changed. Stage 3 formatting and benchmark gates remain
outside this implementation.
<!-- stage-2-local-results:end -->

26 October 2026 — Claude Code review and hosted stage 2 exit verification (Codex). Claude Code independently reviewed
46731ad: **APPROVE, no blocking findings**, with isolated real-database, browser, quality and artifact checks.
The reviewed head was merged unchanged through [PR #20](https://github.com/ZadeNova/INF2003_Database_Project/pull/20).
The [PR run](https://github.com/ZadeNova/INF2003_Database_Project/actions/runs/40209429862) and [main run](https://github.com/ZadeNova/INF2003_Database_Project/actions/runs/40210271108) passed every job.
The [forced-failure run on main](https://github.com/ZadeNova/INF2003_Database_Project/actions/runs/40211006571) reported `1 failed, 7 passed in 39.46s`:
only test_failure_artifact_canary failed; the seven journeys passed and the other jobs succeeded.

| GitHub job | PR | Main | Forced failure |
|---|---|---|---|
| Django suite, migrations and pipeline tests (real PostgreSQL and MongoDB) | success (9m27s) | success (8m4s) | success (7m10s) |
| Documentation check and host Git-index/packaging tests | success (27s) | success (19s) | success (21s) |
| Python lint and dependency audit | success (53s) | success (47s) | success (56s) |
| Chromium demo story (runtime web) | success (4m8s) | success (3m24s) | failure (2m54s) |

Job results and durations above were generated from GitHub's completed-run metadata.
The sanitize and upload steps succeeded. The browser-failure artifact's API creation/expiry metadata confirms
seven-day retention. Its downloaded trace ZIP opened and passed checksum checks; the PNG screenshot verified.
Trace entries contained redaction markers for the login password, session and CSRF cookies. No Cookie or
Set-Cookie value survived. Hosted generated secrets were unavailable outside the run, so inspection checked
the redaction markers rather than claiming a scan against unknown secrets. The downloaded folder was deleted.

**Stage 2's exit check passed on GitHub.** Stage 3 remains: the ruff format gate after the 30 October freeze.
The CI plan stays in-progress and PLAN.md section 14 stays in progress. The owner must still require the four
job names above in Settings → Branches for main; this task did not change protection or repository settings.

Claude Code's non-blocking follow-ups, for stage 3 or later:

- Choose the Ruff line length when the formatter lands: 230 currently allows isort to join imports onto roughly 200-character lines.
- The dated dashboard browser assertion was fixed in the 29 October integration-review round below.
- Remove the leading blank line in src/dashboard/views.py with the formatting work.

29 October 2026 — Implementation notes (Codex; reviewer: pending (Claude Code)). The Phase 4 integration-review
fix round corrects the documented smoke script's customer, approved-seller and operator landing paths, retaining
the Log out check and standard-library-only implementation. A Django test imports its expectations, seeds the
real Olist fixture and compares every role with landing_url. The browser CI job now runs the README smoke command
through migrate after seed_demo and healthy runtime web; it prints no credentials, cookies or response bodies.

The demo-product helper follows the seller list through its last page and checks detail labels only on active
low-stock candidates, including products temporarily restocked by another journey (ci-i18). The dashboard journey
now parses each panel's displayed reporting date and requires all panels to agree, clearing the dated-test follow-up.
Stage 3 still owns the format gate, line length and the blank first line in src/dashboard/views.py. README/AGENTS
status summaries and the team timeline point to PLAN.md; stale generator/load-script/date statements are corrected,
and the recording-day checklist includes a full-data browser run. The CI plan remains in-progress and PLAN.md
section 14 is unchanged. Application code, migrations and Part B's reviewed paths were not changed.

<!-- phase-4-local-results:start -->
Local results generated on 29 October 2026 from saved command logs, coverage JSON and host JUnit XML
in the ignored .cache/phase-4-review directory. Every command below exited 0.

| Check | Observed output or generated metric |
|---|---|
| Full Django suite under coverage | `638 passed, 4 skipped in 478.28s (0:07:58)` |
| Line-only gate | `93.43% (2773/2968 statements); threshold passed` |
| Branch coverage, informational | `83.33% (535/642 branches)` |
| Fixture Chromium | `8 passed in 48.97s` |
| Fresh full-data Chromium | `8 passed in 61.80s (0:01:01)` |
| Fixture smoke through migrate | `{"/": 200, "/health/": 200, "/products/": 200, "customer_login": "passed", "operator_login": "passed", "product_detail": 200, "seller_login": "passed"}` |
| Fresh full-data smoke through migrate | `{"/": 200, "/health/": 200, "/products/": 200, "customer_login": "passed", "operator_login": "passed", "product_detail": 200, "seller_login": "passed"}` |
| Analytics pipeline | `39 passed in 4.60s` |
| Ruff | `All checks passed!` |
| Host Git-index/packaging | `28 passed in 2.77s; host tests: 28 run, 0 skipped` |
| Documentation | `check_docs: ok` |
| Workflow validation | `actionlint exited 0 with no diagnostics` |
| Independent Part B test modules | `156 passed in 203.06s (0:03:23)` |
| Independent runtime probes | `All account runtime privilege and status/audit probes passed; row/schema changes rolled back.` |

Fresh-install step timings generated by the private runner (including Compose startup overhead):

| Step | Elapsed seconds |
|---|---:|
| init | 0.08 |
| hook | 0.05 |
| up | 15.69 |
| databases | 1.74 |
| import | 33.99 |
| verify | 6.09 |
| seed | 4.94 |
| smoke | 3.44 |
| activity | 4.27 |

The import itself printed duration_seconds=31.157 and process_peak_rss_kib=251720.
The fresh local clone started from b4277b8 with this fix diff applied, no .env and fresh volumes. It followed
README setup/load order, using its own project mercer-p4fix-full and loopback port; up used --detach --wait
so health was checked automatically. The fixture reproduction used mercer-p4fix-fixture and a separate
private environment. Images used the existing build cache. Both browser runs used the pinned Windows tools
and runtime web; browser processes received only demo logins. Raw commands and per-step timings are retained
beside their logs. The initial Ruff run found one extra blank line before the new smoke constant; it was
corrected before the final successful run. The four Git-index-only Docker skips are covered by the host
run with no skips. All application source and Part B paths remained unchanged. Teardown removed only
the two mercer-p4fix projects and their volumes; no containers or volumes remained for either project.
<!-- phase-4-local-results:end -->

The separate independent Codex review of Claude Code's roles, grants and account audit SQL is retained outside Git
in .cache/phase-4-review/codex-review.txt. Fresh Claude Code review of this fix branch is pending. This round does
not close Phase 4 or CI stage 3; the owner requested a local commit only, with no push, PR or merge.

29 October 2026 — Review notes: Claude Code (the session that ran the Phase 4 integration review; not a fresh session) reviewed `2d73bd63b9e0003cf60c1b96843a53a7d33b89b5`; the owner reports a fresh full-data install in its own Compose project (torn down afterwards): import_olist, verify_olist and seed_demo passed; smoke_olist.py passed all three role landings; seed_activity and all Chromium journeys passed (`8 passed in 51.57s`); tests/test_smoke_olist.py, tests/test_roles.py, tests/test_registration.py: 112 passed. The docs edits were read against PLAN.md and Part B's evidence in .cache/phase-4-review/codex-review.txt was checked. Results are recorded from the owner's review report. CI remains in-progress for stage 3.

29 October 2026 — Implementation notes, stage 3 (Codex; reviewer: pending (Claude Code)). The owner invoked the
completion-based Phase 4 start rule and authorised the branch cleanup and two local commits for this run, with
Claude Code review next. After fetching and archiving merged-worktree evidence, every existing local and remote
branch was confirmed merged into origin/main `594cc71165605fdfa75b046e6d53c7c81ef88308`, with no open PR.
The retained Claude app worktree and branch were clean and left in place. The Codex checkout-fix worktree was
cleared and unregistered, but Windows held its empty directory open; no process was terminated to remove it.

The shared Ruff line length is now 120. The first commit contains only that setting and formatter output;
import ordering already passed, so no import fix or manual wrap was needed. The remaining E501 diagnostics
were classified from the formatter output, with generated counts below. E501 is ignored centrally because the
formatter owns line length and leaves long string literals and URL comments intact. E/F/I remain the only
selected lint families, with no per-line noqa. These owner choices are ci-i19 to ci-i23 in
[DECISIONS.md](../DECISIONS.md).

`python -m ruff format --check .` follows lint in the existing required `quality` job. Its display name remains
"Python lint and dependency audit", so no ruleset change is needed. The formatting commit's full hash is in
[.git-blame-ignore-revs](../../.git-blame-ignore-revs); README documents local blame configuration beside hooksPath.
The private `.cache/stage3/ast_check.py` compares every Python file changed by that commit with its parent using
`ast.dump` after removing docstring nodes. Its separate docstring-change list and diff are retained beside the
AST result; the generated results below record the comparison.

Verification follows README's CI procedure with private credentials, pinned tools and real PostgreSQL/MongoDB.
All Compose commands explicitly name `mercer-stage3-...` projects. Browser processes receive only demo logins.
Benchmark tests and correctness use separate fresh fixture projects so B5 starts before any restore, without
deleting Docker volumes. The benchmark host wrapper accepts only `mercer-bench...` names, so this run invokes
the same `benchmarks.harness` directly through Compose to preserve the owner's project-name rule. It runs all
default baseline/B1–B6 correctness workloads and generates the report; it is local correctness evidence, not
final measurement evidence. The original mercer, catalogue and checkout Docker projects were left in place;
this run's temporary containers/networks are removed after checks, with all volumes retained.

The plan's done status records completed local implementation; **stage 3 closes on the required green main run
after merge**. PLAN.md section 14 stays at review until then. Fresh Claude Code review and that hosted run remain
pending. No stage 3 push, PR, merge or repository-settings change is authorised by this run.

<!-- stage-3-local-results:start -->
Local results generated on 29 October 2026 from retained .cache/stage3 command logs, coverage JSON,
AST/E501 JSON and benchmark runs.csv. Every verification command exited 0. Commands and full output
remain in the ignored directory; benchmark raw operations, checks, plans and reports remain in the
ignored result directory recorded by .cache/stage3/bench-output.txt.

| Check | Observed output or generated metric |
|---|---|
| Formatting commit | `143 files; +5888/-2045 lines; 16a6ef5238b894eea035de51d524acd599a34c98` |
| Post-format E501 classification | `54 diagnostics: 54 string-literal lines; 0 URL-comment lines; 0 long code/other-comment lines; 0 manual wraps.` |
| AST and separate docstring comparison | `AST check: 142 Python files; 0 differences after removing docstrings; 0 files with docstring changes.` |
| Ruff format check | `196 files already formatted` |
| Ruff lint | `All checks passed!` |
| Migration drift | `No changes detected` |
| Full Django suite under coverage | `664 passed, 4 skipped in 440.16s (0:07:20)` |
| Line coverage gate | `TOTAL                                              2981    195  93.46%` |
| Branch coverage, informational | `83.49% (541/648 branches)` |
| Fixture Chromium | `8 passed in 42.86s` |
| Fixture smoke through migrate | `{"/": 200, "/health/": 200, "/products/": 200, "customer_login": "passed", "operator_login": "passed", "product_detail": 200, "seller_login": "passed"}` |
| Benchmark fixture tests | `35 passed in 206.68s (0:03:26)` |
| Benchmark fixture correctness | `Fixture correctness: 70 checks passed, 0 failed (baseline, B1-B6).` |
| Analytics pipeline | `39 passed in 3.23s` |
| Host Git-index/packaging | `28 passed in 2.83s; host tests: 28 run, 0 skipped` |
| Documentation | `check_docs: ok` |
| Workflow validation | `actionlint exit 0` |
| Dependency audit | `src\requirements.txt: 17 dependencies, 0 advisories, 0 with fixes` |
| Dependency audit | `src\requirements-dev.txt: 51 dependencies, 0 advisories, 0 with fixes` |
| Dependency audit | `analytics\requirements.txt: 11 dependencies, 0 advisories, 0 with fixes` |
| Dependency audit | `scripts\translation-requirements.txt: 6 dependencies, 0 advisories, 0 with fixes` |
| Dependency audit | `scripts\translation-argos-requirements.txt: 1 dependencies, 0 advisories, 0 with fixes` |

The Docker skips are the Git-index cases in tests/test_check_docs.py; the host run above covers them
with no skips. No assertion was weakened or test skipped to obtain these results. The full Django
suite ran once. The AST comparison found no docstring changes to inspect; its separate list is empty.
All test projects were stopped and their temporary containers/networks removed; every Docker volume
was retained. Fresh Claude Code review and the required green main run after merge remain pending.
<!-- stage-3-local-results:end -->

29 October 2026 — Review notes: Claude Code (the session that wrote the stage 3 brief; not a fresh session) reviewed `9fbfed4afbf0f0a18e47e6b0861a236153cd99ad`. The owner reports an independent full-AST comparison, including docstrings, of every Python file in formatting commit `16a6ef5238b894eea035de51d524acd599a34c98` against `594cc71`: no differences; its only other change is the Ruff line length from 230 to 120. Pinned Ruff 0.17.0 lint and format checks passed on both the working tree and a git-archive export, with LF stored blobs; check_docs and host tests passed. The reviewer read the gate/docs commit in full and confirmed the unchanged required quality-job name, central E501 ignore, full blame-ignore hash and accurate README/AGENTS/PLAN/DECISIONS edits; branch cleanup was confirmed. The full Django suite was not rerun in review because the AST proof and recorded local run passed; CI reruns it on the PR. PLAN.md now records CI as done; this plan retains status: done, and the stage 3 exit closes on the first green main run after merge.

## Browser installation DNS recovery (11 November 2026)

Owner-authorised maintenance of the completed CI contract during Phase 5. The browser job in
[main run 43033832127](https://github.com/ZadeNova/INF2003_Database_Project/actions/runs/43033832127)
failed during `playwright install --with-deps chromium`. Fresh Claude Code (Opus) review read both attempts' full
logs: APT tried `azure.archive.ubuntu.com`, `archive.ubuntu.com` and `security.ubuntu.com`, and all failed. APT retained
the first error text for an item, which named Azure even after fallback failures. The exact DNS cause is unproved;
this evidence does not isolate an Azure-only outage.

**First review: not approved.** The first candidate removed Azure from the mirror list and set APT retries and
HTTP/HTTPS timeouts. The reviewer found that the official fallbacks already failed, the retry setting reduced APT's
default, the connection timeout did not bound DNS lookups, and strict update errors added an unrelated-repository
failure condition. Its correct syntax and local passes did not establish a remedy. The new decision is grouped with
[the existing CI decisions](../DECISIONS.md#ci-browser-installation-dns-recovery-11-november-2026).

**Fix round.** Keep the runner's APT sources, mirror order, settings and signature checks. The browser install step
reads hostnames from the active runner mirror list and fails clearly if that configuration is missing, unused or
has no HTTP(S) hosts. Each of at most three rounds bounds each DNS lookup with `timeout 10s getent ahosts`; any
resolving configured mirror permits the unchanged pinned Playwright install, so a failed first mirror alone does
not block its fallbacks. If no host resolves, skip that doomed install; after that or a naturally returned install
failure, wait ten seconds then twenty seconds between rounds. Only a successful installer exit passes the step;
exhaustion fails it. The twenty-minute step limit remains the final backstop and can expire during a long install
before another attempt starts. No per-attempt timeout kills APT or dpkg. DNS readiness is a diagnostic and a chance
for transient recovery, not proof of package connectivity or a fix for a persistent resolver fault.

Local checks passed: YAML parsing and comparison confirming only the browser install step changed; Git Bash syntax;
safe substitutes proving fallback DNS permits installation, DNS failures skip installs, natural install failures
retry, exhaustion fails, success stops retries and missing/unused/empty mirror configurations fail clearly;
`python scripts/check_docs.py` and `git diff --check`. No real DNS, install or retry sleeps were used locally.

Fresh Claude Code (Opus) fix-round review: **APPROVE**. Applied its recommendation to raise the install-step
limit to twenty minutes within the unchanged twenty-five-minute job limit, allowing more time for a slow fallback.
This would not have rescued the observed sustained outage: persistent DNS failure still fails clearly. A hosted
browser run remains pending; local substitutes do not prove hosted recovery. No local Docker, WSL, database,
browser or benchmark commands are part of this isolated `ci/ubuntu-browser-mirror` repair.
The completed workstream remains done; every required check, pin and MongoDB kernel constraint is retained.

**Hosted result: failed.** The PR run [43043906693](https://github.com/ZadeNova/INF2003_Database_Project/actions/runs/43043906693)
(browser job 130602694912, commit `656de3a`) timed out on `archive.ubuntu.com`, `azure.archive.ubuntu.com` and
`security.ubuntu.com` in all three DNS rounds, so the installer never ran and the journeys were skipped; the other
four jobs passed. The retries could only help a short blip, and this failure was not one.

**Evidence (second review, Claude Code, Opus).** Read from the full browser-job logs of the PR run, both main attempts
(130567389449, 130575043360) and the passing PR #43 job (130518209692):

- The observed failures affected the three configured Ubuntu mirror names. In the same jobs, PyPI downloads,
  Docker Hub pulls and the checkout worked, and the failing `apt-get update` fetched `packages.microsoft.com` while
  every Ubuntu name gave `Temporary failure resolving`.
- The repository and runner image did not change. PR #43's job passed on 11 November at 12:21 UTC; main failed from
  13:59 UTC on the identical Git tree (`3057ca5`), with the same runner image (ubuntu-22.04 20261101.347.1) and
  agent. The failures came from three Azure regions (eastus2, westus, centralus), and centralus and westus had also
  passed earlier that day.
- The underlying cause remains unproved. The pattern supports an infrastructure fault affecting Ubuntu names
  (Canonical's DNS or Azure's resolvers), but no public Canonical or GitHub incident could be confirmed (the
  Canonical status page did not render for automated reading), and these logs cannot exclude intermittent
  runner-local resolver or network behaviour, including around Compose networking. They do rule out an Azure-only
  mirror fault, because the official fallbacks failed too. IPv6 was not examined. The fix does not depend on the cause.
- `--with-deps` in the pinned Playwright 1.63.0 only runs the APT dependency installer before the same browser
  download. Chrome for Testing and the headless shell come from `cdn.playwright.dev`. Two observations differ:
  - Both failed main attempts found all 22 `chromium` packages Playwright lists for Ubuntu 22.04 already installed,
    and asked the archive only for seven optional fonts (`fonts-unifont`, `fonts-ipafont-gothic`, `fonts-wqy-zenhei`,
    `fonts-tlwg-loma-otf`, `fonts-freefont-ttf`, `xfonts-cyrillic`, `xfonts-scalable`) and two helper packages.
    Their package lists were stale, because `apt-get update` had failed.
  - The passing job, with fresh lists, installed the same nine packages and also upgraded four, including
    `libglib2.0-0` from `2.72.4-0ubuntu2.10` to `2.72.4-0ubuntu2.11`, one of the 22. So no passing run has used the
    image's unupgraded libraries; the next hosted run must show that Chromium works with them.
- The DNS probe also added failure conditions of its own: a missing or changed mirror list, and a 10-second lookup
  limit, shorter than the time APT allowed each lookup in these logs, which could skip an install that would have
  worked. It could never rescue a run in which APT itself fails to resolve.

**Second fix round.** Replace the probe and retries with `python -m playwright install chromium` and return the step
to the job's own limit. The pinned versions, CDN downloads, journeys, artifact and redaction steps, kernel guard
and `ubuntu-22.04` are unchanged. Playwright validates Chromium's shared libraries with `ldd` when a browser
directory has no fresh `DEPENDENCIES_VALIDATED` marker (it is valid for 30 days). Installation runs that check but
catches a failure, only warns and writes no marker; the next launch then repeats it, and a failure there stops the
journeys with the missing packages named. Hosted runners start with no browser directory, so every run validates.
An installer or download error still exits non-zero. The journeys check DOM text, not rendering, and take
screenshots only on failure, so the missing CJK and Thai fonts should change no assertion; the hosted run must
confirm this. Rejected: falling
back to a browser-only install after `--with-deps` fails, which would give the job two possible setups and spend
many minutes on doomed lookups first. The README keeps `--with-deps` for Linux machines without the libraries.
Decision: [ci-i25](../DECISIONS.md#ci-browser-installation-dns-recovery-11-november-2026), which supersedes ci-i24
before merge.

Host-only checks are listed in the PR handoff. Fresh Codex review found no Major issue. It raised one Medium and
two Minor documentation findings: the passing run's library upgrade, root-cause exclusions stated too strongly, and
cached rather than per-launch validation. All three are corrected above. At that review, hosted verification was pending.

24 November 2026 verification: the Chromium job passed with the browser-only install on the PR #44 merge,
`4a48fbe` ([hosted run](https://github.com/ZadeNova/INF2003_Database_Project/actions/runs/43051609674)).
