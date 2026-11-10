from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView
from django.views.generic.edit import CreateView

from catalogue.models import Product, PurchasableProduct
from config import ratelimit
from config.ids import BIGINT_MAX
from orders.models import Order

from .audit import AUDIT_LABELS, SELLER_ACTIONS, StaleAction, allowed_actions, change_seller_status
from .forms import AuditFilterForm, CustomerCreationForm, ReasonForm, SellerApplicationForm
from .mixins import (
    AnySellerMixin,
    CustomerRequiredMixin,
    OperatorRequiredMixin,
    SellerRequiredMixin,
    landing_url,
    safe_local_path,
)
from .models import AuditLog, CustomerProfile, Seller, User


class RoleLoginView(LoginView):
    """Each role lands on its own home; `next` is honoured only as a same-site path."""

    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def get_redirect_url(self):
        target = self.request.POST.get(self.redirect_field_name, self.request.GET.get(self.redirect_field_name, ""))
        return safe_local_path(self.request, target) or ""

    def get_default_redirect_url(self):
        return landing_url(self.request.user)

    def post(self, request, *args, **kwargs):
        # Counted before the password is checked, so parallel guesses cannot overshoot the limit (Redis; fails open).
        attempt = ratelimit.start_login(request)
        if attempt.blocked:
            return ratelimit.too_many_requests(attempt.retry_after, back_url=request.path, back_label="Back to sign in")
        response = super().post(request, *args, **kwargs)
        if request.user.is_authenticated:
            ratelimit.login_succeeded(attempt)
        else:
            ratelimit.login_failed(attempt)
        return response


class AnonymousOnlyMixin:
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(landing_url(request.user))
        return super().dispatch(request, *args, **kwargs)


class UsernameTakenMixin:
    """Two sign-ups for the same name (ignoring case) at once both pass the form's check; the database refuses the second."""

    def username_taken(self, form, error):
        if not any(name in str(error) for name in ("user_username_ci_unique", "accounts_user_username_key")):
            raise error
        form.add_error("username", "A user with that username already exists.")
        return self.form_invalid(form)


class RegisterView(UsernameTakenMixin, AnonymousOnlyMixin, CreateView):
    form_class = CustomerCreationForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("accounts:login")

    def form_valid(self, form):
        try:
            with transaction.atomic():
                user = form.save(commit=False)
                user.role = User.Role.CUSTOMER
                user.save()
                CustomerProfile.objects.create(
                    user=user,
                    zip_prefix=form.cleaned_data["zip_prefix"],
                    city=form.cleaned_data["city"],
                    state=form.cleaned_data["state"],
                )
        except IntegrityError as error:
            return self.username_taken(form, error)
        self.object = user
        messages.success(self.request, "Account created. You can now log in.")
        return redirect(self.success_url)


class SellerApplyView(UsernameTakenMixin, AnonymousOnlyMixin, CreateView):
    """One transaction creates the seller's user and a pending seller row; neither exists without the other."""

    form_class = SellerApplicationForm
    template_name = "accounts/seller_apply.html"
    success_url = reverse_lazy("accounts:login")

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            with transaction.atomic():
                user = form.save(commit=False)
                user.role = User.Role.SELLER
                user.save()
                Seller.objects.create(
                    user=user,
                    status=Seller.Status.PENDING,
                    shop_name=data["shop_name"],
                    city=data["city"],
                    state=data["state"],
                    zip_prefix=data["zip_prefix"],
                )
        except IntegrityError as error:
            return self.username_taken(form, error)
        self.object = user
        messages.success(self.request, "Application submitted. Log in to follow its status.")
        return redirect(self.success_url)


class AccountView(CustomerRequiredMixin, TemplateView):
    template_name = "accounts/account.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            profile=CustomerProfile.objects.filter(user=self.request.user).first(), **kwargs
        )


class SellerHomeView(SellerRequiredMixin, TemplateView):
    """Read-only seller centre; every figure is filtered by the logged-in seller."""

    template_name = "accounts/seller_home.html"

    def get_context_data(self, **kwargs):
        products = Product.objects.filter(seller=self.seller)
        return super().get_context_data(
            seller=self.seller,
            product_count=products.count(),
            visible_count=products.filter(pk__in=PurchasableProduct.objects.values("id")).count(),
            order_count=Order.objects.filter(seller=self.seller).count(),
            **kwargs,
        )


class SellerStatusView(AnySellerMixin, TemplateView):
    template_name = "accounts/seller_status.html"

    def get_context_data(self, **kwargs):
        decision = (
            AuditLog.objects.filter(table_name="accounts_seller", row_id=str(self.seller.pk))
            .order_by("-created_at", "-id")
            .first()
        )
        return super().get_context_data(seller=self.seller, decision=decision, **kwargs)


