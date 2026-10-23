from django.urls import reverse

from .models import Seller, User


def role_navigation(request):
    """Primary navigation links for the current role only; the shop is public and shown to everyone."""
    links = [("Shop", reverse("catalogue:product_list"), "catalogue:product_list")]
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        links.append(("Sell on Mercer", reverse("accounts:seller_apply"), "accounts:seller_apply"))
    elif user.role == User.Role.CUSTOMER:
        # checkout links
        links += [("Cart", reverse("orders:cart"), "orders:cart"),
                  ("Orders", reverse("orders:history"), "orders:history")]
        links.append(("My account", reverse("accounts:account"), "accounts:account"))
        links += [("Wishlist", reverse("wishlist:list"), "wishlist:list"),
                  ("Alerts", reverse("wishlist:alerts"), "wishlist:alerts")]
    elif user.role == User.Role.SELLER:
        status = Seller.objects.filter(user=user).values_list("status", flat=True).first()
        if status == Seller.Status.APPROVED:
            links.append(("Seller centre", reverse("accounts:seller_home"), "accounts:seller_home"))
            # catalogue links
            links.append(("My products", reverse("catalogue:seller_products"), "catalogue:seller_products"))
            # checkout links
            links.append(("My orders", reverse("orders:seller_orders"), "orders:seller_orders"))
            links.append(("My reviews", reverse("reviews:seller_reviews"), "reviews:seller_reviews"))
        links.append(("Seller status", reverse("accounts:seller_status"), "accounts:seller_status"))
    elif user.role == User.Role.OPERATOR:
        # checkout links
        links.append(("Orders", reverse("orders:operator_orders"), "orders:operator_orders"))
        links += [("Sellers", reverse("accounts:operator_sellers"), "accounts:operator_sellers"),
                  ("Audit log", reverse("accounts:operator_audit"), "accounts:operator_audit")]
        # catalogue links
        links += [("Products", reverse("catalogue:operator_products"), "catalogue:operator_products"),
                  ("Categories", reverse("catalogue:operator_categories"), "catalogue:operator_categories")]
        links.append(("Reviews", reverse("reviews:operator_reviews"), "reviews:operator_reviews"))
    return {"nav_links": links}
