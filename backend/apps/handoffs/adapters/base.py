from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class DeliveryResult:
    """
    Standard outcome returned by delivery channel adapters.
    """
    success: bool
    status: str  # PREPARED, SENT, DELIVERY_UNCONFIRMED, DELIVERED, SEND_FAILED
    outcome_message: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    is_uncertain: bool = False
    is_transient: bool = False
    error_code: str = ""


class BaseDeliveryAdapter(ABC):
    """
    Abstract interface for bank channel transmission adapters.
    """
    @abstractmethod
    def dispatch(
        self,
        handoff,
        channel: str,
        attempt_number: int = 1
    ) -> DeliveryResult:
        """
        Dispatches the handoff through the designated banking channel.
        """
        raise NotImplementedError

    @abstractmethod
    def reconcile_status(
        self,
        handoff,
        external_transmission_id: str
    ) -> DeliveryResult:
        """
        Reconciles in-doubt or uncertain transmission status with external provider logs.
        """
        raise NotImplementedError
