# olist-import: Olist profile, cleaning, schema, import, adaptations, accounts

status: approved
plan owner: Erfan · implementer: Chee Long · reviewer: tbd (fresh session, other agent) · estimate: 3 to 4 days ·
window: 26 October to 1 November · depends on: `foundation`

## Contract

**Goal.** One command loads the cleaned, adapted Olist data into PostgreSQL and MongoDB on an empty database in under ten
minutes on a typical laptop, reproducibly, with a cleaning ledger that accounts for every removed or changed row.

**In scope**

| Area | Deliverable |
|---|---|
| Raw data | `data/raw/olist/` (9 CSVs) committed with `checksums.txt` (SHA-256); licence and attribution in `docs/licenses/olist.txt` |
| Profile | `analytics/profile_olist.py` reproduces the 21 October profile; its output is the generated dataset section of `docs/DATA_MODEL.md` |
| Schema | Fresh migrations (decision a). PostgreSQL tables: users with a role (customer, seller, operator); customer profile; seller (approval status); category (English and Portuguese names, icon); product (owned by one seller; price `numeric(12,2)`, stock, lead time, weight and size, `active`, `featured`, Olist source id); checkout (customer, payments total, idempotency key, Olist order id); order (one per seller per checkout; status; placed, approved, shipped, delivered and estimated dates); order line (product, quantity, unit price, freight); payment (checkout, method, instalments, amount); geolocation (one point per zip prefix). Constraints: every foreign key, `CHECK`s on money, stock, quantity and statuses, `ON DELETE RESTRICT` where history depends on a row |
| MongoDB | `reviews` (one per order line, Portuguese text, English text, score, dates, `from_order_review` flag, Olist review id; unique index on order line id) and `product_specs` (one per product: generated attributes by category template; `$jsonSchema` validator). Created with their indexes and validators by the importer |
| Cleaning | `scripts/clean_olist.py` (pandas) reads `data/raw/olist/`, applies every cleaning rule and adaptation, and writes import-ready files to `data/derived/olist/clean/` (CSV for PostgreSQL, NDJSON for MongoDB) plus `cleaning_ledger.json` (rule, rows affected, reason). Deterministic; outputs committed with checksums, so the importer and the benchmark load the same files |
| Importer | `manage.py import_olist`: `COPY` the clean CSVs into the app tables in foreign-key order, insert the NDJSON into MongoDB in bulk, create indexes and validators. No cleaning logic. Refuses to run on a non-empty database. Prints progress per step |
| Cleaning and adaptations | Exactly as PLAN.md section 5: broken orders removed (D9); latest review per order; shared products split per seller; repeated lines collapsed into a quantity (only where the unit price is equal); multi-seller orders split into one order per seller under one checkout (D17); statuses mapped; categories translated (D5); geolocation reduced (D6); all dates shifted 426 weeks (D7); BRL to SGD at one stored rate; active = ordered at least twice (D13); featured = best seller in each of the top 15 categories (D11) |
| Generated data | Seeded script producing names, descriptions, attributes (rich templates for the top 15 categories), stock and lead times, and the review translation; outputs committed under `data/derived/olist/` with checksums, every field labelled as generated |
| Accounts | One user per `customer_unique_id` and per seller, unusable passwords; `seed_demo` creates usable logins (one customer per member, one operator, one seller tied to a high-volume Olist seller) with passwords from `.env` |
| Removal | Shoe code, data, 3D models and tests; the old importer (`config/dataset.py`, `import_dataset`); the `reporting` app and its migrations (decision c); the `CustomerSegment` model (foundation-b) |
| Fixture | `scripts/make_fixture.py` writes a deterministic subset (about 1,000 checkouts with every related row) to `tests/fixtures/olist/` for tests and CI |
| Docs | ER diagram and 3NF justification in `docs/DATA_MODEL.md`; the cleaning ledger as a generated table there |

**Out of scope:** catalogue UI, search and photos (`catalogue`); checkout logic (`checkout`); review UI and Bayesian rating
(`reviews`); dashboard and reporting tables (`dashboard`); benchmark copies of the data (`benchmark`).

**Tests:** constraints reject bad rows (negative price, negative stock, unknown status, orphan line); the importer on the
fixture produces the expected ledger counts; every checkout's payments equal its orders' total; one seller per order;
MongoDB rejects a spec document that fails `$jsonSchema` and a second review for the same order line.

**Exit check (the reviewer runs all of these)**
1. Fresh clone, `docker compose up`, `import_olist` on the full data: finishes in under ten minutes, progress shown.
2. Rerunning `clean_olist.py` reproduces the committed clean files byte for byte (checksums match). For every raw table:
   rows read = rows kept + rows removed, per the ledger. Ledger counts match the profile (303, 775,
   1 broken orders; 814 duplicate review ids).
3. A query for checkouts whose payments differ from their orders' total returns no rows; no order has two sellers.
4. The delivery-delay table from PLAN.md (score by delay bucket) reproduces from the imported data.
5. Full test suite passes in Docker; the fixture import passes in under a minute.
6. `docs/DATA_MODEL.md` has the ER diagram, the 3NF justification and the generated ledger table.

## Decisions (all approved 21 October 2026)

| ID | Proposal | Why |
|---|---|---|
| a | Fresh migrations: replace all existing migrations with a new `0001` per app | Nothing is deployed; eleven migrations of shoe-era history would only confuse the ER story |
| b | Clean in Python before import; the importer only loads clean files | Simpler code; the committed clean files are also the benchmark's identical input |
| c | Drop the old namespace, fingerprint and inventory-version machinery and the `reporting` app; `dashboard` rebuilds reporting on the new schema | They are built for the old dataset; porting them is the main risk named in PLAN.md section 16 |
| d | Review translation with Argos Translate (offline, open source, Portuguese to English), run once; output committed | No API cost or key; about 41k short texts is practical on a laptop; reproducible |
| e | Exchange rate: the ECB EUR/BRL and EUR/SGD reference rates on the implementation day, stored with the date in `data/derived/olist/fx.json` | One fixed, cited rate; imports are reproducible |
| f | Treat Olist timestamps as Singapore local time after the shift | The shop presents as Singaporean (SGD); avoids a time-zone conversion nobody would see |
| g | No re-import or replay: reset is `docker compose down -v`, migrate, import | Replay logic is the machinery that made the old importer complex |
| h | `product_specs` and its `$jsonSchema` are created here, not in `catalogue` | Generated names come from the attributes, so both are produced together |

## Review notes

(empty until review)
