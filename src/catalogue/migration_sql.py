"""Product audit follows the shared accounts owner/privilege boundary."""

PRODUCT_AUDIT = """
CREATE FUNCTION public.audit_product_update() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
    INSERT INTO public.audit_log (table_name, row_id, action, actor_id, before, after, reason, created_at)
    VALUES (TG_TABLE_NAME, OLD.id::text,
            CASE WHEN OLD.taken_down IS DISTINCT FROM NEW.taken_down
                 THEN CASE WHEN NEW.taken_down THEN 'product.takedown' ELSE 'product.restore' END
                 WHEN OLD.active IS DISTINCT FROM NEW.active
                 THEN CASE WHEN NEW.active THEN 'product.activate' ELSE 'product.deactivate' END
                 ELSE 'product.update' END,
            NULLIF(current_setting('mercer.actor_id', true), '')::bigint,
            jsonb_build_object('id', OLD.id, 'seller_id', OLD.seller_id, 'name', OLD.name,
                'price', OLD.price, 'stock', OLD.stock, 'active', OLD.active, 'taken_down', OLD.taken_down),
            jsonb_build_object('id', NEW.id, 'seller_id', NEW.seller_id, 'name', NEW.name,
                'price', NEW.price, 'stock', NEW.stock, 'active', NEW.active, 'taken_down', NEW.taken_down),
            NULLIF(current_setting('mercer.audit_reason', true), ''), pg_catalog.now());
    RETURN NULL;
END $$;
CREATE TRIGGER product_update_audit AFTER UPDATE ON public.catalogue_product
FOR EACH ROW WHEN (OLD.price IS DISTINCT FROM NEW.price OR OLD.stock IS DISTINCT FROM NEW.stock
    OR OLD.active IS DISTINCT FROM NEW.active OR OLD.taken_down IS DISTINCT FROM NEW.taken_down)
EXECUTE FUNCTION public.audit_product_update();
REVOKE EXECUTE ON FUNCTION public.audit_product_update() FROM PUBLIC;
"""
PRODUCT_AUDIT_REVERSE = """
DROP TRIGGER product_update_audit ON public.catalogue_product;
DROP FUNCTION public.audit_product_update();
"""

# A new product's first price and stock are recorded too; the UPDATE trigger above reads OLD, which an INSERT lacks.
PRODUCT_INSERT_AUDIT = """
CREATE FUNCTION public.audit_product_insert() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
    INSERT INTO public.audit_log (table_name, row_id, action, actor_id, before, after, reason, created_at)
    VALUES (TG_TABLE_NAME, NEW.id::text, 'product.create',
            NULLIF(current_setting('mercer.actor_id', true), '')::bigint, NULL,
            jsonb_build_object('id', NEW.id, 'seller_id', NEW.seller_id, 'name', NEW.name,
                'price', NEW.price, 'stock', NEW.stock, 'active', NEW.active, 'taken_down', NEW.taken_down),
            NULLIF(current_setting('mercer.audit_reason', true), ''), pg_catalog.now());
    RETURN NULL;
END $$;
CREATE TRIGGER product_insert_audit AFTER INSERT ON public.catalogue_product
FOR EACH ROW EXECUTE FUNCTION public.audit_product_insert();
REVOKE EXECUTE ON FUNCTION public.audit_product_insert() FROM PUBLIC;
"""
PRODUCT_INSERT_AUDIT_REVERSE = """
DROP TRIGGER product_insert_audit ON public.catalogue_product;
DROP FUNCTION public.audit_product_insert();
"""


# `SELECT p.*` froze whatever columns the product table had when the view was first created. The same 19 columns, in the same
# order, are now written out, so a column added to the product table is added to the view (or left out) on purpose. CREATE OR
# REPLACE keeps the view's privileges and everything that depends on it; the option is repeated because the statement resets it.
PRODUCT_COLUMNS = (
    "id, olist_product_id, name, price, freight, stock, lead_time_days, weight_g, length_cm, height_cm, width_cm, active, "
    "featured, taken_down, taken_down_reason, has_generated_content, demo_adjustment, category_id, seller_id"
)
_PURCHASABLE_FROM = (
    "FROM catalogue_product p JOIN accounts_seller s ON s.id = p.seller_id "
    "WHERE p.active AND NOT p.taken_down AND s.status = 'approved'"
)
PURCHASABLE_EXPLICIT_COLUMNS = (
    "CREATE OR REPLACE VIEW purchasable_product WITH (security_invoker=true) AS SELECT "
    + ", ".join("p." + name for name in PRODUCT_COLUMNS.split(", "))
    + " "
    + _PURCHASABLE_FROM
)
PURCHASABLE_ALL_COLUMNS = (
    "CREATE OR REPLACE VIEW purchasable_product WITH (security_invoker=true) AS SELECT p.* " + _PURCHASABLE_FROM
)
