# seller-rls: Row-level security for sellers

status: draft
plan owner: Erfan · implementer: Claude Code · reviewer: Opus 5.5 session on this plan, then on the build · phase 5
([PLAN.md section 13](../../PLAN.md#13-phases)) · depends on: `checkout`, `accounts` (done) · backlog item #48
([improvements](improvements.md#batch-8-row-level-security-settled-last))

## Contract

**Goal.** PostgreSQL itself confines a seller's session to that seller's own rows, so a missing `WHERE seller_id = …` in the
application can no longer leak another seller's orders or edit another seller's products. Today AGENTS.md rule 6 is kept by
application filters and tests only; no policy exists.

**Demo.** Connected as a seller's session, `SELECT * FROM orders_order` returns only that seller's orders, and an `UPDATE` of
another seller's product changes no row, with no filter in the statement. The same statements in a customer or operator
session behave as today.

**Kept simple on purpose.** No new database role, no new table, no column-guard trigger, no change to customer or operator
behaviour. The change is one migration, one small middleware and three small edits to existing code (listed below).

**Not covered, said plainly in the report.**
- **Customer sessions are not confined.** Customer A reading customer B's order is the classic marketplace flaw, and this
  feature does not address it; the application filters and tests do. It is the largest known limit (decision D6).
- The owner role (migrations, import, tests) bypasses policies by design.
- Policies limit rows, not columns: a seller session could still rewrite a column of its own rows with hand-written SQL.
  The money triggers catch changes to totals; a dedicated seller role with column grants would close the rest.
- `audit_log` (no seller column), the cart, wishlist, restock-alert and customer-profile tables, and the dashboard
  materialized views (which cannot carry policies) are not restricted.
- MongoDB has no per-row policies of this kind, so seller-scoped reviews stay application-enforced (a point for the SQL
  against NoSQL comparison).
- A session that can run arbitrary SQL could change its own setting; rule 1 (parameterised queries only) prevents that.

## Design

**Declaring the seller.** A middleware looks up the logged-in seller and sets the PostgreSQL setting `mercer.seller_id` on
the request's connection, clearing it in a `finally`. The name follows the existing `mercer.actor_id` audit setting, which is
transaction-local; this one has to cover reads outside a transaction, so it is session-level. Django keeps connections for 60
seconds (`CONN_MAX_AGE`), so a stale value must never reach the next request: any request that follows a seller request on
the same connection resets the setting first (the connection object carries a "dirty" flag, so ordinary requests pay no extra
round trip). The middleware also hands the seller to the access mixin, which saves that mixin its own lookup.

**Policies** (one migration; `ENABLE ROW LEVEL SECURITY`, not `FORCE`, so the owner bypasses). A helper `mercer_seller()`
returns the setting as a bigint, or NULL when unset, and every policy has the same shape: *when the setting is unset the table
behaves as before; when it is set, only the rows below.* One policy per command, so a seller session can neither insert nor
delete where only reading is allowed.

| Table | A seller session may |
|---|---|
| `orders_order` | read and update its own orders (`seller_id` equals the setting; `WITH CHECK` on update); not insert or delete |
| `orders_orderline` | read its own lines; nothing else |
| `orders_refund` | read the refunds of its own orders (`EXISTS` on `orders_order`, which is itself filtered); nothing else |
| `orders_checkout` | **nothing.** A checkout is shared by every seller in one basket, so its total, customer and idempotency key are other sellers' data |
| `orders_payment` | nothing |
| `catalogue_product` | read every product (the shop is public); insert, update and delete only its own (`WITH CHECK`) |

SECURITY DEFINER functions are owner-owned and bypass the policies, so the audit triggers and the dashboard refresh
functions are unaffected. Foreign-key checks bypass them too. Customer and operator sessions never set the setting, so
checkout, which writes across sellers, and cancellation behave as today.

## Step 0 survey (10 November) and what it changed

Every seller-only page and service was read: the seller centre and status pages, product list, edit and deactivate
(`save_product`, `deactivate_product`), My orders and Mark shipped (`change_order_status`), Insights, My reviews (MongoDB only)
and what runs on every request (the navigation and wishlist context processors). A seller session touches `orders_order`,
`orders_orderline`, `orders_checkout`, `catalogue_product`, its own `accounts_seller` and `accounts_user` rows, `audit_log`
and `django_session`; it reads no payment, cart, wishlist or customer-profile table.

- **The money triggers.** `check_checkout_money()` and `check_checkout_refunds()` (the deferred constraint triggers on
  checkout, order, payment and refund) are not SECURITY DEFINER and sum payments, orders and refunds as the invoking role. A
  seller session would show them one order and no payments, so Mark shipped would fail the money check. They become SECURITY
  DEFINER, like the audit triggers (the search path is already fixed). They are the money-critical triggers, so this gets its
  own test and the existing money tests rerun.
- **Checkout is hidden, so three queries change.** (1) `SellerOrdersView` calls `select_related("checkout")`, an inner join
  that would drop every row, although its template shows no checkout column: remove it. (2) `change_order_status` joins
  checkout in its authorization query: make that a `LEFT JOIN`, which the customer branch still satisfies. (3) The same
  function locks the checkout row before the order, to match the deferred checks' lock order and avoid deadlocks: replace
  that statement with `lock_checkout_of_order(order_id)`, a small SECURITY DEFINER function that locks the checkout of that
  order only if the order is visible under the same setting, so a seller session cannot lock another seller's checkout.
- **Left alone on purpose.** `alert_product_restock()` also runs as the invoking role (it reads `wishlist_item` and writes
  `restock_alert`); denying a seller those tables would silently stop customers' restock alerts, so the wishlist tables stay
  unrestricted until that function is made SECURITY DEFINER in a later step.
- **Already right.** `purchasable_product` is created `WITH (security_invoker = true)`, so it respects the product policies.
  The order status and timestamp triggers use only `OLD` and `NEW`. The audit triggers are SECURITY DEFINER.

**Practices followed** (AWS Prescriptive Guidance, the AWS database blog, practitioner write-ups):
- The application never connects as the owner and the runtime role has no `BYPASSRLS` (already so by rule 5); a test asserts
  both and that row security is on for every table above. `FORCE` is not used, because the migrations, the import, the tests
  and the SECURITY DEFINER functions must bypass.
- `WITH CHECK` on every write policy, so a seller cannot move a row to another seller or insert one for another seller.
- The setting is read through one STABLE function in a sub-select (evaluated once per statement), `seller_id` is indexed, and
  a test confirms the seller order list still uses its index.
- A guard test lists every table with a `seller_id` column and fails if one has no policy.
- Row security stays a second layer: the application filters remain.
- **Deliberate deviations.** The guidance prefers a transaction-local setting and a fail-closed default. Django runs in
  autocommit with persistent connections and no pooler between it and PostgreSQL, so a transaction around every seller request
  would be a larger behaviour change than the per-request set-and-reset above; and fail-closed needs a policy for every actor
  (D6), so the default here is fail-open, with a test that every seller-only view runs with the setting set.

## Decisions for Erfan

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | **Scope of this build** | (A) Seller sessions only. (B) Sellers and customers, fail-closed. (C) A dedicated seller database role with column grants | **A.** B touches the checkout code that writes across sellers; C needs a cluster role existing volumes lack |
| D2 | **How the setting travels** | A session setting set per request and reset on connection reuse; a transaction around each seller request; `SET ROLE` | **Session setting** (above) |
| D3 | **When the setting is missing** | Fail open or fail closed | **Open** for scope A, with the view sweep test |
| D4 | **Tests** | Policies as the real runtime role (the existing `runtime_connection()` helper) plus a view sweep | **Both.** The owner bypasses policies, so ordinary tests prove nothing about them; the CI browser journeys drive the runtime `web` service and exercise the policies with real seller traffic |
| D5 | **Benchmark** | Unaffected, or measured | **Unaffected** (the harness connects as the owner); a policy-overhead measurement only if time allows |
| D6 | **Customer sessions** | Confine them in this build; build them as a second stage if the first is green; disclose and leave | **Disclose, leave.** It is the largest limit, but it means a customer policy on every order, checkout, payment, cart and wishlist table and a restock-trigger change, which is the opposite of simple. Revisit after Batch 7 |

## Steps (small, with a short review after each)

0. **Survey**: done (above).
1. **Migration**: `mercer_seller()`, the policies, the two money functions and `lock_checkout_of_order`; reversible, grants
   unchanged; DATA_MODEL documents each policy.
2. **Code edits**: the three listed above, and the middleware (set, reset, tell the mixin) with tests for leakage across
   requests on one connection.
3. **Tests**: as the runtime role, the demo statements (read, update, insert, delete across two sellers, an unfiltered
   query, an update that tries to change `seller_id`), Mark shipped through the real service, the view sweep, the guard
   test, the role-attribute test and the index test; the order, checkout, money and seller test modules unchanged.
4. **Docs**: DATA_MODEL, README (what the owner bypasses), DECISIONS, PLAN.md section 14, the report's security paragraph.
5. **Checks**: the full suite and the browser journeys; one Opus 5.5 review of the build, focused on leakage, the owner
   bypass and connection reuse (it joins Batch 7's named focus areas).

**Time-box.** Build 11 to 13 November. **Go or no-go on 13 November:** if the full suite is not green, cut the feature, keep
this plan and the application filters, and disclose it. The freeze is 15 November.

## Review notes

Not reviewed yet.
