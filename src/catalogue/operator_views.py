from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from accounts.mixins import OperatorRequiredMixin
from config import mongo

from .models import Category, Product
from .seller_forms import TemplateAttributeForm
from .services import moderate_product


class ProductReasonForm(forms.Form):
    reason = forms.CharField(
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Tell the seller why you are changing this product.",
    )


class OperatorProductListView(OperatorRequiredMixin, View):
    http_method_names = ["get", "head"]

    def get(self, request):
        products = Product.objects.select_related("seller", "category").order_by("-id")
        query = request.GET.get("q", "").strip()[:200]
        status = request.GET.get("status", "all")
        if query:
            products = products.filter(name__icontains=query)
        if status == "taken_down":
            products = products.filter(taken_down=True)
        page = Paginator(products, 25).get_page(request.GET.get("page"))
        return render(request, "catalogue/operator_products.html", {"page_obj": page, "q": query, "status": status})


class OperatorProductView(OperatorRequiredMixin, View):
    http_method_names = ["get", "head", "post"]

    def get(self, request, pk):
        item = get_object_or_404(Product.objects.select_related("seller", "category"), pk=pk)
        return render(request, "catalogue/operator_product.html", {"product": item, "form": ProductReasonForm()})

    def post(self, request, pk):
        item = get_object_or_404(Product.objects.select_related("seller", "category"), pk=pk)
        form = ProductReasonForm(request.POST)
        if form.is_valid():
            try:
                moderate_product(request.user, pk, request.POST.get("action"), form.cleaned_data["reason"])
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, "Product decision saved.")
                return redirect("catalogue:operator_product", pk=pk)
        return render(request, "catalogue/operator_product.html", {"product": item, "form": form}, status=400)


class OperatorCategoryListView(OperatorRequiredMixin, View):
    http_method_names = ["get", "head"]

    def get(self, request):
        with mongo.client() as client:
            templates = {row["category_id"]: row for row in client[mongo.database_name()].category_templates.find({})}
        categories = list(Category.objects.order_by("name_en"))
        for category in categories:
            category.template = templates.get(category.pk)
        return render(request, "catalogue/operator_categories.html", {"categories": categories})


class OperatorCategoryView(OperatorRequiredMixin, View):
    http_method_names = ["get", "head", "post"]

    def context(self, category, form):
        with mongo.client() as client:
            template = client[mongo.database_name()].category_templates.find_one({"category_id": category.pk})
        return {"category": category, "template": template, "form": form}

    def get(self, request, pk):
        category = get_object_or_404(Category, pk=pk)
        return render(request, "catalogue/operator_category.html", self.context(category, TemplateAttributeForm()))

    def post(self, request, pk):
        category = get_object_or_404(Category, pk=pk)
        form = TemplateAttributeForm(request.POST)
        if form.is_valid():
            name, definition = form.cleaned_data["name"], form.cleaned_data["definition"]
            with mongo.client() as client:
                result = client[mongo.database_name()].category_templates.update_one(
                    {"category_id": category.pk, "attributes." + name: {"$exists": False}},
                    {"$set": {"attributes." + name: definition}, "$inc": {"version": 1}},
                )
            if result.matched_count == 1:
                messages.success(request, "Product option added. Sellers can fill it in now.")
                return redirect("catalogue:operator_category", pk=pk)
            form.add_error("name", "That name already exists, or this category is temporarily unavailable.")
        return render(request, "catalogue/operator_category.html", self.context(category, form), status=400)
