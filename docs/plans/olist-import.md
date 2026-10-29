# olist-import: Olist cleaning, schema, import, adaptations, accounts

status: done
plan owner: Erfan · implementer: Chee Long · reviewer: a fresh session, ideally the other agent · estimate: 4 to 5 days
· Phase 1A (22 to 24 October 2026, accelerated schedule in PLAN.md section 13) · depends on: `foundation`
The 4-to-5-day estimate remains an effort risk estimate, not a guarantee for this window.

## Contract

**Goal.** One command loads the cleaned, adapted Olist data into PostgreSQL and MongoDB on an empty database in under ten
minutes on a typical laptop, reproducibly, with a cleaning ledger that accounts for every removed or changed row.

**Pipeline: three steps, each with committed output**

| Step | Script and where it runs | Output (committed, with `checksums.txt`) |
|---|---|---|
| Translate (one-off, start early: 1 to 3 hours) | `scripts/translate_reviews.py`: Argos Translate, pinned package and pt→en model version, in its own environment (never the app image; recent versions pull in PyTorch). Translates distinct texts only (about 36k comments and 11.5k titles); resumable, so a stopped run continues | `data/derived/olist/translations.csv` (text hash, English text) |
| Clean | `scripts/clean_olist.py` with pinned pandas, in a pinned `tools` container (Compose profile `tools`) so output is identical on every machine. Reads every CSV with `dtype=str` (23,995 customer zip codes start with 0), keeps money as `Decimal`, sorts deterministically, assigns new ids by sorted source keys, writes with `lineterminator="\n"`. Reads `translations.csv`; never translates | `data/derived/olist/clean/` (CSV for PostgreSQL, NDJSON for MongoDB) and `cleaning_ledger.json` |
| Generate | `scripts/generate_content.py`, same container, fixed seed: reads the clean products and the hand-written templates in `data/derived/olist/templates/categories.json` (rich for the top 15 categories, generic for the rest: attribute definitions and word lists), writes names, descriptions, attributes, stock and lead times into the clean files and the `category_templates` documents | Same folder, checksummed |
| Import | `manage.py import_olist`, run as the **owner** role in the `migrate` service: runs `mongo_setup`; disables user triggers on the tables it loads (`ALTER TABLE … DISABLE TRIGGER USER`), `COPY`s the clean CSVs with their ids in foreign-key order, re-enables the triggers, `setval`s every identity sequence; then runs the money and ownership invariants as plain queries (payments equal checkout totals, refunds equal cancelled totals, one seller per order) and fails if any returns rows (decision o); bulk-inserts the NDJSON into MongoDB. Later workstreams append final steps (`dashboard` refreshes its view). No cleaning logic; refuses a non-empty database; prints progress per step | The loaded databases |

`analytics/profile_olist.py` reproduces the 21 October profile, including the review score by delivery-delay bucket, and
writes the generated dataset section of `docs/DATA_MODEL.md`.

**Cleaning rules (expected counts from the profile; the ledger is the source of truth, and rules overlap)**

