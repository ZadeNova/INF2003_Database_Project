from django.urls import path
from . import operator_views, seller_views, views

app_name = "catalogue"
urlpatterns = [
    path("", views.product_list, name="product_list"),
    path("mine/", seller_views.SellerProductListView.as_view(), name="seller_products"),
    path("mine/new/", seller_views.SellerProductEditView.as_view(), name="product_create"),
    path("mine/<int:pk>/edit/", seller_views.SellerProductEditView.as_view(), name="product_edit"),
    path("mine/<int:pk>/deactivate/", seller_views.SellerProductDeactivateView.as_view(), name="product_deactivate"),
    path("operator/", operator_views.OperatorProductListView.as_view(), name="operator_products"),
    path("operator/<int:pk>/", operator_views.OperatorProductView.as_view(), name="operator_product"),
    path("operator/categories/", operator_views.OperatorCategoryListView.as_view(), name="operator_categories"),
    path("operator/categories/<int:pk>/", operator_views.OperatorCategoryView.as_view(), name="operator_category"),
    path("category/<slug:slug>/", views.category_detail, name="category_detail"),
    path("shops/<int:pk>/", views.seller_shop, name="seller_shop"),
    path("photos/<str:file_id>/", views.product_photo, name="product_photo"),
    path("<int:pk>/", views.product_detail, name="product_detail"),
]
