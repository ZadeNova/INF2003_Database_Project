# catalogue: Shop pages, specifications, faceted search, seller product CRUD, photos, audit, design

status: in-progress
plan owner: Chee Long · implementer: Chee Long · reviewer: a fresh session, ideally the other agent · estimate: 3 to 4 days
· phase 2B (dates in PLAN.md section 13) · depends on: `olist-import`, `accounts`

**Assumes:** the `olist-import` schema (product with seller, category, price, freight, stock, `active`, `featured`;
MongoDB `product_specs` with `attributes`, `rating_summary`, `latest_reviews`; `category_templates`); `accounts` roles,
seller status and the `audit_log` with `SET LOCAL mercer.actor_id`. Recheck these before starting.

## Contract

**Goal.** Customers browse, search and filter the active catalogue; sellers manage their own products across both
databases; the operator evolves category attributes live and takes products down; every price and stock change is audited.

**In scope**

| Area | Deliverable |
|---|---|
| Shop pages | Home (featured products; "trending" slot filled later by `activity`), category pages, product detail, seller shop page. Only products in the `purchasable_product` view (from `olist-import`) are shown. Generated names and descriptions carry a small "generated" label (AGENTS.md rule 9). Product detail = PostgreSQL product + MongoDB spec (description, attributes, rating summary, latest five reviews) + photo or icon card |
| Icon cards (D10) | Category → icon map covering all 74 categories, many to one (about 25 to 30 icons in `src/static/img/icons.svg`, adding what is missing); the card shows icon and name; alt text is the name |
| Featured photos (D11, D12) | 15 openly licensed stock photos (best seller in each of the top 15 categories), chosen after names exist, committed under `data/derived/olist/photos/` with `manifest.csv` (file, product, source URL, author, licence); `manage.py load_photos` (run in `migrate`) stores them in GridFS (bucket `photos`) and records the file id on the spec as `photo_file_id`. Served by a view with caching headers. Shown as "illustrative photo" |
| Search and facets (decision a) | One search page, entered with a category or a name query (with neither, the home page shows featured and trending instead). **PostgreSQL first:** the candidate ids from the `purchasable_product` view, narrowed by category, price range and the name query (`pg_trgm`, decision b; see the note below), at most about 2k for a category. **MongoDB second:** a `$facet` pipeline over `product_specs` with `_id` in those candidates, filtering by attributes and rating, returning the matching ids plus counts per rating band and attribute value, so counts only ever include buyable products. **Ordering:** for price or newest, PostgreSQL sorts and paginates the matching ids with `WHERE id = ANY(%s)`; for "Top rated", the pipeline sorts by `rating_summary.bayesian` and returns one page of ids, which PostgreSQL then fetches |
| Specifications | `$jsonSchema` on outer fields only (from `olist-import`); the app validates `attributes` against the category's template. Multikey index on attribute values used by the facets, created by adding it to `mongo_setup` (`olist-import`) |
| Schema evolution demo | Operator page to add an attribute to a category template (name, type, allowed values). Sellers can then fill it, and the facets show it, with no migration and no `collMod`. The report contrasts this with the `ALTER TABLE` the same change needs in PostgreSQL |
| Seller product CRUD | Seller centre "My products": create, edit (name, price, stock, freight, category, attributes, description), upload or replace a photo (AGENTS.md rule 7; the old GridFS file is deleted once the new one is stored), deactivate. PostgreSQL row and MongoDB spec are written together: PostgreSQL first inside its transaction, then MongoDB; if MongoDB fails, the PostgreSQL transaction rolls back (decision c). Delete is never offered: `ON DELETE RESTRICT` protects products with order history |
| Operator take-down | Operator console "Products": set the `taken_down` flag and reason (columns and view from `olist-import`), so the product leaves the `purchasable_product` view and disappears from the shop, carts and checkout at once; the seller cannot edit it; the operator can restore it |
| Audit trigger | `AFTER UPDATE` trigger on product writing to `audit_log` when price, stock, `active` or `taken_down` changes, with before and after as JSONB and the actor from `SET LOCAL`. The trigger function follows the shared audit boundary in `accounts`: `SECURITY DEFINER`, owned by the migration owner, schema-qualified, `search_path` pinned to `public, pg_temp`; the runtime role has no direct write on `audit_log`; actor and reason come from the bound transaction-local settings |
| Design | Rewrite DESIGN.md for Mercer (foundation-a) and update `site.css` to match: tokens, product card, facet sidebar, seller centre and operator console layouts |

