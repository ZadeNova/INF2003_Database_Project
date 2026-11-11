-- "The database says no" (backlog #38): PostgreSQL refuses each change below on its own, whatever the application does.
-- Runs as the web application's runtime role, the role every page request uses. Nothing here changes data: every
-- statement is refused, and the two that could change rows run inside a transaction that is rolled back.
-- Run from the repository root with the stack up (Bash or Git Bash; PowerShell: see README "Database demonstrations"):
--   docker compose exec -T db sh -c 'psql -X -q -e -U "$APP_RUNTIME_USER" -d "$APP_DB_NAME"' < scripts/demo/database_says_no.sql
\set VERBOSITY terse
\pset pager off
SELECT current_user AS connected_as;

\echo
\echo '1. The runtime role cannot change the schema or empty a table (no DDL, no TRUNCATE)'
DROP TABLE orders_order;
TRUNCATE orders_payment;

\echo
\echo '2. Money rows cannot be deleted, so the order lifecycle and its audit trail cannot be bypassed'
DELETE FROM orders_order WHERE id = (SELECT min(id) FROM orders_order);

\echo
\echo '3. The audit log is read-only to the application; only owner-owned trigger functions write it'
UPDATE audit_log SET reason = 'edited' WHERE id = (SELECT min(id) FROM audit_log);

\echo
\echo '4. Order status follows placed/paid -> shipped -> delivered; a paid order cannot jump to delivered'
BEGIN;
UPDATE orders_order SET status = 'delivered' WHERE id = (SELECT min(id) FROM orders_order WHERE status = 'paid');
ROLLBACK;

\echo
\echo '5. A delivery date cannot be back-dated, so a late delivery cannot be made to look on time'
BEGIN;
UPDATE orders_order SET delivered_at = shipped_at
WHERE id = (SELECT min(id) FROM orders_order WHERE status = 'delivered' AND delivered_at > shipped_at);
ROLLBACK;

\echo
\echo '6. Payments must equal the checkout total; the deferred trigger checks it at COMMIT'
BEGIN;
UPDATE orders_payment SET amount = amount + 1 WHERE id = (SELECT min(id) FROM orders_payment);
\echo '   (the UPDATE above was accepted; the check runs when the transaction commits)'
COMMIT;

\echo
\echo '7. Row-level security: a seller session sees only its own orders (the setting the seller pages use)'
SELECT count(*) AS orders_visible_to_the_web_role FROM orders_order;
SELECT set_config('mercer.seller_id', (
    SELECT s.id::text FROM accounts_seller s JOIN accounts_user u ON u.id = s.user_id WHERE u.username = 'demo-seller'
), false) AS seller_id;
SELECT count(*) AS orders_visible_to_demo_seller FROM orders_order;
SELECT count(*) AS other_sellers_orders_visible FROM orders_order
WHERE seller_id <> current_setting('mercer.seller_id')::bigint;
SELECT count(*) AS checkouts_visible_to_demo_seller FROM orders_checkout;
SELECT set_config('mercer.seller_id', '', false) AS cleared;
