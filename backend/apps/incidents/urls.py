from django.urls import path

from .views import (
    IncidentComplaintLinkView,
    IncidentComplaintUnlinkView,
    IncidentConfirmView,
    IncidentDetailView,
    IncidentDetectView,
    IncidentListView,
)

urlpatterns = [
    path("incidents", IncidentListView.as_view(), name="incident-list"),
    path("incidents/detect", IncidentDetectView.as_view(), name="incident-detect"),
    path("incidents/<uuid:pk>", IncidentDetailView.as_view(), name="incident-detail"),
    path("incidents/<uuid:pk>/confirm", IncidentConfirmView.as_view(), name="incident-confirm"),
    path("incidents/<uuid:pk>/complaints/link", IncidentComplaintLinkView.as_view(), name="incident-complaint-link"),
    path("incidents/<uuid:pk>/complaints/unlink", IncidentComplaintUnlinkView.as_view(), name="incident-complaint-unlink"),
]
