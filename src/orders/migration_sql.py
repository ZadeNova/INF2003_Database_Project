OWNERSHIP = """
ALTER TABLE orders_orderline ADD CONSTRAINT line_order_seller_fk
FOREIGN KEY (order_id, seller_id) REFERENCES orders_order(id, seller_id) ON DELETE RESTRICT;
ALTER TABLE orders_orderline ADD CONSTRAINT line_product_seller_fk
FOREIGN KEY (product_id, seller_id) REFERENCES catalogue_product(id, seller_id) ON DELETE RESTRICT;
ALTER TABLE orders_refund ADD CONSTRAINT refund_order_checkout_fk
FOREIGN KEY (order_id, checkout_id) REFERENCES orders_order(id, checkout_id) ON DELETE RESTRICT;
"""
OWNERSHIP_REVERSE = """
ALTER TABLE orders_refund DROP CONSTRAINT refund_order_checkout_fk;
ALTER TABLE orders_orderline DROP CONSTRAINT line_product_seller_fk;
ALTER TABLE orders_orderline DROP CONSTRAINT line_order_seller_fk;
"""


ORDER_LIFECYCLE = """
CREATE FUNCTION public.check_order_status_transition() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $$
BEGIN
    IF NOT ((OLD.status = 'placed' AND NEW.status IN ('paid', 'cancelled'))
            OR (OLD.status = 'paid' AND NEW.status IN ('shipped', 'cancelled'))
            OR (OLD.status = 'shipped' AND NEW.status = 'delivered')) THEN
        RAISE EXCEPTION 'order status cannot change from % to %', OLD.status, NEW.status USING ERRCODE = '23514';
    END IF;
    CASE NEW.status
        WHEN 'paid' THEN NEW.paid_at := pg_catalog.now();
        WHEN 'shipped' THEN NEW.shipped_at := pg_catalog.now();
        WHEN 'delivered' THEN NEW.delivered_at := pg_catalog.now();
        WHEN 'cancelled' THEN NEW.cancelled_at := pg_catalog.now();
    END CASE;
    RETURN NEW;
END $$;
CREATE TRIGGER order_status_transition BEFORE UPDATE ON public.orders_order
FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION public.check_order_status_transition();

CREATE FUNCTION public.audit_order_status() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
    INSERT INTO public.audit_log (table_name, row_id, action, actor_id, before, after, reason, created_at)
    VALUES (TG_TABLE_NAME, OLD.id::text, 'order.' || NEW.status,
        NULLIF(current_setting('mercer.actor_id', true), '')::bigint,
        jsonb_build_object('id', OLD.id, 'checkout_id', OLD.checkout_id, 'seller_id', OLD.seller_id, 'status', OLD.status),
        jsonb_build_object('id', NEW.id, 'checkout_id', NEW.checkout_id, 'seller_id', NEW.seller_id, 'status', NEW.status),
        NULLIF(current_setting('mercer.audit_reason', true), ''), pg_catalog.now());
    RETURN NULL;
END $$;
CREATE TRIGGER order_status_audit AFTER UPDATE ON public.orders_order
FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION public.audit_order_status();
REVOKE EXECUTE ON FUNCTION public.check_order_status_transition(), public.audit_order_status() FROM PUBLIC;
"""
ORDER_LIFECYCLE_REVERSE = """
DROP TRIGGER order_status_audit ON public.orders_order;
DROP FUNCTION public.audit_order_status();
DROP TRIGGER order_status_transition ON public.orders_order;
DROP FUNCTION public.check_order_status_transition();
"""

