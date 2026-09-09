# ETL / seeding

Cleans source datasets with pandas, then bulk-loads them:

- Postgres: `COPY` (via `asyncpg.copy_records_to_table` or `psql \copy`), never
  row-by-row ORM inserts — the datasets are six-figure row counts.
- MongoDB: `insert_many` / `bulk_write`.

`data/` holds raw source files and is gitignored.
