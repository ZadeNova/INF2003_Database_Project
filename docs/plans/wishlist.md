# wishlist: Wishlist and restock alerts

status: in-progress
plan owner: Erfan · implementer: Chee Long · reviewer: a fresh session · estimate: about 1 day · phase 3A (9 to 13
November) · depends on: `olist-import`, `catalogue` (product pages), `checkout` (cancellation restocks)

**Assumes:** product `stock` in PostgreSQL changes only through seller edits (`catalogue`) and checkout or cancellation
(`checkout`); the customer role from `accounts`, whose audit triggers treat a missing actor as a system change (so a raw `psql`
restock works); `seed_demo` guarantees the demo seller owns a sold-out product.

## Contract

**Goal.** A customer saves products, including sold-out ones, and is told inside the app when a saved product comes
back in stock, by a database trigger that no code path can skip.

**In scope**

| Area | Deliverable |
|---|---|
| Wishlist | `wishlist_item` (customer, product, added_at) with a composite primary key (the many-to-many table). Add and remove buttons (HTMX) on product cards and detail; a wishlist page showing stock status |
| Restock alerts | `restock_alert` (customer, product, created_at, seen_at). An `AFTER UPDATE OF stock` trigger on product, when stock goes from 0 to above 0, inserts one alert per wishlisting customer with `INSERT … SELECT … ON CONFLICT DO NOTHING` |
| No duplicates (decision a) | A partial unique index on `restock_alert (customer, product) WHERE seen_at IS NULL`, so a product restocked twice before the customer looks produces one unseen alert |
| Display | A header badge with the unseen count; an alerts page; opening it marks alerts seen. Alerts for products outside the `purchasable_product` view are hidden |

**Out of scope:** email or push notifications (decision b); alerts for price drops.

**Tests:** stock 0 → 5 creates one alert per wishlisting customer; 5 → 6 creates none; 0 → 5 → 0 → 5 before viewing
leaves one unseen alert; a cancellation that restocks fires the alert; a customer sees only their own wishlist and
alerts; the trigger fires for a raw `UPDATE` in `psql`, not only through the app.

**Exit check**
1. As the demo customer, wishlist a sold-out product; as its seller, restock it; the customer's badge shows 1 and the
   alerts page lists it.
2. The trigger and partial index appear in `docs/DATA_MODEL.md`; the full test suite passes in Docker.

## Decisions (all approved 21 October 2026)

| ID | Proposal | Why |
|---|---|---|
| a | Partial unique index to stop duplicate unseen alerts | A clean, non-standard constraint worth naming in the report |
| b | In-app alerts only | No mail server in a local project; the database behaviour is what is graded |

## Review notes

21 October 2026, cross-plan review (fresh session); findings applied: relies on the `NULLIF` actor rule and the demo sold-out product; uses the
purchasable view.


24 October 2026 — Implementation notes (Codex; reviewer: pending (Claude Code)). Built the composite-key wishlist,
HTMX save/remove buttons, scoped wishlist and paginated alerts, neutral header badge, partial unseen unique index
and stock transition trigger alongside product_update_audit. Focused checks passed for raw runtime UPDATE,
zero/positive transitions, repeated restocks, checkout cancellation, customer ownership, withdrawn visibility,
CSRF, injection negatives, composite identity and the two triggers together. Exit check 1 passed with demo-jun-keat
and the real demo seller's edit form; the badge and alerts page updated, opening marked the alert seen, and the
original sold-out stock was restored. Exit check 2's schema documentation is updated. The migrate image build,
migration/drift checks, required full Docker suite, host docs/packaging checks and scripts/check_docs.py passed;
unaltered command evidence is in .cache/phase3a/wishlist-full-suite.log and wishlist-exit.log (ignored). Existing
container-only Git-index skips remain visible and the host equivalents passed. No contract omissions or scope
deviations; only the visible displayed alerts page is marked seen, and HEAD is read-only. Fresh Claude Code review
and visual inspection remain pending. No push, PR or merge was performed.

24 October 2026 — Integration check on activity/events: recently viewed can repeat the detail product. Responsive browser testing found that only the clicked wishlist button changed. The final stacked branch now returns the saved state through HX-Trigger and updates every visible control for that product. Both save and remove were verified through both copies in the real browser; header regression checks cover the server event. This small integration fix is carried by activity/events.