| # | Rule | Expected |
|---|---|---|
| 1 | Remove orders placed after 31 August 2018 (the tail; R5) | 20 |
| 2 | Remove orders with no lines, or with no payment | 775, 1 |
| 3 | Remove orders whose payments differ from price plus freight by any amount, compared as exact decimals (R2) | 576 |
| 4 | Remove orders with a `not_defined` payment | ≤ 3 |
| 5 | Remove orders whose delivery date contradicts their status (delivered without a date; not delivered with one) | 8, 6 |
| 6 | Change payments with zero instalments to one | 2 |
| 7 | Keep the latest review per order: highest `review_answer_timestamp`, then `review_id` (no ties on the timestamp); drop reviews of removed orders. Reviews on orders never delivered are kept as history (R3) | 551 removed by the first part |
| 8 | Split products shared by several sellers into one product per seller | 32,951 → 34,448 before removals |
| 9 | Collapse repeated (order, product, seller) lines with an equal unit price into one line with a quantity; the line's freight is the sum of the original items' freight | 6.9% of pairs |
| 10 | Split orders spanning several sellers into one order per seller; the Olist order becomes the checkout and keeps its payments | 1.3% of orders |
| 11 | Map the eight statuses to five (PLAN.md section 5); translate the 2 missing category names by hand; put the 610 uncategorised products in "Uncategorised" | |
| 12 | Geolocation: one row per zip prefix (median latitude and longitude, most common city and state) | 1M → 19,015 |
| 13 | Shift every timestamp by 426 weeks and treat it as Singapore local time | Originally stated "ends 30 October 2026"; correction, 29 October: the clean data's last order is 28 October 2026 and its last delivery is 16 December 2026, per [PLAN.md section 5](../../PLAN.md#5-data-olist-adapted) |
| 14 | Currency: convert each original Olist item's price and freight to SGD at the stored rate and round half-up to the cent **before** rule 9 collapses lines; the checkout total is the sum of its lines; split each checkout's payments in proportion to their original values, rounded, with the remainder on the largest payment, so payments equal the total exactly | |
| 15 | Active (`active = true`; "delisted" means `active = false`) = a seller-product in at least two distinct orders, counted after cleaning (D13); featured = the best seller in each of the top 15 categories (D11) | about 13.6k active |
| 16 | Freight per product: the median freight of its order lines, in SGD (the shipping fee for new orders; `checkout` decision b) | every product |
| 17 | Refunds: one refund row (amount = the order total, flagged imported) for each cancelled order whose checkout has payments, so refunds equal cancelled totals (`checkout` decision c) | every cancelled order |
| 18 | Remove products whose every order line was removed by the rules above (no price or freight to derive) (X3) | small; in the ledger |

**PostgreSQL schema (fresh migrations; ids are bigint identities, Olist ids kept as source columns)**

