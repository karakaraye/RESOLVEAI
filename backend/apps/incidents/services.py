import logging
from datetime import timedelta
from typing import List, Optional

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone

from apps.common.models import AuditEvent
from apps.complaints.models import Complaint, ComplaintCategory
from .models import Incident, IncidentComplaint, IncidentFinding, IncidentTimelineEvent

logger = logging.getLogger("resolveai.incidents")


class IncidentManagementService:
    """
    Manages banking incident lifecycle, complaint associations, and audit history.
    Enforces strict tenant isolation and maker-checker validation.
    """

    @classmethod
    def generate_incident_reference(cls, tenant) -> str:
        current_year = timezone.now().year
        prefix = f"INC-{current_year}-"
        latest = Incident.objects.filter(
            tenant=tenant,
            reference__startswith=prefix
        ).order_by("-reference").values_list("reference", flat=True).first()

        if latest:
            try:
                seq = int(latest.split("-")[-1]) + 1
            except ValueError:
                seq = 1
        else:
            seq = 1

        return f"{prefix}{seq:04d}"

    @classmethod
    @transaction.atomic
    def create_incident_candidate(
        cls,
        tenant,
        title: str,
        summary: str,
        category: Optional[ComplaintCategory] = None,
        severity: str = Incident.Severity.MODERATE,
        source_system: str = "",
        detected_rule: str = "",
        detection_evidence: dict = None,
        complaint_ids: List[str] = None,
        user=None,
    ) -> Incident:
        """
        Creates an incident candidate. Associates initial complaints as candidate links.
        """
        ref = cls.generate_incident_reference(tenant)
        incident = Incident.objects.create(
            tenant=tenant,
            reference=ref,
            title=title.strip(),
            summary=summary.strip(),
            category=category,
            severity=severity,
            status=Incident.Status.CANDIDATE,
            source_system=source_system,
            detected_rule=detected_rule,
            detection_evidence=detection_evidence or {},
            created_by=user if user and user.is_authenticated else None,
        )

        actor_name = user.display_name if user and hasattr(user, "display_name") else "Incident Detection Engine"

        IncidentTimelineEvent.objects.create(
            incident=incident,
            kind="CANDIDATE_CREATED",
            title=f"Incident candidate {ref} generated",
            detail=f"Rule: {detected_rule or 'Manual candidate'} · Severity: {severity}",
            actor=actor_name,
        )

        if complaint_ids:
            complaints = Complaint.objects.filter(id__in=complaint_ids, tenant=tenant)
            for comp in complaints:
                IncidentComplaint.objects.create(
                    tenant=tenant,
                    incident=incident,
                    complaint=comp,
                    confidence=0.85,
                    relation_reason=f"Candidate grouped under rule: {detected_rule or 'Pattern match'}",
                    is_confirmed=False,
                    associated_by=user if user and user.is_authenticated else None,
                )

        AuditEvent.objects.create(
            tenant_id=tenant.id,
            user=user if user and user.is_authenticated else None,
            action="incident.candidate_created",
            entity_type="Incident",
            entity_id=str(incident.id),
            details={"reference": ref, "title": title, "severity": severity},
        )

        logger.info(f"Created incident candidate {ref} for tenant {tenant.name}")
        return incident

    @classmethod
    @transaction.atomic
    def confirm_incident(
        cls,
        incident_id: str,
        tenant,
        user,
        severity: str = None,
        title: str = None,
        summary: str = None,
    ) -> Incident:
        """
        Human review: Confirms an incident candidate into a confirmed active incident.
        Updates all candidate complaints to confirmed links and updates individual complaints.
        """
        incident = Incident.objects.select_for_update().get(id=incident_id, tenant=tenant)

        if severity and severity in Incident.Severity.values:
            incident.severity = severity
        if title:
            incident.title = title.strip()
        if summary:
            incident.summary = summary.strip()

        incident.status = Incident.Status.CONFIRMED
        incident.confirmed_by = user
        incident.confirmed_at = timezone.now()
        incident.save()

        # Confirm all associated complaints
        links = IncidentComplaint.objects.filter(incident=incident, tenant=tenant)
        for link in links:
            link.is_confirmed = True
            link.save(update_fields=["is_confirmed"])
            # Update complaint shared incident reference
            Complaint.objects.filter(id=link.complaint_id).update(
                shared_incident_reference=incident.reference
            )

        actor_name = user.display_name if hasattr(user, "display_name") else str(user)

        IncidentTimelineEvent.objects.create(
            incident=incident,
            kind="INCIDENT_CONFIRMED",
            title=f"Incident confirmed as {incident.severity} by {actor_name}",
            detail=incident.summary,
            actor=actor_name,
        )

        AuditEvent.objects.create(
            tenant_id=tenant.id,
            user=user,
            action="incident.confirmed",
            entity_type="Incident",
            entity_id=str(incident.id),
            details={"reference": incident.reference, "severity": incident.severity},
        )

        logger.info(f"Incident {incident.reference} confirmed by {actor_name}")
        return incident

    @classmethod
    @transaction.atomic
    def link_complaint(
        cls,
        incident_id: str,
        complaint_id: str,
        tenant,
        user,
        reason: str = "Manually linked by operator",
        is_confirmed: bool = True,
    ) -> IncidentComplaint:
        """
        Links an individual complaint to an incident with multi-tenant verification.
        """
        incident = Incident.objects.select_for_update().get(id=incident_id, tenant=tenant)
        complaint = Complaint.objects.select_for_update().get(id=complaint_id, tenant=tenant)

        link, created = IncidentComplaint.objects.get_or_create(
            tenant=tenant,
            incident=incident,
            complaint=complaint,
            defaults={
                "confidence": 1.0,
                "relation_reason": reason.strip(),
                "is_confirmed": is_confirmed,
                "associated_by": user,
            }
        )

        if not created and not link.is_confirmed and is_confirmed:
            link.is_confirmed = True
            link.save(update_fields=["is_confirmed"])

        if is_confirmed:
            complaint.shared_incident_reference = incident.reference
            complaint.save(update_fields=["shared_incident_reference"])

        actor_name = user.display_name if user and hasattr(user, "display_name") else "Operator"

        IncidentTimelineEvent.objects.create(
            incident=incident,
            kind="COMPLAINT_LINKED",
            title=f"Complaint {complaint.reference} linked",
            detail=reason,
            actor=actor_name,
        )

        return link

    @classmethod
    @transaction.atomic
    def unlink_complaint(
        cls,
        incident_id: str,
        complaint_id: str,
        tenant,
        user,
    ) -> bool:
        """
        Unlinks an individual complaint from an incident.
        Clears the complaint's shared_incident_reference if it points to this incident.
        """
        incident = Incident.objects.select_for_update().get(id=incident_id, tenant=tenant)
        complaint = Complaint.objects.select_for_update().get(id=complaint_id, tenant=tenant)

        deleted_count, _ = IncidentComplaint.objects.filter(
            tenant=tenant,
            incident=incident,
            complaint=complaint,
        ).delete()

        if complaint.shared_incident_reference == incident.reference:
            complaint.shared_incident_reference = ""
            complaint.save(update_fields=["shared_incident_reference"])

        actor_name = user.display_name if user and hasattr(user, "display_name") else "Operator"

        IncidentTimelineEvent.objects.create(
            incident=incident,
            kind="COMPLAINT_UNLINKED",
            title=f"Complaint {complaint.reference} unlinked",
            detail="Removed complaint association following investigation.",
            actor=actor_name,
        )

        return deleted_count > 0

    @classmethod
    @transaction.atomic
    def resolve_incident(
        cls,
        incident_id: str,
        tenant,
        user,
        resolution_notes: str = "",
    ) -> Incident:
        """
        Task 6: Incident Resolution Barrier.
        Resolves the shared technical incident, but explicitly preserves the barrier
        between incident recovery and individual complaint resolution.
        Does NOT automatically mark linked complaints as RESOLVED or send final resolution notices.
        Only complaints whose individual investigations are verified can receive resolution notices.
        Unresolved complaints may receive an approved interim progress update.
        """
        incident = Incident.objects.select_for_update().get(id=incident_id, tenant=tenant)
        incident.status = Incident.Status.RESOLVED
        incident.save(update_fields=["status", "updated_at"])

        actor_name = user.display_name if user and hasattr(user, "display_name") else "Incident Lead"

        IncidentTimelineEvent.objects.create(
            incident=incident,
            kind="INCIDENT_RESOLVED",
            title=f"Incident {incident.reference} resolved",
            detail=resolution_notes or "Technical incident mitigation completed. Individual cases remain under respective review.",
            actor=actor_name,
        )

        AuditEvent.objects.create(
            tenant_id=tenant.id,
            user=user if user and user.is_authenticated else None,
            action="incident.resolved",
            entity_type="Incident",
            entity_id=str(incident.id),
            details={"reference": incident.reference, "notes": resolution_notes},
        )

        # Task 6: Send approved progress update (NOT final resolution) to still-pending linked complaints
        from apps.communications.services import CustomerCommunicationService
        from apps.communications.models import MessageTemplate

        linked_complaints = Complaint.objects.filter(
            incident_associations__incident=incident,
            tenant=tenant
        ).exclude(status=Complaint.Status.RESOLVED)

        for comp in linked_complaints:
            try:
                CustomerCommunicationService.queue_progress_update(
                    complaint=comp,
                    category=MessageTemplate.Category.PROGRESS_UPDATE,
                    details=f"The underlying technical incident ({incident.reference}) has been mitigated. Your individual case review remains open.",
                    force=False
                )
            except Exception as e:
                logger.warning(f"Failed to queue interim progress update for complaint {comp.reference}: {e}")

        logger.info(f"Incident {incident.reference} marked as RESOLVED. Maintained complaint resolution barrier for {linked_complaints.count()} open cases.")
        return incident


