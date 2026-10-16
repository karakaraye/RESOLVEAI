import uuid
from datetime import timedelta
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from apps.common.models import AuditEvent
from .models import (
    Customer,
    ComplaintCategory,
    SourceEvent,
    Complaint,
    ComplaintNote,
    ComplaintTimelineEvent,
    ComplaintFollowUp,
)


class InvalidStateTransitionError(ValidationError):
    """Raised when an illegal complaint status transition is attempted."""
    pass


class ComplaintWorkflowService:
    """
    Manages complaint lifecycle, valid state machine transitions, and timeline history.
    """
    # Allowed transitions: Current Status -> Set of permitted Next Statuses
    VALID_TRANSITIONS = {
        Complaint.Status.NEW: {
            Complaint.Status.NEEDS_ACTION,
            Complaint.Status.IN_PROGRESS,
            Complaint.Status.FORWARDED,
            Complaint.Status.AWAITING_VERIFICATION,
        },
        Complaint.Status.NEEDS_ACTION: {
            Complaint.Status.IN_PROGRESS,
            Complaint.Status.FORWARDED,
            Complaint.Status.AWAITING_VERIFICATION,
        },
        Complaint.Status.IN_PROGRESS: {
            Complaint.Status.NEEDS_ACTION,
            Complaint.Status.FORWARDED,
            Complaint.Status.AWAITING_VERIFICATION,
        },
        Complaint.Status.FORWARDED: {
            Complaint.Status.IN_PROGRESS,
            Complaint.Status.NEEDS_ACTION,
            Complaint.Status.AWAITING_VERIFICATION,
        },
        Complaint.Status.AWAITING_VERIFICATION: {
            Complaint.Status.RESOLVED,
            Complaint.Status.IN_PROGRESS,
            Complaint.Status.NEEDS_ACTION,
        },
        Complaint.Status.RESOLVED: {
            Complaint.Status.REOPENED,
        },
        Complaint.Status.REOPENED: {
            Complaint.Status.NEEDS_ACTION,
            Complaint.Status.IN_PROGRESS,
            Complaint.Status.FORWARDED,
            Complaint.Status.AWAITING_VERIFICATION,
        },
    }

    @staticmethod
    def compute_allowed_actions(complaint: Complaint, user) -> list[str]:
        """
        Calculates allowed actions on a complaint based on current status and user permissions.
        """
        actions = []
        if not user or not user.is_authenticated:
            return actions

        # Note adding
        if user.has_case_permission("complaints.notes"):
            actions.append("ADD_NOTE")

        # Assignment
        if user.has_case_permission("complaints.assign") and complaint.status != Complaint.Status.RESOLVED:
            actions.append("ASSIGN")

        # Forwarding (defined transition boundary)
        if user.has_case_permission("complaints.forward") and complaint.status not in (
            Complaint.Status.RESOLVED,
            Complaint.Status.AWAITING_VERIFICATION,
        ):
            actions.append("FORWARD")

        # Follow-up
        if user.has_case_permission("complaints.follow_up") and complaint.status != Complaint.Status.RESOLVED:
            actions.append("SET_FOLLOW_UP")

        # Record outcome (can only record outcome if not already resolved or awaiting verification)
        if user.has_case_permission("complaints.record_outcome") and complaint.status not in (
            Complaint.Status.RESOLVED,
            Complaint.Status.AWAITING_VERIFICATION,
        ):
            actions.append("RECORD_OUTCOME")

        # Verify outcome (maker-checker: only in AWAITING_VERIFICATION status)
        if user.has_case_permission("complaints.verify_outcome") and complaint.status == Complaint.Status.AWAITING_VERIFICATION:
            actions.append("VERIFY_OUTCOME")

        # Reopen (only if currently RESOLVED)
        if user.has_case_permission("complaints.reopen") and complaint.status == Complaint.Status.RESOLVED:
            actions.append("REOPEN")

        return actions

    @classmethod
    @transaction.atomic
    def transition_status(
        cls,
        complaint: Complaint,
        new_status: str,
        user,
        actor_name: str,
        reason: str = ""
    ) -> Complaint:
        """
        Validates and executes a complaint status transition.
        """
        current_status = complaint.status
        if new_status == current_status:
            return complaint

        allowed_targets = cls.VALID_TRANSITIONS.get(current_status, set())
        if new_status not in allowed_targets:
            raise InvalidStateTransitionError(
                f"Cannot transition complaint from status '{current_status}' to '{new_status}'."
            )

        # Invariant: Cannot jump directly to RESOLVED without verification
        if new_status == Complaint.Status.RESOLVED:
            if current_status != Complaint.Status.AWAITING_VERIFICATION:
                raise InvalidStateTransitionError(
                    "Complaints can only be resolved through outcome verification."
                )
            if not user.has_case_permission("complaints.verify_outcome"):
                raise PermissionDenied("You do not have permission to verify and resolve complaints.")

        complaint.status = new_status
        complaint.save(update_fields=["status", "updated_at"])

        # Create immutable timeline event
        ComplaintTimelineEvent.objects.create(
            complaint=complaint,
            tenant=complaint.tenant,
            kind="STATUS_CHANGED",
            title=f"Status changed to {complaint.get_status_display()}",
            detail=reason or f"Transitioned from {current_status} to {new_status}.",
            actor=actor_name,
        )

        # Audit event
        AuditEvent.objects.create(
            tenant_id=complaint.tenant.id,
            user=user if user.is_authenticated else None,
            action="complaint.status_changed",
            entity_type="Complaint",
            entity_id=str(complaint.id),
            details={
                "previous_status": current_status,
                "new_status": new_status,
                "reason": reason,
            }
        )
        return complaint

    @classmethod
    @transaction.atomic
    def assign_operator(cls, complaint: Complaint, user, assignee_id: str, reason: str = "") -> Complaint:
        if not user.has_case_permission("complaints.assign"):
            raise PermissionDenied("You do not have permission to assign complaints.")

        # Concurrency control: Pessimistic row-level lock on the complaint record
        complaint = Complaint.objects.select_for_update().get(id=complaint.id, tenant=complaint.tenant)

        from apps.accounts.models import User
        try:
            assignee = User.objects.get(id=assignee_id, tenant=complaint.tenant)
        except User.DoesNotExist:
            raise ValidationError("Target assignee was not found in this institution.")

        previous_operator = complaint.assigned_operator.display_name if complaint.assigned_operator else "Unassigned"
        complaint.assigned_operator = assignee
        complaint.assigned_at = timezone.now()

        # If currently NEW, move to IN_PROGRESS
        if complaint.status == Complaint.Status.NEW:
            complaint.status = Complaint.Status.IN_PROGRESS

        complaint.save(update_fields=["assigned_operator", "assigned_at", "status", "updated_at"])

        actor = user.display_name if hasattr(user, "display_name") else str(user)
        ComplaintTimelineEvent.objects.create(
            complaint=complaint,
            tenant=complaint.tenant,
            kind="ASSIGNED",
            title=f"Assigned to {assignee.display_name}",
            detail=reason or f"Previously: {previous_operator}.",
            actor=actor,
        )

        AuditEvent.objects.create(
            tenant_id=complaint.tenant.id,
            user=user,
            action="complaint.assigned",
            entity_type="Complaint",
            entity_id=str(complaint.id),
            details={"assignee_id": str(assignee.id), "reason": reason}
        )
        return complaint

    @classmethod
    @transaction.atomic
    def add_note(cls, complaint: Complaint, user, text: str) -> ComplaintNote:
        if not user.has_case_permission("complaints.notes"):
            raise PermissionDenied("You do not have permission to add case notes.")

        # Concurrency control: Pessimistic row-level lock on the complaint record
        complaint = Complaint.objects.select_for_update().get(id=complaint.id, tenant=complaint.tenant)

        author_name = user.display_name if hasattr(user, "display_name") else str(user)
        note = ComplaintNote.objects.create(
            complaint=complaint,
            tenant=complaint.tenant,
            author=user,
            author_display_name=author_name,
            text=text.strip(),
        )

        ComplaintTimelineEvent.objects.create(
            complaint=complaint,
            tenant=complaint.tenant,
            kind="NOTE_ADDED",
            title="Internal note added",
            detail=text[:120] + "..." if len(text) > 120 else text,
            actor=author_name,
        )

        AuditEvent.objects.create(
            tenant_id=complaint.tenant.id,
            user=user,
            action="complaint.note_added",
            entity_type="Complaint",
            entity_id=str(complaint.id),
            details={"note_id": str(note.id)}
        )
        return note

    @classmethod
    @transaction.atomic
    def set_follow_up(cls, complaint: Complaint, user, due_at, reason: str) -> ComplaintFollowUp:
        if not user.has_case_permission("complaints.follow_up"):
            raise PermissionDenied("You do not have permission to set follow-up schedules.")

        # Concurrency control: Pessimistic row-level lock on the complaint record
        complaint = Complaint.objects.select_for_update().get(id=complaint.id, tenant=complaint.tenant)

        follow_up = ComplaintFollowUp.objects.create(
            complaint=complaint,
            tenant=complaint.tenant,
            created_by=user,
            due_at=due_at,
            reason=reason.strip(),
        )

        # Update complaint due_at
        complaint.due_at = due_at
        complaint.save(update_fields=["due_at", "updated_at"])

        actor = user.display_name if hasattr(user, "display_name") else str(user)
        ComplaintTimelineEvent.objects.create(
            complaint=complaint,
            tenant=complaint.tenant,
            kind="FOLLOW_UP_SET",
            title=f"Follow-up scheduled for {due_at.strftime('%d %b %Y %H:%M')}",
            detail=reason,
            actor=actor,
        )

        AuditEvent.objects.create(
            tenant_id=complaint.tenant.id,
            user=user,
            action="complaint.follow_up_set",
            entity_type="Complaint",
            entity_id=str(complaint.id),
            details={"due_at": due_at.isoformat(), "reason": reason}
        )
        return follow_up

    @classmethod
    @transaction.atomic
    def record_outcome(cls, complaint: Complaint, user, outcome: str, evidence: str = "") -> Complaint:
        if not user.has_case_permission("complaints.record_outcome"):
            raise PermissionDenied("You do not have permission to record complaint outcomes.")

        # Concurrency control: Pessimistic row-level lock on the complaint record
        complaint = Complaint.objects.select_for_update().get(id=complaint.id, tenant=complaint.tenant)

        if complaint.status in (Complaint.Status.RESOLVED, Complaint.Status.AWAITING_VERIFICATION):
            raise InvalidStateTransitionError(
                f"Cannot record new outcome on complaint in status '{complaint.status}'."
            )

        actor = user.display_name if hasattr(user, "display_name") else str(user)
        complaint.resolution_outcome = outcome.strip()
        complaint.resolution_evidence = (evidence or "").strip()
        complaint.resolution_reported_at = timezone.now()
        complaint.resolution_reported_by = user
        complaint.resolution_verification = Complaint.ResolutionVerification.AWAITING
        complaint.status = Complaint.Status.AWAITING_VERIFICATION
        complaint.save()

        ComplaintTimelineEvent.objects.create(
            complaint=complaint,
            tenant=complaint.tenant,
            kind="OUTCOME_RECORDED",
            title="Outcome recorded (Awaiting verification)",
            detail=f"Outcome: {outcome[:150]}",
            actor=actor,
        )

        AuditEvent.objects.create(
            tenant_id=complaint.tenant.id,
            user=user,
            action="complaint.outcome_recorded",
            entity_type="Complaint",
            entity_id=str(complaint.id),
            details={"outcome": outcome, "evidence": evidence}
        )
        return complaint

    @classmethod
    @transaction.atomic
    def verify_outcome(cls, complaint: Complaint, user, decision: str, note: str = "") -> Complaint:
        if not user.has_case_permission("complaints.verify_outcome"):
            raise PermissionDenied("You do not have permission to verify complaint outcomes.")

        # Concurrency control: Pessimistic row-level lock on the complaint record
        complaint = Complaint.objects.select_for_update().get(id=complaint.id, tenant=complaint.tenant)

        if complaint.status != Complaint.Status.AWAITING_VERIFICATION:
            raise InvalidStateTransitionError(
                "Only complaints awaiting verification can have outcomes verified or rejected."
            )

        # Invariant: Must have an active recorded outcome
        if not complaint.resolution_reported_at or not complaint.resolution_outcome:
            raise ValidationError("Cannot verify a complaint that lacks an active recorded resolution outcome.")

        # Maker-Checker segregation of duties: The recording operator cannot verify their own outcome
        if complaint.resolution_reported_by_id and str(complaint.resolution_reported_by_id) == str(user.id):
            raise PermissionDenied("Segregation of duties violation: maker cannot verify their own resolution outcome.")

        actor = user.display_name if hasattr(user, "display_name") else str(user)
        now = timezone.now()

        if decision == "VERIFY":
            complaint.resolution_verification = Complaint.ResolutionVerification.VERIFIED
            complaint.resolution_verified_at = now
            complaint.resolution_verified_by = user
            complaint.resolution_note = note.strip()
            complaint.status = Complaint.Status.RESOLVED
            complaint.save()

            ComplaintTimelineEvent.objects.create(
                complaint=complaint,
                tenant=complaint.tenant,
                kind="OUTCOME_VERIFIED",
                title="Outcome verified (Case Resolved)",
                detail=note or "Evidence confirmed; case marked as resolved.",
                actor=actor,
            )

            # Task 5: Verified Resolution Communication Gate
            try:
                from apps.communications.services import CustomerCommunicationService
                CustomerCommunicationService.queue_verified_resolution_notification(
                    complaint=complaint,
                    user=user,
                )
            except Exception as e:
                import logging
                logging.getLogger("resolveai.complaints").warning(
                    f"Customer resolution communication queuing failed for {complaint.reference}: {e}"
                )
        elif decision == "REJECT":
            complaint.resolution_verification = Complaint.ResolutionVerification.REJECTED
            complaint.resolution_verified_at = now
            complaint.resolution_verified_by = user
            complaint.resolution_note = note.strip()
            # Moves back to IN_PROGRESS for rework
            complaint.status = Complaint.Status.IN_PROGRESS
            complaint.save()

            ComplaintTimelineEvent.objects.create(
                complaint=complaint,
                tenant=complaint.tenant,
                kind="OUTCOME_REJECTED",
                title="Outcome rejected (Case kept open)",
                detail=note or "Resolution evidence was insufficient.",
                actor=actor,
            )
        else:
            raise ValidationError(f"Invalid verification decision '{decision}'. Expected 'VERIFY' or 'REJECT'.")

        AuditEvent.objects.create(
            tenant_id=complaint.tenant.id,
            user=user,
            action="complaint.outcome_verified",
            entity_type="Complaint",
            entity_id=str(complaint.id),
            details={"decision": decision, "note": note}
        )
        return complaint

    @classmethod
    @transaction.atomic
    def reopen_complaint(cls, complaint: Complaint, user, reason: str) -> Complaint:
        if not user.has_case_permission("complaints.reopen"):
            raise PermissionDenied("You do not have permission to reopen resolved complaints.")

        # Concurrency control: Pessimistic row-level lock on the complaint record
        complaint = Complaint.objects.select_for_update().get(id=complaint.id, tenant=complaint.tenant)

        if complaint.status != Complaint.Status.RESOLVED:
            raise InvalidStateTransitionError("Only resolved complaints can be reopened.")

        actor = user.display_name if hasattr(user, "display_name") else str(user)
        complaint.status = Complaint.Status.REOPENED
        complaint.reopen_reason = reason.strip()

        # Invariant: Reopened complaints require a newly recorded and independently verified outcome
        # before they can ever return to RESOLVED. The prior resolution outcome is completely invalidated.
        complaint.resolution_outcome = ""
        complaint.resolution_evidence = ""
        complaint.resolution_reported_at = None
        complaint.resolution_reported_by = None
        complaint.resolution_verification = Complaint.ResolutionVerification.AWAITING
        complaint.resolution_verified_at = None
        complaint.resolution_verified_by = None
        complaint.resolution_note = ""
        complaint.save()

        ComplaintTimelineEvent.objects.create(
            complaint=complaint,
            tenant=complaint.tenant,
            kind="REOPENED",
            title="Complaint reopened",
            detail=reason,
            actor=actor,
        )

        # Task 7: Invalidate previously queued final-resolution messages that are no longer eligible
        try:
            from apps.communications.services import CustomerCommunicationService
            CustomerCommunicationService.cancel_pending_resolution_communications(
                complaint=complaint,
                reason=reason,
            )
        except Exception as e:
            import logging
            logging.getLogger("resolveai.complaints").warning(
                f"Cancelling pending resolution communications failed for {complaint.reference}: {e}"
            )

        AuditEvent.objects.create(
            tenant_id=complaint.tenant.id,
            user=user,
            action="complaint.reopened",
            entity_type="Complaint",
            entity_id=str(complaint.id),
            details={"reason": reason}
        )
        return complaint


