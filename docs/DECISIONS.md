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
