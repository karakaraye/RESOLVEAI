from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.complaints.models import Complaint
from .models import AIProcessingJob
from .serializers import (
    AIProcessingJobSerializer,
    ClassificationSuggestionSerializer,
    FindingSerializer,
    SimilarComplaintSerializer,
)
from .services.classifier import ComplaintClassificationService
from .services.coordinator import ComplaintIntelligenceCoordinator
from .services.similarity import SimilaritySearchService


class ComplaintClassificationView(APIView):
    """
    POST /api/v1/complaints/{id}/intelligence/classify
    Analyzes complaint text and returns classification recommendations.
    Does NOT automatically overwrite human-entered category/priority.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk=None):
        complaint = get_object_or_404(Complaint, id=pk, tenant=request.user.tenant)
        service = ComplaintClassificationService()
        result = service.classify_complaint(complaint)
        serializer = ClassificationSuggestionSerializer(result)
        return Response(serializer.data, status=status.HTTP_200_OK)


from django.db import transaction
from .models import AIProcessingJob, ComplaintIntelligenceFinding
from .tasks import process_complaint_intelligence_task


class ComplaintIntelligenceAnalyzeView(APIView):
    """
    POST /api/v1/complaints/{id}/intelligence/analyze
    Triggers end-to-end evidence-grounded intelligence pipeline asynchronously via Celery worker.
    Returns findings strictly conforming to the frontend `Finding` schema.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk=None):
        complaint = get_object_or_404(Complaint, id=pk, tenant=request.user.tenant)
        force_refresh = request.data.get("forceRefresh", False)
        idempotency_key = request.headers.get("X-Idempotency-Key")

        coordinator = ComplaintIntelligenceCoordinator()
        fprint = coordinator.compute_fingerprint(complaint)
        job_key = idempotency_key or f"job-{complaint.id}-{fprint[:16]}"

        # 1. Duplicate job detection: if identical job is currently in progress, do not spawn another
        in_flight_job = AIProcessingJob.objects.filter(
            tenant=complaint.tenant,
            complaint=complaint,
            idempotency_key=job_key,
            status__in=[AIProcessingJob.Status.PENDING, AIProcessingJob.Status.PROCESSING]
        ).first()

        existing_finding = ComplaintIntelligenceFinding.objects.filter(
            tenant=complaint.tenant,
            complaint=complaint
        ).first()

        if in_flight_job:
            # Job is already being processed asynchronously
            if existing_finding:
                serializer = FindingSerializer(existing_finding)
                return Response(serializer.data, status=status.HTTP_200_OK, headers={"X-Job-Status": in_flight_job.status})
            return Response(
                {
                    "availability": "AVAILABLE",
                    "facts": ["Intelligence analysis job in progress by background worker."],
                    "hypotheses": [],
                    "evidence": [],
                },
                status=status.HTTP_200_OK,
                headers={"X-Job-Status": in_flight_job.status}
            )

        # 2. Check if cached findings are fresh and no force_refresh
        if existing_finding and not force_refresh and existing_finding.content_fingerprint == fprint:
            serializer = FindingSerializer(existing_finding)
            return Response(serializer.data, status=status.HTTP_200_OK)

        # 3. Create durable AIProcessingJob in PENDING state
        with transaction.atomic():
            job, created = AIProcessingJob.objects.update_or_create(
                tenant=complaint.tenant,
                idempotency_key=job_key,
                defaults={
                    "complaint": complaint,
                    "job_type": AIProcessingJob.JobType.FULL_INTELLIGENCE,
                    "status": AIProcessingJob.Status.PENDING,
                    "attempts": 0,
                    "error_message": "",
                }
            )

            # Enqueue task post-commit
            complaint_id_str = str(complaint.id)
            transaction.on_commit(
                lambda: process_complaint_intelligence_task.delay(
                    complaint_id=complaint_id_str,
                    force_refresh=force_refresh,
                    job_key=job_key,
                )
            )

        if existing_finding:
            serializer = FindingSerializer(existing_finding)
            return Response(serializer.data, status=status.HTTP_200_OK, headers={"X-Job-Id": str(job.id)})

        # Return prompt initial structure while background worker completes
        return Response(
            {
                "availability": "AVAILABLE",
                "facts": [],
                "hypotheses": [],
                "evidence": [],
            },
            status=status.HTTP_200_OK,
            headers={"X-Job-Id": str(job.id), "X-Job-Status": "PENDING"}
        )


class ComplaintSimilarView(APIView):
    """
    GET /api/v1/complaints/{id}/similar
    Returns semantic similar complaints for the same tenant.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk=None):
        complaint = get_object_or_404(Complaint, id=pk, tenant=request.user.tenant)
        limit = int(request.query_params.get("limit", 5))
        threshold = float(request.query_params.get("threshold", 0.50))

        service = SimilaritySearchService()
        similar_candidates = service.find_similar_complaints(
            complaint=complaint,
            limit=limit,
            threshold=threshold
        )
        serializer = SimilarComplaintSerializer(similar_candidates, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ComplaintAIJobsView(APIView):
    """
    GET /api/v1/complaints/{id}/intelligence/jobs
    Returns processing jobs and status for the complaint.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk=None):
        complaint = get_object_or_404(Complaint, id=pk, tenant=request.user.tenant)
        jobs = AIProcessingJob.objects.filter(
            tenant=request.user.tenant,
            complaint=complaint
        ).order_by("-created_at")
        serializer = AIProcessingJobSerializer(jobs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
