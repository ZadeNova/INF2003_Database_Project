# olist-import: Olist cleaning, schema, import, adaptations, accounts

status: approved
plan owner: Erfan · implementer: Chee Long · reviewer: a fresh session, ideally the other agent · estimate: 4 to 5 days
· phase 1 (26 October to 1 November) · depends on: `foundation`

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
| 13 | Shift every timestamp by 426 weeks and treat it as Singapore local time | ends 30 October 2026 |
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
