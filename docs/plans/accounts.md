# accounts: Three roles, seller registration and approval, operator console, audit log

status: draft
plan owner: Erfan · implementer: Chee Long · reviewer: a fresh session, ideally the other agent · estimate: 1.5 to 2 days
· phase 1B (31 October to 1 November) · depends on: `olist-import` (custom user model with `role`, seller table)

## Contract

**Goal.** Customers, sellers and the operator each get their own entry point and only their own pages. A new seller
applies, waits for approval and is approved or rejected by the operator. Every status change is audited in the database.

**In scope**

| Area | Deliverable |
|---|---|
| Roles | One role per user (`customer`, `seller`, `operator`; decision a). Access mixins `CustomerRequired`, `SellerRequired` (approved sellers only, with a pending/suspended page otherwise) and `OperatorRequired`, extending the existing `HtmxLoginRequiredMixin`. After login, each role lands on its own home: the shop, the seller centre, the operator console. Navigation shows only the current role's links |
| Customer registration | The existing `/register/` creates a `customer` user and customer profile (zip prefix, city and state optional) |
| Seller application | `/sell/apply/` creates a `seller` user and seller row with status `pending` (shop name, city, state, zip prefix). A pending seller can log in and sees an "awaiting approval" page and nothing else |
| Seller status | Statuses `pending`, `approved`, `rejected`, `suspended` (`CHECK`). A `BEFORE UPDATE` trigger allows only pending → approved or rejected, approved → suspended, suspended → approved, and rejects anything else. Suspended sellers' products are hidden from the shop and their seller centre is read-only (the catalogue and checkout honour this) |
| Operator console | `/operator/` shell with a seller list filtered by status and approve, reject, suspend and reinstate actions, each with a reason. Product and review take-down pages are added later by `catalogue` and `reviews`. Operator accounts come only from `seed_demo` or a management command, never from a public form |
| Audit log (decision b) | Table `audit_log` (table name, row id, action, actor user id, `before` and `after` as JSONB, reason, timestamp), written by triggers, append-only (the runtime role has `INSERT` and `SELECT` only). The app sets the actor per transaction with `SET LOCAL mercer.actor_id = %s`, and the trigger reads `current_setting('mercer.actor_id', true)`. This plan adds the seller-status trigger; `catalogue` adds the price and stock trigger. Operator page `/operator/audit/` lists entries newest first with filters |
| Demo data | `seed_demo` (from `olist-import`) gets one pending seller application, so approval can be shown on camera |

**Out of scope:** the seller centre's product and order pages (`catalogue`, `checkout`); product and review take-downs
(`catalogue`, `reviews`); row-level security (`seller-rls`, Tier 2); login rate limiting (`redis`, Tier 2).

**Tests:** each role is refused every other role's pages (a parametrised matrix over all role-protected URLs); a pending,
rejected or suspended seller cannot reach the seller centre; the status trigger rejects every illegal transition; an
approval writes one audit row with the operator as actor and the correct before and after; the runtime role cannot
`UPDATE` or `DELETE` audit rows; registration and application forms reject bad input and keep CSRF.

**Exit check (the reviewer runs all of these)**
1. Register a customer, log in, land on the shop; log out.
2. Apply as a seller, log in, see "awaiting approval"; as the operator, approve it with a reason; the seller now reaches
   the seller centre; the audit page shows the change with the operator, the reason, and before and after.
3. As the operator, suspend the demo seller: their products disappear from the shop (once `catalogue` exists) and a
   direct `UPDATE` setting a suspended seller to `pending` fails in `psql`.
4. The full test suite passes in Docker.

## Decisions (for the plan owner)

| ID | Proposal | Why |
|---|---|---|
| a | One role per user: a seller who wants to buy uses a separate customer account | Matches the role field chosen in R7; mixing roles on one account doubles the permission cases for little demo value |
| b | One `audit_log` table filled by triggers, with the actor passed through `SET LOCAL` | The audit cannot be skipped by app code; it is a non-standard technique worth showing in the report; one table serves both seller and price/stock changes |
| c | Add a `rejected` status | A pending application otherwise has nowhere to go but approved |
| d | Operators are never self-registered | Avoids a privilege-escalation path |

## Review notes

(empty until review)
