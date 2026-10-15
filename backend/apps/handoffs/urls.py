from django.urls import path
from .views import (
    ComplaintForwardingOptionsView,
    ComplaintHandoffCreateView,
    HandoffListView,
    HandoffSummaryCountsView,
    HandoffRetryView,
    OperationsHealthView,
)

urlpatterns = [
    path("complaints/<uuid:pk>/forwarding-options", ComplaintForwardingOptionsView.as_view(), name="complaint-forwarding-options"),
    path("complaints/<uuid:pk>/handoffs", ComplaintHandoffCreateView.as_view(), name="complaint-handoff-create"),
    path("handoffs", HandoffListView.as_view(), name="handoff-list"),
    path("handoffs/summary", HandoffSummaryCountsView.as_view(), name="handoff-summary-counts"),
    path("handoffs/<uuid:pk>/retry", HandoffRetryView.as_view(), name="handoff-retry"),
    path("operations/health", OperationsHealthView.as_view(), name="operations-health"),
]
