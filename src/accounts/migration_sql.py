"""Profile ownership constraints; account workflows are added by the accounts workstream."""
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
