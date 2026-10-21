# wishlist: Wishlist and restock alerts

status: draft
plan owner: Erfan · implementer: Chee Long · reviewer: a fresh session · estimate: about 1 day · phase 3A (9 to 13
November) · depends on: `olist-import`, `catalogue` (product pages), `checkout` (cancellation restocks)

**Assumes:** product `stock` in PostgreSQL changes only through seller edits (`catalogue`) and checkout or cancellation
(`checkout`); the customer role from `accounts`.

## Contract

**Goal.** A customer saves products, including sold-out ones, and is told inside the app when a saved product comes
back in stock, by a database trigger that no code path can skip.

**In scope**

| Area | Deliverable |
|---|---|
| Wishlist | `wishlist_item` (customer, product, added_at) with a composite primary key (the many-to-many table). Add and remove buttons (HTMX) on product cards and detail; a wishlist page showing stock status |
| Restock alerts | `restock_alert` (customer, product, created_at, seen_at). An `AFTER UPDATE OF stock` trigger on product, when stock goes from 0 to above 0, inserts one alert per wishlisting customer with `INSERT … SELECT … ON CONFLICT DO NOTHING` |
| No duplicates (decision a) | A partial unique index on `restock_alert (customer, product) WHERE seen_at IS NULL`, so a product restocked twice before the customer looks produces one unseen alert |
| Display | A header badge with the unseen count; an alerts page; opening it marks alerts seen. Alerts for products that are now inactive, taken down or from a suspended seller are hidden |

**Out of scope:** email or push notifications (decision b); alerts for price drops.

**Tests:** stock 0 → 5 creates one alert per wishlisting customer; 5 → 6 creates none; 0 → 5 → 0 → 5 before viewing
leaves one unseen alert; a cancellation that restocks fires the alert; a customer sees only their own wishlist and
alerts; the trigger fires for a raw `UPDATE` in `psql`, not only through the app.

**Exit check**
1. As the demo customer, wishlist a sold-out product; as its seller, restock it; the customer's badge shows 1 and the
   alerts page lists it.
2. The trigger and partial index appear in `docs/DATA_MODEL.md`; the full test suite passes in Docker.

## Decisions (for the plan owner)

| ID | Proposal | Why |
|---|---|---|
| a | Partial unique index to stop duplicate unseen alerts | A clean, non-standard constraint worth naming in the report |
| b | In-app alerts only | No mail server in a local project; the database behaviour is what is graded |

## Review notes

(empty until review)
