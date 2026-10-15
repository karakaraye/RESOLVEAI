import logging
import uuid
from typing import Optional, Dict, Any
from .base import BaseCommunicationAdapter, DeliveryResult

logger = logging.getLogger("resolveai.communications.adapters")


class SimulatedEmailAdapter(BaseCommunicationAdapter):
    channel = "EMAIL"
    provider_name = "SimulatedSendGridMailAdapter"

    def send_message(
        self,
        recipient: str,
        content: str,
        subject: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> DeliveryResult:
        meta = metadata or {}
        msg_id = f"eml_{uuid.uuid4().hex[:12]}"
        ref = f"SG-{uuid.uuid4().hex[:8].upper()}"

        logger.info(f"[SIMULATED_EMAIL] Sending to {recipient}: Subject='{subject}' (ID: {msg_id})")

        # Configurable test triggers
        if "invalid" in recipient.lower() or meta.get("simulate_permanent_failure"):
            return DeliveryResult(
                status="FAILED",
                provider_message_id=msg_id,
                provider_reference=ref,
                provider_response={"statusCode": 400, "message": "Invalid recipient mailbox"},
                latency_ms=85,
                error_detail="550 5.1.1 Recipient mailbox not found",
                is_transient=False,
            )

        if meta.get("simulate_transient_failure"):
            return DeliveryResult(
                status="FAILED",
                provider_message_id=msg_id,
                provider_reference=ref,
                provider_response={"statusCode": 429, "message": "Rate limit exceeded"},
                latency_ms=120,
                error_detail="429 Too Many Requests - Provider queue full",
                is_transient=True,
            )

        if meta.get("simulate_unconfirmed"):
            return DeliveryResult(
                status="ACCEPTED",
                provider_message_id=msg_id,
                provider_reference=ref,
                provider_response={"statusCode": 202, "status": "queued_at_relay"},
                latency_ms=65,
                error_detail="",
                is_transient=False,
            )

        # Default: Confirmed delivered
        return DeliveryResult(
            status="DELIVERED",
            provider_message_id=msg_id,
            provider_reference=ref,
            provider_response={"statusCode": 200, "status": "delivered_to_inbox", "tls": True},
            latency_ms=55,
            error_detail="",
            is_transient=False,
        )

    def check_delivery_status(self, provider_message_id: str) -> DeliveryResult:
        return DeliveryResult(
            status="DELIVERED",
            provider_message_id=provider_message_id,
            provider_reference=f"REC-{uuid.uuid4().hex[:8].upper()}",
            provider_response={"statusCode": 200, "status": "delivered_confirmed"},
            latency_ms=40,
        )


class SimulatedSMSAdapter(BaseCommunicationAdapter):
    channel = "SMS"
    provider_name = "SimulatedTwilioSMSAdapter"

    def send_message(
        self,
        recipient: str,
        content: str,
        subject: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> DeliveryResult:
        meta = metadata or {}
        msg_id = f"sms_{uuid.uuid4().hex[:12]}"
        ref = f"SM-{uuid.uuid4().hex[:8].upper()}"

        logger.info(f"[SIMULATED_SMS] Sending to {recipient}: Content='{content[:40]}...' (ID: {msg_id})")

        if "000000" in recipient or meta.get("simulate_permanent_failure"):
            return DeliveryResult(
                status="FAILED",
                provider_message_id=msg_id,
                provider_reference=ref,
                provider_response={"errorCode": 21211, "message": "Invalid Phone Number"},
                latency_ms=90,
                error_detail="Destination MSISDN unroutable",
                is_transient=False,
            )

        if meta.get("simulate_transient_failure"):
            return DeliveryResult(
                status="FAILED",
                provider_message_id=msg_id,
                provider_reference=ref,
                provider_response={"errorCode": 30008, "message": "Carrier Network Timeout"},
                latency_ms=150,
                error_detail="SMS gateway timeout - transient retryable",
                is_transient=True,
            )

        if meta.get("simulate_unconfirmed"):
            return DeliveryResult(
                status="ACCEPTED",
                provider_message_id=msg_id,
                provider_reference=ref,
                provider_response={"status": "sent", "channel": "SMPP"},
                latency_ms=70,
                error_detail="",
                is_transient=False,
            )

        return DeliveryResult(
            status="DELIVERED",
            provider_message_id=msg_id,
            provider_reference=ref,
            provider_response={"status": "delivered", "segments": 1},
            latency_ms=60,
            error_detail="",
            is_transient=False,
        )

    def check_delivery_status(self, provider_message_id: str) -> DeliveryResult:
        return DeliveryResult(
            status="DELIVERED",
            provider_message_id=provider_message_id,
            provider_reference=f"REC-{uuid.uuid4().hex[:8].upper()}",
            provider_response={"status": "delivery_receipt_received"},
            latency_ms=35,
        )


class SimulatedWhatsAppAdapter(BaseCommunicationAdapter):
    channel = "WHATSAPP"
    provider_name = "SimulatedMetaWhatsAppCloudAdapter"

    def send_message(
        self,
        recipient: str,
        content: str,
        subject: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> DeliveryResult:
        meta = metadata or {}
        msg_id = f"wamid.{uuid.uuid4().hex[:16]}"
        ref = f"WA-{uuid.uuid4().hex[:8].upper()}"

        logger.info(f"[SIMULATED_WHATSAPP] Sending to {recipient}: Content='{content[:40]}...' (ID: {msg_id})")

        if "invalid" in recipient.lower() or meta.get("simulate_permanent_failure"):
            return DeliveryResult(
                status="FAILED",
                provider_message_id=msg_id,
                provider_reference=ref,
                provider_response={"error": {"code": 131026, "message": "Receiver not registered on WhatsApp"}},
                latency_ms=95,
                error_detail="User not opted in or registered on WhatsApp",
                is_transient=False,
            )

        if meta.get("simulate_transient_failure"):
            return DeliveryResult(
                status="FAILED",
                provider_message_id=msg_id,
                provider_reference=ref,
                provider_response={"error": {"code": 500, "message": "Temporary service overload"}},
                latency_ms=110,
                error_detail="Meta Cloud API transient failure",
                is_transient=True,
            )

        if meta.get("simulate_unconfirmed"):
            return DeliveryResult(
                status="ACCEPTED",
                provider_message_id=msg_id,
                provider_reference=ref,
                provider_response={"messages": [{"id": msg_id, "message_status": "accepted"}]},
                latency_ms=50,
                error_detail="",
                is_transient=False,
            )

        return DeliveryResult(
            status="DELIVERED",
            provider_message_id=msg_id,
            provider_reference=ref,
            provider_response={"messages": [{"id": msg_id, "message_status": "read"}]},
            latency_ms=45,
            error_detail="",
            is_transient=False,
        )

    def check_delivery_status(self, provider_message_id: str) -> DeliveryResult:
        return DeliveryResult(
            status="DELIVERED",
            provider_message_id=provider_message_id,
            provider_reference=f"REC-{uuid.uuid4().hex[:8].upper()}",
            provider_response={"status": "read_receipt_confirmed"},
            latency_ms=30,
        )


def get_communication_adapter(channel: str) -> BaseCommunicationAdapter:
    """
    Returns simulated adapter instance for given channel.
    """
    channel_upper = (channel or "EMAIL").upper()
    if channel_upper == "SMS":
        return SimulatedSMSAdapter()
    elif channel_upper == "WHATSAPP":
        return SimulatedWhatsAppAdapter()
    return SimulatedEmailAdapter()
