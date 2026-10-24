from django.urls import path
from . import views

app_name = "wishlist"
urlpatterns = [
    path("wishlist/", views.WishlistView.as_view(), name="list"),
    path("wishlist/<int:pk>/add/", views.WishlistActionView.as_view(), {"saved": True}, name="add"),
    path("wishlist/<int:pk>/remove/", views.WishlistActionView.as_view(), {"saved": False}, name="remove"),
    path("alerts/", views.AlertsView.as_view(), name="alerts"),
]
