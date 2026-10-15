from django.urls import path

from .views import (
    ComplaintAIJobsView,
    ComplaintClassificationView,
    ComplaintIntelligenceAnalyzeView,
    ComplaintSimilarView,
)

urlpatterns = [
    path("complaints/<uuid:pk>/intelligence/classify", ComplaintClassificationView.as_view(), name="complaint-classify"),
    path("complaints/<uuid:pk>/intelligence/analyze", ComplaintIntelligenceAnalyzeView.as_view(), name="complaint-analyze"),
    path("complaints/<uuid:pk>/similar", ComplaintSimilarView.as_view(), name="complaint-similar"),
    path("complaints/<uuid:pk>/intelligence/jobs", ComplaintAIJobsView.as_view(), name="complaint-ai-jobs"),
]
