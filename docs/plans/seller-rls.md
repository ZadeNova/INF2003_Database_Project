# seller-rls: Row-level security for sellers

status: approved
plan owner: Erfan · implementer: Claude Code · reviewer: Opus 5.5 (plan reviewed 10 Nov; the build gets its own review) ·
phase 5 ([PLAN.md section 13](../../PLAN.md#13-phases)) · depends on: `checkout`, `accounts` (done) · backlog item #48
([improvements](improvements.md#batch-8-row-level-security-settled-last))

## Contract

**Goal.** While a seller-centre page runs, PostgreSQL itself confines the database session to that seller's rows, so a
missing `WHERE seller_id = …` in the application can no longer leak another seller's orders or edit another seller's
products. Today AGENTS.md rule 6 is kept by application filters and tests only; no policy exists. The honest wording for the
report: **tenant isolation for sellers, a second layer under the seller pages**, not "the database enforces all isolation".

**Demo.** Connected as the runtime role with a seller's setting, `SELECT * FROM orders_order` returns only that seller's
orders, and an `UPDATE` of another seller's product changes no row, with no filter in the statement. The same statements in a
customer or operator session (no setting) behave as today.

**Kept simple on purpose.** No new database role, no new table, no column-guard trigger, no middleware, no change to customer
or operator behaviour. The change is one migration, a few lines in the seller access mixin and three small edits to existing
code (listed below).

**Not covered, said plainly in the report.**
- **Customer sessions are not confined.** Customer A reading customer B's order is the classic marketplace flaw, and this
  feature does not address it; the application filters and tests do. It is the largest known limit (decision D6).
- The setting is applied only while a seller-centre view runs. Public pages a seller browses, and everything a seller's
  session does outside those views, run unconstrained, as today.
- The owner role (migrations, import, tests) bypasses policies by design.
- Policies limit rows, not columns: a seller session could still rewrite a column of its own rows with hand-written SQL. The
  money triggers catch changes to totals (once made SECURITY DEFINER, below); a dedicated seller role with column grants
  would close the rest.
- The cart, wishlist, restock-alert and customer-profile tables, `django_session` and the dashboard materialized views (which
  cannot carry policies) are not restricted, and the runtime role can call the refresh and audit functions.
- Foreign-key checks bypass policies, so an FK error versus a success reveals whether a hidden row exists. No table a seller
  can insert into references a restricted table, so nothing is exposed today.
- Locking reads (`FOR UPDATE`, `FOR SHARE`) hide rows that a plain `SELECT` shows, for example another seller's product.
  No seller path does this today.
- MongoDB has no per-row policies of this kind, so seller-scoped reviews stay application-enforced (a point for the SQL
  against NoSQL comparison).
- A session that can run arbitrary SQL could change its own setting; rule 1 (parameterised queries only) prevents that.

## Design

**Declaring the seller.** `AnySellerMixin.dispatch` (the base of every seller-centre view) sets the PostgreSQL setting
`mercer.seller_id` after it has found the seller, calls the view, renders the response, and resets the setting in a
`finally`. The name follows the existing `mercer.actor_id` audit setting, which is transaction-local; this one has to cover
reads outside a transaction, so it is session-level. Because the mixin is the only place that sets it, no ordering with other
middleware is needed and public pages are never affected. Details that matter: template responses render after `dispatch`
returns, so the mixin renders the response before it resets; the reset is `set_config('mercer.seller_id', '', false)`; and if
the reset itself fails (the database has gone), the error is swallowed and the connection is closed, so a stale value cannot
survive into a reused connection and the database-unavailable handling is not overwritten. If a worker is killed, its
connection dies with it; a health-check reconnect starts a session without the setting.

**Policies** (one migration; `ENABLE ROW LEVEL SECURITY`, not `FORCE`, so the owner bypasses). A helper `mercer_seller()`
returns `NULLIF(current_setting('mercer.seller_id', true), '')::bigint`, NULL when unset or empty, and every policy has the
same shape: *when the setting is unset the table behaves as before; when it is set, only the rows below.* One policy per
command, so a seller session can neither insert nor delete where only reading is allowed. **Rule: every table's SELECT policy
allows at least what its write policies allow**, because `INSERT … RETURNING` and `UPDATE … WHERE` also need the new or old
row to pass SELECT.

| Table | A seller session may |
|---|---|
| `orders_order` | read and update its own orders (`seller_id` equals the setting; `WITH CHECK` on update); not insert or delete |
| `orders_orderline` | read its own lines; nothing else |
| `orders_refund` | read the refunds of its own orders (`EXISTS` on `orders_order`, which is itself filtered); nothing else |
| `orders_checkout` | **nothing.** A checkout is shared by every seller in one basket, so its total, customer and idempotency key are other sellers' data |
| `orders_payment` | nothing |
| `catalogue_product` | read every product (the shop is public); insert, update and delete only its own (`WITH CHECK`) |
| `audit_log` | **read only** the rows of its own seller (`table_name = 'accounts_seller'` and `row_id` its id) and the rows whose `seller_id` (in `after`, else `before`) is its own; no writes. It carries customers' free-text cancellation reasons and every seller's price history, which one seller must not read. Writes come only from SECURITY DEFINER triggers and are unaffected. Droppable if its expression proves awkward |

SECURITY DEFINER functions are owner-owned and bypass the policies, so the audit triggers and the dashboard refresh functions
are unaffected. Customer and operator sessions never set the setting, so checkout, which writes across sellers, and
cancellation behave as today. The `purchasable_product` view is created `security_invoker`, but the product SELECT policy
allows everything, so for that view the policies change nothing.

## Step 0 survey (10 November), the plan review, and what they changed

Every seller-only page and service was read, and an independent Opus 5.5 review then tested the plan's PostgreSQL claims on a
scratch database. A seller session touches `orders_order`, `orders_orderline`, `orders_checkout`, `catalogue_product`, its
own `accounts_seller` and `accounts_user` rows, `audit_log` and `django_session`; it reads no payment, cart, wishlist or
customer-profile table.

- **The money triggers (the review corrected this).** `check_checkout_money()` and `check_checkout_refunds()` (the deferred
  constraint triggers on checkout, order, payment and refund) are not SECURITY DEFINER. Under a seller session the trigger
  cannot see the checkout, `IF NOT FOUND THEN CONTINUE` skips it, and the money check **passes silently**. On the scratch
  database a seller session's `UPDATE orders_order SET total = 999` committed, and was rejected once the functions were
  SECURITY DEFINER. They become SECURITY DEFINER with `ALTER FUNCTION` (which keeps the triggers and the revoked EXECUTE
  grants; the search path is already fixed and the owner role is not a superuser). The required test is therefore *a seller
  session's update of its own order total is rejected at commit*, run as the runtime role; "Mark shipped works" passes either
  way and proves nothing. General rule, written into DATA_MODEL: a function that runs with the caller's rights and reads a
  restricted table quietly stops checking.
- **Checkout is hidden, so three queries change.** (1) `SellerOrdersView` calls `select_related("checkout")`, an inner join
  that would drop every row, although its template shows no checkout column: remove it. (2) `change_order_status` joins
  checkout in its authorization query: make that a `LEFT JOIN`, which the customer branch still satisfies. (3) The same
  function locks the checkout row before the order, to match the deferred checks' lock order and avoid deadlocks: replace
  that statement with `lock_checkout_of_order(order_id)`, a SECURITY DEFINER function (`SET search_path = public, pg_temp`,
  schema-qualified names, `REVOKE … FROM PUBLIC`, `GRANT` to the runtime role) that locks the checkout of that order only if
  the order passes the same `mercer_seller()` test, and returns NULL otherwise (the caller raises a 404). With the setting
  unset it locks any checkout, as today.
- **Public pages read `orders_order` too.** `_present` in `reviews/queries.py` asks for the delivered status of each review's
  order on every product page, and would label every review of another shop "historical" for a seller whose setting is on.
  Because the setting is applied only inside seller-centre views, public pages are unaffected; this is the reason for
  setting it in the mixin and not in a middleware.
- **Left alone on purpose.** `alert_product_restock()` also runs as the invoking role (it reads `wishlist_item` and writes
  `restock_alert`); denying a seller those tables would silently stop customers' restock alerts, so the wishlist tables stay
  unrestricted until that function is made SECURITY DEFINER in a later step.
- **Confirmed by experiment:** the refund `EXISTS` policy sees only the seller's own orders, with no recursion; `FOR UPDATE`
  works on a seller's own orders; `WITH CHECK` blocks moving a row to another seller; the planned ship path (LEFT JOIN, the
  lock function, the SECURITY DEFINER triggers) works; the setting is read once per statement.
- **Corrections from the review kept as rules:** an index on `seller_id` is used only because the application keeps its own
  `seller_id` filter (the policy alone cannot use it), so there is no index test and the report says the policy relies on the
  application's filter for speed; Django's `save()` on an unchanged existing row falls back to an `INSERT`, so the demo and
  tests use raw SQL or `.update()`.

**Practices followed** (AWS Prescriptive Guidance, the AWS database blog, practitioner write-ups):
- The application never connects as the owner and the runtime role has no `BYPASSRLS` (already so by rule 5); a test asserts
  both. `FORCE` is not used, because the migrations, the import, the tests and the SECURITY DEFINER functions must bypass.
- `WITH CHECK` on every write policy, so a seller cannot move a row to another seller or insert one for another seller.
- The setting is read through one STABLE function in a sub-select (evaluated once per statement).
- A guard test compares an explicit map of table to expected policies with `pg_policies` (ordinary tables only, row security
  not forced) and fails when a table with a `seller_id` column is missing from the map.
- Row security stays a second layer: the application filters remain.
- **Deliberate deviations.** The guidance prefers a transaction-local setting and a fail-closed default. Django runs in
  autocommit with persistent connections and no pooler between it and PostgreSQL, so a transaction around every seller request
  would be a larger behaviour change than the set-and-reset above; and fail-closed needs a policy for every actor (D6), so the
  default is fail-open, with a test that every seller-centre view runs with the setting set.

## Decisions for Erfan

| # | Decision | Options | Recommendation (approved 10 Nov) |
|---|---|---|---|
| D1 | **Scope of this build** | (A) Seller sessions only. (B) Sellers and customers, fail-closed. (C) A dedicated seller database role with column grants | **A.** B touches the checkout code that writes across sellers; C needs a cluster role existing volumes lack |
| D2 | **How the setting travels** | A middleware; set and reset in the seller mixin; a transaction around each seller request; `SET ROLE` | **The seller mixin**, with `finally`, render-before-reset and close-on-failed-reset. No middleware, no dirty flag |
| D3 | **When the setting is missing** | Fail open or fail closed | **Open** for scope A, with the view sweep test |
| D4 | **Tests** | Policies as the raw runtime role; the real views and service under the policies; a view sweep | **All.** The owner bypasses policies, so ordinary tests prove nothing about them. A fixture switches the Django test connection to the runtime role for `transaction=True` tests (and restores the owner before the flush), so the real seller views and `change_order_status` run under the policies in the normal suite; the CI browser journeys add real traffic |
| D5 | **Benchmark** | Unaffected, or measured | **Unaffected** (the harness connects as the owner); no overhead measurement |
| D6 | **Customer sessions** | Confine them in this build; as a second stage; disclose and leave | **Disclose, leave**, framed as tenant isolation for sellers. It means a customer policy on every order, checkout, payment, cart and wishlist table and a restock-trigger change, the opposite of simple. Revisit after Batch 7 |
| D7 | **`audit_log` policy** | Include or disclose only | **Include** (one SELECT-only policy), droppable |

## Steps (small, with a short review after each)

0. **Survey and plan review**: done (above).
1. **Migration** (in the `orders` app, after the latest `catalogue` and `accounts` migrations): `mercer_seller()`, the policies,
   `ALTER FUNCTION … SECURITY DEFINER` for the two money functions and `lock_checkout_of_order`; reversible, grants unchanged.
   Tests as the raw runtime role: the demo statements (read, update, insert, delete across two sellers, an unfiltered query, an
   update that tries to change `seller_id`), **a seller's update of its own order total rejected at commit**, the lock function
   returning NULL for another seller's order, every row visible when the setting is unset, the `audit_log` policy, the
   role-attribute test and the guard test.
2. **Code**: the mixin (set, render, reset, close on failure) and the three edits above, with the runtime-role fixture and
   tests of the real seller views and of `change_order_status` under the policies.
3. **More tests**: the view sweep (every seller-centre view runs with the setting set), a failed reset closing the connection,
   and a concurrency test as the runtime role (a seller ships while a customer cancels, on sibling orders and on the same
   order).
4. **Docs**: DATA_MODEL (each policy, the caller-rights rule, locking reads, the `RETURNING` rule), README (what the owner
   bypasses), DECISIONS, PLAN.md section 14, the report's security paragraph.
5. **Checks**: the full suite and the browser journeys; one Opus 5.5 review of the build, focused on leakage, the owner bypass
   and connection reuse (it joins Batch 7's named focus areas).

**Time-box.** Build 11 to 13 November. **Go or no-go on 13 November:** if the full suite is not green, cut the feature, keep
this plan and the application filters, and disclose it. The freeze is 15 November.

## Review notes

10 November 2026, independent Opus 5.5 plan review, tested on a scratch PostgreSQL 18 database with the real money triggers.
Verdict: ready after named changes. Blocker: the money-trigger reasoning was backwards (the check passes silently, it does not
fail), so the test and the DATA_MODEL rule changed. Major: public pages read `orders_order` (fixed by setting the value in
the seller mixin), the test plan could not run the real service under the policies (runtime-role fixture), and the
`audit_log` leak was understated (policy added). Minor: the index test proved nothing and is dropped, the helper uses
`NULLIF`, the guard test uses an explicit map, extra tests added, small documentation rules. Nothing else in the plan was
found worse than stated.