class ComplaintIngestionService:
    """
    Ingests complaints from banking feeds and webhooks with strict duplicate prevention.
    """
    @classmethod
    @transaction.atomic
    def ingest_event(cls, tenant, external_event_id: str, payload: dict) -> tuple[Complaint, bool]:
        """
        Idempotently ingest an event. If (tenant, external_event_id) exists, return the existing complaint.
        """
        existing_event = SourceEvent.objects.filter(
            tenant=tenant,
            external_event_id=external_event_id
        ).first()

        if existing_event:
            # Duplicate webhook/event detected: find and return existing complaint
            complaint = Complaint.objects.filter(
                tenant=tenant,
                original_source_reference=external_event_id
            ).first()
            if complaint:
                return complaint, False

        # Extract payload attributes with validation
        cust_number = payload.get("customer_number") or payload.get("customerReference") or f"CUST-{uuid.uuid4().hex[:6].upper()}"
        full_name = (payload.get("customerName") or "").strip().split(" ", 1)
        first_name = payload.get("customer_first_name") or (full_name[0] if full_name and full_name[0] else "Valued")
        last_name = payload.get("customer_last_name") or (full_name[1] if len(full_name) > 1 else "Customer")
        email = payload.get("customer_email") or payload.get("customerEmail")
        phone = payload.get("customer_phone") or payload.get("customerPhone")
        account_number = payload.get("account_number") or payload.get("accountNumber")

        customer, _ = Customer.objects.get_or_create(
            tenant=tenant,
            customer_number=cust_number,
            defaults={
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "phone": phone,
                "account_number": account_number,
            }
        )

        category_code = payload.get("category_code") or payload.get("category")
        category = None
        if category_code:
            category = ComplaintCategory.objects.filter(
                tenant=tenant,
                code=category_code
            ).first() or ComplaintCategory.objects.filter(
                tenant__isnull=True,
                code=category_code
            ).first()
            if not category:
                category_label = payload.get("category_label") or payload.get("categoryLabel") or category_code.replace("_", " ").title()
                category, _ = ComplaintCategory.objects.get_or_create(
                    tenant=tenant,
                    code=category_code,
                    defaults={"label": category_label, "is_active": True}
                )

        source_channel = payload.get("source_channel") or payload.get("channel", "Contact centre feed")
        summary = payload.get("summary") or payload.get("title", "Customer Incident Report")
        narrative = payload.get("narrative") or payload.get("description", "")
        priority = payload.get("priority", Complaint.Priority.MEDIUM)
        if priority not in Complaint.Priority.values:
            priority = Complaint.Priority.MEDIUM

        received_at = payload.get("received_at")
        if not received_at:
            received_at = timezone.now()

        # Due date default: +48h for normal, +24h for high, +12h for critical
        due_delta = {
            Complaint.Priority.LOW: timedelta(hours=72),
            Complaint.Priority.MEDIUM: timedelta(hours=48),
            Complaint.Priority.HIGH: timedelta(hours=24),
            Complaint.Priority.CRITICAL: timedelta(hours=12),
        }.get(priority, timedelta(hours=48))
        due_at = payload.get("due_at") or (received_at + due_delta)

        # Unique reference formatting: CMP-YYYY-XXXXX
        year = received_at.year if hasattr(received_at, "year") else timezone.now().year
        ref_seq = Complaint.objects.filter(tenant=tenant).count() + 1
        reference = f"CMP-{year}-{ref_seq:04d}"

        complaint = Complaint.objects.create(
            reference=reference,
            tenant=tenant,
            customer=customer,
            customer_reference=customer.customer_number,
            original_source_reference=external_event_id,
            source_channel=source_channel,
            summary=summary,
            narrative=narrative,
            category=category,
            priority=priority,
            status=Complaint.Status.NEW,
            received_at=received_at,
            due_at=due_at,
        )

        # Record SourceEvent for duplicate prevention
        SourceEvent.objects.create(
            tenant=tenant,
            external_event_id=external_event_id,
            source_channel=source_channel,
            payload=payload,
            processed=True,
        )

        # Create initial timeline event
        ComplaintTimelineEvent.objects.create(
            complaint=complaint,
            tenant=tenant,
            at=received_at,
            kind="RECEIVED",
            title=f"Complaint received via {source_channel}",
            detail=f"External source reference: {external_event_id}",
            actor="Channel Ingestion Service",
        )

        AuditEvent.objects.create(
            tenant_id=tenant.id,
            action="complaint.ingested",
            entity_type="Complaint",
            entity_id=str(complaint.id),
            details={
                "reference": reference,
                "external_event_id": external_event_id,
                "channel": source_channel,
            }
        )

        # Task 2: Automated Complaint Acknowledgements
        try:
            from apps.communications.services import CustomerCommunicationService
            channel_already_acked = bool(payload.get("channel_acknowledged", False))
            CustomerCommunicationService.queue_acknowledgement(
                complaint=complaint,
                originating_event_id=external_event_id,
                channel_already_acknowledged=channel_already_acked,
            )
        except Exception as e:
            import logging
            logging.getLogger("resolveai.complaints").warning(
                f"Automatic customer acknowledgement queuing failed for {reference}: {e}"
            )

        return complaint, True


