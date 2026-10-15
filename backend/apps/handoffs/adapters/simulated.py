import logging
import uuid
from typing import Optional
from django.utils import timezone

from .base import BaseDeliveryAdapter, DeliveryResult

logger = logging.getLogger("resolveai.handoffs.adapters")


class SimulatedBankDeliveryAdapter(BaseDeliveryAdapter):
    """
    Synthetic banking delivery adapter for development and testing.
    Simulates reliable submission, confirmed delivery, transient/permanent errors,
    network timeouts with uncertain outcomes, and approved fallback switching.
    Never initiates production SMS, email, WhatsApp, or external banking requests.
    """

    def __init__(self, mode: Optional[str] = None):
        """
        mode: Optional forced simulation mode:
            - 'SUCCESS_DELIVERED': Immediate delivery confirmation
            - 'SUCCESS_SENT': Submitted, delivery unconfirmed
            - 'TRANSIENT_FAILURE': Temporary connection drop / queue busy
            - 'PERMANENT_FAILURE': Rejected / unknown destination
            - 'TIMEOUT_UNCERTAIN': Transmission timeout; delivery outcome in doubt
            - 'FALLBACK_TRIGGER': Primary fails, requiring fallback channel
        """
        self.mode = mode

    def dispatch(
        self,
        handoff,
        channel: str,
        attempt_number: int = 1
    ) -> DeliveryResult:
        mode = self.mode

        # If not explicitly forced, inspect handoff metadata or recipient for test hints
        if not mode:
            recipient = (handoff.recipient or "").lower()
            msg = (handoff.message or "").lower()
            if "sim:transient" in recipient or "sim:transient" in msg:
                mode = "TRANSIENT_FAILURE"
            elif "sim:permanent" in recipient or "sim:permanent" in msg:
                mode = "PERMANENT_FAILURE"
            elif "sim:timeout" in recipient or "sim:timeout" in msg:
                mode = "TIMEOUT_UNCERTAIN"
            elif "sim:unconfirmed" in recipient or "sim:unconfirmed" in msg:
                mode = "SUCCESS_SENT"
            elif "sim:fallback" in recipient or "sim:fallback" in msg:
                mode = "FALLBACK_TRIGGER"
            else:
                mode = "SUCCESS_DELIVERED"

        transmission_id = f"TX-SYNTH-{uuid.uuid4().hex[:10].upper()}"
        timestamp = timezone.now().isoformat()

        if mode == "TRANSIENT_FAILURE":
            logger.warning(f"Simulating transient transmission failure on channel '{channel}' for handoff {handoff.id}")
            return DeliveryResult(
                success=False,
                status="SEND_FAILED",
                outcome_message=f"Temporary network error: queue connection dropped on {channel}.",
                evidence={
                    "transmissionId": transmission_id,
                    "channel": channel,
                    "attempt": attempt_number,
                    "timestamp": timestamp,
                    "errorCode": "QUEUE_TEMPORARILY_UNAVAILABLE",
                    "synthetic": True,
                },
                is_transient=True,
                is_uncertain=False,
                error_code="QUEUE_TEMPORARILY_UNAVAILABLE",
            )

        if mode == "PERMANENT_FAILURE":
            logger.warning(f"Simulating permanent delivery failure on channel '{channel}' for handoff {handoff.id}")
            return DeliveryResult(
                success=False,
                status="SEND_FAILED",
                outcome_message=f"Permanent rejection: recipient or channel '{channel}' is invalid or unroutable.",
                evidence={
                    "transmissionId": transmission_id,
                    "channel": channel,
                    "attempt": attempt_number,
                    "timestamp": timestamp,
                    "errorCode": "DESTINATION_REJECTED",
                    "synthetic": True,
                },
                is_transient=False,
                is_uncertain=False,
                error_code="DESTINATION_REJECTED",
            )

        if mode == "TIMEOUT_UNCERTAIN":
            logger.warning(f"Simulating socket timeout with uncertain delivery outcome on channel '{channel}' for handoff {handoff.id}")
            return DeliveryResult(
                success=False,
                status="DELIVERY_UNCONFIRMED",
                outcome_message=f"Connection timed out after 30s. Submission initiated but delivery receipt unconfirmed on {channel}.",
                evidence={
                    "transmissionId": transmission_id,
                    "channel": channel,
                    "attempt": attempt_number,
                    "timestamp": timestamp,
                    "timeoutSeconds": 30,
                    "status": "IN_DOUBT",
                    "synthetic": True,
                },
                is_transient=True,
                is_uncertain=True,
                error_code="SOCKET_TIMEOUT_UNCERTAIN",
            )

        if mode == "FALLBACK_TRIGGER":
            # Primary channel fails so service will switch to fallback channel
            if channel == handoff.team.channel and handoff.team.fallback_channel:
                logger.info(f"Simulating primary channel failure to trigger approved fallback on handoff {handoff.id}")
                return DeliveryResult(
                    success=False,
                    status="SEND_FAILED",
                    outcome_message=f"Primary channel '{channel}' unavailable. Escalating to approved fallback channel.",
                    evidence={
                        "transmissionId": transmission_id,
                        "channel": channel,
                        "attempt": attempt_number,
                        "timestamp": timestamp,
                        "errorCode": "PRIMARY_CHANNEL_UNAVAILABLE",
                        "fallbackSuggested": handoff.team.fallback_channel,
                        "synthetic": True,
                    },
                    is_transient=True,
                    is_uncertain=False,
                    error_code="PRIMARY_CHANNEL_UNAVAILABLE",
                )
            # If already on fallback, succeed
            mode = "SUCCESS_DELIVERED"

        if mode == "SUCCESS_SENT":
            logger.info(f"Simulating successful submission with unconfirmed receipt on channel '{channel}' for handoff {handoff.id}")
            return DeliveryResult(
                success=True,
                status="SENT",
                outcome_message=f"Submitted through {channel}. Awaiting delivery confirmation receipt.",
                evidence={
                    "transmissionId": transmission_id,
                    "channel": channel,
                    "attempt": attempt_number,
                    "timestamp": timestamp,
                    "deliveryReceiptReceived": False,
                    "synthetic": True,
                },
                is_uncertain=False,
            )

        # Default: SUCCESS_DELIVERED
        logger.info(f"Simulating successful delivery confirmation on channel '{channel}' for handoff {handoff.id}")
        return DeliveryResult(
            success=True,
            status="DELIVERED",
            outcome_message=f"Confirmed delivered by {channel} gateway. Receipt token recorded.",
            evidence={
                "transmissionId": transmission_id,
                "channel": channel,
                "attempt": attempt_number,
                "timestamp": timestamp,
                "deliveryReceiptReceived": True,
                "receiptToken": f"ACK-{uuid.uuid4().hex[:8].upper()}",
                "synthetic": True,
            },
            is_uncertain=False,
        )

    def reconcile_status(
        self,
        handoff,
        external_transmission_id: str
    ) -> DeliveryResult:
        """
        Simulates querying the banking switch / message gateway audit logs
        to reconcile an uncertain transmission without duplicating the message.
        """
        logger.info(f"Reconciling uncertain transmission {external_transmission_id} for handoff {handoff.id}")
        return DeliveryResult(
            success=True,
            status="DELIVERED",
            outcome_message=f"Reconciliation query confirmed prior transmission {external_transmission_id} was successfully accepted by receiving gateway.",
            evidence={
                "reconciledTransmissionId": external_transmission_id,
                "reconciledAt": timezone.now().isoformat(),
                "statusConfirmed": "DELIVERED",
                "synthetic": True,
            },
            is_uncertain=False,
        )