**What a trigram index is.** A trigram is a run of three characters: "hose" becomes `  h`, ` ho`, `hos`, `ose`, `se `.
PostgreSQL's `pg_trgm` extension compares strings by how many trigrams they share, so a search for "hose nozle" still
finds "Hose Nozzle" despite the typo, and `ILIKE '%nozz%'` can use an index instead of scanning every row. A GIN index
on the trigrams of `product.name` makes both fast. The report shows `EXPLAIN` with and without it.

**Out of scope:** reviews UI and Bayesian ranking (`reviews`); trending and recently viewed (`activity`); wishlist
buttons (`wishlist`); more than 15 photos (top 3 per category only if time allows); full-text search (`search`, Tier 2).

**Tests:** facet counts match a direct count on the fixture and never include products outside the purchasable view; generated names and descriptions show the label; filters combine correctly across MongoDB and PostgreSQL; a
suspended seller's or delisted product never appears; a seller cannot edit another's product (scoping); a failed
MongoDB write leaves PostgreSQL unchanged; uploads reject SVG, oversize and non-image files; an attribute added to a
template appears in facets without a migration; the audit trigger records price and stock changes with the actor;
injection negatives on search parameters.

**Exit check**
1. Browse a category, filter by two attributes and a price range: counts and results are correct; `EXPLAIN` and
   `explain("executionStats")` show the trigram, multikey and `id = ANY` paths using indexes.
2. As the demo seller, create a product with a photo, edit its price and stock, deactivate it; the audit page shows each
   change with the seller as actor.
3. As the operator, add an attribute to a category template; the seller fills it on a product; the facet appears.
4. As the operator, take a product down; it disappears from the shop.
5. The 15 featured photos load from GridFS; every other product shows an icon card.
6. The full test suite passes in Docker.

## Decisions (all approved 21 October 2026)

| ID | Proposal | Why |
|---|---|---|
| a | PostgreSQL first (purchasable candidates by category, price and name), then MongoDB `$facet` on those ids (attributes, rating, counts); price or newest sorted in PostgreSQL, "Top rated" in the pipeline (X1, revised after the cross-plan review) | Purchasability and price live only in PostgreSQL, so facet counts are correct only if PostgreSQL filters first; a category holds at most about 2k buyable products, so passing ids across is cheap, and its cost is measured for the report |
| b | Name search with a `pg_trgm` GIN index | Typo-tolerant, one index, a PostgreSQL feature worth showing; full-text search stays Tier 2 |
| c | Cross-store writes: PostgreSQL transaction open, MongoDB write, then commit; a MongoDB failure rolls PostgreSQL back. A MongoDB success followed by a failed PostgreSQL commit is logged and repaired by `manage.py check_specs`, which compares product ids in PostgreSQL with spec ids in MongoDB, removes orphan specs and reports products without one | No distributed transaction exists across the two engines; this keeps the rare failure visible and fixable, and it is a good report discussion |
| d | Take-down is a separate flag from seller deactivation | The seller cannot undo an operator take-down |