class OperatorSellerListView(OperatorRequiredMixin, ListView):
    template_name = "operator/seller_list.html"
    paginate_by = 25
    context_object_name = "sellers"

    def get_queryset(self):
        status = self.request.GET.get("status", Seller.Status.PENDING)
        self.status = status if status in Seller.Status.values else Seller.Status.PENDING
        return Seller.objects.filter(status=self.status).select_related("user").order_by("id")

    def get_context_data(self, **kwargs):
        counts = dict.fromkeys(Seller.Status.values, 0)
        counts.update(Seller.objects.order_by().values_list("status").annotate(n=Count("id")))
        return super().get_context_data(status=self.status, counts=counts, statuses=Seller.Status.values, **kwargs)


def seller_detail_context(seller, form=None, failed_action=None):
    return {
        "seller": seller,
        "actions": [
            (action, form if action == failed_action else ReasonForm(prefix=action))
            for action in allowed_actions(seller.status)
        ],
        "history": (
            AuditLog.objects.filter(table_name="accounts_seller", row_id=str(seller.pk))
            .select_related("actor")
            .order_by("-created_at", "-id")[:10]
        ),
        "product_count": Product.objects.filter(seller=seller).count(),
    }


class OperatorSellerDetailView(OperatorRequiredMixin, DetailView):
    template_name = "operator/seller_detail.html"
    queryset = Seller.objects.select_related("user")

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), **seller_detail_context(self.object)}


class OperatorSellerActionView(OperatorRequiredMixin, View):
    """POST only. The service locks the seller, rechecks the expected status and sets the audit context."""

    http_method_names = ["post"]

    def post(self, request, pk, action):
        if action not in SELLER_ACTIONS:
            raise Http404
        seller = get_object_or_404(Seller.objects.select_related("user"), pk=pk)
        form = ReasonForm(request.POST, prefix=action)
        if not form.is_valid():
            return render(
                request, "operator/seller_detail.html", seller_detail_context(seller, form, action), status=400
            )
        try:
            change_seller_status(seller.pk, action, request.user, form.cleaned_data["reason"])
        except StaleAction:
            seller.refresh_from_db()
            messages.error(
                request,
                f"No change made: {seller.display_name} is already {seller.get_status_display().lower()}. "
                "Another operator may have acted first.",
            )
            return redirect("accounts:operator_seller", pk=seller.pk)
        messages.success(request, f"{AUDIT_LABELS['seller.' + action]} {seller.display_name}.")
        return redirect("accounts:operator_seller", pk=seller.pk)


class OperatorAuditView(OperatorRequiredMixin, ListView):
    template_name = "operator/audit_list.html"
    paginate_by = 25
    context_object_name = "entries"

    def get_queryset(self):
        self.filters = AuditFilterForm(self.request.GET)
        entries = AuditLog.objects.select_related("actor").order_by("-created_at", "-id")
        self.query = {}
        if self.filters.is_valid():
            actor, action = self.filters.cleaned_data["actor"], self.filters.cleaned_data["action"]
            if actor == "system":
                entries = entries.filter(actor__isnull=True)
            elif actor:
                entries = entries.filter(actor_id=int(actor))
            if action:
                entries = entries.filter(action=action)
            self.query = {key: value for key, value in self.filters.cleaned_data.items() if value}
        return entries

    def get_context_data(self, **kwargs):
        context = super().get_context_data(filters=self.filters, query=urlencode(self.query), **kwargs)
        # Resolve each audited row on this page to its current shop: one query per record type, ids bound as values.
        entries = context["entries"]
        lookups = {
            "accounts_seller": lambda ids: {pk: (None, seller) for pk, seller in Seller.objects.in_bulk(ids).items()},
            "orders_order": lambda ids: {
                order.pk: (None, order.seller) for order in Order.objects.filter(pk__in=ids).select_related("seller")
            },
            "catalogue_product": lambda ids: {
                product.pk: (product, product.seller)
                for product in Product.objects.filter(pk__in=ids).select_related("seller")
            },
        }
        wanted = {}
        for entry in entries:
            entry.shop = entry.product = None
            if entry.table_name in lookups and entry.row_id.isdecimal() and 0 < int(entry.row_id) <= BIGINT_MAX:
                wanted.setdefault(entry.table_name, set()).add(int(entry.row_id))
        found = {table: lookups[table](ids) for table, ids in wanted.items()}
        for entry in entries:
            if entry.table_name in found and entry.row_id.isdecimal():
                entry.product, entry.shop = found[entry.table_name].get(int(entry.row_id), (None, None))
        return context