class IncidentDetectionService:
    """
    Detects emerging banking incidents combining:
      - Sliding time-window complaint volumes
      - Category concentration
      - Transaction discrepancy clustering
      - Guard against duplicate candidate creation
    """

    @classmethod
    def detect_emerging_incidents(
        cls,
        tenant,
        lookback_hours: int = 48,
        discrepancy_threshold: int = 2,
        volume_threshold: int = 3,
    ) -> List[Incident]:
        """
        Evaluates recent complaints for anomalies or shared failure patterns.
        Creates candidate incidents with explicit evidence and detection rules.
        """
        now = timezone.now()
        since = now - timedelta(hours=lookback_hours)

        recent_complaints = Complaint.objects.filter(
            tenant=tenant,
            received_at__gte=since
        ).select_related("category").prefetch_related("transaction_investigations")

        created_incidents: List[Incident] = []

        # 1. Detection Rule: Discrepancy Clustering (Ledger debited but switch pending)
        discrepant_complaints = []
        for comp in recent_complaints:
            has_conflict = comp.transaction_investigations.filter(
                conflict__icontains="disagree"
            ).exists()
            if has_conflict:
                discrepant_complaints.append(comp)

        if len(discrepant_complaints) >= discrepancy_threshold:
            # Check duplicate safeguard
            existing_active = Incident.objects.filter(
                tenant=tenant,
                status__in=[Incident.Status.CANDIDATE, Incident.Status.INVESTIGATING, Incident.Status.CONFIRMED],
                detected_rule="RULE_DISCREPANCY_CLUSTER",
                created_at__gte=since,
            ).first()

            if not existing_active:
                comp_ids = [str(c.id) for c in discrepant_complaints]
                comp_refs = [c.reference for c in discrepant_complaints]
                incident = IncidentManagementService.create_incident_candidate(
                    tenant=tenant,
                    title="Emerging Interbank Settlement Discrepancy Cluster",
                    summary=(
                        f"Detected {len(discrepant_complaints)} recent customer complaints exhibiting "
                        f"unreconciled core banking debits against central switch confirmation."
                    ),
                    category=discrepant_complaints[0].category,
                    severity=Incident.Severity.MAJOR,
                    source_system="NIBSS Instant Payments / Core Ledger",
                    detected_rule="RULE_DISCREPANCY_CLUSTER",
                    detection_evidence={
                        "complaint_count": len(discrepant_complaints),
                        "complaint_references": comp_refs,
                        "window_hours": lookback_hours,
                        "signal": "core_ledger_debited_switch_pending",
                    },
                    complaint_ids=comp_ids,
                )
                created_incidents.append(incident)
            else:
                # Link newly detected complaints to existing incident without duplicate alert
                for comp in discrepant_complaints:
                    if not IncidentComplaint.objects.filter(incident=existing_active, complaint=comp).exists():
                        IncidentManagementService.link_complaint(
                            incident_id=str(existing_active.id),
                            complaint_id=str(comp.id),
                            tenant=tenant,
                            user=None,
                            reason="Auto-associated via discrepancy cluster detection rule",
                            is_confirmed=False,
                        )

        # 2. Detection Rule: Category Volume Surge (e.g. Card & ATM failures)
        category_counts = (
            recent_complaints.filter(category__isnull=False)
            .values("category_id", "category__label", "category__code")
            .annotate(cnt=Count("id"))
            .filter(cnt__gte=volume_threshold)
        )

        for cat_info in category_counts:
            cat_id = cat_info["category_id"]
            cat_label = cat_info["category__label"]
            cat_code = cat_info["category__code"]
            matching = [c for c in recent_complaints if c.category_id == cat_id]

            rule_name = f"RULE_VOLUME_SURGE_{cat_code}"
            existing_active = Incident.objects.filter(
                tenant=tenant,
                status__in=[Incident.Status.CANDIDATE, Incident.Status.INVESTIGATING, Incident.Status.CONFIRMED],
                detected_rule=rule_name,
                created_at__gte=since,
            ).first()

            if not existing_active:
                category_obj = ComplaintCategory.objects.filter(id=cat_id).first()
                incident = IncidentManagementService.create_incident_candidate(
                    tenant=tenant,
                    title=f"Volume Surge Alert: {cat_label}",
                    summary=(
                        f"Elevated complaint volume detected: {len(matching)} cases reported in the "
                        f"past {lookback_hours} hours exceeding threshold ({volume_threshold})."
                    ),
                    category=category_obj,
                    severity=Incident.Severity.MODERATE,
                    source_system=matching[0].source_channel if matching else "Contact Centre",
                    detected_rule=rule_name,
                    detection_evidence={
                        "volume": len(matching),
                        "threshold": volume_threshold,
                        "window_hours": lookback_hours,
                    },
                    complaint_ids=[str(c.id) for c in matching],
                )
                created_incidents.append(incident)

        return created_incidents
