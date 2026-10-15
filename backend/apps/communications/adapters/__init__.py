from .base import BaseCommunicationAdapter, DeliveryResult
from .simulated import (
    SimulatedEmailAdapter,
    SimulatedSMSAdapter,
    SimulatedWhatsAppAdapter,
    get_communication_adapter,
)

__all__ = [
    "BaseCommunicationAdapter",
    "DeliveryResult",
    "SimulatedEmailAdapter",
    "SimulatedSMSAdapter",
    "SimulatedWhatsAppAdapter",
    "get_communication_adapter",
]
