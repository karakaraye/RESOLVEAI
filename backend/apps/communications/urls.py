from django.urls import path
from .views import (
    ComplaintCommunicationsListView,
    CommunicationComplianceReportView,
    MessageTemplateListView,
    CustomerCommunicationRetryView,
)

urlpatterns = [
    path("complaints/<uuid:complaint_id>/communications", ComplaintCommunicationsListView.as_view(), name="complaint-communications-list"),
    path("communications/compliance-report", CommunicationComplianceReportView.as_view(), name="communication-compliance-report"),
    path("communications/templates", MessageTemplateListView.as_view(), name="communication-templates-list"),
    path("communications/<uuid:communication_id>/retry", CustomerCommunicationRetryView.as_view(), name="communication-retry"),
]
