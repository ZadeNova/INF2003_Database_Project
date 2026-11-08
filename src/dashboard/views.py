from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.views import View

from accounts.mixins import OperatorRequiredMixin

from .forms import DashboardFilters
from .services import as_of_date, dashboard_data, refresh_sales, sales_populated


def pager(rows, request, key):
    page = Paginator(rows, 25).get_page(request.GET.get(key))

    def url(number):
        query = request.GET.copy()
        query[key] = str(number)
        return "?" + query.urlencode() + "#" + key

    return {
        "page": page,
        "previous": url(page.previous_page_number()) if page.has_previous() else None,
        "next": url(page.next_page_number()) if page.has_next() else None,
    }


class DashboardView(OperatorRequiredMixin, View):
    http_method_names = ["get", "head"]

    def get(self, request):
        as_of = as_of_date()
        form = DashboardFilters(request.GET)
        context = {"as_of": as_of, "form": form}
        if not form.is_valid():
            return render(request, "dashboard/dashboard.html", context, status=400)
        if as_of is not None and sales_populated():
            category = form.cleaned_data.get("category")
            data = dashboard_data(as_of, category.pk if category else None, form.cleaned_data.get("seller"))
            latest = data["category_rows"][0]["month"] if data["category_rows"] else None
            chart = [row for row in data["category_rows"] if row["month"] == latest][:10]
            context.update(
                data,
                stock_pager=pager(data["stock_rows"], request, "stock"),
                category_pager=pager(data["category_rows"], request, "categories"),
                seller_pager=pager(data["seller_rows"], request, "sellers"),
                chart={"labels": [row["category"] for row in chart], "revenue": [str(row["revenue"]) for row in chart]},
                chart_month=latest,
                ready=True,
            )
        response = render(request, "dashboard/dashboard.html", context)
        if context.get("cache_status"):
            response["X-Cache"] = context["cache_status"].upper()  # HIT, MISS, WAIT, DOWN or OFF
        return response


class RefreshView(OperatorRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request):
        refresh_sales()
        messages.success(request, "Sales history refreshed.")
        return redirect("dashboard:home")
