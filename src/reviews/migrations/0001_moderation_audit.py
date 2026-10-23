import os

from django.db import migrations
from psycopg import sql


CREATE = """
CREATE FUNCTION public.audit_review_moderation(review_id text, decision text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE actor bigint := NULLIF(current_setting('mercer.actor_id', true), '')::bigint;
        reason text := NULLIF(btrim(current_setting('mercer.audit_reason', true)), '');
BEGIN
    IF actor IS NULL OR NOT EXISTS (SELECT 1 FROM public.accounts_user WHERE id = actor AND role = 'operator') THEN
        RAISE EXCEPTION 'operator required' USING ERRCODE = '42501';
    END IF;
    IF decision IS NULL OR decision NOT IN ('takedown', 'restore') OR reason IS NULL
       OR review_id IS NULL OR review_id !~ '^[1-9][0-9]{0,18}$' THEN
        RAISE EXCEPTION 'review id, moderation decision and reason required' USING ERRCODE = '23514';
    END IF;
    INSERT INTO public.audit_log(table_name, row_id, action, actor_id, before, after, reason, created_at)
    VALUES ('reviews', review_id, 'review.' || decision, actor,
            jsonb_build_object('taken_down', decision = 'restore'),
            jsonb_build_object('taken_down', decision = 'takedown'), reason, pg_catalog.now());
END $$;
REVOKE EXECUTE ON FUNCTION public.audit_review_moderation(text, text) FROM PUBLIC;
"""


def grant_execute(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(sql.SQL("GRANT EXECUTE ON FUNCTION public.audit_review_moderation(text, text) TO {}")
                       .format(sql.Identifier(os.environ["POSTGRES_RUNTIME_USER"])))


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_audit_log"), ("orders", "0002_checkout")]
    operations = [migrations.RunSQL(CREATE, "DROP FUNCTION public.audit_review_moderation(text, text)"),
                  migrations.RunPython(grant_execute, migrations.RunPython.noop)]
