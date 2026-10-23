# checkout: Cart across sellers, split checkout, simulated payment, order lifecycle, cancellation

status: done
plan owner: Chee Long · implementer: Chee Long · reviewer: a fresh session, ideally the other agent · estimate: 2.5 to 3 days
· phase 2A (dates in PLAN.md section 13) · depends on: `olist-import` (schema), `accounts` (roles, seller status, audit actor)

## Contract

**Goal.** A customer fills one cart from several sellers and pays once; the database creates one order per seller,
keeps stock and money exactly right under concurrency, and enforces the order lifecycle. Each seller ships their own
order, the operator delivers it, and a customer can cancel before shipping with stock and money returned.

**Starting point.** The old baseline's cart and checkout services (`cart/services.py`, `orders/services.py` in git
history before `olist-import`) already lock rows in id order, replay a repeated submit by idempotency key, and detect a
cart that changed between review and submit with a fingerprint. Port those patterns to the new schema; do not copy the
shoe-specific code.

**In scope**

| Area | Deliverable |
|---|---|
| Cart | One cart per customer; `UNIQUE (cart, product)`; add, change quantity, remove (HTMX). The cart page groups lines by seller with a subtotal and shipping fee per seller. Only products in the `purchasable_product` view (from `olist-import`: active, not taken down, approved seller) can be added; lines that left the view are flagged at review and refused at checkout. `catalogue`'s take-down flag works here automatically through the view |
| Shipping fee (decision b) | Each product carries a `freight` amount (its median historical freight in SGD, computed by `olist-import`); an order's freight is the sum over its lines, as in Olist |
| Checkout and payment (decision a) | One "Place order and pay" action in **one transaction**, raw SQL: lock the cart lines, then lock the products with `SELECT … FOR UPDATE` ordered by id (no deadlocks); re-check active, seller status, price and stock; insert the checkout, one order per seller (status `paid`), the order lines, and the payment row(s); decrement stock; empty the cart. Price, stock and freight are read only from PostgreSQL (AGENTS.md rule 2). Idempotency: `UNIQUE (customer_id, idempotency_key)`, where `customer_id` is the user's id; a repeated submit returns the existing checkout; a changed cart fingerprint asks the customer to review again |
| Payment | Method picker (credit card with 1 to 12 instalments, boleto, voucher, debit card). One payment row per method used (a row means money received; there is no payment status); the UI offers one method, tests cover several. No card numbers stored; if card fields are shown they are checked in the browser and discarded (at most the last four digits kept) |
| Money invariants (decision c) | Two deferred constraint triggers (`DEFERRABLE INITIALLY DEFERRED`), checked at commit on any insert, update or delete of payments, refunds, orders or checkouts: (1) a checkout's payments sum to its total, and its total equals the sum of its orders' totals; (2) its refunds sum to the totals of its cancelled orders. The importer disables these triggers while loading and checks the same invariants with queries (`olist-import` decision o); here they guard every app write |
| Order lifecycle | Statuses `placed`, `paid`, `shipped`, `delivered`, `cancelled`. A `BEFORE UPDATE … WHEN (OLD.status IS DISTINCT FROM NEW.status)` trigger allows only placed → paid or cancelled, paid → shipped or cancelled, shipped → delivered, and stamps `paid_at`, `shipped_at`, `delivered_at` or `cancelled_at`. This plan also owns an order-status audit trigger writing each change to `audit_log`; its function follows the shared audit boundary in `accounts` (`SECURITY DEFINER`, owned by the migration owner, schema-qualified, `search_path` pinned to `public, pg_temp`, no runtime direct writes to `audit_log`). Who may act is enforced in the app: the seller ships their own orders (seller centre "My orders"), the operator marks delivered (operator console "Orders"), the customer cancels their own. Every transaction here sets the audit actor and reason first (bound transaction-local settings, `accounts`) |
| Cancellation | Allowed while `placed` or `paid`. One transaction: lock the order `FOR UPDATE`, set `cancelled` (the trigger rejects it after `shipped`), return each line's quantity to stock, insert a `refund` row (order, checkout, amount = order total, reason, time; `UNIQUE (order_id)`) |
| Pages | Customer: cart, review and pay, order history (checkouts with their orders and statuses), order detail, cancel. Seller centre: own orders with "mark shipped". Operator console: all orders with "mark delivered" |
| Seller scoping | Every seller and customer query filters by the logged-in user; tests prove one seller cannot see or ship another seller's order and one customer cannot see or cancel another's |

