import os

from django.db import migrations
from psycopg import sql


CREATE = """
CREATE FUNCTION public.dashboard_as_of() RETURNS date
LANGUAGE sql STABLE SET search_path = public, pg_temp AS $$
    SELECT max((o.placed_at AT TIME ZONE 'Asia/Singapore')::date)
    FROM public.orders_order o JOIN public.orders_checkout c ON c.id = o.checkout_id
    WHERE c.olist_order_id IS NOT NULL
$$;
REVOKE EXECUTE ON FUNCTION public.dashboard_as_of() FROM PUBLIC;
CREATE MATERIALIZED VIEW public.daily_product_sales AS
WITH cutoff AS MATERIALIZED (SELECT public.dashboard_as_of() AS as_of)
SELECT l.product_id, (o.placed_at AT TIME ZONE 'Asia/Singapore')::date AS day,
       sum(l.quantity)::bigint AS units, sum(l.quantity * l.unit_price)::numeric(12,2) AS revenue
FROM public.orders_orderline l JOIN public.orders_order o ON o.id = l.order_id CROSS JOIN cutoff
WHERE (o.placed_at AT TIME ZONE 'Asia/Singapore')::date <= cutoff.as_of
  AND (o.status <> 'cancelled' OR (o.cancelled_at AT TIME ZONE 'Asia/Singapore')::date > cutoff.as_of)
GROUP BY l.product_id, (o.placed_at AT TIME ZONE 'Asia/Singapore')::date
WITH NO DATA;
CREATE UNIQUE INDEX daily_product_sales_product_day ON public.daily_product_sales(product_id, day);

CREATE FUNCTION public.refresh_daily_product_sales() RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
    -- The first population cannot be concurrent. Later refreshes keep readers on the previous snapshot.
    PERFORM pg_catalog.pg_advisory_xact_lock(820304);
    IF (SELECT relispopulated FROM pg_catalog.pg_class WHERE oid = 'public.daily_product_sales'::regclass) THEN
        REFRESH MATERIALIZED VIEW CONCURRENTLY public.daily_product_sales;
    ELSE
        REFRESH MATERIALIZED VIEW public.daily_product_sales;
    END IF;
END $$;
REVOKE EXECUTE ON FUNCTION public.refresh_daily_product_sales() FROM PUBLIC;
"""


def grant_refresh(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        role = sql.Identifier(os.environ["POSTGRES_RUNTIME_USER"])
        cursor.execute(sql.SQL("GRANT SELECT ON public.daily_product_sales TO {}").format(role))
        cursor.execute(sql.SQL("GRANT EXECUTE ON FUNCTION public.refresh_daily_product_sales() TO {}").format(role))
        cursor.execute(sql.SQL("GRANT EXECUTE ON FUNCTION public.dashboard_as_of() TO {}").format(role))


class Migration(migrations.Migration):
    dependencies = [("orders", "0002_checkout"), ("catalogue", "0002_product_search_audit")]
    operations = [migrations.RunSQL(CREATE,
        "DROP FUNCTION public.refresh_daily_product_sales(); DROP MATERIALIZED VIEW public.daily_product_sales; DROP FUNCTION public.dashboard_as_of();"),
        migrations.RunPython(grant_refresh, migrations.RunPython.noop)]
