# accounts: Three roles, seller registration and approval, operator console, audit log

status: approved
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
| Seller status | Statuses `pending`, `approved`, `rejected`, `suspended` (the `CHECK` is in `olist-import`'s `0001`). A `BEFORE UPDATE … WHEN (OLD.status IS DISTINCT FROM NEW.status)` trigger, so other edits such as the shop name pass, allows only pending → approved or rejected, approved → suspended, suspended → approved, and rejects anything else. Suspended sellers' products drop out of the `purchasable_product` view (from `olist-import`), and their seller centre is read-only |
| Operator console | `/operator/` shell with a seller list filtered by status and approve, reject, suspend and reinstate actions, each with a reason. Product and review take-down pages are added later by `catalogue` and `reviews`. Operator accounts come only from `seed_demo` or `manage.py create_operator` (password from `.env`), never from a public form |
| Audit log (decision b) | Table `audit_log` (table name, row id as `text` so it can also hold a MongoDB id, action, actor user id, `before` and `after` as JSONB, reason, timestamp), written by triggers, append-only: the migration explicitly `REVOKE`s `UPDATE`, `DELETE` and `TRUNCATE` from the runtime role, which the default privileges would otherwise grant. The app sets the actor at the start of each transaction with `SET LOCAL mercer.actor_id = %s`; triggers read `NULLIF(current_setting('mercer.actor_id', true), '')::bigint`, because the setting reads as an empty string, not NULL, after an earlier `SET LOCAL` on the same connection. NULL means a system change (import, seed, `psql`). This plan adds the seller-status trigger; `catalogue` adds the price and stock trigger. Operator page `/operator/audit/` lists entries newest first with filters |
| Demo data | `seed_demo` (from `olist-import`) gets one pending seller application, so approval can be shown on camera |

**Out of scope:** the seller centre's product and order pages (`catalogue`, `checkout`); product and review take-downs
(`catalogue`, `reviews`); row-level security (`seller-rls`, Tier 2); login rate limiting (`redis`, Tier 2).

**Tests:** each role is refused every other role's pages (a parametrised matrix over all role-protected URLs); a pending,
rejected or suspended seller cannot reach the seller centre; the status trigger rejects every illegal transition and lets a shop-name edit through; an update with no actor set is audited with a NULL actor instead of failing; an
approval writes one audit row with the operator as actor and the correct before and after; the runtime role cannot
`UPDATE` or `DELETE` audit rows; registration and application forms reject bad input and keep CSRF.

**Exit check (the reviewer runs all of these)**
1. Register a customer, log in, land on the shop; log out.
2. Apply as a seller, log in, see "awaiting approval"; as the operator, approve it with a reason; the seller now reaches
   the seller centre; the audit page shows the change with the operator, the reason, and before and after.
3. As the operator, suspend the demo seller: their products leave the `purchasable_product` view, so the phase-1 product list hides them, and a
   direct `UPDATE` setting a suspended seller to `pending` fails in `psql`.
4. The full test suite passes in Docker.

## Decisions (all approved 21 October 2026)

| ID | Proposal | Why |
|---|---|---|
| a | One role per user: a seller who wants to buy uses a separate customer account | Matches the role field chosen in R7; mixing roles on one account doubles the permission cases for little demo value |
| b | One `audit_log` table filled by triggers, with the actor passed through `SET LOCAL` | The audit cannot be skipped by app code; it is a non-standard technique worth showing in the report; one table serves both seller and price/stock changes |
| c | A `rejected` status (in `olist-import`'s `0001`) | A pending application otherwise has nowhere to go but approved |
| d | Operators are never self-registered: `seed_demo` or a management command creates them, with the password from the git-ignored `.env` (never hardcoded) | Avoids a privilege-escalation path and a committed credential |

## Review notes

21 October 2026, cross-plan review (fresh session); findings applied: status triggers fire only on a real status change; actor read with `NULLIF`;
`audit_log` row id as text and an explicit `REVOKE`; `rejected` moved into the `0001` schema; the operator command named;
suspension checked through the `purchasable_product` view.
