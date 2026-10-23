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
| Featured photos (D11, D12; deferred by amendment j) | On hold until after Phase 3A, only if time allows before the 30 October freeze; otherwise dropped. Every product shows an icon card unless its seller uploaded a photo |
| Search and facets (decision a) | One search page, entered with a category or a name query (with neither, the home page shows featured and trending instead). **PostgreSQL first:** the candidate ids from the `purchasable_product` view, narrowed by category, price range and the name query (`pg_trgm`, decision b; see the note below), at most about 2k for a category. **MongoDB second:** a `$facet` pipeline over `product_specs` with `_id` in those candidates, filtering by attributes and rating, returning the matching ids plus counts per rating band and attribute value, so counts only ever include buyable products. **Ordering:** for price or newest, PostgreSQL sorts and paginates the matching ids with `WHERE id = ANY(%s)`; for "Top rated", the pipeline sorts by `rating_summary.bayesian` and returns one page of ids, which PostgreSQL then fetches |
| Specifications | `$jsonSchema` on outer fields only (from `olist-import`); the app validates `attributes` against the category's template. A wildcard index on `attributes.$**` used by the facets (amendment i), created by adding it to `mongo_setup` (`olist-import`) |
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
buttons (`wishlist`); featured stock photos (amendment j); full-text search (`search`, Tier 2).

**Tests:** facet counts match a direct count on the fixture and never include products outside the purchasable view; generated names and descriptions show the label; filters combine correctly across MongoDB and PostgreSQL; a
suspended seller's or delisted product never appears; a seller cannot edit another's product (scoping); a failed
MongoDB write leaves PostgreSQL unchanged; uploads reject SVG, oversize and non-image files; an attribute added to a
template appears in facets without a migration; the audit trigger records price and stock changes with the actor;
injection negatives on search parameters.

**Exit check**
1. Browse a category, filter by two attributes and a price range: counts and results are correct; `EXPLAIN` and
   `explain("executionStats")` show the trigram, wildcard attribute and `id = ANY` paths using indexes.
2. As the demo seller, create a product with a photo, edit its price and stock, deactivate it; the audit page shows each
   change with the seller as actor.
3. As the operator, add an attribute to a category template; the seller fills it on a product; the facet appears.
4. As the operator, take a product down; it disappears from the shop.
5. Every product without an uploaded photo shows an icon card; seller-uploaded photos load from GridFS.
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
| f | The design rewrite (DESIGN.md and `site.css`) and the 15 featured photos are a separate, owner-steered step after the core is built, not part of an unattended run. The design remains required; the featured photos are deferred by amendment j. Until then pages use the current design and products show icon cards | Design is a taste decision tied to the presentation grade (foundation-a: the UI work decides the design); each photo needs its licence verified on its source page |
| g | Icons map many to one: the 26 existing symbols plus any added cover all 74 imported categories | The import produced 74 categories, not 73 |
| h | Benchmark case B1 is not built in this workstream | `benchmark` owns it on its separate bench databases; PLAN.md section 13 only aligns the timing |
| i | The attribute index is a wildcard index on `attributes.$**` (approved by Chee Long, 23 October 2026, replacing "multikey index") | It also covers attributes the operator adds later. The imported attributes are scalars, so explain reports `isMultiKey: false`; the report calls it a wildcard index (multikey-capable for arrays) and does not claim a multikey demonstration |
| j | The 15 featured stock photos (D11, D12; amendment f decisions f4-f8) are deferred: picked up after Phase 3A only if time allows before the 30 October freeze, otherwise dropped. Exit check 5 becomes "every product without an uploaded photo shows an icon card; seller-uploaded photos load from GridFS" (approved by Chee Long, 23 October 2026) | GridFS is already demonstrated by seller photo upload (exit check 2); the photos were the slowest, owner-blocked part of amendment f; the design rewrite is what affects the presentation grade |

**Amendment f plan (approved by Chee Long, 23 October 2026).** Design direction chosen by Chee Long on
23 October 2026 (f1 to f4); f5 to f8 and the work order were approved the same day:

