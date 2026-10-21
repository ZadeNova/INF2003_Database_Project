# activity: Activity events in a MongoDB time-series collection (M1)

status: draft
plan owner: Erfan · implementer: Chee Long · reviewer: a fresh session · estimate: 1 to 1.5 days · phase 3A (9 to 13
November) · depends on: `catalogue` (product pages, search), `checkout` (purchases for conversion)

**Assumes:** product detail and search views from `catalogue`; orders and lines from `checkout`; MongoDB 9.0 time-series
collections with `expireAfterSeconds`.

## Contract

**Goal.** Record what shoppers look at and search for, at high write volume, and turn it into recently viewed,
trending now and a views-to-purchases figure for sellers.

**In scope**

| Area | Deliverable |
|---|---|
| Collection | `events`: time-series collection (`timeField: ts`, `metaField: meta` with `type` view or search, `product_id`, `category`, `user_id` or anonymous session key), `expireAfterSeconds` = 30 days, a secondary index on `meta.product_id` and `meta.user_id`. Created by a migration-style management command run by the owner |
| Writing | Product detail writes a view event; search writes a search event with the query text (trimmed, at most 100 characters). Writes use `w: 1`; a failed event write is logged and never breaks the page |
| Recently viewed | The customer's last 10 distinct products, on the home and product pages (anonymous visitors by session) |
| Trending now | Views in the last 24 hours per product, ranked with `$setWindowFields` (`$rank`), overall and per category; fills the home page slot `catalogue` left |
| Seller conversion | Seller centre "Insights": per product, views in the last 30 days (MongoDB) against units sold in the same window (PostgreSQL), joined in Python by product id |
| Demo data (decision a) | `manage.py seed_activity` writes about 200k synthetic view events over the past 30 days, spread in proportion to real sales, marked `is_generated`, so trending and conversion are not empty on camera |

**Out of scope:** recommendations; event export; personal data beyond the user id or session key.

**Tests:** a product view and a search each write one event; an event write failure does not change the page; recently
viewed returns distinct products newest first; trending ranks match a direct count; the TTL option is set to 30 days;
conversion equals views and units counted directly on a small fixture; anonymous events never carry a user id.

**Exit check**
1. Browse five products as the demo customer: recently viewed lists them newest first.
2. After `seed_activity`, the home page shows trending products, and the seller centre shows views and conversion.
3. `explain("executionStats")` of the trending pipeline uses the time-series bucket index; noted for the report.
4. The full test suite passes in Docker.

## Decisions (for the plan owner)

| ID | Proposal | Why |
|---|---|---|
| a | Seed synthetic events relative to the time of seeding, labelled as generated | Olist has no browsing data, and a 30-day TTL only keeps recent events, so a fixed historical date would expire at once. This is demo data, not benchmark data, so it need not be byte-reproducible |
| b | Fire-and-forget event writes with `w: 1` | Page speed matters more than losing an occasional view event; the tradeoff is named in the report |

## Review notes

(empty until review)
