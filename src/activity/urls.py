from django.urls import path

from .views import InsightsView

app_name = "activity"
urlpatterns = [path("seller/insights/", InsightsView.as_view(), name="insights")]
