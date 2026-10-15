import logging
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.common.models import AuditEvent
from apps.complaints.models import Complaint, ComplaintTimelineEvent
from apps.transactions.models import TransactionInvestigation
from .models import EvidenceRecord

logger = logging.getLogger("resolveai.evidence")


class EvidenceManagementService:
    """
    Manages authoritative evidence attachments, provenance tracking,
    and maker-checker evidence verification.

    Enforces pessimistic row-level locking via select_for_update() on parent complaints
    to ensure database consistency.
    """

    @classmethod
    @transaction.atomic
    def attach_evidence(
        cls,
        complaint: Complaint,
        evidence_data: dict,
        user=None,
    ) -> EvidenceRecord:
        """
        Attaches an authoritative evidence record to a complaint.
        Applies select_for_update() concurrency control on the parent complaint.
        """
        if user and not user.has_case_permission("evidence.create") and not user.has_case_permission("complaints.notes"):
            raise PermissionDenied("You do not have permission to attach evidence records.")

        # Concurrency control: Exclusive pessimistic row lock on the complaint
        complaint = Complaint.objects.select_for_update().get(
            id=complaint.id, tenant=complaint.tenant
        )

        doc_ref = (
            evidence_data.get("document_reference")
            or evidence_data.get("documentReference")
            or ""
        ).strip()
        title = (evidence_data.get("title") or "").strip()
        if not doc_ref or not title:
            raise ValidationError("Both document_reference and title are required for evidence records.")

        source_ts = evidence_data.get("source_timestamp") or evidence_data.get("sourceTimestamp")
        if isinstance(source_ts, str):
            source_ts = parse_datetime(source_ts)

        txn_inv = None
        txn_id = evidence_data.get("transaction_investigation_id") or evidence_data.get("transactionInvestigationId")
        txn_ref = evidence_data.get("transaction_reference") or evidence_data.get("transactionReference")
        if txn_id:
            txn_inv = TransactionInvestigation.objects.filter(
                id=txn_id, tenant=complaint.tenant
            ).first()
        elif txn_ref:
            txn_inv = TransactionInvestigation.objects.filter(
                reference=txn_ref, complaint=complaint, tenant=complaint.tenant
            ).first()

        evidence = EvidenceRecord.objects.create(
            tenant=complaint.tenant,
            complaint=complaint,
            transaction_investigation=txn_inv,
            kind=evidence_data.get("kind", EvidenceRecord.EvidenceKind.LEDGER_ENTRY),
            document_reference=doc_ref,
            title=title,
            summary=evidence_data.get("summary", ""),
            source_system=evidence_data.get("source_system") or evidence_data.get("sourceSystem") or "Core Banking",
            source_timestamp=source_ts,
            provenance=evidence_data.get("provenance", "Manually attached during case investigation"),
            data_freshness=evidence_data.get("data_freshness") or evidence_data.get("dataFreshness") or EvidenceRecord.DataFreshness.FRESH,
            raw_payload=evidence_data.get("raw_payload") or evidence_data.get("rawPayload") or {},
        )

        actor = (
            user.display_name
            if user and hasattr(user, "display_name")
            else "Investigation Engine"
        )

        ComplaintTimelineEvent.objects.create(
            complaint=complaint,
            tenant=complaint.tenant,
            kind="EVIDENCE_ATTACHED",
            title=f"Evidence document attached: {evidence.document_reference}",
            detail=f"{evidence.get_kind_display()} from {evidence.source_system} · {evidence.title}",
            actor=actor,
        )

        AuditEvent.objects.create(
            tenant_id=complaint.tenant.id,
            user=user if user and user.is_authenticated else None,
            action="complaint.evidence_attached",
            entity_type="Complaint",
            entity_id=str(complaint.id),
            details={
                "evidence_id": str(evidence.id),
                "document_reference": evidence.document_reference,
                "kind": evidence.kind,
                "source_system": evidence.source_system,
            },
        )

        logger.info(
            f"Attached evidence {evidence.document_reference} to complaint {complaint.reference}"
        )
        return evidence

    @classmethod
    @transaction.atomic
    def verify_evidence(
        cls,
        evidence_id: str,
        tenant,
        user,
        is_verified: bool = True,
    ) -> EvidenceRecord:
        """
        Verifies an evidence record for compliance and maker-checker validation.
        """
        if not user.has_case_permission("evidence.verify"):
            raise PermissionDenied("You do not have permission to verify authoritative evidence.")

        evidence = EvidenceRecord.objects.select_for_update().get(
            id=evidence_id, tenant=tenant
        )

        evidence.is_verified = is_verified
        evidence.verified_by = user if is_verified else None
        evidence.verified_at = timezone.now() if is_verified else None
        evidence.save(update_fields=["is_verified", "verified_by", "verified_at", "updated_at"])

        actor = user.display_name if hasattr(user, "display_name") else str(user)
        action_verb = "verified" if is_verified else "marked unverified"

        ComplaintTimelineEvent.objects.create(
            complaint=evidence.complaint,
            tenant=tenant,
            kind="EVIDENCE_VERIFIED",
            title=f"Evidence {action_verb}: {evidence.document_reference}",
            detail=f"Authoritative proof ({evidence.title}) was {action_verb} by {actor}.",
            actor=actor,
        )

        AuditEvent.objects.create(
            tenant_id=tenant.id,
            user=user,
            action="evidence.verified" if is_verified else "evidence.unverified",
            entity_type="EvidenceRecord",
            entity_id=str(evidence.id),
            details={
                "document_reference": evidence.document_reference,
                "is_verified": is_verified,
            },
        )

        logger.info(f"Evidence {evidence.document_reference} was {action_verb} by {user.username}")
        return evidence
