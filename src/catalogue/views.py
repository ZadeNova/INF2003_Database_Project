from django.shortcuts import get_object_or_404, render
from django.core.paginator import Paginator
from django.views.decorators.http import require_safe

from config import mongo
from .models import Product, PurchasableProduct


def visible_products():
    return Product.objects.filter(pk__in=PurchasableProduct.objects.values("id")).select_related("category", "seller")


@require_safe
def product_list(request):
    page = Paginator(visible_products().order_by("id"), 24).get_page(request.GET.get("page"))
    return render(request, "catalogue/product_list.html", {"page_obj": page})


@require_safe
def product_detail(request, pk):
    product = get_object_or_404(visible_products(), pk=pk)
    with mongo.client() as client:
        spec = client[mongo.database_name()]["product_specs"].find_one({"_id": product.pk})
    return render(request, "catalogue/product_detail.html", {"product": product, "spec": spec})
