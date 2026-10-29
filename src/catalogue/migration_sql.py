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
