from django.urls import path

from . import views

app_name = "reviews"
urlpatterns = [
    path("reviews/line/<int:line_id>/", views.CustomerReviewView.as_view(), name="write"),
    path("seller/reviews/", views.SellerReviewsView.as_view(), name="seller_reviews"),
    path("operator/reviews/", views.OperatorReviewsView.as_view(), name="operator_reviews"),
    path("operator/reviews/<int:line_id>/", views.OperatorReviewView.as_view(), name="operator_review"),
]
