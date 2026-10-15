from django.urls import path
from .views import (
    CategoriesReferenceView,
    ComplaintListView,
    ComplaintDetailView,
    ComplaintEligibleAssigneesView,
    ComplaintAssignmentView,
    ComplaintNotesView,
    ComplaintFollowUpsView,
    ComplaintResolutionView,
    ComplaintVerificationView,
    ComplaintReopenView,
    ComplaintForwardingOptionsView,
    WorkspaceSummaryView,
    IngestionEventsView,
)

urlpatterns = [
    path("reference/categories", CategoriesReferenceView.as_view(), name="categories-reference"),
    path("workspace/summary", WorkspaceSummaryView.as_view(), name="workspace-summary"),
    path("complaints", ComplaintListView.as_view(), name="complaint-list"),
    path("complaints/<uuid:pk>", ComplaintDetailView.as_view(), name="complaint-detail"),
    path("complaints/<uuid:pk>/eligible-assignees", ComplaintEligibleAssigneesView.as_view(), name="complaint-assignees"),
    path("complaints/<uuid:pk>/assignment", ComplaintAssignmentView.as_view(), name="complaint-assignment"),
    path("complaints/<uuid:pk>/notes", ComplaintNotesView.as_view(), name="complaint-notes"),
    path("complaints/<uuid:pk>/follow-ups", ComplaintFollowUpsView.as_view(), name="complaint-follow-ups"),
    path("complaints/<uuid:pk>/resolution", ComplaintResolutionView.as_view(), name="complaint-resolution"),
    path("complaints/<uuid:pk>/resolution/verification", ComplaintVerificationView.as_view(), name="complaint-verification"),
    path("complaints/<uuid:pk>/reopen", ComplaintReopenView.as_view(), name="complaint-reopen"),
    path("complaints/<uuid:pk>/forwarding-options", ComplaintForwardingOptionsView.as_view(), name="complaint-forwarding-options"),
    path("ingestion/events", IngestionEventsView.as_view(), name="ingestion-events"),
]
