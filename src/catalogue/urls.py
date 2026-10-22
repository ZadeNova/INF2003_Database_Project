from django.urls import path
from . import views

app_name = "catalogue"
urlpatterns = [
    path("", views.product_list, name="product_list"),
    path("category/<slug:slug>/", views.category_detail, name="category_detail"),
    path("shops/<int:pk>/", views.seller_shop, name="seller_shop"),
    path("photos/<str:file_id>/", views.product_photo, name="product_photo"),
    path("<int:pk>/", views.product_detail, name="product_detail"),
]
