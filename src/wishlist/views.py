import json

from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from accounts.mixins import CustomerRequiredMixin, safe_local_path
from catalogue.models import Product
from catalogue.search import attach_photos, visible_products
from config import mongo

from .models import RestockAlert, WishlistItem
from .services import set_saved, visible_alerts


class WishlistView(CustomerRequiredMixin, View):
    http_method_names = ["get", "head"]

    def get(self, request):
        saved = WishlistItem.objects.filter(customer=request.user).values("product_id")
        products = visible_products().filter(pk__in=saved).order_by("-wishlistitem__added_at")
        # The reverse join must be scoped too: other customers' save dates must not duplicate or reorder rows.
        products = products.filter(wishlistitem__customer=request.user)
        page = Paginator(products, 24).get_page(request.GET.get("page"))
        with mongo.database() as database:
            page.object_list = attach_photos(database, page.object_list)
        return render(request, "wishlist/list.html", {"page_obj": page})


class WishlistActionView(CustomerRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk, saved):
        set_saved(request.user, pk, saved)
        if request.headers.get("HX-Request") == "true":
            item = get_object_or_404(Product, pk=pk)
            response = render(
                request,
                "wishlist/_button.html",
                {"product": item, "wishlist_next": safe_local_path(request, request.POST.get("next"))},
            )
            response["HX-Trigger"] = json.dumps(
                {
                    "wishlistChanged": {
                        "product_id": pk,
                        "saved": WishlistItem.objects.filter(customer=request.user, product_id=pk).exists(),
                    }
                }
            )
            return response
        return redirect(safe_local_path(request, request.POST.get("next")) or "wishlist:list")


class AlertsView(CustomerRequiredMixin, View):
    http_method_names = ["get", "head"]

    def get(self, request):
        with transaction.atomic():
            alerts = visible_alerts(request.user).select_related("product").order_by("-created_at", "-pk")
            page = Paginator(alerts, 25).get_page(request.GET.get("page"))
            page.object_list = list(page.object_list)
            if request.method == "GET":
                RestockAlert.objects.filter(
                    customer=request.user, pk__in=[a.pk for a in page], seen_at__isnull=True
                ).update(seen_at=timezone.now())
        return render(request, "wishlist/alerts.html", {"page_obj": page})
