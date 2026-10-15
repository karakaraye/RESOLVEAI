import logging
from celery import shared_task
from django.db import transaction

logger = logging.getLogger("resolveai.communications.tasks")


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def dispatch_customer_communication_task(self, communication_id: str):
    """
    Celery background worker task for reliable customer message delivery.
    Executes outside HTTP request lifecycle.
    Idempotent, transactional, with revalidation of complaint status.
    """
    from apps.communications.services import CustomerCommunicationService

    logger.info(f"[Celery Worker] Starting dispatch for communication {communication_id}")
    try:
        comm = CustomerCommunicationService.dispatch_communication(communication_id)
        if not comm:
            logger.error(f"[Celery Worker] Communication {communication_id} not found.")
            return {"communication_id": communication_id, "status": "NOT_FOUND"}

        logger.info(f"[Celery Worker] Communication {communication_id} dispatch finished in state {comm.status}")
        return {
            "communication_id": str(comm.id),
            "status": comm.status,
            "category": comm.category,
            "channel": comm.channel,
        }
    except Exception as exc:
        logger.exception(f"[Celery Worker] Error dispatching communication {communication_id}: {exc}")
        # Retry with exponential backoff for unexpected worker errors
        raise self.retry(exc=exc)


@shared_task
def reconcile_unconfirmed_communications_task():
    """
    Celery Beat task to reconcile unconfirmed deliveries.
    Checks delivery receipts for messages in DELIVERY_UNCONFIRMED state.
    """
    from apps.communications.models import CustomerCommunication, CommunicationEvent
    from apps.communications.adapters import get_communication_adapter
    from django.utils import timezone

    unconfirmed = CustomerCommunication.objects.filter(
        status=CustomerCommunication.Status.DELIVERY_UNCONFIRMED
    )[:50]

    reconciled_count = 0
    for comm in unconfirmed:
        adapter = get_communication_adapter(comm.channel)
        res = adapter.check_delivery_status(comm.provider_message_id)
        if res.status == "DELIVERED":
            with transaction.atomic():
                comm = CustomerCommunication.objects.select_for_update().get(id=comm.id)
                comm.status = CustomerCommunication.Status.DELIVERED
                comm.delivered_at = timezone.now()
                comm.save(update_fields=["status", "delivered_at", "updated_at"])

                CommunicationEvent.objects.create(
                    communication=comm,
                    event_type="RECONCILED",
                    title="Delivery receipt confirmed via provider poll",
                    detail=f"Reconciled via receipt token {res.provider_reference}.",
                    actor="Reconciliation Worker",
                )
                reconciled_count += 1

    return {"reconciled_count": reconciled_count}
