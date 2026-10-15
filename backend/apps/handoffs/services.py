import logging
from datetime import timedelta
import zoneinfo
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.common.models import OutboxMessage, AuditEvent
from apps.complaints.models import Complaint, ComplaintTimelineEvent
from apps.notifications.models import Notification
from .adapters.simulated import SimulatedBankDeliveryAdapter
from .models import (
    ForwardingHandoff,
    ForwardingPolicy,
    HandoffAttempt,
    HandoffEvent,
    HandoffResponse,
    ReceivingTeam,
)

logger = logging.getLogger("resolveai.handoffs.services")


class HandoffService:
    """
    Core domain service managing operations forwarding, case handoffs,
    outbox event dispatch, and delivery state reconciliation.
    """

    @classmethod
    def get_forwarding_options(cls, complaint: Complaint, user) -> dict:
        """
        Computes eligible receiving teams, privacy-minimised shareable summary,
        and AI/policy suggested destination.
        Guarantees tenant isolation: only returns teams belonging to complaint's tenant.
        """
        tenant = complaint.tenant
        teams = ReceivingTeam.objects.filter(
            tenant=tenant,
            is_active=True
        ).prefetch_related("recipients").order_by("name")

        # Determine recommended team from AI suggestion or category policy
        recommended_team_id = None
        finding = getattr(complaint, "intelligence_finding", None)
        if finding and finding.possible_responsible_team:
            suggested_name = finding.possible_responsible_team.lower()
            for team in teams:
                if team.name.lower() in suggested_name or team.code.lower() in suggested_name:
                    recommended_team_id = str(team.id)
                    break

        if not recommended_team_id and complaint.category:
            policy = ForwardingPolicy.objects.filter(
                tenant=tenant,
                category=complaint.category,
                is_active=True
            ).first()
            if policy and policy.default_team:
                recommended_team_id = str(policy.default_team.id)

        # Build shareable privacy-minimised summary
        txns = complaint.transaction_investigations.all()
        txn_str = f" Transaction {txns[0].reference}." if txns.exists() else ""
        shareable_summary = f"{complaint.reference} · {complaint.summary}.{txn_str}"

        shared_fields = [
            "Complaint reference",
            "Issue summary",
            "Transaction reference",
            "Masked customer reference",
        ]

        return {
            "recommendedTeamId": recommended_team_id,
            "teams": teams,
            "shareableSummary": shareable_summary,
            "sharedFields": shared_fields,
        }

    @classmethod
    @transaction.atomic
    def create_handoff(
        cls,
        complaint: Complaint,
        user,
        team_id: str,
        recipient: str = "",
        message: str = "",
    ) -> ForwardingHandoff:
        """
        Validates permissions, tenant isolation, and creates a ForwardingHandoff.
        Atomically records the handoff, timeline event, and outbox event.
        Dispatches background worker via transaction.on_commit.
        """
        tenant = complaint.tenant

        # 1. Tenant and destination validation
        try:
            team = ReceivingTeam.objects.get(id=team_id, tenant=tenant, is_active=True)
        except (ReceivingTeam.DoesNotExist, ValueError):
            raise ValidationError({"teamId": "The specified receiving team is invalid, inactive, or not authorised for this tenant."})

        # 2. Category validation if team restricts categories
        if team.allowed_categories.exists() and complaint.category:
            if not team.allowed_categories.filter(id=complaint.category.id).exists():
                raise ValidationError({"teamId": f"Team '{team.name}' is not approved for category '{complaint.category.label}'."})

        # 3. Calculate response deadline using tenant timezone & team SLA hours
        policy = ForwardingPolicy.objects.filter(tenant=tenant, category=complaint.category, is_active=True).first()
        sla_hours = policy.sla_response_hours if policy else team.response_due_hours
        response_due_at = SLAMonitoringService.calculate_response_deadline(tenant, sla_hours)

        shared_fields = [
            "Complaint reference",
            "Issue summary",
            "Transaction reference",
            "Masked customer reference",
        ]

        operator_name = getattr(user, "display_name", str(user)) if user else "System"

        # 4. Create ForwardingHandoff in PREPARED state
        handoff = ForwardingHandoff.objects.create(
            tenant=tenant,
            complaint=complaint,
            team=team,
            recipient=recipient.strip(),
            channel=team.channel,
            state=ForwardingHandoff.State.PREPARED,
            message=message.strip() or complaint.summary,
            shared_fields=shared_fields,
            created_by=user if user and user.is_authenticated else None,
            created_by_name=operator_name,
            response_due_at=response_due_at,
        )

        # 5. Transition complaint status to FORWARDED
        if complaint.status != Complaint.Status.FORWARDED:
            complaint.status = Complaint.Status.FORWARDED
            complaint.save(update_fields=["status", "updated_at"])

        # 6. Record timeline event & handoff domain event
        ComplaintTimelineEvent.objects.create(
            complaint=complaint,
            tenant=tenant,
            kind="FORWARDED",
            title=f"Forwarded to {team.name}",
            detail=f"Dispatched via {team.channel}{f' to {recipient}' if recipient else ''}. Response due within {sla_hours} hours.",
            actor=operator_name,
        )
        HandoffEvent.objects.create(
            handoff=handoff,
            event_type="CREATED",
            title=f"Handoff prepared for {team.name}",
            detail=f"Initial channel: {team.channel}",
            actor=operator_name,
        )

        # 7. Persist transactional outbox message
        OutboxMessage.objects.create(
            tenant_id=tenant.id,
            topic="handoffs.dispatch",
            payload={"handoff_id": str(handoff.id)},
            status=OutboxMessage.Status.PENDING,
        )

        # 8. Dispatch background worker task safely post-commit
        from .tasks import dispatch_handoff_task
        handoff_id_str = str(handoff.id)
        transaction.on_commit(lambda: dispatch_handoff_task.delay(handoff_id_str))

        logger.info(f"Handoff {handoff.id} created for complaint {complaint.reference} to team {team.name}")
        return handoff

    @classmethod
    @transaction.atomic
    def execute_dispatch(cls, handoff_id: str, adapter=None) -> ForwardingHandoff:
        """
        Executes transmission attempt using channel adapter.
        Handles delivery confirmation, uncertain timeouts, and fallback routing.
        """
        try:
            handoff = ForwardingHandoff.objects.select_for_update().select_related("team", "complaint", "tenant").get(id=handoff_id)
        except ForwardingHandoff.DoesNotExist:
            logger.error(f"Handoff {handoff_id} not found for dispatch execution.")
            return None

        # Prevent duplicate dispatch if already delivered or closed
        if handoff.state in (
            ForwardingHandoff.State.DELIVERED,
            ForwardingHandoff.State.ACKNOWLEDGED,
            ForwardingHandoff.State.ACCEPTED,
            ForwardingHandoff.State.RESPONDED,
            ForwardingHandoff.State.CLOSED,
        ):
            logger.info(f"Handoff {handoff.id} already in terminal state {handoff.state}; skipping duplicate dispatch.")
            return handoff

        delivery_adapter = adapter or SimulatedBankDeliveryAdapter()
        attempt_num = handoff.retry_count + 1
        active_channel = handoff.channel

        # If currently in fallback, use fallback channel
        if handoff.state == ForwardingHandoff.State.FALLBACK_IN_PROGRESS and handoff.team.fallback_channel:
            active_channel = handoff.team.fallback_channel

        result = delivery_adapter.dispatch(
            handoff=handoff,
            channel=active_channel,
            attempt_number=attempt_num,
        )

        handoff.retry_count = attempt_num
        handoff.last_attempt_at = timezone.now()
        handoff.delivery_evidence = result.evidence

        # Record attempt audit log
        HandoffAttempt.objects.create(
            handoff=handoff,
            attempt_number=attempt_num,
            channel=active_channel,
            outcome=result.outcome_message,
            evidence=result.evidence,
            error_code=result.error_code,
            is_uncertain=result.is_uncertain,
        )

        if result.success:
            if result.status == "DELIVERED":
                handoff.state = ForwardingHandoff.State.DELIVERED
                handoff.delivered_at = timezone.now()
            else:
                handoff.state = ForwardingHandoff.State.SENT

            HandoffEvent.objects.create(
                handoff=handoff,
                event_type="DISPATCH_SUCCESS",
                title=f"Dispatched via {active_channel}",
                detail=result.outcome_message,
                actor="Worker",
            )
        else:
            if result.is_uncertain:
                # Network timeout with uncertain outcome: NEVER retry blindly!
                handoff.state = ForwardingHandoff.State.DELIVERY_UNCONFIRMED
                HandoffEvent.objects.create(
                    handoff=handoff,
                    event_type="DELIVERY_UNCONFIRMED",
                    title="Transmission timeout — delivery unconfirmed",
                    detail=result.outcome_message,
                    actor="Worker",
                )
            else:
                # Failure: check if fallback channel is available and not yet tried
                if (
                    handoff.team.fallback_channel
                    and active_channel != handoff.team.fallback_channel
                    and handoff.retry_count >= handoff.max_retries
                ):
                    # Switch to fallback channel
                    handoff.state = ForwardingHandoff.State.FALLBACK_IN_PROGRESS
                    handoff.channel = handoff.team.fallback_channel
                    handoff.retry_count = 0  # reset for fallback channel
                    HandoffEvent.objects.create(
                        handoff=handoff,
                        event_type="FALLBACK_ACTIVATED",
                        title=f"Switching to approved fallback channel: {handoff.team.fallback_channel}",
                        detail=f"Primary channel failed: {result.outcome_message}",
                        actor="Worker",
                    )
                elif handoff.retry_count < handoff.max_retries and result.is_transient:
                    handoff.state = ForwardingHandoff.State.RETRY_SCHEDULED
                    HandoffEvent.objects.create(
                        handoff=handoff,
                        event_type="RETRY_SCHEDULED",
                        title=f"Retry scheduled for attempt #{attempt_num + 1}",
                        detail=result.outcome_message,
                        actor="Worker",
                    )
                else:
                    handoff.state = ForwardingHandoff.State.SEND_FAILED
                    HandoffEvent.objects.create(
                        handoff=handoff,
                        event_type="SEND_FAILED",
                        title="Send failed on all approved channels",
                        detail=result.outcome_message,
                        actor="Worker",
                    )

        handoff.save()
        logger.info(f"Handoff {handoff.id} dispatch completed with state {handoff.state}")
        return handoff

    @classmethod
    @transaction.atomic
    def retry_handoff(cls, handoff: ForwardingHandoff, user) -> ForwardingHandoff:
        """
        Manually triggers a retry of a failed or fallback handoff.
        """
        if not handoff.retry_allowed:
            raise ValidationError("Retry is not permitted for this handoff in its current state or retry limit reached.")

        operator_name = getattr(user, "display_name", str(user)) if user else "Operator"
        handoff.state = ForwardingHandoff.State.RETRY_SCHEDULED
        if handoff.retry_count >= handoff.max_retries:
            handoff.max_retries = handoff.retry_count + 1
        handoff.save(update_fields=["state", "max_retries", "last_updated_at"])

        HandoffEvent.objects.create(
            handoff=handoff,
            event_type="RETRY_REQUESTED",
            title="Manual retry requested by operator",
            detail=f"Queued for background worker dispatch through {handoff.channel}.",
            actor=operator_name,
        )

        from .tasks import dispatch_handoff_task
        handoff_id_str = str(handoff.id)
        transaction.on_commit(lambda: dispatch_handoff_task.delay(handoff_id_str))

        return handoff

    @classmethod
    @transaction.atomic
    def record_response(
        cls,
        handoff: ForwardingHandoff,
        summary: str,
        details: dict = None,
        responder_name: str = "",
        responder_contact: str = "",
    ) -> HandoffResponse:
        """
        Records the receiving team's formal response.
        Transitions handoff to RESPONDED, logs events, and creates in-app notification.
        """
        response, created = HandoffResponse.objects.update_or_create(
            handoff=handoff,
            defaults={
                "summary": summary.strip(),
                "details": details or {},
                "responder_name": responder_name.strip(),
                "responder_contact": responder_contact.strip(),
                "received_at": timezone.now(),
            }
        )

        handoff.state = ForwardingHandoff.State.RESPONDED
        handoff.responded_at = timezone.now()
        handoff.save(update_fields=["state", "responded_at", "last_updated_at"])

        ComplaintTimelineEvent.objects.create(
            complaint=handoff.complaint,
            tenant=handoff.tenant,
            kind="RESPONSE_RECEIVED",
            title=f"Response from {handoff.team.name}",
            detail=summary,
            actor=responder_name or handoff.team.name,
        )

        HandoffEvent.objects.create(
            handoff=handoff,
            event_type="RESPONSE_RECEIVED",
            title=f"Response recorded from {handoff.team.name}",
            detail=summary,
            actor=responder_name or "Team",
        )

        # Notify assigned operator or creator
        recipient_user = handoff.complaint.assigned_operator or handoff.created_by
        if recipient_user:
            Notification.objects.create(
                tenant=handoff.tenant,
                recipient=recipient_user,
                kind=Notification.Kind.RESPONSE,
                title=f"Response received from {handoff.team.name} on {handoff.complaint.reference}",
                complaint=handoff.complaint,
            )

        return response


