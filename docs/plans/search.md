# search: Full-text search on review text, MongoDB text index against PostgreSQL tsvector (benchmark B7)

status: draft
plan owner: Erfan · implementer: Claude Code · reviewer: Opus 5.5 (plan, then build) · phase 5
([PLAN.md section 13](../../PLAN.md#13-phases)) · depends on: `reviews`, `benchmark` (done) · backlog item #71
([improvements](improvements.md#batch-6b-full-text-search-on-review-text)) · **time-box: built and green by the end of 12 November,
otherwise cut and listed as future work**

## Contract

**Goal.** Customers, sellers and the operator can search the written text of reviews, and the same search is measured on both
engines. It is the one feature in the project that is text retrieval rather than aggregation, so it is the second
"same feature on both engines" comparison for the NoSQL half (the first is B2). Reviews live only in MongoDB (AGENTS.md), so
the application side uses a MongoDB text index; PostgreSQL gets a `tsvector` with a GIN index **only in the isolated
benchmark databases**, as B7. No SQL review table is added to the application.

**Corpus (checked on the dev data).** About 100,000 reviews, of which about 43,600 carry written English text (title or
comment, machine-translated from Portuguese, about 70 characters on average). It is small, so both engines will answer an
indexed query quickly; the value of B7 is the plans, the index cost and the semantics, not a dramatic speed gap, and the
report must say so.

**Application behaviour.**
- A search box on the review lists that already exist: the product's full list (`?all=1`), the seller's My reviews and the
  operator's Reviews. One shared change in `review_page`, so all three behave the same and keep their own scope (a product, a
  seller, everything) and their own visibility rule (the operator also sees hidden reviews, the others do not).
- **Semantics: every word must appear** (an AND of the words, stemmed, case-insensitive), so "late delivery" finds reviews
  containing both. The user's text is reduced to plain words (quotes, `-`, `$` and operators removed, at most 8 words of at most
  30 characters) and sent to MongoDB as quoted terms, which MongoDB combines with AND. The query is a bound value, never part of
  an operator (AGENTS.md rule 1), with an injection negative test.
- Results are in the usual newest-first order, paginated by 10, with the match count, as `review_page` does today.
- English only (`title_en`, `text_en`). The Portuguese originals are not searched, and the page says the text is machine-translated, as
  it already does.

**Benchmark B7** (a new workload; the existing ones are untouched). The measured operation is exactly what the page does: the
total match count plus the 10 newest visible matches (`review id`, `answered_at`), for a fixed set of queries chosen before any run:
a rare word, a medium-frequency word, a common word, two words that must both appear, and a phrase. Variants:

| Variant | Engine | What it is |
|---|---|---|
| `text` | MongoDB | `$text` on the text index (`title_en`, `text_en`, English), the application's query |
| `gin` | PostgreSQL | a `tsvector` generated from the same two fields (`english`), a GIN index, `@@` with `plainto_tsquery` |
| `scan` | PostgreSQL | the same query with the index forbidden: a sequential scan computing the `tsvector` per row, to show what the index buys |

B7 also reports each engine's index build time and size, and stores `EXPLAIN (ANALYZE)` and `explain("executionStats")`
output for each query, so the report can compare plans, which is what the brief asks for ("rigorous comparison"). The
PostgreSQL objects live in their own bench-only table, `bench_review_text`, so the existing `reviews` copy, B2, B4 and B5 are
unchanged. On the MongoDB side the text index is created by B7's own setup after B4 and B5 have measured storage (or dropped after
B7), so it does not alter their figures.

**Correctness (a timing counts only if its check passed).** For every query, the MongoDB result and the PostgreSQL `gin` and
`scan` results must return the **same match count and the same 10 ids in the same order**. PostgreSQL's `scan` result is the
reference. MongoDB and PostgreSQL both stem with Snowball English but keep different stop-word lists and tokenise
punctuation differently, so the fixed queries avoid stop words and are checked in the pilot; a query on which the engines
disagree is replaced **before any timing**, and the replacement is recorded in the plan's review notes. A disagreement after
that fails the run.

**Not covered, said plainly in the report.** Relevance ranking is not compared (`$text` score and `ts_rank` are not
equivalent); results are ordered by date on both. Phrase queries are measured on the benchmark only, not offered in the page.
Fuzzy matching and Portuguese search are out. Each review write now also updates the text index (a small write cost the page
accepts). The comparison runs on one dataset of this size.

## Decisions for Erfan

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | **Scope** | (A) page search and B7. (B) B7 only. (C) page search only | **A.** C has nothing to compare, B has nothing to show in the demo. The page search is small once the index exists |
| D2 | **Where the box appears** | All three review lists through `review_page`; the product page only | **All three**: one function, one test set, and the operator and seller lists are where a long list needs searching |
| D3 | **Query semantics** | Words reduced to plain terms and ANDed; MongoDB's own syntax (OR of words, `-`, quotes); a prefix search | **Plain terms, all required.** It gives both engines the same question, removes syntax surprises and keeps the input safe. Phrases stay a benchmark-only case |
| D4 | **What B7 measures** | Count plus 10 newest (the page); the match ids only; ranked results | **Count plus 10 newest**, the page's real operation, ordered the same on both engines so correctness is an exact comparison |
| D5 | **PostgreSQL side placement** | A column and index on the bench `reviews` copy; a separate bench table | **A separate `bench_review_text` table**, so B2, B4 and B5 (storage) are not changed and the existing evidence stays comparable |
| D6 | **Fixed queries** | Chosen from the corpus by frequency band before any run; chosen after seeing timings | **Before any run**, from document frequencies counted on the data, written into the code (the same discipline as the B2 pairs) |
| D7 | **Kill switch** | Build to the end whatever happens; cut at a date | **Cut at the end of 12 Nov** if the page search is not green or the engines' results do not agree on the fixed queries. List it as future work in the report; nothing else depends on it |

## Steps (small, a short review after each)

0. **Read first (no code):** how the benchmark loader creates the `reviews` indexes and which indexes B4 and B5 count, to place B7's
   text index so storage figures are unchanged; the document frequencies for the fixed queries.
1. **Index and page:** `mongo_setup` creates the text index (English, `title_en` weight 2, `text_en`); `review_page` takes a search
   string; the three views and `reviews/list.html` get the box. Tests: the index exists and is idempotent; AND semantics, stemming
   and case; scope and visibility are kept (a seller never finds another seller's review, a hidden review appears only for the
   operator); an empty or operator-only string (`-`, `$where`, `"`) is harmless; an injection negative; pagination with a search.
2. **B7:** `bench_review_text` (title, text, generated `tsvector`, GIN) in the loader; `benchmarks/workloads/b7.py` with the three
   variants and the fixed queries; the agreement check; plan capture; index build time and size; registered in the headline pairs
   (`gin` against `text`, with `scan` as the unindexed reference). Fixture-database tests for the agreement check.
3. **Docs:** DATA_MODEL (the index, `bench_review_text`), README (the search box, B7 in the benchmark list), benchmark.md (an
   amendment for B7), DECISIONS, PLAN.md section 14, the report note in [deliverables](deliverables.md).
4. **Checks:** the full suite; one Opus 5.5 review of the build, then one fix round. The pilot (agreement on the fixed queries on
   full data) and the timed runs happen with the fresh benchmark after the freeze.

## Review notes

(empty: the plan review has not been run yet)
