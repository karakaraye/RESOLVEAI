import logging
from celery import shared_task

logger = logging.getLogger("resolveai.intelligence.tasks")


@shared_task(
    bind=True,
    name="apps.intelligence.tasks.process_complaint_intelligence_task",
    max_retries=3,
    default_retry_delay=5,
    acks_late=True,
)
def process_complaint_intelligence_task(
    self,
    complaint_id: str,
    force_refresh: bool = False,
    job_key: str = None,
):
    """
    Celery background worker task for complaint classification, embedding generation,
    semantic similarity, and root-cause processing.
    Executes AI workloads outside the HTTP request process.
    """
    logger.info(f"[Celery Worker] Starting AI intelligence pipeline for complaint {complaint_id}")
    try:
        from apps.complaints.models import Complaint
        from .services.coordinator import ComplaintIntelligenceCoordinator

        complaint = Complaint.objects.select_related("tenant", "category").get(id=complaint_id)
        coordinator = ComplaintIntelligenceCoordinator()

        finding, job = coordinator.process_complaint_intelligence(
            complaint=complaint,
            force_refresh=force_refresh,
            idempotency_key=job_key,
        )

        logger.info(f"[Celery Worker] AI pipeline completed for complaint {complaint.reference}: finding={finding.id}")
        return {
            "complaint_id": str(complaint.id),
            "reference": complaint.reference,
            "job_id": str(job.id),
            "status": job.status,
            "availability": finding.availability,
        }

    except Exception as exc:
        logger.error(f"[Celery Worker] AI pipeline failed for complaint {complaint_id}: {exc}", exc_info=True)
        # Update job record to FAILED or RETRYING
        try:
            from .models import AIProcessingJob
            if job_key:
                AIProcessingJob.objects.filter(idempotency_key=job_key).update(
                    status=AIProcessingJob.Status.FAILED,
                    error_message=str(exc)
                )
        except Exception:
            pass
        raise self.retry(exc=exc, countdown=min(60, 2 ** self.request.retries * 5))
