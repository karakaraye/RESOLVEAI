import logging
from datetime import datetime
from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.common.models import AuditEvent
from apps.complaints.models import Complaint, ComplaintTimelineEvent
from .adapters.simulated import SimulatedBankAdapter
from .models import TransactionInvestigation

logger = logging.getLogger("resolveai.transactions")


class TransactionInvestigationService:
    """
    Manages transaction investigations, ledger reconciliation,
    and banking source conflict detection.

    Enforces pessimistic row-level locking via select_for_update() to prevent
    contradictory updates from concurrent investigations.
    """

    @classmethod
    @transaction.atomic
    def link_transaction(
        cls,
        complaint: Complaint,
        txn_data: dict,
        user=None,
    ) -> TransactionInvestigation:
        """
        Links or updates a transaction investigation record on a complaint.
        Applies select_for_update() concurrency control on the parent complaint.
        """
        # Concurrency control: Exclusive pessimistic row lock on the complaint
        complaint = Complaint.objects.select_for_update().get(
            id=complaint.id, tenant=complaint.tenant
        )

        reference = txn_data.get("reference", "").strip()
        if not reference:
            raise ValidationError("Transaction reference is required.")

        occurred_at = txn_data.get("occurred_at")
        if isinstance(occurred_at, str):
            occurred_at = parse_datetime(occurred_at)

        last_updated_at = txn_data.get("last_updated_at")
        if isinstance(last_updated_at, str):
            last_updated_at = parse_datetime(last_updated_at)
        elif not last_updated_at:
            last_updated_at = timezone.now()

        amount_val = txn_data.get("amount_value")
        if amount_val is not None and not isinstance(amount_val, Decimal):
            amount_val = Decimal(str(amount_val))

        conflict = txn_data.get("conflict")
        # Ensure standard banking discrepancy phrasing when conflict exists
        if conflict and not conflict.startswith("Sources disagree:"):
            conflict = f"Sources disagree: {conflict}"
        if conflict and "No final outcome is assumed" not in conflict:
            conflict = f"{conflict}. No final outcome is assumed."

        investigation, created = TransactionInvestigation.objects.update_or_create(
            tenant=complaint.tenant,
            complaint=complaint,
            reference=reference,
            defaults={
                "source_system": txn_data.get("source_system", "Core banking"),
                "amount_value": amount_val,
                "amount_currency": txn_data.get("amount_currency", "NGN"),
                "occurred_at": occurred_at,
                "status_label": txn_data.get("status_label", "Debited"),
                "status": txn_data.get("status", TransactionInvestigation.SourceStatus.AVAILABLE),
                "last_updated_at": last_updated_at,
                "conflict": conflict,
                "match_evidence": txn_data.get("match_evidence", ""),
            },
        )

        actor = (
            user.display_name
            if user and hasattr(user, "display_name")
            else "Banking Adapter"
        )

        action_title = (
            f"Linked transaction {investigation.reference}"
            if created
            else f"Refreshed transaction {investigation.reference}"
        )
        amt_display = (
            f"{investigation.amount_currency} {investigation.amount_value:,.2f}"
            if investigation.amount_value is not None
            else "unspecified amount"
        )
        detail_msg = f"{investigation.source_system} · {amt_display} · Status: {investigation.status_label}"
        if investigation.conflict:
            detail_msg += f" · [Discrepancy: {investigation.conflict}]"

        ComplaintTimelineEvent.objects.create(
            complaint=complaint,
            tenant=complaint.tenant,
            kind="TRANSACTION_LINKED",
            title=action_title,
            detail=detail_msg,
            actor=actor,
        )

        AuditEvent.objects.create(
            tenant_id=complaint.tenant.id,
            user=user if user and user.is_authenticated else None,
            action="complaint.transaction_investigation_updated",
            entity_type="Complaint",
            entity_id=str(complaint.id),
            details={
                "investigation_id": str(investigation.id),
                "reference": investigation.reference,
                "source_system": investigation.source_system,
                "conflict": bool(investigation.conflict),
            },
        )

        logger.info(
            f"Linked transaction {investigation.reference} to complaint {complaint.reference} (Created: {created})"
        )
        return investigation

    @classmethod
    @transaction.atomic
    def search_and_link_from_bank_adapter(
        cls,
        complaint: Complaint,
        user=None,
    ) -> list[TransactionInvestigation]:
        """
        Executes automated lookup against the SimulatedBankAdapter using
        customer account, references from grievance narrative, and timestamp windows.
        Links all matching transaction records and evaluates ledger discrepancies.
        """
        # Concurrency control: Exclusive pessimistic row lock on the complaint
        complaint = Complaint.objects.select_for_update().get(
            id=complaint.id, tenant=complaint.tenant
        )

        adapter = SimulatedBankAdapter()
        linked_records = []

        # 1. Identify search criteria
        account_number = None
        if complaint.customer and complaint.customer.account_number:
            account_number = complaint.customer.account_number

        reference_query = None
        # Check if complaint narrative mentions a specific transaction or session reference
        for word in complaint.narrative.replace(",", " ").replace(".", " ").replace(":", " ").split():
            clean_word = word.strip()
            if any(clean_word.startswith(prefix) for prefix in ("TXN-", "ATM-", "CRD-", "FEE-", "CORP-", "999014")):
                reference_query = clean_word
                break

        # 2. Query simulated bank systems
        transactions_found = adapter.fetch_transactions(
            account_number=account_number,
            reference=reference_query,
        )

        # 3. Link records
        for txn in transactions_found:
            inv = cls.link_transaction(
                complaint=complaint,
                txn_data=txn,
                user=user,
            )
            linked_records.append(inv)

        return linked_records