**Out of scope:** reviews (`reviews`); the wishlist restock alert fired by cancellation restocks (`wishlist` adds the
trigger); partial cancellation of single lines; real payment gateways; vouchers and discounts.

**Tests:** checkout of a three-seller cart creates one checkout, three orders and correct lines, totals and payments;
a repeated submit with the same key creates nothing new; a changed cart is refused at submit; insufficient stock rolls
everything back; **concurrency**: 20 threads on separate connections race for the last 5 units and exactly 5 succeed with
stock ending at 0 (port the old real-thread tests); each deferred invariant rejects a commit that breaks it; every illegal
status transition is rejected; cancelling a shipped order fails; cancellation restores stock and writes the refund;
role and scoping negatives; SQL-injection negatives on every raw-SQL path.

**Exit check (the reviewer runs all of these)**
1. As the demo customer, buy from three sellers in one checkout: one checkout, three orders, payments equal the total.
2. As the demo seller, ship your order; as the operator, deliver it; the customer sees each status change.
3. Cancel another order before shipping: stock returns, a refund row appears, the invariants still hold.
4. Submitting the same checkout twice (resend the form) creates one checkout.
5. The concurrency test passes ten times in a row; the full suite passes in Docker.

## Decisions (all approved 21 October 2026)

| ID | Proposal | Why |
|---|---|---|
| a | One-step "Place order and pay": checkout, orders and payments in a single transaction; new orders start as `paid` | No unpaid orders to expire or clean up; the deferred payment check runs on every checkout. `placed` remains for imported history |
| b | Shipping fee from each product's median historical freight (computed at import) | Realistic, consistent with Olist's per-line freight, no invented rate. Needs one column added in `olist-import` |
| c | Refund invariant: refunds equal cancelled orders' totals. `olist-import` adds a refund row for each imported cancelled order that has payments, flagged as imported | Keeps the books balanced for every checkout, old and new, so the invariant can be a hard constraint |
| d | Cancellation cancels a whole order (one seller's order), not single lines | As on Shopee, where a shop order is cancelled as a whole before shipping; per-item handling there is a post-delivery return, which is out of scope |

**Phase 2 amendments (approved by Chee Long, 22 October 2026)**, settling questions the contract left open; see
[DECISIONS](../DECISIONS.md#phase-2-plan-amendments-22-october-2026):

| ID | Decision | Why |
|---|---|---|
| e | New purchases charge freight **per unit**: line freight = `product.freight` × quantity; an order's freight is the sum of its lines. Imported lines keep their stored freight | Olist charges `freight_value` per item. `product.freight` equals the per-unit median for 90.3% of products; the rest (from multi-unit lines, 6.6% of lines) are slightly high, documented rather than regenerated now. Settles the review note below |
| f | New orders' `estimated_delivery` = placed time + the longest `lead_time_days` among that order's products + 15 days | The column is required. Olist's own estimates have a 23.3-day median (18 to 28 days for the middle half); generated lead times have an 8-day median, so this lands near Olist's typical estimate |
| g | The review fingerprint covers each line's product, quantity, unit price and freight, sorted; the idempotency key is created when the review page renders and submitted with the pay form | Ports the old fingerprint/replay pattern, but includes price and freight so a customer never pays an amount they did not review |
| h | Benchmark cases B3/B6 are not built in this workstream | `benchmark` owns them in its separate bench databases ("not the full app checkout"); PLAN.md section 13 only aligns their timing with checkout |

## Review notes

22 October 2026, follow-up from the independent `olist-import` code review: confirm whether the shipping fee on
Product is per collapsed line or per unit before implementing new checkout charges. The current cleaner takes
the median collapsed historical line freight, while Product.price is per item. Preserve imported historical
line freight and exact checkout totals; document and test the chosen new-purchase quantity rule here.

21 October 2026, cross-plan review (fresh session); findings applied: cart and checkout use the `purchasable_product` view; the importer's trigger
handling; status triggers fire only on a real change, with the named timestamps; an order-status audit trigger owned
here; the actor set at the start of each transaction; no payment status.

22 October 2026, Phase 1B decision P3 (accepted by Chee Long): the order-status audit trigger follows the shared
owner-owned audit boundary defined in `accounts`; no other contract change.

22 October 2026, Phase 2 amendments e–h approved by Chee Long before implementation (freight per unit, estimated
delivery, fingerprint contents, benchmark scope); the freight follow-up note above is resolved by e.


23 October 2026, implementation self-check complete; independent Claude Code review pending. The additive orders
migration, ORM cart edits, parameterised split checkout and scoped lifecycle actions implement the approved contract
and amendments e–h. Full-data browser checks used the demo customer, seller and operator: a three-shop purchase,
shipping and delivery, customer cancellation with stock/refund reconciliation, and replay of the original review key
and digest all passed. Desktop and 375px checks covered cart, review, purchase, history, order, seller and operator
pages; wide management tables keep their horizontal scroll inside the page.

Migration drift, the full Docker suite (including the required repeated real-thread race), analytics tests, host
Git-index/packaging tests and documentation checks passed. The application image lacks Git, so its staged-index
checks skip there; the separate host run executes them. Raw command logs, browser screenshots and generated full-data
reconciliation are retained in the isolated worktree's local handoff evidence. No benchmark cases were added.
The remaining owner confirmations are checkout-i1 through checkout-i9 in [DECISIONS](../DECISIONS.md#checkout-implementation).
Integration must retain both workstreams' separate navigation/audit lookup blocks, the cart include in product detail,
and each appended CSS block. PLAN.md marks checkout review; this plan stays in-progress until independent review.


23 October 2026, integration self-check: order-audit test assertions are scoped to orders_order, with a real seller
status transition proving unrelated audit events can coexist. Affected checkout modules were rerun after this
assertion-only change; the orchestrator's independent final suite covers the resulting branch. Shared seed/audit-page
integration decisions are recorded alongside the existing cart and lookup decisions.

23 October 2026, independent Claude Code review of `5e65e3b` (fresh session): **APPROVE with two Should-fix doc
items for the fix round; no blockers.** Build, migration drift check (no changes), the full Docker suite (500 passed,
4 git-index skips), the concurrency module twice (20 race runs), host Git-index/packaging tests, analytics tests and
`check_docs.py` passed. A disposable project's fresh full import and `verify_olist` passed, with the deferred
invariants holding for every imported checkout. Exit checks 1–4 passed over HTTP against the full-data app (three
shops, freight × quantity, delivery estimate, replay, ship/deliver/audit, cancel with stock/refund); runtime-role
probes for audit writes, trigger tampering, illegal transitions and deferred money breaks were all rejected.
**CK1 (Should fix):** checkout-i10/i11 record catalogue code absent from this branch; move them to the integration
change. **CK2 (Should fix):** add Cart/CartLine to the main ER diagram and move the orders 0002 text into the
tables/triggers sections of DATA_MODEL. **Optional:** CK3 server-side cap on the cancel reason; CK4 per-unit shipping
label on the review page; CK5 move the README section beside the other feature sections. checkout-i1–i9 approvable as
written. Full report: the review chat.

23 October 2026, fix round (Claude Code, at Chee Long's request): CK1 removed checkout-i10/i11, which describe
catalogue code, for the integration change to record; CK2 added Cart and CartLine to the main ER diagram and tables,
moved the trigger and invariant text into "View, triggers and privileges" and the 3NF section, and removed the
appended section; CK3 refuses cancel reasons over 1000 characters in the service (test added); CK4 makes per-unit and
total shipping explicit on the review page; CK5 moved the README section above "Regenerate the data".

23 October 2026, Phase 2 checkpoint on `main` (Claude Code, at Chee Long's request), against the full-data `mercer`
database through the running web service (runtime role): the demo customer bought from three sellers in one checkout
(one checkout, three paid orders, payments = total = 278.25; stock fell by one each, every change audited with the
buyer and a reason; resending the pay form created nothing); the demo seller could not ship another shop's order,
shipped its own, and the operator delivered it, with the customer seeing Delivered and the audit trail recording both;
faceted category search with a price range rendered; the demo seller created a product with an uploaded photo, saw
it on the detail page and deactivated it (it then left the shop). 20 of 20 steps passed. Merged: amendments PR #8,
checkout PR #9, catalogue PR #10 (combined suite 566 passed, 4 skipped; both CI jobs green on the combined code).
Checkout is done: every exit check has passed, alone and combined with catalogue.

23 October 2026: Chee Long confirmed checkout-i1 through checkout-i9 as recommended by both reviews; see
[DECISIONS](../DECISIONS.md).
