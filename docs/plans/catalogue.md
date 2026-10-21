# catalogue: Shop pages, specifications, faceted search, seller product CRUD, photos, audit, design

status: draft
plan owner: Erfan · implementer: Chee Long · reviewer: a fresh session, ideally the other agent · estimate: 3 to 4 days
· phase 2B (5 to 8 November) · depends on: `olist-import`, `accounts`

**Assumes:** the `olist-import` schema (product with seller, category, price, freight, stock, `active`, `featured`;
MongoDB `product_specs` with `attributes`, `rating_summary`, `latest_reviews`; `category_templates`); `accounts` roles,
seller status and the `audit_log` with `SET LOCAL mercer.actor_id`. Recheck these before starting.

## Contract

**Goal.** Customers browse, search and filter the active catalogue; sellers manage their own products across both
databases; the operator evolves category attributes live and takes products down; every price and stock change is audited.

**In scope**

| Area | Deliverable |
|---|---|
| Shop pages | Home (featured products; "trending" slot filled later by `activity`), category pages, product detail, seller shop page. Only active products of approved sellers are shown. Product detail = PostgreSQL product + MongoDB spec (description, attributes, rating summary, latest five reviews) + photo or icon card |
| Icon cards (D10) | Category → icon map covering all 73 categories (about 25 to 30 icons in `src/static/img/icons.svg`, adding what is missing); the card shows icon and name; alt text is the name |
| Featured photos (D11, D12) | 15 openly licensed stock photos (best seller in each of the top 15 categories), chosen after names exist, committed under `data/derived/olist/photos/` with `manifest.csv` (file, product, source URL, author, licence); `manage.py load_photos` stores them in GridFS (bucket `photos`) and records the file id on the spec. Served by a view with caching headers. Shown as "illustrative photo" |
| Search and facets (decision a) | One search page. MongoDB runs a `$facet` pipeline over `product_specs`: matching product ids for the category, attribute and rating filters, plus counts per category, rating band and attribute value. PostgreSQL then applies the price filter, active and seller-status checks, sorting and pagination with `WHERE id = ANY(%s)`. Name search uses a `pg_trgm` GIN index on product name (decision b) |
| Specifications | `$jsonSchema` on outer fields only (from `olist-import`); the app validates `attributes` against the category's template. Multikey index on attribute values used by the facets |
| Schema evolution demo | Operator page to add an attribute to a category template (name, type, allowed values). Sellers can then fill it, and the facets show it, with no migration and no `collMod`. The report contrasts this with the `ALTER TABLE` the same change needs in PostgreSQL |
| Seller product CRUD | Seller centre "My products": create, edit (name, price, stock, freight, category, attributes, description), upload or replace a photo (AGENTS.md rule 7), deactivate. PostgreSQL row and MongoDB spec are written together: PostgreSQL first inside its transaction, then MongoDB; if MongoDB fails, the PostgreSQL transaction rolls back (decision c). Delete is never offered: `ON DELETE RESTRICT` protects products with order history |
| Operator take-down | Operator console "Products": take a product down with a reason (`taken_down` flag plus reason, hidden from the shop, not editable by the seller), or restore it |
| Audit trigger | `AFTER UPDATE` trigger on product writing to `audit_log` when price, stock, `active` or `taken_down` changes, with before and after as JSONB and the actor from `SET LOCAL` |
| Design | Rewrite DESIGN.md for Mercer (foundation-a) and update `site.css` to match: tokens, product card, facet sidebar, seller centre and operator console layouts |

**Out of scope:** reviews UI and Bayesian ranking (`reviews`); trending and recently viewed (`activity`); wishlist
buttons (`wishlist`); more than 15 photos (top 3 per category only if time allows); full-text search (`search`, Tier 2).

**Tests:** facet counts match a direct count on the fixture; filters combine correctly across MongoDB and PostgreSQL; a
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

## Decisions (for the plan owner)

| ID | Proposal | Why |
|---|---|---|
| a | MongoDB narrows by category, attributes and rating and counts the facets; PostgreSQL filters by price, checks status, sorts and paginates | Price and stock live only in PostgreSQL; a category holds at most about 2k active products, so passing ids across is cheap, and its cost is measured for the report |
| b | Name search with a `pg_trgm` GIN index | Typo-tolerant, one index, a PostgreSQL feature worth showing; full-text search stays Tier 2 |
| c | Cross-store writes: PostgreSQL transaction open, MongoDB write, then commit; a MongoDB failure rolls PostgreSQL back. A MongoDB success followed by a failed PostgreSQL commit is logged and repaired by `manage.py check_specs` | No distributed transaction exists across the two engines; this keeps the rare failure visible and fixable, and it is a good report discussion |
| d | Take-down is a separate flag from seller deactivation | The seller cannot undo an operator take-down |

## Review notes

(empty until review)
