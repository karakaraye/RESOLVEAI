from django.urls import path
from .views import DataSourceListView

urlpatterns = [
    path("data-sources", DataSourceListView.as_view(), name="data-sources-list"),
]
