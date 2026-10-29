from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect, resolve_url
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .models import Seller, User


class HtmxLoginRequiredMixin(LoginRequiredMixin):
    def handle_no_permission(self):
        if not self.request.user.is_authenticated and self.request.headers.get("HX-Request") == "true":
            return HttpResponse(status=200, headers={"HX-Redirect": resolve_url(self.get_login_url())})
        return super().handle_no_permission()


class RoleRequiredMixin(HtmxLoginRequiredMixin):
    """Anonymous users go to login; a logged-in user with another role gets 403.

    The role (and a seller's status) is read from the database on every request, so a change made by an
    operator applies to sessions that are already logged in.
    """

    role = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.role != self.role:
            raise PermissionDenied
        denied = self.check_access(request)
        if denied is not None:
            return denied
        return super().dispatch(request, *args, **kwargs)

    def check_access(self, request):
        return None


class CustomerRequiredMixin(RoleRequiredMixin):
    role = User.Role.CUSTOMER


class OperatorRequiredMixin(RoleRequiredMixin):
    role = User.Role.OPERATOR


class AnySellerMixin(RoleRequiredMixin):
    """Any seller, whatever their status: only for the seller's own status page."""

    role = User.Role.SELLER

    def check_access(self, request):
        self.seller = Seller.objects.filter(user=request.user).first()
        if self.seller is None:
            raise PermissionDenied
        return None


class SellerRequiredMixin(AnySellerMixin):
    """Approved sellers only. Pending, rejected and suspended sellers are sent to their status page (GET) or
    refused (any other method)."""

    def check_access(self, request):
        super().check_access(request)
        if self.seller.status == Seller.Status.APPROVED:
            return None
        if request.method in ("GET", "HEAD"):
            return redirect("accounts:seller_status")
        raise PermissionDenied


def landing_url(user):
    """Where a user lands after login: the shop, the seller centre (or status page) or the operator console."""
    if user.role == User.Role.OPERATOR:
        return reverse("accounts:operator_sellers")
    if user.role == User.Role.SELLER:
        status = Seller.objects.filter(user=user).values_list("status", flat=True).first()
        return reverse("accounts:seller_home" if status == Seller.Status.APPROVED else "accounts:seller_status")
    return reverse("catalogue:product_list")


def safe_local_path(request, target):
    """A same-site path for `next`, or None. Absolute URLs, scheme-relative and backslash tricks are refused."""
    if not target or not target.startswith("/") or target.startswith(("//", "/\\")):
        return None
    if not url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return None
    return target