# The delay analysis is computed from these columns, so the database refuses to let them be rewritten. Without a
# status change none may move; with one, only the destination timestamp, which order_status_transition (it fires first,
# by name) stamps with now() whatever the statement said.
ORDER_TIMESTAMP_GUARD = """
CREATE FUNCTION public.protect_order_timestamps() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $$
BEGIN
    IF OLD.placed_at IS DISTINCT FROM NEW.placed_at
       OR OLD.estimated_delivery IS DISTINCT FROM NEW.estimated_delivery
       OR (NEW.status IS DISTINCT FROM OLD.status AND NEW.status <> 'paid' AND OLD.paid_at IS DISTINCT FROM NEW.paid_at)
       OR (NEW.status IS DISTINCT FROM OLD.status AND NEW.status <> 'shipped' AND OLD.shipped_at IS DISTINCT FROM NEW.shipped_at)
       OR (NEW.status IS DISTINCT FROM OLD.status AND NEW.status <> 'delivered' AND OLD.delivered_at IS DISTINCT FROM NEW.delivered_at)
       OR (NEW.status IS DISTINCT FROM OLD.status AND NEW.status <> 'cancelled' AND OLD.cancelled_at IS DISTINCT FROM NEW.cancelled_at)
       OR (NEW.status IS NOT DISTINCT FROM OLD.status
           AND (OLD.paid_at, OLD.shipped_at, OLD.delivered_at, OLD.cancelled_at)
               IS DISTINCT FROM (NEW.paid_at, NEW.shipped_at, NEW.delivered_at, NEW.cancelled_at)) THEN
        RAISE EXCEPTION 'order lifecycle timestamps cannot be changed directly' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER order_timestamp_guard BEFORE UPDATE ON public.orders_order
FOR EACH ROW WHEN ((OLD.status, OLD.placed_at, OLD.estimated_delivery, OLD.paid_at, OLD.shipped_at, OLD.delivered_at,
                    OLD.cancelled_at)
                   IS DISTINCT FROM (NEW.status, NEW.placed_at, NEW.estimated_delivery, NEW.paid_at, NEW.shipped_at,
                                     NEW.delivered_at, NEW.cancelled_at))
EXECUTE FUNCTION public.protect_order_timestamps();
REVOKE EXECUTE ON FUNCTION public.protect_order_timestamps() FROM PUBLIC;
"""
ORDER_TIMESTAMP_GUARD_REVERSE = """
DROP TRIGGER order_timestamp_guard ON public.orders_order;
DROP FUNCTION public.protect_order_timestamps();
"""

# Both OLD and NEW parents matter for a moved row. Lock parents in ID order before aggregating, so
# concurrent writers cannot each commit using an earlier view of the other writer's money changes.
_PARENT_IDS = """
    IF TG_TABLE_NAME = 'orders_checkout' THEN
        IF TG_OP <> 'INSERT' THEN old_parent := OLD.id; END IF;
        IF TG_OP <> 'DELETE' THEN new_parent := NEW.id; END IF;
    ELSE
        IF TG_OP <> 'INSERT' THEN old_parent := OLD.checkout_id; END IF;
        IF TG_OP <> 'DELETE' THEN new_parent := NEW.checkout_id; END IF;
    END IF;
    FOR parent IN SELECT DISTINCT x FROM unnest(ARRAY[old_parent, new_parent]) x WHERE x IS NOT NULL ORDER BY x LOOP
        SELECT total INTO checkout_total FROM public.orders_checkout WHERE id = parent FOR UPDATE;
        IF NOT FOUND THEN CONTINUE; END IF;
"""
MONEY_INVARIANTS = (
    """
CREATE FUNCTION public.check_checkout_money() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $$
DECLARE old_parent bigint; new_parent bigint; parent bigint; checkout_total numeric;
BEGIN
"""
    + _PARENT_IDS
    + """
        IF checkout_total <> (SELECT COALESCE(sum(amount), 0) FROM public.orders_payment WHERE checkout_id = parent)
            OR checkout_total <> (SELECT COALESCE(sum(total), 0) FROM public.orders_order WHERE checkout_id = parent) THEN
            RAISE EXCEPTION 'checkout payments and orders must equal its total' USING ERRCODE = '23514';
        END IF;
    END LOOP;
    RETURN NULL;
END $$;
CREATE FUNCTION public.check_checkout_refunds() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $$
DECLARE old_parent bigint; new_parent bigint; parent bigint; checkout_total numeric;
BEGIN
"""
    + _PARENT_IDS
    + """
        IF (SELECT COALESCE(sum(amount), 0) FROM public.orders_refund WHERE checkout_id = parent)
            <> (SELECT COALESCE(sum(total), 0) FROM public.orders_order WHERE checkout_id = parent AND status = 'cancelled') THEN
            RAISE EXCEPTION 'checkout refunds must equal cancelled orders' USING ERRCODE = '23514';
        END IF;
    END LOOP;
    RETURN NULL;
END $$;
REVOKE EXECUTE ON FUNCTION public.check_checkout_money(), public.check_checkout_refunds() FROM PUBLIC;
"""
)
MONEY_INVARIANTS_REVERSE = ""
for _table in ("orders_checkout", "orders_order", "orders_payment", "orders_refund"):
    for _kind in ("money", "refunds"):
        MONEY_INVARIANTS += f"""
CREATE CONSTRAINT TRIGGER {_table}_{_kind} AFTER INSERT OR UPDATE OR DELETE ON public.{_table}
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.check_checkout_{_kind}();
"""
        MONEY_INVARIANTS_REVERSE += f"DROP TRIGGER {_table}_{_kind} ON public.{_table};\n"
MONEY_INVARIANTS_REVERSE += (
    "DROP FUNCTION public.check_checkout_money(); DROP FUNCTION public.check_checkout_refunds();"
)
