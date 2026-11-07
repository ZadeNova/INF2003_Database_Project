from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.views import View

from accounts.mixins import CustomerRequiredMixin, OperatorRequiredMixin, SellerRequiredMixin
from catalogue.models import Product
from config import mongo

from .forms import ModerationForm, ReviewForm
from .queries import review_page
from .services import customer_line, moderate_review, write_review


class CustomerReviewView(CustomerRequiredMixin, View):
    http_method_names = ["get", "head", "post"]

    def get(self, request, line_id):
        try:
            line = customer_line(request.user, line_id)
        except ValidationError:
            raise Http404 from None
        with mongo.client() as client:
            review = client[mongo.database_name()].reviews.find_one(
                {"order_line_id": line.pk, "customer_id": request.user.pk}
            )
        form = ReviewForm(
            initial={"score": review["score"], "title": review["title_en"], "text": review["text_en"]} if review else {}
        )
        return render(request, "reviews/form.html", {"line": line, "review": review, "form": form})

    def post(self, request, line_id):
        try:
            line = customer_line(request.user, line_id)
        except ValidationError:
            raise Http404 from None
        action = request.POST.get("action")
        form = ReviewForm(request.POST)
        if action == "delete" or form.is_valid():
            with mongo.client() as client:
                existing = client[mongo.database_name()].reviews.find_one(
                    {"order_line_id": line.pk, "customer_id": request.user.pk}, {"taken_down": 1}
                )
            try:
                write_review(request.user, line_id, action, form.cleaned_data if action != "delete" else None)
            except ValidationError as error:
                form.add_error(None, error)
            else:
                if action == "delete":
                    messages.success(request, "Review deleted.")
                elif existing and existing.get("taken_down"):
                    messages.info(request, "Review saved, but it stays hidden until an operator restores it.")
                else:
                    messages.success(request, "Review saved.")
                return redirect("orders:order_detail", pk=line.order_id)
        with mongo.client() as client:
            review = client[mongo.database_name()].reviews.find_one(
                {"order_line_id": line.pk, "customer_id": request.user.pk}
            )
        return render(request, "reviews/form.html", {"line": line, "review": review, "form": form}, status=400)


class SellerReviewsView(SellerRequiredMixin, View):
    http_method_names = ["get", "head"]

    def get(self, request):
        ids = list(Product.objects.filter(seller=self.seller).values_list("pk", flat=True))
        with mongo.client() as client:
            page = review_page(
                client[mongo.database_name()],
                {"seller_id": self.seller.pk, "product_id": {"$in": ids}},
                request.GET.get("page"),
            )
        return render(request, "reviews/list.html", {"page_obj": page, "seller_view": True})


class OperatorReviewsView(OperatorRequiredMixin, View):
    http_method_names = ["get", "head"]

    def get(self, request):
        with mongo.client() as client:
            page = review_page(client[mongo.database_name()], {}, request.GET.get("page"), include_hidden=True)
        return render(request, "reviews/list.html", {"page_obj": page})


class OperatorReviewView(OperatorRequiredMixin, View):
    http_method_names = ["get", "head", "post"]

    def context(self, line_id, form=None):
        with mongo.client() as client:
            review = client[mongo.database_name()].reviews.find_one({"order_line_id": line_id})
        if review is None:
            raise Http404
        return {
            "review": review,
            "form": form or ModerationForm(initial={"action": "restore" if review.get("taken_down") else "takedown"}),
        }

    def get(self, request, line_id):
        return render(request, "reviews/moderate.html", self.context(line_id))

    def post(self, request, line_id):
        form = ModerationForm(request.POST)
        if form.is_valid():
            try:
                moderate_review(request.user, line_id, **form.cleaned_data)
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, "Review decision saved.")
                return redirect("reviews:operator_review", line_id=line_id)
        return render(request, "reviews/moderate.html", self.context(line_id, form), status=400)
