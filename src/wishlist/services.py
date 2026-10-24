"""The many-to-many insert/delete is customer scoped; restocks are entirely trigger driven."""
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404

from accounts.models import User
from catalogue.models import PurchasableProduct

from .models import RestockAlert


def set_saved(actor, product_id, saved):
    if actor.role != User.Role.CUSTOMER:
        raise PermissionDenied
    try:
        product_id = int(product_id)
        if not 0 < product_id < 2**63:
            raise ValueError
    except (ValueError, TypeError):
        raise Http404 from None
    with connection.cursor() as cursor:
        if saved:
            if not PurchasableProduct.objects.filter(pk=product_id).exists():
                raise Http404
            cursor.execute("""INSERT INTO wishlist_item(customer_id, product_id, added_at)
                SELECT %s, id, CURRENT_TIMESTAMP FROM purchasable_product WHERE id = %s
                ON CONFLICT (customer_id, product_id) DO NOTHING""", [actor.pk, product_id])
        else:
            cursor.execute("DELETE FROM wishlist_item WHERE customer_id = %s AND product_id = %s", [actor.pk, product_id])


def visible_alerts(user):
    return RestockAlert.objects.filter(customer=user, product_id__in=PurchasableProduct.objects.values("pk"))


def unseen_count(user):
    return visible_alerts(user).filter(seen_at__isnull=True).count()
