from django.urls import path
from .views import ReportDetailView

urlpatterns = [
    path("reports/<slug:report_type>", ReportDetailView.as_view(), name="report-detail"),
]
