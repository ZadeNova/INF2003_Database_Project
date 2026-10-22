"""Profile ownership constraints and the seller status workflow with its audit trigger."""
PROFILE_GUARDS = """
CREATE FUNCTION check_profile_role() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE expected text; actual text;
BEGIN
    expected := CASE TG_TABLE_NAME WHEN 'accounts_customerprofile' THEN 'customer' ELSE 'seller' END;
    SELECT role INTO actual FROM accounts_user WHERE id = NEW.user_id FOR SHARE;
    IF actual IS DISTINCT FROM expected THEN
        RAISE EXCEPTION 'profile role does not match user role' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER customer_profile_role BEFORE INSERT OR UPDATE ON accounts_customerprofile
FOR EACH ROW EXECUTE FUNCTION check_profile_role();
CREATE TRIGGER seller_profile_role BEFORE INSERT OR UPDATE ON accounts_seller
FOR EACH ROW EXECUTE FUNCTION check_profile_role();
CREATE FUNCTION protect_profile_role() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.role IS DISTINCT FROM OLD.role AND (
        (NEW.role <> 'customer' AND EXISTS (SELECT 1 FROM accounts_customerprofile WHERE user_id = NEW.id)) OR
        (NEW.role <> 'seller' AND EXISTS (SELECT 1 FROM accounts_seller WHERE user_id = NEW.id))
    ) THEN
        RAISE EXCEPTION 'user role conflicts with existing profile' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER user_profile_role BEFORE UPDATE OF role ON accounts_user
FOR EACH ROW EXECUTE FUNCTION protect_profile_role();
"""
PROFILE_GUARDS_REVERSE = """
DROP TRIGGER user_profile_role ON accounts_user;
DROP FUNCTION protect_profile_role();
DROP TRIGGER seller_profile_role ON accounts_seller;
DROP TRIGGER customer_profile_role ON accounts_customerprofile;
DROP FUNCTION check_profile_role();
"""

# Seller status workflow (accounts plan). Both functions are owned by the migration owner, reference only
# schema-qualified objects and pin search_path, so the runtime role cannot redirect them through pg_temp or a
# schema of its own. Only the audit function is SECURITY DEFINER: it alone writes a table runtime cannot.
SELLER_STATUS = """
CREATE FUNCTION public.check_seller_status_transition() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $$
BEGIN
    IF NOT ((OLD.status = 'pending' AND NEW.status IN ('approved', 'rejected'))
            OR (OLD.status = 'approved' AND NEW.status = 'suspended')
            OR (OLD.status = 'suspended' AND NEW.status = 'approved')) THEN
        RAISE EXCEPTION 'seller status cannot change from % to %', OLD.status, NEW.status USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER seller_status_transition BEFORE UPDATE ON public.accounts_seller
FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION public.check_seller_status_transition();

CREATE FUNCTION public.audit_seller_status() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
    -- Actor and reason come from the transaction-local context set by accounts.audit; a NULL actor is a
    -- system change. Snapshots name their fields, so a column added later cannot leak into the log.
    INSERT INTO public.audit_log (table_name, row_id, action, actor_id, before, after, reason, created_at)
    VALUES (TG_TABLE_NAME, OLD.id::text,
            'seller.' || CASE
                WHEN OLD.status = 'pending' AND NEW.status = 'approved' THEN 'approve'
                WHEN OLD.status = 'pending' AND NEW.status = 'rejected' THEN 'reject'
                WHEN OLD.status = 'approved' AND NEW.status = 'suspended' THEN 'suspend'
                WHEN OLD.status = 'suspended' AND NEW.status = 'approved' THEN 'reinstate'
            END,
            NULLIF(current_setting('mercer.actor_id', true), '')::bigint,
            jsonb_build_object('id', OLD.id, 'user_id', OLD.user_id, 'status', OLD.status, 'shop_name', OLD.shop_name),
            jsonb_build_object('id', NEW.id, 'user_id', NEW.user_id, 'status', NEW.status, 'shop_name', NEW.shop_name),
            NULLIF(current_setting('mercer.audit_reason', true), ''),
            pg_catalog.now());
    RETURN NULL;
END $$;
CREATE TRIGGER seller_status_audit AFTER UPDATE ON public.accounts_seller
FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION public.audit_seller_status();

-- Hygiene only: triggers do not check EXECUTE when they fire. The controls are the table and sequence
-- revocations (config.privileges), owner ownership and the pinned search path.
REVOKE EXECUTE ON FUNCTION public.check_seller_status_transition(), public.audit_seller_status() FROM PUBLIC;
"""
SELLER_STATUS_REVERSE = """
DROP TRIGGER seller_status_audit ON public.accounts_seller;
DROP FUNCTION public.audit_seller_status();
DROP TRIGGER seller_status_transition ON public.accounts_seller;
DROP FUNCTION public.check_seller_status_transition();
"""