class SLAMonitoringService:
    """
    Service responsible for calculating response deadlines using tenant timezone,
    detecting approaching deadlines, flagging overdue handoffs, and sending deduplicated alerts.
    """

    @classmethod
    def calculate_response_deadline(cls, tenant, hours: int) -> timezone.datetime:
        """
        Calculates response due date using the tenant's approved timezone.
        """
        tz_name = getattr(tenant, "time_zone", "Africa/Lagos") or "Africa/Lagos"
        try:
            tz = zoneinfo.ZoneInfo(tz_name)
        except Exception:
            tz = zoneinfo.ZoneInfo("UTC")

        now_in_tz = timezone.now().astimezone(tz)
        due_in_tz = now_in_tz + timedelta(hours=hours)
        return due_in_tz

    @classmethod
    def monitor_active_handoffs(cls, tenant=None) -> dict:
        """
        Scans active handoffs for approaching deadlines and breaches.
        Deduplicates notifications to avoid repeated alerts for the same condition.
        """
        now = timezone.now()
        qs = ForwardingHandoff.objects.filter(
            response_due_at__isnull=False
        ).exclude(
            state__in=[
                ForwardingHandoff.State.RESPONDED,
                ForwardingHandoff.State.CLOSED,
            ]
        ).select_related("complaint", "tenant", "team", "created_by", "complaint__assigned_operator")

        if tenant:
            qs = qs.filter(tenant=tenant)

        reminders_sent = 0
        escalations_sent = 0

        for handoff in qs:
            due_at = handoff.response_due_at

            # 1. Check for OVERDUE breach
            if now >= due_at:
                if handoff.state != ForwardingHandoff.State.OVERDUE:
                    handoff.state = ForwardingHandoff.State.OVERDUE
                    handoff.save(update_fields=["state", "last_updated_at"])

                    HandoffEvent.objects.create(
                        handoff=handoff,
                        event_type="OVERDUE_BREACH",
                        title=f"Response deadline breached for {handoff.team.name}",
                        detail=f"Due at {due_at.isoformat()}. Escalation triggered.",
                        actor="SLAMonitor",
                    )

                    # Task 8: Customer Progress Update on SLA breach (investigation delay)
                    try:
                        from apps.communications.services import CustomerCommunicationService
                        from apps.communications.models import MessageTemplate
                        CustomerCommunicationService.queue_progress_update(
                            complaint=handoff.complaint,
                            category=MessageTemplate.Category.INVESTIGATION_DELAY,
                            details=f"Technical review with {handoff.team.name} requires extended investigation.",
                            force=False,
                        )
                    except Exception as e:
                        logger.warning(f"Customer progress update failed for overdue handoff {handoff.id}: {e}")

                # Send supervisor / operator escalation if not already sent
                if not handoff.escalated_at:
                    handoff.escalated_at = now
                    handoff.save(update_fields=["escalated_at"])

                    target_user = handoff.complaint.assigned_operator or handoff.created_by
                    if target_user:
                        Notification.objects.create(
                            tenant=handoff.tenant,
                            recipient=target_user,
                            kind=Notification.Kind.OVERDUE,
                            title=f"OVERDUE: {handoff.team.name} response overdue on {handoff.complaint.reference}",
                            complaint=handoff.complaint,
                        )
                        escalations_sent += 1

            # 2. Check for approaching deadline (e.g. within 4 hours)
            elif now >= (due_at - timedelta(hours=4)):
                if not handoff.reminder_sent_at:
                    handoff.reminder_sent_at = now
                    handoff.save(update_fields=["reminder_sent_at"])

                    target_user = handoff.complaint.assigned_operator or handoff.created_by
                    if target_user:
                        Notification.objects.create(
                            tenant=handoff.tenant,
                            recipient=target_user,
                            kind=Notification.Kind.DEADLINE,
                            title=f"Deadline approaching: {handoff.team.name} response due within 4h on {handoff.complaint.reference}",
                            complaint=handoff.complaint,
                        )
                        reminders_sent += 1

        return {
            "remindersSent": reminders_sent,
            "escalationsSent": escalations_sent,
            "scannedCount": qs.count(),
        }
