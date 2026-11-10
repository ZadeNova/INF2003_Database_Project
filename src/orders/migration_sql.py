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


# Row-level security for sellers (docs/plans/seller-rls.md). A session that sets `mercer.seller_id` sees and changes only
# that seller's rows; with the setting unset every policy lets everything through, so customers, operators and the owner
# role behave as before. The owner bypasses the policies (row security is enabled, never forced).
_SELLER = "(SELECT public.mercer_seller())"
_UNSET = f"{_SELLER} IS NULL"
_OWN = f"({_UNSET} OR seller_id = {_SELLER})"
_AUDIT_OWN = (
    f"({_UNSET} OR (table_name = 'accounts_seller' AND row_id = {_SELLER}::text) "
    f"OR COALESCE(after, before) ->> 'seller_id' = {_SELLER}::text)"
)
_DENY = {"INSERT": (None, _UNSET), "UPDATE": (_UNSET, _UNSET), "DELETE": (_UNSET, None)}

# table -> command -> (USING, WITH CHECK). A SELECT policy always allows at least what the write policies allow,
# because INSERT ... RETURNING and UPDATE ... WHERE also need the row to pass SELECT.
SELLER_POLICIES = {
    "orders_order": {
        "SELECT": (_OWN, None),
        "INSERT": (None, _UNSET),
        "UPDATE": (_OWN, _OWN),
        "DELETE": (_UNSET, None),
    },
    "orders_orderline": {"SELECT": (_OWN, None), **_DENY},
    "orders_refund": {
        "SELECT": (
            f"({_UNSET} OR EXISTS (SELECT 1 FROM public.orders_order o WHERE o.id = orders_refund.order_id))",
            None,
        ),
        **_DENY,
    },
    "orders_checkout": {"ALL": (_UNSET, _UNSET)},
    "orders_payment": {"ALL": (_UNSET, _UNSET)},
    "catalogue_product": {
        "SELECT": ("true", None),
        "INSERT": (None, _OWN),
        "UPDATE": (_OWN, _OWN),
        "DELETE": (_OWN, None),
    },
    "audit_log": {"SELECT": (_AUDIT_OWN, None)},  # written only by SECURITY DEFINER triggers, which bypass the policies
}

SELLER_ROW_SECURITY = """
CREATE FUNCTION public.mercer_seller() RETURNS bigint
LANGUAGE sql STABLE SET search_path = pg_catalog, pg_temp AS $$
    SELECT NULLIF(pg_catalog.current_setting('mercer.seller_id', true), '')::bigint
$$;

-- The deferred money checks read every payment, order and refund of a checkout. With the caller's rights a seller session
-- would not see the checkout, the loop would skip it (IF NOT FOUND THEN CONTINUE) and the check would pass silently.
ALTER FUNCTION public.check_checkout_money() SECURITY DEFINER;
ALTER FUNCTION public.check_checkout_refunds() SECURITY DEFINER;

-- Locks the checkout of an order before the order itself (the lock order of the deferred checks), for a seller session
-- that cannot read the checkout. It locks only a checkout whose order the caller may see, and returns NULL otherwise.
CREATE FUNCTION public.lock_checkout_of_order(p_order_id bigint) RETURNS bigint
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT c.id FROM public.orders_order o JOIN public.orders_checkout c ON c.id = o.checkout_id
    WHERE o.id = p_order_id AND (public.mercer_seller() IS NULL OR o.seller_id = public.mercer_seller())
    FOR UPDATE OF c
$$;
REVOKE EXECUTE ON FUNCTION public.lock_checkout_of_order(bigint) FROM PUBLIC;
"""
SELLER_ROW_SECURITY_REVERSE = ""
for _table, _commands in SELLER_POLICIES.items():
    SELLER_ROW_SECURITY += f"ALTER TABLE public.{_table} ENABLE ROW LEVEL SECURITY;\n"
    for _command, (_using, _check) in _commands.items():
        _clauses = (f" USING ({_using})" if _using else "") + (f" WITH CHECK ({_check})" if _check else "")
        SELLER_ROW_SECURITY += f"CREATE POLICY seller_{_command.lower()} ON public.{_table} FOR {_command}{_clauses};\n"
        SELLER_ROW_SECURITY_REVERSE += f"DROP POLICY seller_{_command.lower()} ON public.{_table};\n"
    SELLER_ROW_SECURITY_REVERSE += f"ALTER TABLE public.{_table} DISABLE ROW LEVEL SECURITY;\n"
SELLER_ROW_SECURITY_REVERSE += """
DROP FUNCTION public.lock_checkout_of_order(bigint);
ALTER FUNCTION public.check_checkout_refunds() SECURITY INVOKER;
ALTER FUNCTION public.check_checkout_money() SECURITY INVOKER;
DROP FUNCTION public.mercer_seller();
"""


# A row is created under one parent and stays there. Nothing in the application moves an order to another checkout, a
# payment or refund to another checkout, a line to another order or product, or changes who placed a checkout and when,
# so the database refuses it. (Moving a row to a parent with the same total would pass the deferred money checks, and
# the reviews in MongoDB hold these ids.) An order's seller_id is already tied to its lines by a foreign key and to the
# session by row-level security. The importer disables user triggers for its inserts, and inserts never fire this.
ORDER_KEY_GUARD_TRIGGERS = {
    "orders_order": "OLD.checkout_id IS DISTINCT FROM NEW.checkout_id",
    "orders_checkout": "(OLD.customer_id, OLD.placed_at, OLD.olist_order_id) IS DISTINCT FROM "
    "(NEW.customer_id, NEW.placed_at, NEW.olist_order_id)",
    "orders_orderline": "(OLD.order_id, OLD.product_id) IS DISTINCT FROM (NEW.order_id, NEW.product_id)",
    "orders_payment": "OLD.checkout_id IS DISTINCT FROM NEW.checkout_id",
    "orders_refund": "(OLD.checkout_id, OLD.order_id) IS DISTINCT FROM (NEW.checkout_id, NEW.order_id)",
}
ORDER_KEY_GUARD = """
CREATE FUNCTION public.protect_order_keys() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $$
BEGIN
    RAISE EXCEPTION '% keys cannot be changed after the row is created', TG_TABLE_NAME USING ERRCODE = '23514';
END $$;
REVOKE EXECUTE ON FUNCTION public.protect_order_keys() FROM PUBLIC;
"""
ORDER_KEY_GUARD_REVERSE = ""
for _table, _changed in ORDER_KEY_GUARD_TRIGGERS.items():
    ORDER_KEY_GUARD += f"""
CREATE TRIGGER {_table}_key_guard BEFORE UPDATE ON public.{_table}
FOR EACH ROW WHEN ({_changed}) EXECUTE FUNCTION public.protect_order_keys();
"""
    ORDER_KEY_GUARD_REVERSE += f"DROP TRIGGER {_table}_key_guard ON public.{_table};\n"
ORDER_KEY_GUARD_REVERSE += "DROP FUNCTION public.protect_order_keys();"
