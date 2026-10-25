from django.urls import path

from . import views

app_name = "orders"
urlpatterns = [
    path("cart/", views.CartView.as_view(), name="cart"),
    path("cart/add/<int:pk>/", views.CartAddView.as_view(), name="cart_add"),
    path("cart/lines/<int:pk>/quantity/", views.CartChangeView.as_view(), {"action": "quantity"}, name="cart_quantity"),
    path("cart/lines/<int:pk>/remove/", views.CartChangeView.as_view(), {"action": "remove"}, name="cart_remove"),
    path("checkout/", views.ReviewView.as_view(), name="review"),
    path("checkouts/<int:pk>/", views.CheckoutDetailView.as_view(), name="checkout_detail"),
    path("orders/", views.HistoryView.as_view(), name="history"),
    path("orders/<int:pk>/", views.OrderDetailView.as_view(), name="order_detail"),
    path("orders/<int:pk>/cancel/", views.CancelView.as_view(), name="cancel"),
    path("seller/orders/", views.SellerOrdersView.as_view(), name="seller_orders"),
    path("seller/orders/<int:pk>/ship/", views.ShipView.as_view(), name="ship"),
    path("operator/orders/", views.OperatorOrdersView.as_view(), name="operator_orders"),
    path("operator/orders/<int:pk>/deliver/", views.DeliverView.as_view(), name="deliver"),
]
