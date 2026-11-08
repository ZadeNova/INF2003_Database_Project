# reviews: Per-item reviews, rating summaries in one transaction, Bayesian ranking, take-downs

status: done
plan owner: Chee Long · implementer: Chee Long · reviewer: a fresh session, ideally the other agent · estimate: about 2
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
| Bayesian rating (decision a) | Score = (C × m + sum of scores) / (C + n), with m the platform mean and C the median review count per product, both computed at import into the `platform_stats` document (`olist-import`, which also fills `rating_summary.sum` and `bayesian`). Each write recomputes `bayesian` in the same transaction with a MongoDB update pipeline (`$set` with the formula), so the pipeline version of the formula lives here. Used for "Top rated" sorting in the catalogue and for seller ranking on shop pages. The benchmark computes the same formula in SQL on its copy (B2) |
| Display | Product detail shows the summary, a score histogram and the written reviews. It opens on the specification's own `latest_reviews` (the subset, so the page needs one MongoDB read); bare star ratings among them collapse into one line. `?all=1` (or any `?page=`) pages through every written review from the `reviews` collection, with the count of ratings without a comment. Operator and seller review lists keep every row. Imported reviews show the English machine translation, labelled, with a toggle to the Portuguese original; reviews of undelivered orders are marked as historical |
| Take-down | Operator console "Reviews": take a review down with a reason (hidden, excluded from summaries, recomputed in the same transaction) or restore it. The action is logged to `audit_log` (row id = the review's id as text), since no trigger can see MongoDB, through one narrow owner-owned `SECURITY DEFINER` function (search path pinned as in `accounts`): its table name is fixed to reviews, its action is only take-down or restore, the actor comes from `mercer.actor_id` rather than a parameter, and a reason is required. The runtime role gets `EXECUTE` on this function only and keeps no direct write on `audit_log`. PostgreSQL cannot verify the MongoDB change, so this path trusts the application. It uses `catalogue` decision c's order: PostgreSQL transaction open with the audit row, MongoDB transaction, then the PostgreSQL commit |
| Seller view | Seller centre "My reviews": a read-only list of reviews on the seller's own products, with a scoping test (PLAN.md section 2) |

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

## Decisions (all approved 21 October 2026)

| ID | Proposal | Why |
|---|---|---|
| a | Bayesian constants m and C fixed at import, stored once, and documented | Scores stay stable and reproducible; recomputing the platform mean on every write would change every product's score |
| b | Keep the running sum in `rating_summary`, not only the average | Edits and deletes then update exactly without rereading every review |
| c | Log review take-downs to the PostgreSQL `audit_log` from the app, through the narrow moderation function (amended 22 October, P3) | One audit trail for the operator, even though reviews live in MongoDB; the app cannot write arbitrary audit rows |

## Review notes

21 October 2026, cross-plan review (fresh session); findings applied: `platform_stats`, `sum` and `bayesian` come from the import; the Bayesian
update is a MongoDB update pipeline; take-down audit write order and text row id; the seller's read-only "My reviews"
page that PLAN.md section 2 promised.

22 October 2026, Phase 1B decision P3 (accepted by Chee Long): take-down audit rows go through the narrow
owner-owned moderation function instead of a direct app insert; no other contract change.


24 October 2026 — Implementation notes (Codex; reviewer: pending (Claude Code)). Built customer create/edit/delete
for delivered owned lines, snapshot MongoDB transactions with conflict retry, running summaries and latest five,
Bayesian shop scores, the new-product prior fix, a histogram with paginated English/Portuguese reviews and historical
labels, scoped seller reviews, and operator take-down/restore through the narrow owner-owned audit function.
Exit checks 1–3 passed against demo-joash and demo-operator through rendered Django requests; the temporary review
was deleted and the imported product document returned exactly to its original state. Exit check 4 passed through
the catalogue's existing Top rated search path in test_reviews.py. Exit check 5 passed: built migrate, applied the
migration, then ran the full Docker suite (unaltered output in .cache/phase3a/reviews-full-suite.log). The focused
review checks, Django system and migration drift checks, host docs/packaging checks and scripts/check_docs.py passed.
Local execution evidence is under .cache/phase3a (ignored), including reviews-exit.log. The existing container-only
Git-index skips remain visible in the suite output; the host equivalents ran successfully. No contract omissions
or scope deviations. Existing import precision is preserved explicitly in the update pipeline. Fresh Claude Code
review and visual inspection remain pending; no push, PR or merge was performed.

24 October 2026 — Review (Claude Code; session that wrote the Codex brief, not a fresh session), finding reviews R2.
Seller ratings and My reviews matched seller_id without an index. Added review_seller_date on seller_id ascending,
answered_at descending through idempotent mongo_setup and documented it in DATA_MODEL.md. The test was added first:
test_seller_rating_match_uses_seller_date_index_and_only_own_documents explains the seller_rating match with
executionStats, requires IXSCAN on the named index and checks that documents examined belong only to that seller.
It also runs mongo_setup twice and compares the actual seller rating count with the fixture. The regression failed
with a COLLSCAN on the previous implementation.
Rebuilt migrate and ran all of test_reviews.py successfully; the unaltered output is
.cache/phase3a-review/reviews-R2-tests.log. No hint is used in the execution-plan assertion.

24 October 2026 — Review (Claude Code; session that wrote the Codex brief, not a fresh session), finding reviews R4.
Removed the optional historical-label assertion. The real-database display test now uses an existing review on an
undelivered order or inserts one on a new paid order line if missing, then always checks the review's historical
state and the rendered product-page label. It selects the page containing that review. Parameterized runs cover
both retained fixture history and a fixture with that history removed, so the fallback is exercised too. The
missing-history variant failed before the fixture fallback was added; no application code change was needed.
Ran all of test_reviews.py successfully with both variants; the unaltered result is
.cache/phase3a-review/reviews-R4-tests.log.