| ID | Decision | Why |
|---|---|---|
| f1 | Evolve VoiceBox into Mercer's own system: same tokens, square 2px-bordered surfaces, accessibility fixes and motion rules; blog-only parts (pull quotes, bylines, avatars, 56px display) go | Keeps the contrast-checked, dark-mode and motion work already built; lowest risk before the 30 October freeze |
| f2 | Keep the red accent (`#EF4444`, `#B91C1C` where read) and its eleven placements | Already contrast-checked in both themes |
| f3 | Product grid: 4 per row on desktop, 3 on tablet, 2 on phones | Room for name, price, stock and the labels without truncation |
| f4 — on hold (amendment j) | Photos only from Wikimedia Commons under CC0, public domain, CC BY or CC BY-SA, each verified on its file page | Every manifest row is checkable; "openly licensed" holds literally |
| f5 — on hold (amendment j) | The featured set is the import's `featured` flag (most units sold in each of the 15 largest categories by units), not recomputed | Committed by the reproducible cleaning script; ranking by order lines would swap two products (Watches gifts, Telephony) |
| f6 — on hold (amendment j) | Generated names are generic ("Woven Bed bath table 99A478"), so each photo shows the category item described by the product's generated attributes (for example a queen-size geometric linen sheet) | The only product detail that exists; the page labels it "Illustrative photo" |
| f7 — on hold (amendment j) | `manifest.csv` columns: file, product_id, title, source_url, author, licence, licence_url, changes. Images are resized to at most 1200 px and re-encoded by the existing upload path (metadata removed, at most 2 MB); no cropping, so changes read "resized, re-encoded" | Satisfies CC BY/BY-SA attribution and change notice without turning a BY-SA photo into a derivative |
| f8 — on hold (amendment j) | `load_photos` stores the credit (author, licence, source) in the GridFS file's metadata; the detail page shows "Illustrative photo · author · licence" with links; cards show "Illustrative photo"; seller uploads carry no credit | The credit belongs to the photo, one store; idempotent: rerunning replaces each product's photo and deletes the old file |

**Work, in order** (branch `catalogue/design-photos`; revised by amendment j, approved by Chee Long,
23 October 2026):
1. Record amendment j as a separate docs commit; remove uncommitted featured-photo assets, loader, manifest and credit
   UI. Decisions f4-f8 are on hold. Temporary research/contact sheets stay outside the committed tree.
2. `DESIGN.md` rewrite: one Mercer system (the "As built" deviations folded into the main text) with the marketplace
   components: product grid and card (icon or seller-uploaded photo, generated labels, mono price, stock), facet
   sidebar (attribute counts, price range, active-filter chips), product detail, seller centre, operator console,
   cart and checkout, order-status chips. The VoiceBox MIT attribution and font/icon licences stay.
3. `site.css`: remove rules no template or script uses (a selector-usage check lists them first), implement the 4/3/2
   grid, then align the seller and operator layouts. Literal colours live only in the `:root` tokens.
4. Visual pass in the browser: home, category with facets, product detail (icon and seller-uploaded photo), cart,
   checkout, seller products and form, operator lists and audit; light and dark; 375 px and desktop; no horizontal
   scroll and AA contrast for every new pair. Show screenshots and the DESIGN.md diff to Chee Long for sign-off;
   this is the only stop.
5. After sign-off, record implementation and checks, set catalogue to review in PLAN.md section 14, update AI_USE and
   CONTRIBUTIONS, commit and request fresh Claude Code review. Do not mark catalogue done, push, merge or open a PR.

**Amendment f exit check (revised by amendment j):** exit check 5 above; `DESIGN.md` tokens match the `:root` block in
`site.css`; the visual pass shows no overflow or contrast failure; the full suite passes in Docker and
`scripts/check_docs.py` passes. Catalogue enters review; Phase 2B closes only after the required review and merge.

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

