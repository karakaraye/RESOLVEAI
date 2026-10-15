from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class BankSystemAdapter(ABC):
    """
    Abstract contract for bank integration adapters.
    Provides standard read-only querying for core banking ledgers,
    payment switch sessions, and transaction verification.

    IMPORTANT SAFETY GUARANTEE:
    This adapter contract is strictly read-only. It NEVER executes
    financial transfers, fund debits, or live ledger reversals.
    """

    @abstractmethod
    def fetch_account(self, account_number: str) -> dict[str, Any] | None:
        """Fetches masked customer account metadata and current status."""
        pass

    @abstractmethod
    def fetch_transactions(
        self,
        account_number: str | None = None,
        reference: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Queries ledger entries for an account or specific reference
        within an optional datetime window.
        """
        pass

    @abstractmethod
    def check_switch_status(
        self,
        session_id: str | None = None,
        rrn: str | None = None,
        stan: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Queries electronic payment switch (NIBSS / Interswitch / Postilion)
        session state using Session ID, Retrieval Reference Number (RRN), or STAN.
        """
        pass

    @abstractmethod
    def fetch_reversal_logs(self, reference: str) -> list[dict[str, Any]]:
        """
        Queries automatic or manual reversal journal entries related to a transaction.
        """
        pass
