from django.urls import path

from . import views

app_name = "dashboard"
urlpatterns = [
    path("operator/dashboard/", views.DashboardView.as_view(), name="home"),
    path("operator/dashboard/refresh/", views.RefreshView.as_view(), name="refresh"),
]
