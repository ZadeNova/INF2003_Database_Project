from django.core.paginator import Paginator
from django.shortcuts import render
from django.views import View

from accounts.mixins import SellerRequiredMixin

from .services import seller_insights


class InsightsView(SellerRequiredMixin, View):
    http_method_names = ["get", "head"]

    def get(self, request):
        context = seller_insights(self.seller)
        context["page_obj"] = Paginator(context["insights"], 25).get_page(request.GET.get("page"))
        return render(request, "activity/insights.html", context)
