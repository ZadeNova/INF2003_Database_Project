from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path("sell/apply/", views.SellerApplyView.as_view(), name="seller_apply"),
    path("login/", views.RoleLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("account/", views.AccountView.as_view(), name="account"),
    path("seller/", views.SellerHomeView.as_view(), name="seller_home"),
    path("seller/status/", views.SellerStatusView.as_view(), name="seller_status"),
    path("operator/", views.OperatorSellerListView.as_view(), name="operator_sellers"),
    path("operator/sellers/<int:pk>/", views.OperatorSellerDetailView.as_view(), name="operator_seller"),
    path("operator/sellers/<int:pk>/<slug:action>/", views.OperatorSellerActionView.as_view(), name="operator_seller_action"),
    path("operator/audit/", views.OperatorAuditView.as_view(), name="operator_audit"),
]