**Phase 2 amendments (approved by Chee Long, 22 October 2026)**, settling questions the contract left open; see
[DECISIONS](../DECISIONS.md#phase-2-plan-amendments-22-october-2026):

| ID | Decision | Why |
|---|---|---|
| e | `lead_time_days` is a required field in seller create and edit (with the price, stock and freight fields); new products start with `has_generated_content` false | The column is not nullable; the field list above omitted it |
| f | The design rewrite (DESIGN.md and `site.css`) and the 15 featured photos are a separate, owner-steered step after the core is built, not part of an unattended run. They remain in this contract and its exit check 5. Until then pages use the current design and products show icon cards | Design is a taste decision tied to the presentation grade (foundation-a: the UI work decides the design); each photo needs its licence verified on its source page |
| g | Icons map many to one: the 26 existing symbols plus any added cover all 74 imported categories | The import produced 74 categories, not 73 |
| h | Benchmark case B1 is not built in this workstream | `benchmark` owns it on its separate bench databases; PLAN.md section 13 only aligns the timing |

## Review notes

21 October 2026, cross-plan review (fresh session); findings applied: search reversed to PostgreSQL first so
facet counts exclude unbuyable products, with "Top rated" sorted in the pipeline (X1); `taken_down` and the
`purchasable_product` view now come from `olist-import`; the multikey index joins `mongo_setup`; the generated-content
label; `photo_file_id`, old-photo deletion and `check_specs` defined.

22 October 2026, follow-ups from the independent `olist-import` code review: reuse a MongoClient per application
process rather than opening one for each product-detail request, while retaining explicit test-database routing
and controlled outage behaviour; replace the minimum import's generic `package` category icons with the category
mapping required by DESIGN.md. These remain catalogue work and do not block the Phase 1A data import.

22 October 2026, Phase 1B decision P3 (accepted by Chee Long): the product audit trigger follows the shared
owner-owned audit boundary defined in `accounts`; no other contract change.

22 October 2026, Phase 2 amendments e–h approved by Chee Long before implementation (lead time field, design and
photos as an owner-steered step, many-to-one icons for 74 categories, benchmark scope).


23 October 2026, Codex implementation under Chee Long's approved parallel Phase 2A/2B run: the core is ready for
fresh Claude Code review. The plan remains in-progress and PLAN section 14 is review. Local slice commits contain
additive catalogue migration 0002, search/facets, public shops, scoped seller CRUD and re-encoded GridFS uploads,
operator take-down/restore and template additions, product audit and the repair command. No existing initial
migration was changed. The design rewrite/featured stock photos and benchmark B1 remain outside this run.

Self-check evidence is retained in the ignored .cache directory with a command ledger, raw command outputs,
full-data exit results, EXPLAIN/executionStats JSON and browser screenshots. Migration drift, the full Docker suite,
tools-profile analytics tests, host Git-index/packaging checks and documentation checks passed. The full suite ran
before the narrow audit-table display fix; affected audit and product modules were rerun after the fix and audit
assertions were scoped to catalogue_product for integration. The Docker image lacks Git, so its Git-index skips were
covered by the separate host run without skips. All new page routes were checked at desktop and 375px; tables scroll
inside their regions. A long audit badge overflow was fixed in the appended catalogue CSS block and rechecked.

Exit checks 2, 3 and 4 passed against the full import through CSRF-enabled Django clients using the demo logins:
photo create/serve, price/stock edit and deactivation with seller audit; new template option filled and faceted;
operator take-down, denied seller edit and restore. check_specs found no missing/orphan specs or category mismatch.
Exit check 1's counts matched a direct count for two attributes plus a price range; natural PostgreSQL plans use
product_name_trgm and the primary-key ANY path, and natural MongoDB winning plans use spec_attributes for both
existing and newly added fields. The imported scalar dictionaries report isMultiKey false: strict multikey wording
remains catalogue-i1 for owner confirmation, not a claimed array demonstration. The without-trigram comparison was
captured by dropping only that index inside a transaction which rolled back; no forced plan is claimed as natural.
Exit check 5 is pending the owner-steered amendment f step. The Phase 2B buy/ship/deliver checkpoint remains pending
checkout integration. The shared cart include and separate product/order audit lookups must be retained at merge;
implementation choices catalogue-i1 through catalogue-i10 remain marked needs owner confirmation in DECISIONS.

Final coverage audit: the bound cross-store ANY helper has its own hostile-ID PostgreSQL negative, in addition to
the search parameter negatives. The affected search module was rerun after adding it; no application code changed.
