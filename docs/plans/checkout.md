# checkout: Cart across sellers, split checkout, simulated payment, order lifecycle, cancellation

status: approved
plan owner: Erfan · implementer: Chee Long · reviewer: a fresh session, ideally the other agent · estimate: 2.5 to 3 days
· phase 2A (2 to 4 November) · depends on: `olist-import` (schema), `accounts` (roles, seller status, audit actor)

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
| Cart | One cart per customer; `UNIQUE (cart, product)`; add, change quantity, remove (HTMX). The cart page groups lines by seller with a subtotal and shipping fee per seller. Products that are inactive, delisted, or belong to a non-approved seller cannot be added, and are flagged at review if they became so |
| Shipping fee (decision b) | Each product carries a `freight` amount (its median historical freight in SGD, computed by `olist-import`); an order's freight is the sum over its lines, as in Olist |
| Checkout and payment (decision a) | One "Place order and pay" action in **one transaction**, raw SQL: lock the cart lines, then lock the products with `SELECT … FOR UPDATE` ordered by id (no deadlocks); re-check active, seller status, price and stock; insert the checkout, one order per seller (status `paid`), the order lines, and the payment row(s); decrement stock; empty the cart. Price, stock and freight are read only from PostgreSQL (AGENTS.md rule 2). Idempotency: `UNIQUE (customer_id, idempotency_key)`; a repeated submit returns the existing checkout; a changed cart fingerprint asks the customer to review again |
| Payment | Method picker (credit card with 1 to 12 instalments, boleto, voucher, debit card). One payment row per method used; the UI offers one method, tests cover several. No card numbers stored; if card fields are shown they are checked in the browser and discarded (at most the last four digits kept) |
| Money invariants (decision c) | Two deferred constraint triggers (`DEFERRABLE INITIALLY DEFERRED`), checked at commit on any insert, update or delete of payments, refunds, orders or checkouts: (1) a checkout's payments sum to its total, and its total equals the sum of its orders' totals; (2) its refunds sum to the totals of its cancelled orders |
| Order lifecycle | Statuses `placed`, `paid`, `shipped`, `delivered`, `cancelled`. A `BEFORE UPDATE` trigger allows only placed → paid or cancelled, paid → shipped or cancelled, shipped → delivered, and stamps the matching timestamp. Who may act is enforced in the app: the seller ships their own orders (seller centre "My orders"), the operator marks delivered (operator console "Orders"), the customer cancels their own. Every status change sets the audit actor (`accounts`) |
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

## Review notes

(empty until review)
