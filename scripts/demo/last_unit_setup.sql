-- Last-unit race (backlog #47), step 1: leave exactly one unit of one demo-seller product.
-- The product update trigger records the original stock in audit_log with this reason, which last_unit_restore.sql
-- reads back. Runs as the runtime role:
--   docker compose exec -T db sh -c 'psql -X -q -U "$APP_RUNTIME_USER" -d "$APP_DB_NAME"' < scripts/demo/last_unit_setup.sql
\set ON_ERROR_STOP on
\pset pager off
SELECT set_config('mercer.audit_reason', 'demo: last-unit race setup', false) IS NOT NULL AS reason_set \gset
SELECT p.id AS product_id, p.name AS product_name, p.stock AS stock_before
FROM purchasable_product p
JOIN accounts_seller s ON s.id = p.seller_id
JOIN accounts_user u ON u.id = s.user_id
WHERE u.username = 'demo-seller' AND p.stock > 1 AND coalesce(p.demo_adjustment, '') = ''
ORDER BY p.id
LIMIT 1 \gset
UPDATE catalogue_product SET stock = 1 WHERE id = :product_id;
\echo
\echo 'Product for the race:' :product_id '-' :product_name
\echo 'Stock was' :stock_before 'and is now 1. In both terminals use product id' :product_id