class WorkspaceSummaryService:
    """
    Computes dashboard workload counts and actionable items strictly from real database records.
    """
    @classmethod
    def get_summary(cls, tenant, user, scope: str = "all") -> dict:
        now = timezone.now()
        qs = Complaint.objects.filter(tenant=tenant)
        if scope == "mine" and user.is_authenticated:
            qs = qs.filter(assigned_operator=user)

        new_count = qs.filter(status=Complaint.Status.NEW).count()
        needs_action_count = qs.filter(status=Complaint.Status.NEEDS_ACTION).count()
        in_progress_count = qs.filter(status=Complaint.Status.IN_PROGRESS).count()
        awaiting_verif_count = qs.filter(status=Complaint.Status.AWAITING_VERIFICATION).count()
        resolved_count = qs.filter(status=Complaint.Status.RESOLVED).count()

        # Overdue: active cases past due_at
        overdue_count = qs.filter(
            due_at__lt=now
        ).exclude(
            status=Complaint.Status.RESOLVED
        ).count()

        counts = {
            "new": new_count,
            "needsAttention": needs_action_count,
            "inProgress": in_progress_count,
            "awaitingVerification": awaiting_verif_count,
            "overdue": overdue_count,
            "resolvedVerified": resolved_count,
        }

        if scope == "mine" and user.is_authenticated:
            counts["totalAssigned"] = Complaint.objects.filter(
                tenant=tenant,
                assigned_operator=user
            ).exclude(
                status=Complaint.Status.RESOLVED
            ).count()

        # Next actions derived from real status and urgency
        next_actions = []
        if overdue_count > 0:
            first_overdue = qs.filter(due_at__lt=now).exclude(status=Complaint.Status.RESOLVED).first()
            next_actions.append({
                "kind": "OVERDUE",
                "count": overdue_count,
                "complaintId": str(first_overdue.id) if first_overdue and overdue_count == 1 else None,
            })

        if awaiting_verif_count > 0:
            first_verif = qs.filter(status=Complaint.Status.AWAITING_VERIFICATION).first()
            next_actions.append({
                "kind": "VERIFY_RESOLUTION",
                "count": awaiting_verif_count,
                "complaintId": str(first_verif.id) if first_verif and awaiting_verif_count == 1 else None,
            })

        reopened_count = qs.filter(status=Complaint.Status.REOPENED).count()
        if reopened_count > 0:
            first_reopened = qs.filter(status=Complaint.Status.REOPENED).first()
            next_actions.append({
                "kind": "REVIEW_REOPENED",
                "count": reopened_count,
                "complaintId": str(first_reopened.id) if first_reopened and reopened_count == 1 else None,
            })

        if new_count > 0:
            first_new = qs.filter(status=Complaint.Status.NEW).first()
            next_actions.append({
                "kind": "REVIEW_NEW",
                "count": new_count,
                "complaintId": str(first_new.id) if first_new and new_count == 1 else None,
            })

        if in_progress_count > 0:
            first_in_progress = qs.filter(status=Complaint.Status.IN_PROGRESS).first()
            next_actions.append({
                "kind": "INVESTIGATE",
                "count": in_progress_count,
                "complaintId": str(first_in_progress.id) if first_in_progress and in_progress_count == 1 else None,
            })

        return {
            "counts": counts,
            "nextActions": next_actions,
            "generatedAt": now.isoformat(),
        }
