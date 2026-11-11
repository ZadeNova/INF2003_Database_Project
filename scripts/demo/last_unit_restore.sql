-- Last-unit race (backlog #47), last step: put back the stock recorded by last_unit_setup.sql and show the audit trail
-- the race left. Raising stock from 0 also fires the restock-alert trigger for anyone who wishlisted the product.
--   docker compose exec -T db sh -c 'psql -X -q -U "$APP_RUNTIME_USER" -d "$APP_DB_NAME"' < scripts/demo/last_unit_restore.sql
\set ON_ERROR_STOP on
\pset pager off
SELECT set_config('mercer.audit_reason', 'demo: last-unit race restore', false) IS NOT NULL AS reason_set \gset
SELECT row_id AS product_id, (before ->> 'stock')::int AS original_stock
FROM audit_log
WHERE table_name = 'catalogue_product' AND reason = 'demo: last-unit race setup'
ORDER BY id DESC
LIMIT 1 \gset
UPDATE catalogue_product SET stock = :original_stock WHERE id = :product_id;
\echo 'Restored product' :product_id 'to stock' :original_stock '. Its latest audit rows:'
SELECT action, before ->> 'stock' AS stock_before, after ->> 'stock' AS stock_after, coalesce(reason, '') AS reason
FROM audit_log
WHERE table_name = 'catalogue_product' AND row_id = :'product_id'
ORDER BY id DESC
LIMIT 4;
