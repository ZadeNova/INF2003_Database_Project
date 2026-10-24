from django import template

from wishlist.models import WishlistItem

register = template.Library()


@register.simple_tag(takes_context=True)
def is_saved(context, product):
    request = context["request"]
    if not hasattr(request, "_wishlist_ids"):
        request._wishlist_ids = set(WishlistItem.objects.filter(customer=request.user).values_list("product_id", flat=True))
    return product.pk in request._wishlist_ids