23 October 2026, independent fresh Claude Code review of `495dc01` (on `cdd421f`): **CHANGES REQUESTED, no
blockers.** Rebuilt migrate/web; the drift check found no changes; the full Docker suite passed (454 passed, 4 skipped,
which are the Git-index tests the image cannot run); the host Git-index/packaging tests passed (28) and
`check_docs.py` passed. Exit checks were run over HTTP against the running full import on port 8031 with the demo
logins. Exit 1 passed: Housewares, material steel, capacity 500 ml and S$10–100 gave 73 results, which matched an
independent count (PostgreSQL 606 candidates, then a direct MongoDB count). The unhinted plans used
`product_name_trgm` (BitmapOr of both trigram predicates), `catalogue_product_pkey` for `id = ANY` and
`spec_attributes` for the facet (786 keys examined). Exits 2–4 passed: create with photo, then edit and deactivate,
wrote `product.update` (25.00→27.50, 7→5) and `product.deactivate` with demo-seller as actor. The added
`review_colour` option was filled by the seller and showed as a facet. Take-down hid the product from the shop,
search and detail page, and the seller's edit and deactivate calls returned 404. Restore worked. Each of these
operator actions was audited with its reason. Exit 5 and the Phase 2B core demo remain pending under amendment f.
The probes found no 5xx across 33 hostile search, filter, sort, page and attribute parameters. SVG, SVG
disguised as PNG, GIF, text and over-2 MB uploads were rejected. A PNG with an HTML trailer was re-encoded to JPEG
without the trailer and served with nosniff. A missing CSRF token returned 403, cross-seller edits returned 404 and
the role gates held. The trigger function is owner-owned, SECURITY DEFINER, with a pinned search_path; runtime has
SELECT only on `audit_log` and no TRIGGER or EXECUTE privilege.
**Should fix in the fix round:** CG1, the photo endpoint (`src/catalogue/views.py:101`) looks up `photo_file_id`
without an index (COLLSCAN of 34,215 specs, 22 ms per image, and 24 scans per page once featured photos land): add an
index, or put the product id in the URL. CG2: the README catalogue sections sit under "## Team" (README.md:320); move them
into the user manual. CG3: the blank line before `docs/AI_USE.md:28` splits the table. CG4: catalogue-i5 and
DATA_MODEL say "text", but the stored and operator type is `string`. CG5: the owner should replace "Multikey index" in
this contract with the wildcard wording (catalogue-i1).
**Optional:** CG6, a name-only search is unbounded (`?q=a` passes 11,818 ids, 330–530 ms against 40–60 ms for the
largest category, 1,292). CG7: `check_specs` cannot see edit-path divergence or unreferenced GridFS files. CG8: the
`categories` facet (`search.py:76`) is unused. CG9: no test covers seed_demo's NULL actor under a bound caller actor.
CG10: no seller reactivation. CG11: seller-rewritten imported products keep the generated label.
catalogue-i1 to i10 are recommended for approval (i5 with the CG4 wording fix). The report should call
`spec_attributes` a wildcard index that would be multikey for arrays, and should say that the scalar attributes give
isMultiKey false. Review artefacts (rows 34213–34215 and the Housewares option `review_colour`) remain in the
review project. No application code or tests changed; this entry is left uncommitted.

23 October 2026, fix round (Claude Code, at Chee Long's request): CG1 adds the `spec_photo_file` index (test proves an
index scan); CG2 moves the catalogue manual into one README section above "Regenerate the data"; CG3 rejoins the
AI_USE table; CG4 says `string`; CG5 approved by Chee Long as amendment i (wildcard index wording; catalogue-i1
confirmed); CG6 caps candidates at 2,000 ordered by trigram similarity, with a note when a broad name search is
narrowed (the largest category has 1,292 buyable products, so category browsing is never capped); CG8 removes the
unused category facet; CG9 tests that seed_demo writes system audit rows inside a caller's actor context. CG7, CG10
and CG11 remain follow-ups.

23 October 2026, Phase 2 checkpoint on `main` (Claude Code, at Chee Long's request), against the full-data `mercer`
database through the running web service (runtime role): the demo customer bought from three sellers in one checkout
(one checkout, three paid orders, payments = total = 278.25; stock fell by one each, every change audited with the
buyer and a reason; resending the pay form created nothing); the demo seller could not ship another shop's order,
shipped its own, and the operator delivered it, with the customer seeing Delivered and the audit trail recording both;
faceted category search with a price range rendered; the demo seller created a product with an uploaded photo, saw
it on the detail page and deactivated it (it then left the shop). 20 of 20 steps passed. Merged: amendments PR #8,
checkout PR #9, catalogue PR #10 (combined suite 566 passed, 4 skipped; both CI jobs green on the combined code).
The catalogue core is merged; this plan stays in progress until the owner-steered step (amendment f: the
DESIGN.md/site.css rewrite and the 15 featured photos, exit check 5) is done. Follow-ups CG7, CG10 and CG11 remain.

23 October 2026: Chee Long confirmed catalogue-i2 through catalogue-i10 as recommended by both reviews (catalogue-i1
was confirmed earlier as amendment i); see [DECISIONS](../DECISIONS.md).
