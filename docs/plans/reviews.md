# reviews: Per-item reviews, rating summaries in one transaction, Bayesian ranking, take-downs

status: draft
plan owner: Erfan · implementer: Chee Long · reviewer: a fresh session, ideally the other agent · estimate: about 2
days · phase 3A (9 to 13 November) · depends on: `catalogue`, `checkout`, `accounts`

**Assumes:** MongoDB `reviews` (unique `order_line_id`) and `product_specs` (`rating_summary`, `latest_reviews`) from
`olist-import`; order lines and the `delivered` status from `checkout`; the operator console from `accounts`.

## Contract

**Goal.** A customer reviews each item they received, once; ratings everywhere stay exactly consistent with the
reviews; products and sellers are ranked fairly even with few reviews.

**In scope**

| Area | Deliverable |
|---|---|
| Write rules | A customer may review an order line only if it is theirs and its order is `delivered` (checked in PostgreSQL first, AGENTS.md cross-store rule); one review per line (unique index); edit and delete their own |
| One transaction | Insert, edit or delete of a review updates, in one MongoDB multi-document transaction with retry on write conflict: the review, the product's `rating_summary` (count, sum, average, distribution) and its `latest_reviews` subset (five newest) |
| Bayesian rating (decision a) | Score = (C × m + sum of scores) / (C + n), with m the platform mean and C the median review count per product, both computed at import and stored in a `platform_stats` document. Stored in `rating_summary.bayesian`, updated in the same transaction. Used for "Top rated" sorting in the catalogue and for seller ranking on shop pages. The benchmark computes the same formula in SQL on its copy (B2) |
| Display | Product detail shows the summary, a score histogram and paginated reviews. Imported reviews show the English machine translation, labelled, with a toggle to the Portuguese original; reviews of undelivered orders are marked as historical |
| Take-down | Operator console "Reviews": take a review down with a reason (hidden, excluded from summaries, recomputed in the same transaction) or restore it; the action is logged to `audit_log` from the app, since the trigger cannot see MongoDB |

**Out of scope:** seller replies and review moderation queues (Tier 2); full-text search on reviews (`search`, Tier 2).

**Tests:** a review of an undelivered, cancelled or someone else's line is refused; a second review for the same line is
refused by the unique index; after each insert, edit, delete and take-down, the summary and subset equal a full
recomputation; two concurrent reviews on one product both land and the count is exact (write-conflict retry); the
Bayesian score matches a hand calculation; injection negatives on review parameters.

**Exit check**
1. As the demo customer, review a line from a delivered order: the product page shows it at once, the count and average
   change correctly, and the latest-five list updates.
2. Edit and delete it; the summary returns to its previous values exactly.
3. As the operator, take a review down; it disappears and the summary excludes it.
4. "Top rated" sorting puts a product with many good reviews above one with a single five-star review.
5. The full test suite passes in Docker.

## Decisions (for the plan owner)

| ID | Proposal | Why |
|---|---|---|
| a | Bayesian constants m and C fixed at import, stored once, and documented | Scores stay stable and reproducible; recomputing the platform mean on every write would change every product's score |
| b | Keep the running sum in `rating_summary`, not only the average | Edits and deletes then update exactly without rereading every review |
| c | Log review take-downs to the PostgreSQL `audit_log` from the app | One audit trail for the operator, even though reviews live in MongoDB |

## Review notes

(empty until review)
