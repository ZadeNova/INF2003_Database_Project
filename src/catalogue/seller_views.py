from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from accounts.mixins import SellerRequiredMixin
from config import mongo
from config.ids import BIGINT_MAX

from .models import Category, Product
from .seller_forms import ProductForm
from .services import StaleProductError, deactivate_product, save_product


class SellerProductListView(SellerRequiredMixin, View):
    http_method_names = ["get", "head"]

    def get(self, request):
        products = Product.objects.filter(seller=self.seller).select_related("category").order_by("-id")
        # PostgreSQL text cannot hold a NUL byte; a hand-made URL would otherwise end in a 500.
        query = request.GET.get("q", "").replace("\x00", "").strip()[:200]
        if query:
            products = products.filter(name__icontains=query)
        page = Paginator(products, 25).get_page(request.GET.get("page"))
        return render(request, "catalogue/seller_products.html", {"seller": self.seller, "page_obj": page, "q": query})


class SellerProductEditView(SellerRequiredMixin, View):
    http_method_names = ["get", "head", "post"]

    def product(self, pk):
        return get_object_or_404(Product, pk=pk, seller=self.seller, taken_down=False) if pk is not None else None

    def form(self, request, item, data=None):
        # The category is still validated by ModelChoiceField; this conversion only chooses template fields.
        raw = request.POST.get("category") if request.method == "POST" else request.GET.get("category")
        try:
            selected = (
                int(raw)
                if raw
                else item.category_id
                if item
                else Category.objects.order_by("name_en").values_list("pk", flat=True).first()
            )
            selected = selected if selected is not None and 0 < selected <= BIGINT_MAX else None
        except (TypeError, ValueError):
            selected = None
        with mongo.database() as database:
            template = database.category_templates.find_one({"category_id": selected})
            spec = database.product_specs.find_one({"_id": item.pk}) if item else None
        bound = request.method == "POST"
        form = ProductForm(
            (request.POST if data is None else data) if bound else None,
            request.FILES if bound else None,
            instance=item,
            template=template,
            spec=spec,
            initial={"category": selected},
        )
        return form

    def get(self, request, pk=None):
        item = self.product(pk)
        return render(
            request,
            "catalogue/product_form.html",
            {"product": item, "form": self.form(request, item), "categories": Category.objects.order_by("name_en")},
        )

    def post(self, request, pk=None):
        item = self.product(pk)
        form = self.form(request, item)
        if form.is_valid():
            try:
                save_product(self.seller, request.user, form.cleaned_data, pk=pk)
            except StaleProductError as error:
                # Keep what the seller typed, but expect the live values from now on so a second save can succeed.
                refreshed = request.POST.copy()
                refreshed["expected_stock"] = str(error.live["stock"])
                refreshed["expected_price"] = str(error.live["price"])
                form = self.form(request, item, data=refreshed)
                form.add_error(None, error)
                if request.FILES.get("photo"):
                    form.add_error(None, "Choose your photo again: a browser cannot keep a selected file.")
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, "Product saved.")
                return redirect("catalogue:seller_products")
        return render(
            request,
            "catalogue/product_form.html",
            {"product": item, "form": form, "categories": Category.objects.order_by("name_en")},
            status=400,
        )


class SellerProductDeactivateView(SellerRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        deactivate_product(self.seller, request.user, pk)
        messages.success(request, "Product deactivated.")
        return redirect("catalogue:seller_products")
