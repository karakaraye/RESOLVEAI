from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class DeliveryResult:
    """
    Structured outcome of a communication delivery attempt.
    """
    status: str  # SUBMITTED, ACCEPTED, DELIVERED, FAILED, TIMED_OUT
    provider_message_id: str
    provider_reference: str
    provider_response: Dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 45
    error_detail: str = ""
    is_transient: bool = False


class BaseCommunicationAdapter(ABC):
    """
    Abstract interface for messaging providers.
    All adapters (Email, SMS, WhatsApp) implement these methods to support
    uniform dispatch, status tracking, and reconciliation.
    """
    channel: str = "UNKNOWN"
    provider_name: str = "BaseProvider"

    @abstractmethod
    def send_message(
        self,
        recipient: str,
        content: str,
        subject: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> DeliveryResult:
        """
        Submits message payload to the downstream provider.
        """
        pass

    @abstractmethod
    def check_delivery_status(self, provider_message_id: str) -> DeliveryResult:
        """
        Polls or verifies downstream delivery receipt for reconciliation.
        """
        pass