| Table | Key points |
|---|---|
| `accounts.User` | Custom user model with `role` (`customer`, `seller`, `operator`; `CHECK`); `AUTH_USER_MODEL` set before the first migration (R7) |
| customer profile | One per user; `olist_customer_unique_id` unique; zip prefix, city, state (no foreign key to geolocation: some prefixes are missing there) |
| seller | One per user; status `pending`, `approved`, `rejected`, `suspended` (`CHECK`, all four in this `0001`); shop name; Olist seller id unique; zip prefix, city, state |
| category | 74 rows (73 Olist categories plus "Uncategorised"); slug unique; English and Portuguese names; `icon` (the icon's name in the sprite, the one home for the mapping); `hand_translated` flag |
| product | Seller and category foreign keys; `UNIQUE (id, seller_id)`; Olist product id (unique per seller); name; price `numeric(12,2) CHECK > 0`; freight `numeric(12,2) CHECK >= 0`; stock `CHECK >= 0`; lead time; weight and size (nullable: 2 products lack them); `active`, `featured`; `taken_down` (default false) and `taken_down_reason`, set later by `catalogue`; `has_generated_content` |
| checkout | `customer_id` (the user's id, as everywhere in this schema); placed time; total; idempotency key with `UNIQUE (customer_id, idempotency_key)` (nullable for imported rows); Olist order id (unique, nullable) |
| order | Checkout and seller; `UNIQUE (checkout_id, seller_id)` and `UNIQUE (id, seller_id)`; status (`CHECK`); items, freight and total; `placed_at`, `paid_at` (Olist's approval time), `shipped_at`, `delivered_at`, `cancelled_at`, `estimated_delivery` |
| order line | Composite foreign keys `(order_id, seller_id)` → order and `(product_id, seller_id)` → product, so a line's product always belongs to its order's seller and an order has one seller, enforced by the database; quantity `CHECK > 0`; unit price; freight |
| payment | Checkout; sequence; method (`CHECK`); instalments `CHECK >= 1`; amount `CHECK >= 0`. No status column: a payment row means money received |
| refund | Order (unique) and checkout; amount; reason; time; `imported` flag. Created here for imported cancellations; `checkout` adds app cancellations |
| geolocation | Zip prefix primary key; latitude, longitude, city, state |
| `purchasable_product` (view) | Products with `active`, not `taken_down`, and an `approved` seller: the one definition of "can be bought or shown", used by `checkout`, `catalogue`, `wishlist`, `dashboard` and `activity` (decision p) |

**Runtime privileges (review finding 1).** The default privileges in `src/docker/10-roles.sh` exist only in the `mercer`
database, not in pytest's test database. The first migration therefore runs `GRANT … ON ALL TABLES` and `ON ALL
SEQUENCES` plus `ALTER DEFAULT PRIVILEGES` for the runtime role named in `POSTGRES_RUNTIME_USER`, so both databases
match and the privilege tests test something.

Product **names** live in PostgreSQL (order history, cart and seller pages need them); descriptions and attributes live in
MongoDB. Imported customers and sellers get unusable passwords written directly (no hashing during import).

**MongoDB**

| Collection | Contents and rules |
|---|---|
| `reviews` | One per order line (multi-line orders get a copy per line, `from_order_review: true`); order line, order, checkout, product, seller and customer ids; score; Portuguese and English title and text (`machine_translated: true`); dates; Olist review id (indexed, **not** unique). Unique index on `order_line_id` |
| `product_specs` | `_id` = product id; category; generated description; `attributes`; `photo_file_id` (null unless featured, set by `catalogue`); `rating_summary` (count, sum, average, distribution, `bayesian`) and `latest_reviews` (five), computed by the cleaning step. `$jsonSchema` validates the outer fields only |
| `platform_stats` | One document: the platform mean score m and the prior weight C (median review count per product), computed by the cleaning step for the Bayesian rating (`reviews` decision a) |
| `category_templates` | One per category: its attribute definitions (rich for the top 15 categories, generic for the rest). The app validates attributes against these, and the schema-evolution demo edits a template, which needs no `collMod` (the app user's `readWrite` does not grant it) |

**`mongo_setup` (decision q).** One idempotent command creates every MongoDB collection, validator and index. The app
user's `readWrite` role is enough to create collections, validators and indexes, so there is no MongoDB owner. It runs
from `migrate` and from a pytest session fixture on `test_mercer`; a per-test fixture deletes the documents the test
created. Later workstreams add their objects to it (`catalogue`: the attribute multikey index; `activity`: `events`).

**Where each command runs (review finding 12)**

| Command | Service |
|---|---|
| `translate_reviews.py` | Its own environment (never the app image) |
| `clean_olist.py`, `generate_content.py`, their tests (`pytest analytics/tests`), `make_fixture.py`, `profile_olist.py` | `tools` (Compose profile; pandas and pytest pinned) |
| `migrate`, `mongo_setup`, `import_olist`, `seed_demo`, later `load_photos` | `migrate` (owner role, `data/` mounted read-only) |
| The app test suite | `migrate`, as AGENTS.md says |

Demo passwords (`DEMO_CUSTOMER_PASSWORD`, `DEMO_SELLER_PASSWORD`, `DEMO_OPERATOR_PASSWORD`) are generated by
`init_env.py`, listed in `.env.example` and passed to `migrate`.

**Also in scope**
- **Accounts:** `seed_demo` creates usable logins (one customer per member, one operator, one seller tied to a high-volume
  Olist seller), passwords from `.env`. It also guarantees the demo seller owns one sold-out product and one product that
  the dashboard will flag (for the `wishlist` and `dashboard` exit checks), labelled as demo adjustments.
- **Removal:** shoe code, data, 3D models (with `CREDITS.md`) and tests; `config/dataset.py` and `import_dataset`; the
  `reporting` app (models including `CustomerSegment`, migrations, commands, templates and tests);
  `analytics/build_shoe_dataset.py`, `analytics/export_coverage.py` and their tests.
- **Minimum working after phase 1:** home, product list and product detail render from the new schema; the three demo
  logins work. Cart, checkout, order and dashboard routes return 404, and their old tests are removed, until `checkout`
  and `dashboard` rebuild them.
- **Fixture:** `scripts/make_fixture.py` picks a deterministic raw subset (about 1,000 Olist orders, including at least two
  of every broken kind, shared products, multi-seller orders and duplicate reviews) into `tests/fixtures/olist/raw/`;
  tests run cleaning and import on it.
- **Docs:** `docs/DATA_MODEL.md` gets the ER diagram (Mermaid), the 3NF justification, the MongoDB model (what is embedded,
  what is referenced, and why), and the generated profile and ledger tables.

**Out of scope:** catalogue UI, search and photos (`catalogue`); checkout logic (`checkout`); review UI and Bayesian
rating (`reviews`); dashboard (`dashboard`); benchmark copies of the data (`benchmark`).

**Tests:** one per cleaning rule on the fixture; two cleaning runs give identical checksums; rows read = kept + removed
for every table; constraints reject a negative price or stock, an unknown status, a line whose product belongs to another
seller, and a second order for the same seller in one checkout; every checkout's payments equal its total; the importer
refuses a non-empty database; MongoDB rejects a spec missing an outer field and a second review for an order line; the
runtime role can read the imported data in the test database; an import whose data breaks an invariant fails with the
query's rows; generation is deterministic; rule 18 drops exactly the products left without lines.

**Exit check (the reviewer runs all of these)**
1. Fresh clone, `docker compose up`, then `import_olist` on the full data as the owner: under ten minutes, progress shown.
2. Rerunning `clean_olist.py` reproduces the committed files byte for byte; the ledger shows rows read = kept + removed
   for every table, and its counts match the table above or the difference is explained in the review notes.
3. No checkout's payments differ from its total (the query returns no rows).
4. The delay-bucket table from `profile_olist.py` (raw data) and the same query on the imported data show the same
   pattern (bucket averages within 0.05).
5. The full test suite passes in Docker; cleaning plus import of the fixture takes under a minute.
6. `docs/DATA_MODEL.md` has the ER diagram, the 3NF justification, the MongoDB model and the ledger.
7. Product list and detail pages render, and the three demo logins work.

## Decisions (all approved 21 October 2026)

| ID | Decision |
|---|---|
| a | Fresh migrations, one new `0001` per app |
| b | Clean in Python before import; the importer only loads committed clean files |
| c | Drop the old import machinery and the `reporting` app; `dashboard` rebuilds reporting |
| d | Translate offline with Argos Translate, once, as a separate step |
| e | ECB rate on the implementation day, stored with its date in `data/derived/olist/fx.json` |
| f | Olist timestamps become Singapore local time after the shift |
| g | No re-import: reset with `docker compose down -v`, migrate, import |
| h | MongoDB collections, validators and indexes are created here |
| i | Remove all 576 orders whose payments differ from their total (R2) |
| j | Keep reviews of undelivered orders as history (R3) |
| k | Drop the 20 orders after August 2018 (R5) |
| l | Bigint ids; Olist ids as source columns (R6) |
| m | Custom user model with a `role` field (R7) |
| n | Drop products left without any order line after cleaning (X3) |
| o | The importer disables user triggers while loading and checks the invariants with queries at the end (X4); the triggers guard every app write |
| p | `taken_down` and the `purchasable_product` view are created here, so `checkout` (phase 2A) can use them before `catalogue` (2B) |
| q | One idempotent `mongo_setup` command owns MongoDB setup; later plans extend it |

## Implementation notes (Codex, 22 October 2026; independent review complete)

- The accelerated Phase 1A header follows PLAN.md section 13; the original effort estimate remains a risk estimate.
- The initial migrations replace the baseline. Existing local databases need the documented project-scoped reset.
- Implementation choices are recorded in [DECISIONS.md](../DECISIONS.md#olist-import-implementation-22-october-2026-independent-review-complete),
  including source-address/date anchors, minimal offline Argos inference, FX publication timing, trigger restoration,
  ledger grouping semantics and a demo product with real recent demand. These are implementation notes, not Claude Code findings.
- The fixture includes both one-cent and larger exact payment mismatches. Its selection manifest records the source's
  single no-payment order rather than inventing a second. Its intentionally adversarial tiny longest-delay cohort
  changes by more than the full-data comparison tolerance when that broken order is removed; a test verifies that
  strict comparison rejects this case. Full-data comparison remains a required exit check.
- Profile and verification use the five non-overlapping delay buckets from the dashboard contract. They count one
  original checkout review, including reviews copied to lines, and preserve the actual raw ordering pattern.
- No later application routes, benchmark loader, Redis, activity collection, photos, checkout service or dashboard
  implementation is added. Applicable auth/security/privilege/logging/outage coverage is ported to the new schema.
- Independent Claude Code review and fix-round verification are complete; their record is retained below.
  The workstream is closed out and its AI-use log is recorded.

### Implementation verification (Codex; not independent review)

The importer emits measured duration and loader RSS as JSON; `verify_olist` emits the full-data invariant and delivery
comparison. Execution logs and review evidence remain outside the data checksum tree (decision olist-i17). The test
commands report their own outcomes; fixture and full-data determinism checks are separate. All required implementation
exit checks passed. PostgreSQL/MongoDB were recreated from the
ownership-verified local project volumes and initial migrations applied successfully. The final bulk import, invariant
queries, demo accounts and real HTTP smoke checks passed. Two full clean/generation runs in separate directories have
identical checksums; raw and derived manifests verify. The generated profile and ledger are in DATA_MODEL.md.

The final Docker suite uses real databases. Its Git-index-only documentation checks are skipped because the app image
has no Git; those checks passed in the separate host run. No database test is skipped. Host pytest needed a fresh temp
directory outside the repository after a Windows temp ACL conflict; README records the remedy.

The first full MongoDB load exceeded a single transaction's lifetime. Bounded batch transactions and ID-scoped
compensation fixed it; affected failure tests and the complete Docker suite were rerun. Counts in the approved profile
reproduce exactly. The approximate active estimate and product-removal counts are defined precisely by the ledger:
active is counted after cleaning per seller-product, and rule 18 separately records removed seller-products and source
products with no surviving lines. Rule counters overlap and source grouping differs from output row counts.

The workstream is closed out following independent review and fix-round verification; PLAN.md section 14 records
its status. Benchmark and CI plan review and approval are still required for Phase 1A. No later workstream or Tier 2/3
feature was added. Publication uses the workstream branch and a pull request; merging is outside this close-out.

## Review notes

21 October 2026, fresh Claude Code session; findings verified against the data and accepted: exact payment comparison
(576, of which 273 off by one cent), review selection (551 removed; Olist review ids not unique; tie-break on answer time),
the currency rounding rule, rules for the remaining data quirks, the tail after August 2018, the active count per
seller-product, rating summaries computed at import, outer-field-only validation with templates in their own collection,
the schema details (custom user, bigint ids, composite foreign keys, owner role and `setval`), the minimum working state
after phase 1, where cleaning runs and how it stays deterministic, translation as a separate resumable step, the raw
fixture, and the missing tests. Names stay in PostgreSQL and descriptions move to MongoDB, so no value lives in both.

21 October 2026, cross-plan review (fresh session): runtime privileges in the test database, trigger handling during
import (X4), `mongo_setup`, `platform_stats` and the Bayesian fields, settled names (idempotency key, `rejected`,
timestamps, no payment status, "delisted"), `taken_down` and the `purchasable_product` view moved here, where each
command runs, demo passwords, the generation step, freight and rounding order, dropped products (X3), 74 categories
with `category.icon`, and the demo products `seed_demo` guarantees.

22 October 2026, independent code review (fresh Claude Code session) of the uncommitted implementation. No blocking
findings; every exit check was rerun and passed. After an ownership-verified reset of this project's three named
volumes: full `import_olist` well under ten minutes with progress; `verify_olist` before `seed_demo` with zero invariant
rows, all five delay buckets within 0.05 and the raw ordering pattern; `seed_demo` (rerun idempotently) and the HTTP
smoke script with all three role logins; runtime-role DDL, TRUNCATE, DROP, trigger, `COPY PROGRAM` and `setval`
negatives refused. Pipeline tests and the full Docker suite passed (only the Git-index checks skipped, which passed on
the host); `check_docs.py` passed. Two full clean and generation runs matched each other and the committed files; the
profile, generated DATA_MODEL.md sections, fixture and `make_fixture` subset reproduced; fixture clean plus import ran
well under a minute. Types, composite FKs, trigger and sequence restoration, validators and indexes were inspected on
the live databases; ledger counts match the rule table. Translation was reviewed by reading only (model not present).
- **Medium, open:** `data/derived/olist/verification.json` is built by an uncommitted script in ignored `.cache/` from
  uncommitted logs, embeds timings, test counts and a review status, and sits in the derived checksum tree. Commit its
  generator or drop it, and keep evidence outside the data checksums.
- **Low, open:** the detail page doubles the "Demo adjustment:" prefix; `seed_demo` relists a delisted product without
  saying so in its label; README says full-data determinism is covered by pipeline tests (only the fixture is); the
  runtime role has DML on `django_migrations`; import errors drop their cause (`from None`); the detail view opens a
  MongoClient per request (`catalogue`); product freight takes the median of collapsed lines while price is per item
  (`checkout` to confirm per-line or per-unit fees); every category icon is `package` while DESIGN.md says the icon is
  selected by category (`catalogue`).
- **Noted, accepted:** the FX rate is the 21 October ECB fixing retrieved on 22 October, as olist-i1 records; the
  fixture's strict delay comparison fails by design and full data is the real evidence; MongoDB batches commit
  separately, so a hard kill mid-load needs the documented reset.

22 October 2026, Codex fix round responding to the independent review above:
- **Medium, resolved:** dropped the ad hoc `verification.json` from the repository data tree and regenerated the
  derived manifest. Its execution evidence remains in ignored local review logs; README points to the commands
  that emit measurements and comparisons. No ignored evidence generator is required to reproduce the dataset.
- **Low, fixed:** the product template renders the stored demo label once; relisting is labelled explicitly and
  the label survives repeated seeding; README distinguishes fixture tests from the separate full-data determinism
  procedure; runtime is read-only on `django_migrations` and has no privileges on its identity sequence; import
  command errors retain their causes for the owner's `--traceback` diagnostics.
- **Low, deferred:** [catalogue](catalogue.md#review-notes) owns MongoClient reuse and the category-icon mapping;
  [checkout](checkout.md#review-notes) must confirm the product freight unit before implementing new purchases.
  Imported historical totals and the existing cleaning rule remain unchanged.
- **Fix-round validation:** affected catalogue, import, role and SQL-injection modules passed on the real databases,
  followed by the complete Docker suite. The Git-only container skips passed in the host documentation/packaging
  run. The documented full-data cleaning/generation procedure matched both output directories and the prepared
  dataset byte for byte. The app image was rebuilt; the migration-history restriction was reapplied to the existing
  local application database and verified independently in the newly migrated test database. Execution logs remain
  local review evidence outside the data manifests. Repeated demo seeding, live product pages, all three role logins,
  SQL invariants and the runtime database health check passed; the migration drift check reported no changes.
  The workstream remains at review with all changes uncommitted.

22 October 2026, fix-round verification (the independent Claude Code reviewer). Each fix was checked against its
finding and holds: `verification.json` is gone and the derived manifest verifies; the detail page shows one demo
label; relisting is labelled and tested; README separates fixture tests from the full-data procedure; on the live
database the runtime role can read `django_migrations` but not insert, delete or draw its sequence, while app DML
still works; import errors keep their cause; the deferred items are recorded in the catalogue and checkout plans.
On a rebuilt image the full Docker suite passed (only the Git-index checks skipped), the migration drift check found
no changes, host documentation checks, `check_docs.py` and pipeline tests passed, raw, derived and fixture manifests
verified, and the earlier full-data runs still match the prepared clean data. Rerunning `seed_demo`, the HTTP smoke
script and all three role logins passed.
- **Low, open (follow-up):** on the live database seeded before the fix, product 549 shows no relisted label. The fix
  decides from the current `active` flag, which the earlier seed had already set, so a rerun cannot tell the product
  was relisted. A fresh reset and import labels it correctly, as the new test shows. A sturdier rule would derive
  relisting from imported order history (fewer than two distinct orders) instead of the current flag.

22 October 2026, Codex resolution of the previously seeded product's missing-label follow-up: `seed_demo` now derives original
visibility from distinct retained imported orders (cleaning rule 15), alongside current visibility and any existing
relisting label. This repairs an earlier seed's missing label without resetting the database; later application
orders do not contribute to the source threshold. A real-database regression starts with an already-active imported
product whose old demo label omits relisting and checks repair and repeated-seed stability. On the rebuilt image,
the catalogue module and complete Docker suite passed (the same Git-only checks skipped). Rerunning the seeder
repaired the existing live product without a reset; a second run preserved the label, all SQL invariants returned
no diagnostic rows, and the live HTTP smoke check and role logins passed. The recorded low follow-up is resolved;
final close-out remains pending and all changes remain uncommitted.
