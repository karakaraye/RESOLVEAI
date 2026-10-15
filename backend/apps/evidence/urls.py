from django.urls import path
from .views import (
    ComplaintEvidenceListView,
    ComplaintEvidenceCreateView,
    EvidenceVerifyView,
)

app_name = "evidence"

urlpatterns = [
    path(
        "complaints/<uuid:complaint_id>/evidence",
        ComplaintEvidenceListView.as_view(),
        name="complaint-evidence-list"
    ),
    path(
        "complaints/<uuid:complaint_id>/evidence/create",
        ComplaintEvidenceCreateView.as_view(),
        name="complaint-evidence-create"
    ),
    path(
        "evidence/<uuid:evidence_id>/verify",
        EvidenceVerifyView.as_view(),
        name="evidence-verify"
    ),
]
