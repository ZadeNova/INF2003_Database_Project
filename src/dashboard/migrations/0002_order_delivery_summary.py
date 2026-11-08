import os

from django.db import migrations
from psycopg import sql

# One row per delivered order up to the reporting date: the same rows, columns and arithmetic as the live DELAY_BUCKETS
# query in dashboard/queries.py (a test compares the two), without the shop name, which is always read live. The cut-off
# is the end of the reporting day in Singapore, evaluated once per refresh like the sales view.
CREATE = """
CREATE MATERIALIZED VIEW public.order_delivery_summary AS
WITH cutoff AS MATERIALIZED (
    SELECT as_of, ((as_of + 1)::timestamp AT TIME ZONE 'Asia/Singapore') AS cutoff_end
    FROM (SELECT public.dashboard_as_of() AS as_of) reporting
), deliveries AS (
    SELECT o.id AS order_id, o.seller_id, cutoff.as_of,
           (o.delivered_at AT TIME ZONE 'Asia/Singapore')::date -
               (o.estimated_delivery AT TIME ZONE 'Asia/Singapore')::date AS delay_days,
           CASE WHEN sg.zip_prefix IS NULL OR cg.zip_prefix IS NULL THEN NULL ELSE
               6371 * 2 * asin(sqrt(least(1.0, greatest(0.0,
                   power(sin(radians((cg.latitude - sg.latitude)::double precision) / 2), 2) +
                   cos(radians(sg.latitude::double precision)) * cos(radians(cg.latitude::double precision)) *
                   power(sin(radians((cg.longitude - sg.longitude)::double precision) / 2), 2)))))
           END AS distance_km
    FROM cutoff
    CROSS JOIN public.orders_order o
    JOIN public.orders_checkout ch ON ch.id = o.checkout_id
    JOIN public.accounts_seller s ON s.id = o.seller_id
    JOIN public.accounts_customerprofile cp ON cp.user_id = ch.customer_id
    LEFT JOIN public.accounts_geolocation sg ON sg.zip_prefix = s.zip_prefix
    LEFT JOIN public.accounts_geolocation cg ON cg.zip_prefix = cp.zip_prefix
    WHERE o.status = 'delivered' AND o.placed_at < cutoff.cutoff_end AND o.delivered_at < cutoff.cutoff_end
)
SELECT order_id, seller_id, delay_days, distance_km,
       CASE WHEN delay_days < -7 THEN 'early_over_7'
            WHEN delay_days <= 0 THEN 'early_up_to_7_or_on_time'
            WHEN delay_days <= 7 THEN 'late_1_to_7'
            WHEN delay_days <= 14 THEN 'late_8_to_14' ELSE 'late_over_14' END AS bucket,
       as_of
FROM deliveries
WITH NO DATA;
CREATE UNIQUE INDEX order_delivery_summary_order ON public.order_delivery_summary(order_id);

CREATE FUNCTION public.refresh_order_delivery_summary() RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
    -- The same lock as the sales view, so a refresh of both views serialises. The first population cannot be
    -- concurrent; later refreshes keep readers on the previous snapshot.
    PERFORM pg_catalog.pg_advisory_xact_lock(820304);
    IF (SELECT relispopulated FROM pg_catalog.pg_class WHERE oid = 'public.order_delivery_summary'::regclass) THEN
        REFRESH MATERIALIZED VIEW CONCURRENTLY public.order_delivery_summary;
    ELSE
        REFRESH MATERIALIZED VIEW public.order_delivery_summary;
    END IF;
END $$;
REVOKE EXECUTE ON FUNCTION public.refresh_order_delivery_summary() FROM PUBLIC;
"""

DROP = """
DROP FUNCTION public.refresh_order_delivery_summary();
DROP MATERIALIZED VIEW public.order_delivery_summary;
"""


def grant_runtime(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        role = sql.Identifier(os.environ["POSTGRES_RUNTIME_USER"])
        cursor.execute(sql.SQL("GRANT SELECT ON public.order_delivery_summary TO {}").format(role))
        cursor.execute(sql.SQL("GRANT EXECUTE ON FUNCTION public.refresh_order_delivery_summary() TO {}").format(role))


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0001_daily_product_sales"),
        ("orders", "0004_order_timestamp_guard"),
        ("accounts", "0002_audit_log"),
    ]
    operations = [
        migrations.RunSQL(CREATE, DROP),
        migrations.RunPython(grant_runtime, migrations.RunPython.noop),
    ]
