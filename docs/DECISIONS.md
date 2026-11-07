# Decisions

Lasting decisions someone could later question, with the reason. Scope, tiers and dates are in [PLAN.md](../PLAN.md);
this file holds the choices behind the code. Add a row when a decision is made, not when it is rediscovered.

## Schedule (22 October 2026)

| ID | Decision | Why |
|---|---|---|
| schedule-gating | A phase starts as soon as the previous phase is closed (exit check passed, work merged to `main`); PLAN.md section 13 dates are targets and deadlines, not start gates. Decided by Chee Long | Phase 1A finished early; waiting for a calendar window would waste sprint time without adding safety. Dependency order, approved plans, reviews and exit checks stay binding |

## Phase 2 plan amendments (22 October 2026)

Approved by Chee Long before implementation, so unattended builds do not invent business rules. Details are in
[checkout](plans/checkout.md#decisions-all-approved-21-october-2026) (e–h) and
[catalogue](plans/catalogue.md#decisions-all-approved-21-october-2026) (e–h).

| ID | Decision | Why |
|---|---|---|
| phase2-c1 | New purchases charge freight per unit (`product.freight` × quantity) | Olist charges freight per item; `product.freight` matches the per-unit median for 90.3% of products, and the slightly high remainder is documented rather than regenerated |
| phase2-c2 | Estimated delivery = placed time + longest product lead time + 15 days | Calibrated to Olist's 23.3-day median estimate, given generated lead times with an 8-day median |
| phase2-c3 | The checkout review fingerprint includes unit price and freight as well as product and quantity | The old pattern deliberately excluded price; including it means a customer never pays an amount they did not review |
| phase2-c4 | Benchmark cases B1, B3 and B6 stay in `benchmark`, not in checkout or catalogue | benchmark.md runs them on separate bench databases; PLAN.md section 13 only aligns their timing |
| phase2-k1 | `lead_time_days` is a required seller product field | The column is not nullable; the catalogue field list omitted it |
| phase2-k2 | The design rewrite is an owner-steered step after the catalogue core; the 15 licensed photos (D11/D12) are deferred by catalogue amendment j | Design affects the presentation grade (foundation-a); photo licences must be verified individually |
| phase2-k3 | Category icons map many to one across all 74 categories | 26 icons exist; the import produced 74 categories, not the 73 the plan stated |
| catalogue-amendment-j (approved by Chee Long, 23 October 2026) | Defer the 15 featured stock photos (D11/D12 and f4-f8): revisit after Phase 3A only if time allows before the 30 October freeze, otherwise drop them. Every product shows an icon card unless its seller uploaded a photo; exit check 5 verifies icon fallbacks and seller photos served from GridFS | GridFS is already demonstrated by seller photo upload (exit check 2); the photos were the slowest, owner-blocked part of amendment f; the design rewrite affects the presentation grade |
| catalogue-amendment-f (design direction chosen by Chee Long, 23 October 2026) | Mercer evolves VoiceBox into its own system (same tokens, square 2px-bordered surfaces, accessibility, dark-mode and motion rules; blog-only parts removed), keeps the red accent and its placements, and lays products out 4 per row on desktop, 3 on tablet and 2 on phones | Keeps the contrast-checked, dark-mode and motion work already built, the lowest-risk path before the 30 October freeze; see [catalogue amendment f](plans/catalogue.md) |

## Benchmark outcomes, benchmark scope and featured photos (27 October 2026)

Approved by Chee Long before the benchmark build. Details are in [benchmark](plans/benchmark.md) (amendments f to j)
and [catalogue](plans/catalogue.md) (amendment k).

| ID | Decision | Why |
|---|---|---|
| benchmark-amendments-f-i | Each workload states its question, tested decision and expectation, committed before the final runs; fairness rules (idiomatic models, equal index effort, explicit equal durability, B3 with USER triggers off plus a separate run with the app's triggers, stated limits); a comparison matrix beyond speed; a fixed write-up with generated charts and tables | The rubric's top bands grade analysis, conclusions, implications and a rigorous SQL-to-NoSQL comparison (presentation part iii, required); the method alone produced numbers without conclusions |
| benchmark-amendment-j | Cut the HTTP load script; keep per-request database timing; defer the generator until the first correctness pass shows B1 or B4 differences inside the no-op baseline's noise | Neither part earns Tier 1 marks (performance analysis is optional); the benchmark starts after Phase 3A, so the saved time goes to graded work |
| catalogue-amendment-k | Drop the 15 featured stock photos (D11/D12, f4-f8); the demo seller uploads a few photos live | Amendment j's condition after Phase 3A: no time before the freeze; the photos show no database feature and each needs an owner licence check |

## ci stage 1 implementation (22 October 2026; reviewed, hosted runs passed)

The contract is [ci](plans/ci.md); these are the implementation choices behind stage 1.

| ID | Decision | Why |
|---|---|---|
| ci-i1 | Two jobs: `databases` (one Compose project for build, migrate, drift, fixture import, seed, suite and pipeline tests) and `host` (docs check, Git-index and packaging tests) | One database job builds the images once, which keeps runner-minutes inside the budget recommendation; the host checks need no Docker and finish quickly in parallel |
| ci-i2 | The project name is `mercer-ci-<run id>-<attempt>`, set both as `COMPOSE_PROJECT_NAME` and with `-p` on every call; teardown runs `if: always()` against that name only | Overrides compose.yaml's `name: mercer`, gives re-runs their own volumes and image tag, and cannot remove another project's data |
| ci-i3 | Actions pinned to verified commit SHAs of releases at least two weeks old: checkout v7.0.1 and setup-python v7.0.0, both node24; `persist-credentials: false` | A tag can move and a same-day release has had no time for problems to surface; the job never needs the checkout token |
| ci-i4 | Generated passwords and the secret key are passed to `::add-mask::` straight after `init_env.py`; other values stay readable | Defence in depth if a tool ever echoes a secret, without masking names such as `mercer` that the logs need |
| ci-i5 | The host job writes JUnit XML and fails if any test skipped | The Git-index tests skip silently without Git; CI must prove they ran (ci.md CI2) |
| ci-i6 | Pull-request runs of the same ref cancel older in-progress runs; pushes to `main` never cancel | Saves minutes on repeated pushes to a branch while every `main` revision keeps its own result |
| ci-i7 | The kernel guard compares major/minor/patch numerically and fails for 6.19.0 through 7.0.13 inclusive | Fails clearly before MongoDB starts (foundation-m) instead of timing out on a container health check |
| ci-i8 | The `databases` job runs on hosted `ubuntu-22.04`; `host` stays on `ubuntu-24.04` (ci decision b amended by Chee Long) | From image 20261021, ubuntu-24.04 runners use kernel 7.0.0-azure. MongoDB 9.0 refuses every Ubuntu 7.0 kernel because Ubuntu reports 7.0.0 even when the 7.0.14 fix is backported (SERVER-136848), and no MongoDB release fixes SERVER-121912. Ubuntu 22.04 kernels stop at 6.8, so real MongoDB checks stay on hosted runners without pinning an older MongoDB (foundation-f) |

## CI startup correction (23 October 2026)

| ID | Decision | Why |
|---|---|---|
| ci-i9 | Pass mongosh credentials with `--username=...` and `--password=...` in startup and healthcheck commands; retry new `token_urlsafe` secrets beginning with `-`, preserving token size and alphabet and all existing `.env` values | A dash-leading password was parsed as an option, intermittently preventing MongoDB from becoming healthy. Attached arguments also support existing credentials; regenerating a stored credential would not update the database user |

## CI stage 2 implementation choices (25 October 2026; reviewed by Claude Code)

| ID | Decision | Why |
|---|---|---|
| ci-i10 | Pin the additional tools in src/requirements-dev.txt, including the runtime file; keep existing pytest pins in runtime. Build migrate from a dev stage with its own image, and web explicitly from runtime | Coverage and quality/browser tools belong to the owner test runner and host CI, while runtime web keeps its limited role and dependency set. Release ages were checked through PyPI against the two-week cutoff |
| ci-i11 | Extract translation pins into a normal requirements file plus an Argos-only file installed with --no-deps; audit that actual minimal environment. Chee Long approved the sole setuptools upgrade to 84.1.0 on 25 October | The initial unchanged pin had fixable advisories, including [GHSA-h35f-9h28-mq5c](https://github.com/advisories/GHSA-h35f-9h28-mq5c) and [GHSA-xmj3-9gf7-h52w](https://github.com/advisories/GHSA-xmj3-9gf7-h52w). This approved security exception changes that component only; Argos and the unused Torch/Stanza dependency boundary stay unchanged |
| ci-i12 | Ruff E/F/I with line length 230; exclude migrations, data, cache and vendored static files | The longest existing Python line measured 229 characters. Import ordering, unused imports and required statement/name corrections satisfy lint; statement splitting preserves the AST. Stage 3 revisits formatting after freeze |
| ci-i13 | Run the full suite once with branch data; keep XML/HTML artifacts and derive a line-only CoverageData file for coverage report --fail-under=80 | Coverage's ordinary branch report combines line and branch totals. The public data API preserves the original report while enforcing the approved line-only denominator, including unexecuted namespace files |
| ci-i14 | One owned, expiring TOML exception file; audit unfiltered results before applying any --ignore-vuln flags | Expired, future-dated and overlong exceptions fail. A newly available fix invalidates an exception immediately; strict collection rejects unaudited packages. The committed file starts empty |
| ci-i15 | One serial Chromium job against runtime web; independent accounts/orders and a third checkout shop created through the real approval UI; failure-only artifacts retained seven days | The small fixture has only two established public shops. Browser processes receive demo logins only; traces and console output redact credentials. The manual forced-failure canary proves artifact creation without a permanently failing test |
| ci-i16 | Keep the database/browser jobs on ubuntu-22.04 and host/quality on ubuntu-24.04, all with explicit timeouts; use separate Compose project names and retain local timing evidence in the CI plan | MongoDB needs the existing kernel guard. Local measured durations inform the owner's runner-minute budget; hosted required-job and canary checks still await PR/main runs. No billing, protection or repository setting is changed |

Upload-artifact v7.0.2 was checked through GitHub's release and tag APIs: its release predates the cutoff and the
workflow pins its verified commit. The [workflow](../.github/workflows/ci.yml) is the home for action SHAs, job names,
runner versions, timeouts and artifact retention. The [CI plan](plans/ci.md#review-notes) holds the generated local results.

## CI Phase 4 integration fixes (29 October 2026; review pending)

| ID | Decision | Why |
|---|---|---|
| ci-i17 | Keep the standard-library smoke script's role, demo username and expected landing path together; check the URL path and Log out, and compare its expectations with landing_url after real seed_demo in a Django test. Run the script through migrate after runtime web is healthy in the browser job | Approved sellers and operators have distinct landing pages; a drift check and the documented HTTP command in CI protect fresh installs without importing Django into the smoke script or printing secrets |
| ci-i18 | Scan My products through its final Next link, then inspect labels only for active rows with stock at most five; report missing labels after the last page | Seeded demo stocks are zero and one, and journeys temporarily restock to five. Ordinary imported stock starts at twenty. This uses only the seller's visible UI, reaches the oldest products on full data, and avoids opening every detail page or depending on earlier journeys |

## CI stage 3 formatting (29 October 2026; owner choices, review pending)

| ID | Decision | Why |
|---|---|---|
| ci-i19 | Set Ruff's shared formatter/linter line length to 120, replacing stage 2's 230 | A conventional width keeps code readable on a laptop; the owner chose it for the post-freeze formatting pass |
| ci-i20 | Keep the formatting and line-length change in one commit, followed by a CI/docs/blame-ignore commit; compare every changed Python AST with docstrings removed and inspect docstring changes separately | Reviewers can isolate mechanical reflow from the gate, and the AST proof supplements real-database regression checks |
| ci-i21 | Ignore E501 centrally, with the formatter owning line length; wrap any remaining long code manually without behaviour changes or per-line noqa | Ruff leaves long string literals and URL comments intact; the generated stage 3 diagnostics and counts are recorded in the [CI plan](plans/ci.md) |
| ci-i22 | Run `python -m ruff format --check .` immediately after Ruff lint in the existing required `quality` job, preserving its display name | The existing required check includes formatting without a ruleset change; stage 3 closes after its green main run |
| ci-i23 | Record the full formatting commit hash in root `.git-blame-ignore-revs`, and document the per-clone `blame.ignoreRevsFile` setting beside hooksPath | GitHub and configured local blame skip mechanical reflow so authorship remains useful |

## Benchmark and CI planning documents (22 October 2026)

| ID | Decision | Why |
|---|---|---|
| benchmark-plan | Keep [benchmark](plans/benchmark.md) as the canonical B1–B6 contract; Chee Long owns/implements it | BM1–BM9 and placement/a–e decisions accepted 22 October; plan approved 22 October after fresh re-review, with no app privilege change or scaled Tier 1 runs |
| ci-plan | Keep [ci](plans/ci.md) as the sole CI contract; Chee Long owns/implements it | CI1–CI6 and a–f/full-data decisions accepted 22 October; plan approved 22 October after fresh re-review. The requested minutes-budget amount is a recommendation pending confirmation, not a billing change |

## accounts implementation (22 October 2026; review complete)

The approved contract is [accounts](plans/accounts.md); these are the implementation choices behind it.

| ID | Decision | Why |
|---|---|---|
| accounts-i1 | Two seller triggers: a BEFORE UPDATE transition check and an AFTER UPDATE audit insert, both `WHEN (OLD.status IS DISTINCT FROM NEW.status)`; only the audit function is SECURITY DEFINER | The audit row records the final committed change; the definer privilege is limited to the one function that writes a table runtime cannot |
| accounts-i2 | A CHECK on audit_log requires a non-blank reason whenever an actor is set | "Operator actions require a reason" holds in the database too, not only in the form |
| accounts-i3 | Snapshots name their fields (id, user_id, status, shop_name) instead of `to_jsonb(row)` | A column added later cannot leak into the log unreviewed |
| accounts-i4 | `TRIGGER_WRITTEN_TABLES` in config/privileges.py: `grant_runtime` revokes runtime writes on these tables after every broad grant | The default and broad grants would otherwise give runtime DML on audit_log; rerunning a grant helper must not restore it |
| accounts-i5 | Role and seller status are read from the database on each request; another role gets 403, an unapproved seller's GET on a seller page redirects to the status page | Operator decisions apply to sessions already logged in; sellers who are waiting or blocked are pointed at the one page they may use |
| accounts-i6 | `next` after login is honoured only as a same-site path (leading `/`, not `//` or `/\`) | Stricter than Django's host check: no absolute URLs, even to this host |
| accounts-i7 | In Phase 1B the seller centre and customer account are read-only pages | Product CRUD and orders belong to catalogue and checkout; the pages give the role checks real targets |
| accounts-i8 | `create_operator <username>` creates an operator or resets an existing operator's password; it refuses any other role | Idempotent for the demo set-up, with no path from a customer or seller to operator |
| accounts-i9 | The purchasable-view schema test uses one seller per status instead of moving one seller through every status | The new transition trigger forbids approved → pending or rejected; the test still checks the same visibility rule |
| accounts-i10 | Audit privilege tests connect as the runtime role to pytest's database (transactional tests) and also check the migrated application database read-only | Default and migration grants now apply in both databases (compare foundation-n); the application check fails, not skips, if it was not migrated |
| accounts-i11 | Account and operator pages use plain labels; stored action codes map once in `accounts/audit.py`. Audit shop links resolve the current seller. Imported placeholder names ("Olist seller 0015a82c") display everywhere, product pages included, as "Santo Andre Shop 0015A82C" with a "Generated name" tag; names applicants type are never rewritten. Status badges use one include: approved green, pending amber, rejected and suspended neutral | Operators read decisions without database terminology; the code keeps 695 São Paulo shops distinguishable where "Shop in City" would not; DESIGN.md keeps red out of statuses. Stored records, audit snapshots, schema and access are unchanged |

## Phase 1B planning document (22 October 2026)

| ID | Decision | Why |
|---|---|---|
| phase-1b-review | Keep [the Phase 1B decision/review record](plans/phase-1b.md), as requested by Chee Long | Chee Long accepted P1–P7 on 22 October 2026. Canonical contracts live in accounts/ci and the affected downstream plans; accounts, benchmark and ci were approved 22 October 2026; catalogue, checkout and reviews carry only the P3 amendment and stay approved |

## olist-import implementation (22 October 2026; independent review complete)

The approved scope decisions remain in [the workstream plan](plans/olist-import.md#decisions-all-approved-21-october-2026).

| ID | Decision | Why |
|---|---|---|
| olist-i1 | Store the ECB XML, retrieval day and actual reference publication date; use the latest reference available when execution starts | The Singapore execution precedes that day's European fixing. Reproducibility requires an honest, fixed source date rather than inventing or relabelling a rate |
| olist-i2 | Fixed content seed 82; per-product SHA-256 seeds include both source product and seller; template keys are sorted | Reordering or adding unrelated products does not change an existing product's generated content |
| olist-i3 | Use the pinned Argos package loader/tokenizer and CTranslate2 backend on whole newline-separated review paragraphs, in a separate offline image | Avoids optional sentence-segmentation/PyTorch dependencies in the application; batches distinct short review texts reproducibly. Model version, SHA-256, beam, numeric mode and thread count are recorded |
| olist-i4 | Customer profiles keep the latest retained source purchase address, then source customer ID; generated imported usernames never include fabricated personal names | Olist has one customer ID/address per order but a customer_unique_id may repeat |
| olist-i5 | Source rows contributing to grouping count as kept/transformed; output counts are separate | Source read = kept + removed remains meaningful when products/orders/reviews expand or rows aggregate |
| olist-i6 | Preserve cancelled-order reviews as history; anchor imported cancellation/refund times to purchase time with an explicit ledger note | Olist supplies no cancellation timestamp. A deterministic, labelled anchor is preferable to an invented event date |
| olist-i7 | Flush deferred FKs before restoring USER triggers; check all SQL invariants before committing MongoDB; compensate a final PostgreSQL commit failure | PostgreSQL forbids ALTER TABLE while deferred trigger events are pending. Cross-store loading is explicit and cannot claim a distributed atomic commit |
| olist-i8 | Composite refund (order, checkout) FK and role/profile guard triggers complement the approved ownership FKs | Prevents contradictory profile roles and a refund pointing at another checkout, without implementing later account/payment workflows |
| olist-i9 | Minimum product pages query the canonical visibility view through an unmanaged ORM ID model | Keeps one definition of visible products and avoids duplicating the conditions or introducing a raw-SQL web path |
| olist-i10 | Raw-versus-imported delivery analysis counts one review per original checkout | Per-line copies of an order review must not weight multi-line orders more heavily |
| olist-i11 | Include every available scarce broken fixture case and record shortages in its selection manifest | The real source has only one order with no payment; two examples cannot be selected without inventing data |
| olist-i12 | Port auth, CSRF, logging, privilege and outage checks; retain idempotency as a customer-scoped database constraint test while old checkout routes are closed | Preserves applicable security coverage without implementing a later workstream. Real refused connections replace database mocks |
| olist-i13 | Run Git-index documentation checks separately on the host | The minimal application image has no Git; these temporary-tree checks need no database or app credentials |
| olist-i14 | Seed the dashboard product from non-cancelled imported sales in the final imported 28-day window | Stock 1 with a 30-day lead time is guaranteed to flag only if demand is positive; selecting an arbitrary historical product would not ensure the later demo works |
| olist-i15 | Preserve the source profile's actual adjacent-bucket ordering, including its small longest-delay uptick | The exit check requires the same pattern within tolerance, not an invented strictly declining trend. The source profile and imported comparison retain the evidence |
| olist-i16 | Commit MongoDB import batches separately, retaining one PostgreSQL transaction and ID-scoped compensation | The first full-data run exceeded MongoDB's transaction lifetime. Bounded transactions respect its limits; the fixture's malformed-input/reference tests also verify cleanup after earlier batches commit |
| olist-i17 | Keep execution logs, timings, test summaries and review status outside the derived data tree; retain command-produced JSON as local review evidence | Execution evidence changes between runs and is not a deterministic dataset input or output. The independent review identified that the ad hoc report and its ignored generator did not belong in the data manifests |
| olist-i18 | Runtime may read Django migration history but may not modify it or use its identity sequence | Broad application-table grants must not allow web to fabricate or erase the owner's migration record |
| olist-i19 | Demo relisting labels use distinct retained imported orders, alongside current visibility and existing labels | Cleaning rule 15 gives the original visibility threshold. An earlier seeder may already have set active, so the current flag alone cannot repair a missing relisting label; later application orders must not change this historical decision |

## foundation (21 October 2026)

| ID | Decision | Why |
|---|---|---|
| foundation-a | `DESIGN.md`: strip dead links and AWS text only; the full rewrite moves to `catalogue` | The UI work decides the design |
| foundation-b | Remove the K-means scripts now; the `CustomerSegment` model goes with the `reporting` app in `olist-import` | Avoids a throwaway migration |
| foundation-c | MongoDB container, users and health check land in `foundation`, not `catalogue` | `olist-import` needs it running |
| foundation-d | Images are pinned by digest | Reproducible benchmarks |
| foundation-e | `scripts/check_docs.py` uses only the standard library and runs on the host | Works in the git hook without a virtual environment |
| foundation-f | Latest stable PostgreSQL (18) and MongoDB (9.0), checked at pin time | The brief asks for the latest systems |
| foundation-g | Two PostgreSQL roles: an owner (migrate, import, pytest) and a runtime role for `web` (rows only) | Makes AGENTS.md rule 5 true; before, the app role owned its database |
| foundation-h | Delete the old load harness; `benchmark` writes a new local load script | The old harness was built around the AWS variants and shoe sizes |
| foundation-i | `.env` and `.env.example` live at the repository root, next to the one `compose.yaml` | Compose reads `.env` from the project directory; the old location relied on `include` |
| foundation-j | pytest runs in the `migrate` service (`docker compose run --rm migrate pytest ...`), not `web` | Only the owner role may create the test database, and `web` must never hold it |
| foundation-k | The MongoDB replica set is initialised by `src/docker/mongo-start.sh` beside `mongod`, with the keyfile generated into a named volume | A bind-mounted keyfile cannot be chmod 400 on Windows; the replica set and users must be created while `mongod` already runs with the keyfile |
| foundation-l | The startup event no longer carries an `environment` field | `DJANGO_ENV` is gone, so there is only one environment |
| foundation-m | Keep MongoDB 9.0; the team develops and benchmarks on Windows with Docker Desktop, whose VM kernel is not affected by SERVER-121912 | Docker Engine on Linux shares the host kernel, and MongoDB 9.0 refuses kernels 6.19 to 7.0.13; Linux users need an older or newer kernel (README, Troubleshooting) |
| foundation-n | The role tests run against the real `mercer` database, with uniquely named probe tables that they drop | The default privileges that make the runtime role work exist only there, not in pytest's test database |
| foundation-o | Plan files are kept after close-out with `status: done`, not deleted; `check_docs.py` now checks that every plan has a valid status line | The team wants the plans as a reference; each holds the contract, decisions and review notes behind its workstream |
| foundation-p | `docs/OVERVIEW.md`: a plain-language team guide that summarises PLAN.md and links to it rather than copying details | Teammates need one readable page on scope and features; linking keeps PLAN.md the single home of each fact |
| foundation-q | No separate human gate: the implementer asks a teammate to review in a fresh Claude Code session | One main developer; the fresh-session review already runs the tests and exit checks |


## catalogue implementation (23 October 2026; reviewed and merged, PR #10)

| ID | Decision | Why |
|---|---|---|
| catalogue-i1 (confirmed by Chee Long, 23 October 2026; catalogue amendment i) | Use an attributes.$** wildcard index for the scalar attribute dictionaries already imported; it supports multikey array values without changing documents | A fixed attribute index cannot cover live schema evolution; explain evidence must distinguish scalar isMultiKey false from actual arrays |
| catalogue-i2 (confirmed by Chee Long, 23 October 2026) | Newest means descending product ID | The approved schema has no creation timestamp; additive indexing and audit need no product-field/import-format change |
| catalogue-i3 (confirmed by Chee Long, 23 October 2026) | Resolve category icons at render time with a complete slug map, including a package icon only for Uncategorised | Preserves the checked source CSVs and their reproducible import; no stored/generated-data rewrite is needed |
| catalogue-i4 (confirmed by Chee Long, 23 October 2026) | Product detail keeps the context name product; checkout adds orders/_add_to_cart.html there after integration, posting to orders:cart_add at /cart/add/<product id>/ | Both branches remain runnable independently; the shared integration review must preserve that include placement |
| catalogue-i5 (confirmed by Chee Long, 23 October 2026) | Template attributes use the imported scalar types `string` (shown to sellers as "Text"), `integer` and `boolean`, and are optional unless the template explicitly requires them | Existing products need no rewrite when a new option is added; sellers validate filled values against that category's allowed values |
| catalogue-i6 (confirmed by Chee Long, 23 October 2026) | check_specs reports missing specs, orphan specs and category mismatches; --repair explicitly removes orphan specs and their photos | A successful MongoDB write followed by an uncertain PostgreSQL commit stays visible; missing text/attributes cannot safely be invented |
| catalogue-i7 (confirmed by Chee Long, 23 October 2026) | Keep separate catalogue product-to-shop and checkout order-to-shop additions in OperatorAuditView when integrating | Product and order audit rows share the existing paginated page; each must resolve only the current page's own entity IDs |
| catalogue-i8 (confirmed by Chee Long, 23 October 2026) | Re-encode seller photos into a new JPEG or PNG after format/size/pixel checks, and delete replaced files after the committed save | Image metadata/trailing content do not enter GridFS; a failed save keeps the previous photo; a logged cleanup failure leaves a harmless orphan file |
| catalogue-i9 (confirmed by Chee Long, 23 October 2026) | seed_demo calls set_audit_context() before its existing transaction's reads/writes; COPY imports keep their disabled-trigger loading boundary | System changes must never inherit a caller's actor; checkout and catalogue share this actor/reason convention |
| catalogue-i10 (confirmed by Chee Long, 23 October 2026) | The shared audit page uses a generic changes lead and wraps long decision badges only inside its audit table | Product and order actions share narrow cells; the adjustment preserves global badge styling and both audit lookup additions |

Pillow 13.0.0 is pinned for the upload path after checking the [maintainer release listing](https://pypi.org/project/pillow/13.0.0/).

## checkout implementation (23 October 2026; reviewed and merged, PR #9)

| ID | Decision | Why |
|---|---|---|
| checkout-i1 (confirmed by Chee Long, 23 October 2026) | Lock the cart parent for all edits and checkout, followed by cart lines and products in ID order | Serializes first inserts, removals and duplicate submits without a cart phantom; products retain the contract's consistent lock order |
| checkout-i2 (confirmed by Chee Long, 23 October 2026) | Keep imported CSV headers fixed and allow omission only of the database-defaulted checkout fingerprint | The reproducible clean dataset predates application review metadata; unknown and other missing columns remain rejected |
| checkout-i3 (confirmed by Chee Long, 23 October 2026) | Deferred checks lock old and new parent checkouts before summing | Moving a payment cannot leave either checkout unbalanced; concurrent writers serialize at the parent |
| checkout-i4 (confirmed by Chee Long, 23 October 2026) | Keep the requested untracked local PROGRESS-checkout.md ignored by its exact filename | Local handoff state is execution evidence, like .cache; it is excluded from source packaging and documentation checks |
| checkout-i5 (confirmed by Chee Long, 23 October 2026) | Product detail includes orders/_add_to_cart.html; its customer-only form posts orders:cart_add at /cart/add/<product id>/ | Small shared boundary with catalogue; server validates role, canonical visibility and stock |
| checkout-i6 (confirmed by Chee Long, 23 October 2026) | Payment UI asks for method and instalments only; it never collects card details | Simulated payments need no sensitive input; multi-method payments remain available to the tested service |
| checkout-i7 (confirmed by Chee Long, 23 October 2026) | Audit pages resolve each page's order IDs to their current seller in a separate lookup block | Order decisions display readable shop names; integration retains the existing seller lookup and catalogue's product lookup |
| checkout-i8 (confirmed by Chee Long, 23 October 2026) | Imported-refund provenance is checked only during import; ongoing reconciliation checks amount, status and ownership for every refund | A customer may cancel imported paid history later; that new refund is correctly non-imported, while malformed source labels must still reject the import |
| checkout-i9 (confirmed by Chee Long, 23 October 2026) | Seller and operator order pages offer validated status and exact order-number filters, preserving the role's original queryset | The shifted Olist history includes dates after the current date; these filters make a newly placed order findable without paging through that history |
| checkout-i10 (approved by Chee Long, 29 October 2026) | Supersede checkout-i1's product-lock description with cart → cart lines → sellers in id order → products in id order; lifecycle actions keep checkout → order → products. Recheck product ownership after locking | The independent review reproduced checkout/product-edit deadlocks from opposite seller/product lock orders. Catalogue already takes seller first; real-connection deactivation, multi-product and suspension races verify the shared order. The complete path inventory is in [DATA_MODEL](DATA_MODEL.md#view-triggers-and-privileges) |
| checkout-i11 (approved by Chee Long, 29 October 2026) | Revoke runtime DELETE on checkout, order, order-line, payment and refund tables in orders 0003 and reapply it after broad runtime grants; leave owner privileges unchanged | The app never deletes money history. Narrowing direct SQL prevents shipped-order delete/reinsert and paid-checkout erasure without adding an insert-status trigger |
| checkout-i12 (approved by Chee Long, 29 October 2026) | Document per-order refund matching and line/order totals as service rules checked by verify_olist, without new triggers | Freeze-time scope: the application cannot reach either mismatch, and checkout-i11 narrows direct-SQL access. Existing deferred triggers enforce checkout sums; direct SQL can still violate these finer rules. Further trigger work is outside this approved fix round |

## reviews implementation (24 October 2026; review pending)

| ID | Decision | Why |
|---|---|---|
| reviews-i1 | Use PyMongo with_transaction with snapshot reads and majority commits; retry the entire MongoDB callback on write conflicts | Concurrent reviews serialize at the product summary without losing either review |
| reviews-i2 | Preserve the import's 28 significant digit Decimal arithmetic in the MongoDB update pipeline, including intermediate Bayesian operations | Insert/delete round trips return imported averages and scores exactly; counts, sums and histograms remain integer totals |
| reviews-i3 | New seller products use the same import-fixed Bayesian prior helper as review writes; zero reviews start at m | The prior count C is not a rating and must never seed the score |
| reviews-i4 | Moderation opens PostgreSQL with its audit row, commits MongoDB, then commits PostgreSQL; log an uncertain final SQL commit | Follows the approved cross-store order without pretending the two databases share an atomic commit |
| reviews-i5 | Keep moderation fields optional on existing review documents and preserve the strict imported outer validator | Missing taken_down means visible; no data reset or validator rewrite is needed |

## wishlist implementation (24 October 2026; review pending)

| ID | Decision | Why |
|---|---|---|
| wishlist-i1 | Use Django's composite primary key for wishlist_item(customer_id, product_id) and a PostgreSQL partial unique index for unseen restock_alert rows | The database enforces both many-to-many identity and duplicate unseen suppression |
| wishlist-i2 | Add an AFTER UPDATE OF stock trigger alongside product_update_audit, firing only on zero to positive | Seller edits, raw SQL and cancellation restocks share the same database path; both triggers retain their work |
| wishlist-i3 | Hide non-purchasable products in wishlist/alerts; mark only the displayed page's visible alerts seen on GET, leaving HEAD unchanged | A customer keeps unseen alerts they have not actually opened; hidden products do not leak through the badge |
| wishlist-i4 | Cache saved product IDs only for the current rendered request | Product cards share one ownership query without introducing a cache service or a second source of truth |

## dashboard amendment a (24 October 2026; confirmed by Chee Long)

Derive the reporting date from the latest imported order placed_at (checkouts with an Olist source ID), through the central dashboard_as_of() SQL function. Demo orders never move this anchor. Every panel excludes events after that local date. Shifted deliveries after the last placed_at remain valid source history and are left unchanged. This supersedes the fixed date in the original dashboard decision a; fixture checks use their own imported date.

## benchmark implementation (27 October 2026; review pending)

Implementation choices supplied and authorised by Chee Long for [benchmark](plans/benchmark.md); the plan's
precommitted expectations remain unchanged.

| ID | Decision | Why |
|---|---|---|
| benchmark-i1 | Keep harness, workloads, standard-library reference, golden outputs, tests, results and host runner in benchmarks; no Markdown beneath it | One reproducible package with evidence formats accepted by the documentation contract |
| benchmark-i2 | Dedicated bench profile, matching pinned images, separate BENCH credentials/volumes, no ports/socket, two CPU/two GiB limits with no extra swap on engines and runner; checkpoint grant only to bench owner | Isolation, equal resources and explicit durability without changing app grants. Existing environments must rerun init_env because required interpolation precedes profile filtering |
| benchmark-i3 | Run unchanged app migrations/importer first, add typed EAV/JSONB and bench reviews, then idiomatic MongoDB products/orders; persist both manifests, vacuum/checkpoint, create a template and checksum NDJSON restore files | The same verified data and real app constraints underpin every workload |
| benchmark-i4 | Pure-Python oracle over clean files; commit fixture/full CSVs and byte checksums, explicit ID ordering, Singapore days, decimal scales and ROUND_HALF_EVEN; preserve LF/exact bytes with Git attributes | Independent correctness and cross-platform reproducibility; neither engine supplies the oracle |
| benchmark-i5 | Seeded selective/broad one-to-three scalar predicates including string, boolean and integer range; typed EAV EXISTS, JSONB GIN/range expressions and MongoDB wildcard; reject operators supplied as values | Comparable flexible-attribute models, with parameterised SQL and scalar-only MongoDB inputs |
| benchmark-i6 | Import the four app SQL texts; shadow sales with a live CTE, prove equality with the view, and separate view/refresh outputs; equivalent rank/shift/calendar-window and lookup pipelines | Live work is compared with live work; B2d excludes copied order reviews and averages per-order scores before buckets |
| benchmark-i7 | Fifty buyers at each concurrency, conditional decrement and balanced order/payment writes; PostgreSQL USER triggers off headline and on separately; MongoDB snapshot transactions, majority journaled writes and counted retries | Equivalent minimal operations, real keys/checks and an explicit trigger-cost comparison |
| benchmark-i8 | Deterministic barrier demonstrations for lost updates and protected alternatives, outside the timing matrix; put FOR UPDATE's barrier before the locking read | Both workers can reach the barrier without a lock/barrier deadlock; serialization/write-conflict retries must occur |
| benchmark-i9 | Save each B4 before/after plan, restore the complete index catalogue in finally, and record B5 physical data/index bytes beside cache sizes | Reversible index evidence and model/storage costs. The full-data unindexed all-product rating lookup was cancelled and retained as failed; the compound-index example uses fixed product 1 with an independently generated B2c_index golden. B2c still checks all entities |
| benchmark-i10 | Correctness mode accepts no timings; measure mode retains a warm-up and five fixed-operation runs, raw operations and median/range summaries; host records hardware/settings/digests/limits and streams Docker samples. Preserve semantic MongoDB compound-key order in plans and an explicit key sequence in index evidence | Failed results remain visible with null accepted timing; exact measured operation boundaries and throughput overhead are recorded |
| benchmark-i11 | Request-local ContextVar counters, Django execute_wrapper and one PyMongo listener per created client; JSON fields and Server-Timing only | Per-request database share without query text, values, command bodies or telemetry infrastructure |
| benchmark-i12 | Full and fixture correctness passes followed by a labelled baseline/B1/B4 trial; generate the prescribed per-parameter/index noise comparison; no generator | The owner evaluates amendment j using evidence before any scope promotion |
| benchmark-i13 | Standard-library report generator emits CSV tables and standalone SVG charts, ratios with absolute metrics and visible failures | Every figure comes from retained results; no plotting dependency or hand-typed benchmark table |
| benchmark-i14 | Real-database fixture tests for reference determinism, manifest refusal, CTE/view equality, injection, races/anomalies, restoration and BM4; optional fixture correctness CI job with duration artifact | Reproducible gates without changing required checks; hosted results and duration belong to the PR checks, and the review's actual session history is recorded in the plan |
| benchmark-i15 (fix round, 28 October) | Drop/recreate restored MongoDB collections from checksummed documents, validators and ordered index metadata; insert before bulk-building secondary indexes and verify both digest and catalogue. B5 runs before mutations and requires restores_since_load=0. Physical probes wait 65 seconds after a load/restore, covering the bench server's explicit 60-second checkpoint period. Test two cycles against fresh sizes with 10% tolerance and a 64 KiB allocation floor | Delete/reinsert retained WiredTiger free space; a checkpoint is also needed before comparing allocated file sizes. No additional MongoDB privilege is granted. PostgreSQL resets disallow new connections and wait for existing/background users instead of force-terminating another role |
| benchmark-i16 (fix round, 28 October) | Prime every connection, synchronise readiness, validate one untimed first result per worker, then release a shared timing barrier. Default five operations per client at 1/10/50 clients; B3 retains fifty total buyers. Compare later fetched rows directly; MongoDB analytical pipelines end with deterministic sorts | Connection setup and full canonicalisation must not overlap another client's measured operations; measured counts, boundaries and validation overhead are explicit in provenance |
| benchmark-i17 (fix round, 28 October) | Keep the Python no-op as overhead only; use SELECT 1 and MongoDB ping round-trip baselines for amendment j, taking the larger baseline noise across the engines compared. Attribute one-second Docker CPU intervals to each run; at median runner CPU >=180%, flag client_saturated and remove the headline ratio while retaining measurements | The earlier no-op did not measure database round-trip noise. CPU attribution is coarse for sub-second runs and must remain visible rather than masking load-client limits |
| benchmark-i18 (fix round, 28 October) | Keep B1 broad's planner-chosen MongoDB path as headline and add documents_hinted using spec_attributes and the same golden as a separate equal-index-effort comparison | The existing broad plan used _id_ and examined the retained product set; forcing the index in the headline would hide the planner's actual choice |
| benchmark-i19 (fix round, 28 October) | Record replacement fixture/full/BM4/trial evidence on a clean committed fix head in fresh projects. Ignore new run output until explicitly force-staged; remove retained -dirty directories and the old validation coverage.json, leaving history intact. Keep the cited first pass and mark its B5 storage and old timings superseded | Review evidence must identify the code that ran; the 28 October first-pass date remains historically correct |
| benchmark-i20 (fix round, 28 October) | Add the existing MongoDB kernel guard to the optional job, reload after mutating fixture tests, capture the current runner's printed directory and upload only that directory plus this job's duration | B5 needs a fresh load, and artifact upload must not collect unrelated committed runs; required checks and CI stage 3 stay unchanged |
| benchmark-i21 (owner decision, 28 October 2026) | No generator and no 10x run (Chee Long, 28 October 2026). Report B4_bench_product_visible, the MongoDB partial index on B2b, as an index that buys almost nothing; use its before/after and run-range figures from the [fix-round amendment-j.csv](../benchmarks/results/2026-10-28T230836_d6fc7e44_fix-trial/report/amendment-j.csv) | The B2b partial index selects about 40% of products inside a pipeline dominated by the per-product $lookup, so more data would not change the finding. The generator decision belongs to the owner; designated-machine final measurements remain |

## Benchmark final-run preparation (31 October 2026)

| ID | Decision | Why |
|---|---|---|
| benchmark-i22 | Amendment k1/k3 (approved by Chee Long, 30 October 2026) supersedes benchmark-i16's counts for final measurements: default 100 operations per client at 1/10/50, falling back to 50 if the baseline/B1/B2 pilot projects beyond one sitting; B2 uses 1/10 clients with 20 operations per client, falling back to 10. B2refresh uses the B2 count at one client. B3 retains fifty buyers. B4 uses one client; its B2-derived cases use the B2 count and its other cases use the default count, recorded per case in workload_matrix. Keep the legacy provenance keys; correctness query passes stay at one client/one operation | Longer windows improve p95 and CPU attribution, while B2 is operator analytics and the fifty-client full-data pipelines risk timeout and excessive duration. Its B4 index experiments are outside the pilot and also need the smaller count. The pilot, final flags and report disclose the chosen limit |

## Benchmark designated-machine final and close-out (2 November 2026)

Chee Long approved these final-run and close-out decisions. The underlying measurements identify clean commit
`b53e5d0`; report regeneration is recorded separately and does not rewrite measurement provenance.

| ID | Decision | Why and evidence |
|---|---|---|
| benchmark-i23 | Trim only the pilot's B2 count to five operations per client, retaining the default one hundred; select the full final counts of one hundred/default and twenty/B2 from the pilot projection | The owner needed a timely pilot covering both slow parts. [Pilot provenance](../benchmarks/results/2026-11-01T220402_b53e5d0a_pilot/provenance.json) records the actual matrix and counts; the [generated decision arithmetic](../benchmarks/results/2026-11-01T220402_b53e5d0a_pilot/count-decision.json) includes all warm-up/measured windows and the owner's remaining-work allowances. Pilot timings are not final headline results |
| benchmark-i24 | Use B3 and B6 entirely from the separately reloaded `final-b3-b6` run; use every other final comparison output from `final`. Keep all failed cells in the original run visible | After the unexpected OOM, the owner used the single infrastructure retry for only the affected workloads at the same commit, machine and limits. [Original failed summary](../benchmarks/results/2026-11-02T004351_b53e5d0a_final/summary.csv), [fresh B3/B6 checks](../benchmarks/results/2026-11-02T095518_b53e5d0a_final-b3-b6/report/checks.csv), and both provenances retain the full history; do not combine the original partial B3 sample into the final B3 result |
| benchmark-i25 | Record the unexpected out-of-memory kill as a resource observation using already-collected samples; retain identical limits for the scoped retry | Cite the generated [original memory table](../benchmarks/results/2026-11-02T004351_b53e5d0a_final/report/memory.csv), [fresh-run memory table](../benchmarks/results/2026-11-02T095518_b53e5d0a_final-b3-b6/report/memory.csv), [recorded settings/input footprint](../benchmarks/results/2026-11-02T004351_b53e5d0a_final/report/memory-settings.csv) and [Docker failure capture](../benchmarks/results/2026-11-02T004351_b53e5d0a_final/failure-docker-state.txt), rather than typing measured memory figures into prose |

The kill was **unexpected**. Nothing in the benchmark was designed to test memory. The 2 GB per-engine caps were
chosen beforehand for fairness: identical caps for both engines; the clean Olist data, about 150 MB, fits comfortably;
PostgreSQL `shared_buffers` 512 MB and WiredTiger cache 0.75 GB follow each engine's guidance; and the three limited
containers fit the designated machine. The generated settings/input-footprint table above supplies the recorded
configuration and checksum-verified dataset size; Docker reports the enforced cap in binary units.

> We observed an unexpected out-of-memory kill, investigated it with the resource data the runner already collects, found it consistent with our B2 analysis, and reran the affected tests under identical limits.

Under those identical caps, PostgreSQL's sampled peak stayed well below its limit. MongoDB memory rose during B2
analytics, stayed high afterwards and approached its cap during the final fifty-client B3 round before Docker
reported an OOM kill. B3 had passed on the freshly loaded [correctness database](../benchmarks/results/2026-11-02T002948_b53e5d0a_final-correctness/report/B3-states.csv).
Use `scope=run` rows for whole-run peaks, including preparation/restoration, and `scope=workload` rows for samples
inside the CSV timing windows. The failed B3 row has no timing range: its association with the final round does not
identify a particular operation or restoration step as the cause. B5 and B6 rows without windows have blank memory
figures; no neighbouring samples or values at the cap are invented.

This is an observation, not a controlled memory test. The caches are configured differently, and Docker attributes
memory to each engine somewhat differently. It does not establish that MongoDB needs twice the memory or that the
same operation used more memory. The fresh run has a different workload history; its observed success supports
reporting the affected tests after a fresh load, without claiming a controlled causal explanation.

The failed run's raw payload was compressed after verifying its original hash and then verifying the decompressed
hash; its [manifest](../benchmarks/results/2026-11-02T004351_b53e5d0a_final/raw-compression.json) records why the
runner had not reached its own compression step. Annotation skips stopped-container CPU placeholders, and
`benchmarks.report` now generates memory tables for each driver report. Neither change alters the original
provenance or removes failed checks. BM4's fresh full-data controls remain deliberately failed with no accepted
timing; [their verification record](../benchmarks/results/2026-11-02T110623_b53e5d0a_final-bm4/bm4-verification.json)
is evidence that the gate rejects incorrect data.

## dashboard implementation (24 October 2026; review pending)

| ID | Decision | Why |
|---|---|---|
| dashboard-i1 | Fill all 28 calendar days, use AVG/SUM windows, compare stock × 28 with lead days × units | Zero-sale days count and replenishment stays exact at the lead-time boundary |
| dashboard-i2 | Revenue is item value without freight; cancellations are evaluated as of the reporting date | Stock demand and category performance share one historical definition, including later cancellation events |
| dashboard-i3 | First materialization is a normal refresh, subsequent refreshes are concurrent, serialized by an advisory lock | PostgreSQL cannot refresh an unpopulated view concurrently; the runtime role still receives only the narrow function privilege |
| dashboard-i4 (review amendment, 24 October 2026) | List and flag sellers only with at least ten delivered orders by the as-of date; above 20% late is at risk. Order at-risk sellers first, then late share descending and seller ID; show the excluded count. Mean score uses reviewed orders only | A handful of deliveries gives an unstable risk signal and obscures sellers with substantial history; unreviewed deliveries still count in the lateness denominator |
| dashboard-i5 | A calendar-month gap yields no month-on-month percentage, and the chart shows the latest month's leading categories | Comparing with an older observed month would mislabel the change; the full category history stays in the table |
| dashboard-i6 | Keep analytical SQL importable; the Bayesian counterpart expects the benchmark's future SQL reviews relation and is tested with a statement-local CTE | No review scores are persisted in PostgreSQL by the application; no benchmark implementation is started |
| dashboard-i7 | Vendor Chart.js 4.5.1 with its source map and MIT licence | The chart works without a runtime CDN and Django's static manifest resolves the upstream source-map reference |
| dashboard-i8 (team review decision, 24 October 2026) | Accept a few seconds on the full data for Tier 1 and preload the dashboard before filming; leave caching to the Tier 2 redis workstream | The Python cross-store delay join preserves decision c's single-store ownership. Its measured cost is report material, not authorization to start Tier 2 work |

## activity implementation (24 October 2026; review pending)

| ID | Decision | Why |
|---|---|---|
| activity-i1 | Create events separately from the import's four file-backed collections, with ts/meta time-series options, seconds granularity and a 30-day TTL | No events file is invented for Olist; mongo_setup owns all collection/index setup and refuses incompatible existing options |
| activity-i2 | Use acknowledged w:1 writes; catch/log MongoDB failures and refuse missing/non-time-series collection writes | Telemetry must not break shopping, and an early request must not silently create ordinary events storage |
| activity-i3 (review amendment, 24 October 2026) | Anonymous events store a salted_hmac hexadecimal digest of the Django session key in meta.session_key, using the fixed salt mercer.activity.visitor; authenticated events contain only user_id | A raw session key can act as a login cookie. The keyed hash keeps histories distinct without storing that credential; the existing index and synthetic seeder label remain unchanged |
| activity-i4 | Resolve ranked/recent IDs through purchasable_product in batches of fifty and continue past withdrawn items | Reads stay explicit and bounded without letting unavailable products consume all visible slots |
| activity-i5 | Apply the deterministic product-ID sort after the computed rank, sorting by rank rather than extending the views sort | Keeps tied view counts at the same rank; the regression check caught changed ties when the final sort extended the window ordering |
| activity-i6 | Insights compares non-cancelled units with views over the same rolling 30 days and labels the ratio as units per view | Aggregate totals are not individual purchase attribution and may exceed one unit per view |
| activity-i7 | seed_activity appends relative-time synthetic views, weighted by imported non-cancelled unit sales, using a synthetic session key | Real browsing data does not exist in Olist; is_generated and the UI label preserve provenance without inventing user histories |
| activity-i8 (integration fix) | Disable Chart.js automatic colours and set the theme palette before chart construction | The responsive browser check found blue defaults overriding the intended ink palette; both themes now use the design tokens |
| activity-i9 (integration fix) | Return a committed wishlistChanged event and update all matching visible buttons before the HTMX swap | A product can occur in detail and recently viewed simultaneously; both controls must keep the same action and pressed state |
| activity-i10 (team review decision, 24 October 2026) | Keep Insights on the real rolling window; on recording day, run seed_activity and place a few demo purchases before filming the seller's page | Imported sales become near-empty after the imported data ends. Browsing events expire, so anchoring the window to imported history cannot preserve comparable views and sales |

## Reuse disclosure (31 October 2026)

| ID | Decision | Why |
|---|---|---|
| deliverables-no-written-reuse-approval | Chee Long decided on 31 October 2026 that written approval from the professors is not required for building on the earlier module project. Keep the reuse disclosure in docs/AI_USE.md and report appendix D; this supersedes the written-approval requirement carried over from Phase 0 | Mercer is a substantially different project after most of the earlier project was changed |

## Improvements batch 2 (8 November 2026)

| ID | Decision | Why |
|---|---|---|
| demo-fixed-passwords | Erfan decided that the three demo passwords are fixed and documented in the README and `.env.example` (`mercer-demo-customer`, `mercer-demo-seller`, `mercer-demo-operator`), instead of random per-machine secrets. The variables are still required, with no code fallback; database and Django secrets stay random in the ignored `.env`. Reverses the earlier "generated demo secrets" design | The application runs only on a marker's or teammate's own machine and is never deployed; anyone must be able to log in without reading `.env` |
| product-stock-cap | A seller can list at most 99,999 units of a product, and the database ceiling is 1,000,000 (`product_stock_capped`). The gap leaves room for cancellation restocks, which add at most 999 units per cart line | A form maximum of 2,147,483,647 let a cancellation overflow the integer column and fail with no refund. Marketplace listings use small per-listing caps (Etsy is reported at 999) |
| product-create-audit | Creating a product writes a `product.create` audit row (AFTER INSERT trigger) with the first price and stock | The plan claims every price and stock change is audited; the UPDATE-only trigger missed the first values. Audit growth is small: rows appear only on sensitive events, about 0.6 KB each |
| bigint-ids | Every id in a route uses one `bigint` path converter and one `BIGINT_MAX` constant (`src/config/ids.py`) | Ids above the 8-byte limit reached MongoDB and caused a 500; the bound was copied by hand in six places |

## Improvements batch 3 (8 November 2026)

| ID | Decision | Why |
|---|---|---|
| seller-edit-merge | Saving a product edit is a field-level compare-and-set under the row lock. The form carries the stock and price it was opened with; a field the seller left alone keeps its live value, and a field the seller changed is applied only if nobody else changed it meanwhile, otherwise the save is refused and the live value shown | Sales change stock while a form is open; overwriting it with an old number undid sales (the lost update benchmark B6 measures). Refusing every save after any sale would have made busy shops retry constantly |
| order-timestamp-guard | A BEFORE UPDATE trigger refuses any change to an order's `placed_at`, `estimated_delivery` and the four status timestamps unless the status changes, and then only the destination timestamp, which the status trigger stamps with `now()` | The delay analysis is computed from these columns; the web role could rewrite them without an audit row |
| delay-analysis-copies | The delivery-delay analysis includes copied order reviews, and MongoDB returns the integer sum and count of scores per order | Copies in an order share its score, so they did not bias the mean, but excluding them dropped every multi-line order; the integer form is exact and cheaper than converting every review to Decimal128 |
| stock-planning-fast | The dashboard uses a grouped 28-day sum (`STOCK_PLANNING_FAST`); the window-function query stays as `STOCK_PLANNING` for benchmark B2 | Same rows, far faster; B2 and its golden output keep their definition until the Batch 6 amendment |
