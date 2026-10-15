import logging
from celery import shared_task

logger = logging.getLogger("resolveai.handoffs.tasks")


@shared_task(
    bind=True,
    name="apps.handoffs.tasks.dispatch_handoff_task",
    max_retries=3,
    default_retry_delay=5,
    acks_late=True,
)
def dispatch_handoff_task(self, handoff_id: str):
    """
    Celery background worker task for reliable out-of-process handoff dispatch.
    Executes channel transmission outside the HTTP request/response cycle.
    """
    logger.info(f"[Celery Worker] Starting dispatch for handoff {handoff_id}")
    try:
        from .services import HandoffService
        handoff = HandoffService.execute_dispatch(handoff_id)
        if handoff:
            logger.info(f"[Celery Worker] Handoff {handoff_id} finished in state {handoff.state}")
            return {
                "handoff_id": handoff_id,
                "state": handoff.state,
                "retry_count": handoff.retry_count,
            }
        return {"handoff_id": handoff_id, "error": "Handoff not found"}
    except Exception as exc:
        logger.error(f"[Celery Worker] Exception during dispatch of handoff {handoff_id}: {exc}", exc_info=True)
        # Bounded retry with exponential backoff
        raise self.retry(exc=exc, countdown=min(60, 2 ** self.request.retries * 5))


@shared_task(
    name="apps.handoffs.tasks.monitor_sla_and_escalations_task",
    ignore_result=True,
)
def monitor_sla_and_escalations_task():
    """
    Periodic Celery Beat task scanning for approaching deadlines and SLA breaches.
    """
    try:
        from .services import SLAMonitoringService
        result = SLAMonitoringService.monitor_active_handoffs()
        logger.debug(f"[Celery Beat] SLA scan completed: {result}")
        return result
    except Exception as exc:
        logger.error(f"[Celery Beat] SLA monitoring task failed: {exc}", exc_info=True)
        return {"error": str(exc)}
