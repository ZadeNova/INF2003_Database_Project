"""The many-to-many insert/delete is customer scoped; restocks are entirely trigger driven."""

from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404

from accounts.models import User
from catalogue.models import PurchasableProduct
from config.ids import BIGINT_MAX

from .models import RestockAlert


def set_saved(actor, product_id, saved):
    if actor.role != User.Role.CUSTOMER:
        raise PermissionDenied
    try:
        product_id = int(product_id)
        if not 0 < product_id <= BIGINT_MAX:
            raise ValueError
    except (ValueError, TypeError):
        raise Http404 from None
    with connection.cursor() as cursor:
        if saved:
            # One statement checks visibility and saves: the product is looked up once, so it cannot become invisible between a
            # separate check and the insert. A product that is not purchasable is a 404, an already saved one is left alone.
            cursor.execute(
                """WITH wanted AS (SELECT id FROM purchasable_product WHERE id = %s),
                added AS (INSERT INTO wishlist_item(customer_id, product_id, added_at)
                          SELECT %s, id, CURRENT_TIMESTAMP FROM wanted
                          ON CONFLICT (customer_id, product_id) DO NOTHING)
                SELECT count(*) FROM wanted""",
                [product_id, actor.pk],
            )
            if cursor.fetchone()[0] == 0:
                raise Http404
        else:
            cursor.execute(
                "DELETE FROM wishlist_item WHERE customer_id = %s AND product_id = %s", [actor.pk, product_id]
            )


def visible_alerts(user):
    return RestockAlert.objects.filter(customer=user, product_id__in=PurchasableProduct.objects.values("pk"))


def unseen_count(user):
    return visible_alerts(user).filter(seen_at__isnull=True).count()
