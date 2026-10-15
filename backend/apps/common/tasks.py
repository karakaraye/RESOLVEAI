import logging
from celery import shared_task
from django.utils import timezone

from .models import OutboxMessage

logger = logging.getLogger("resolveai.common.tasks")


@shared_task(
    name="apps.common.tasks.dispatch_outbox_messages_task",
    ignore_result=True,
)
def dispatch_outbox_messages_task():
    """
    Periodic Celery Beat task scanning for PENDING transactional outbox messages.
    Ensures work survives process restarts and network interruptions.
    """
    pending_msgs = OutboxMessage.objects.filter(
        status=OutboxMessage.Status.PENDING
    ).order_by("created_at")[:50]

    processed_count = 0

    for msg in pending_msgs:
        try:
            msg.status = OutboxMessage.Status.PROCESSING
            msg.save(update_fields=["status"])

            topic = msg.topic
            payload = msg.payload or {}

            if topic == "handoffs.dispatch":
                from apps.handoffs.tasks import dispatch_handoff_task
                handoff_id = payload.get("handoff_id")
                if handoff_id:
                    dispatch_handoff_task.delay(handoff_id)

            elif topic == "intelligence.analyze":
                from apps.intelligence.tasks import process_complaint_intelligence_task
                complaint_id = payload.get("complaint_id")
                force_refresh = payload.get("force_refresh", False)
                job_key = payload.get("job_key")
                if complaint_id:
                    process_complaint_intelligence_task.delay(
                        complaint_id=complaint_id,
                        force_refresh=force_refresh,
                        job_key=job_key,
                    )

            elif topic == "communication.dispatch":
                from apps.communications.tasks import dispatch_customer_communication_task
                communication_id = payload.get("communication_id")
                if communication_id:
                    dispatch_customer_communication_task.delay(communication_id)

            msg.status = OutboxMessage.Status.PUBLISHED
            msg.processed_at = timezone.now()
            msg.save(update_fields=["status", "processed_at"])
            processed_count += 1

        except Exception as e:
            logger.error(f"Failed to publish outbox message {msg.id}: {e}", exc_info=True)
            msg.status = OutboxMessage.Status.FAILED
            msg.retry_count += 1
            msg.last_error = str(e)
            msg.save(update_fields=["status", "retry_count", "last_error"])

    return {"processed_count": processed_count}
