import uuid
from urllib.parse import urlencode

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache

from accounts.mixins import CustomerRequiredMixin, OperatorRequiredMixin, SellerRequiredMixin

from .forms import OrderFilterForm, PaymentForm
from .models import Checkout, Order, OrderLine
from .services import (
    CheckoutError,
    add_to_cart,
    cart_review,
    change_order_status,
    checkout,
    remove_from_cart,
    set_cart_quantity,
)


@method_decorator(never_cache, name="dispatch")
class CartView(CustomerRequiredMixin, View):
    def get(self, request):
        return render(request, "orders/cart.html", cart_review(request.user))


class CartAddView(CustomerRequiredMixin, View):
    def post(self, request, pk):
        error = None
        try:
            add_to_cart(request.user, pk, request.POST.get("quantity", "1"))
        except CheckoutError as exc:
            error = str(exc)
        if request.headers.get("HX-Request") == "true":
            return render(request, "orders/_cart_added.html", {"error": error})
        (messages.error if error else messages.success)(request, error or "Added to your cart.")
        return redirect("orders:cart")


class CartChangeView(CustomerRequiredMixin, View):
    def post(self, request, pk, action):
        error = None
        try:
            if action == "remove":
                remove_from_cart(request.user, pk)
            else:
                set_cart_quantity(request.user, pk, request.POST.get("quantity"))
        except CheckoutError as exc:
            error = str(exc)
        if request.headers.get("HX-Request") == "true":
            context = cart_review(request.user)
            context["error"] = error
            return render(request, "orders/_cart.html", context)
        if error:
            messages.error(request, error)
        return redirect("orders:cart")


@method_decorator(never_cache, name="dispatch")
class ReviewView(CustomerRequiredMixin, View):
    def get(self, request):
        context = cart_review(request.user)
        context["form"] = PaymentForm(
            initial={
                "idempotency_key": uuid.uuid4(),
                "fingerprint": context["fingerprint"],
                "method": "credit_card",
                "instalments": 1,
            }
        )
        return render(request, "orders/review.html", context)

    def post(self, request):
        form = PaymentForm(request.POST)
        if form.is_valid():
            try:
                record = checkout(
                    request.user,
                    form.cleaned_data["idempotency_key"],
                    form.cleaned_data["fingerprint"],
                    [{"method": form.cleaned_data["method"], "instalments": form.cleaned_data["instalments"]}],
                )
            except CheckoutError as exc:
                messages.error(request, str(exc))
                return redirect("orders:review")
            messages.success(request, "Payment received. Each shop will prepare its order.")
            return redirect("orders:checkout_detail", pk=record.pk)
        context = cart_review(request.user)
        context["form"] = form
        return render(request, "orders/review.html", context, status=400)


@method_decorator(never_cache, name="dispatch")
class HistoryView(CustomerRequiredMixin, View):
    def get(self, request):
        records = (
            Checkout.objects.filter(customer=request.user)
            .prefetch_related("orders__seller")
            .order_by("-placed_at", "-pk")
        )
        return render(
            request, "orders/history.html", {"page_obj": Paginator(records, 20).get_page(request.GET.get("page"))}
        )


@method_decorator(never_cache, name="dispatch")
class CheckoutDetailView(CustomerRequiredMixin, View):
    def get(self, request, pk):
        record = get_object_or_404(
            Checkout.objects.filter(customer=request.user).prefetch_related("orders__seller", "payments"), pk=pk
        )
        return render(request, "orders/checkout_detail.html", {"checkout": record})


@method_decorator(never_cache, name="dispatch")
class OrderDetailView(CustomerRequiredMixin, View):
    def get(self, request, pk):
        order = get_object_or_404(
            Order.objects.filter(checkout__customer=request.user)
            .select_related("seller", "checkout", "refund")
            .prefetch_related(Prefetch("lines", queryset=OrderLine.objects.select_related("product").order_by("pk"))),
            pk=pk,
        )
        return render(request, "orders/order_detail.html", {"order": order})


class CancelView(CustomerRequiredMixin, View):
    def post(self, request, pk):
        try:
            change_order_status(request.user, pk, "cancel", request.POST.get("reason", ""))
        except CheckoutError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Order cancelled. Your payment for this shop has been refunded.")
        return redirect("orders:order_detail", pk=pk)


@method_decorator(never_cache, name="dispatch")
class SellerOrdersView(SellerRequiredMixin, View):
    def get(self, request):
        filters = OrderFilterForm(request.GET)
        orders = (
            filters.apply(Order.objects.filter(seller=self.seller))
            .select_related(
                "seller"
            )  # not the checkout: it is shared by every seller in the basket and hidden from them
            .order_by("-placed_at", "-pk")
        )
        query = (
            urlencode({key: value for key, value in filters.cleaned_data.items() if value})
            if filters.is_valid()
            else ""
        )
        return render(
            request,
            "orders/manage_orders.html",
            {
                "page_obj": Paginator(orders, 20).get_page(request.GET.get("page")),
                "seller_mode": True,
                "filters": filters,
                "query": query,
            },
        )


class ShipView(SellerRequiredMixin, View):
    def post(self, request, pk):
        try:
            change_order_status(request.user, pk, "ship")
        except CheckoutError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Order marked shipped.")
        return redirect("orders:seller_orders")


@method_decorator(never_cache, name="dispatch")
class OperatorOrdersView(OperatorRequiredMixin, View):
    def get(self, request):
        filters = OrderFilterForm(request.GET)
        orders = filters.apply(Order.objects.all()).select_related("checkout", "seller").order_by("-placed_at", "-pk")
        query = (
            urlencode({key: value for key, value in filters.cleaned_data.items() if value})
            if filters.is_valid()
            else ""
        )
        return render(
            request,
            "orders/manage_orders.html",
            {
                "page_obj": Paginator(orders, 20).get_page(request.GET.get("page")),
                "seller_mode": False,
                "filters": filters,
                "query": query,
            },
        )


class DeliverView(OperatorRequiredMixin, View):
    def post(self, request, pk):
        try:
            change_order_status(request.user, pk, "deliver")
        except CheckoutError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Order marked delivered.")
        return redirect("orders:operator_orders")
