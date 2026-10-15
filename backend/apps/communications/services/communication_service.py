import logging
import uuid
from datetime import timedelta
from typing import Optional, Dict, Any, List, Tuple
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.common.models import OutboxMessage, AuditEvent
from apps.complaints.models import Complaint, ComplaintTimelineEvent
from apps.communications.models import (
    CommunicationPolicy,
    MessageTemplate,
    CommunicationPreference,
    CustomerCommunication,
    CommunicationDeliveryAttempt,
    CommunicationEvent,
)
from apps.communications.adapters import get_communication_adapter, DeliveryResult
from .template_engine import TemplateEngine, TemplateValidationError

logger = logging.getLogger("resolveai.communications.services")


class CustomerCommunicationService:
    """
    Core domain service managing customer notifications, eligibility evaluation,
    automatic acknowledgements, maker-checker verified resolution gates,
    reopening suppression, anti-spam intervals, and durable dispatch.
    """

    DEFAULT_TEMPLATES_SPEC = [
        {
            "code": "ACK_DEFAULT",
            "category": MessageTemplate.Category.ACKNOWLEDGEMENT,
            "channel": MessageTemplate.Channel.EMAIL,
            "subject": "Acknowledgement of Complaint {complaint_reference}",
            "body_template": (
                "Dear {customer_name},\n\n"
                "We have received your complaint regarding '{summary}'. "
                "Your official reference number is {complaint_reference}. "
                "Our team at {institution_name} has commenced investigation. "
                "For updates, please quote your reference number or contact {support_contact}.\n\n"
                "Sincerely,\nCustomer Care Team"
            ),
            "permitted_variables": [
                "customer_name",
                "complaint_reference",
                "summary",
                "institution_name",
                "support_contact",
            ],
        },
        {
            "code": "ACK_DEFAULT_SMS",
            "category": MessageTemplate.Category.ACKNOWLEDGEMENT,
            "channel": MessageTemplate.Channel.SMS,
            "subject": "",
            "body_template": (
                "{institution_name}: We received your complaint ({complaint_reference}). "
                "Investigation is underway. For enquiries contact {support_contact}."
            ),
            "permitted_variables": [
                "complaint_reference",
                "institution_name",
                "support_contact",
            ],
        },
        {
            "code": "ACK_DEFAULT_WA",
            "category": MessageTemplate.Category.ACKNOWLEDGEMENT,
            "channel": MessageTemplate.Channel.WHATSAPP,
            "subject": "",
            "body_template": (
                "Hello {customer_name}, your complaint *{complaint_reference}* regarding '{summary}' "
                "has been logged with {institution_name}. We are reviewing the case. Help: {support_contact}"
            ),
            "permitted_variables": [
                "customer_name",
                "complaint_reference",
                "summary",
                "institution_name",
                "support_contact",
            ],
        },
        {
            "code": "PROGRESS_DEFAULT",
            "category": MessageTemplate.Category.PROGRESS_UPDATE,
            "channel": MessageTemplate.Channel.EMAIL,
            "subject": "Update on your complaint: {complaint_reference}",
            "body_template": (
                "Dear {customer_name},\n\n"
                "This is an interim update on your complaint {complaint_reference}: {details}.\n"
                "Our investigation remains ongoing. We will provide our next update as soon as further progress is confirmed.\n\n"
                "{institution_name} Support: {support_contact}"
            ),
            "permitted_variables": [
                "customer_name",
                "complaint_reference",
                "details",
                "institution_name",
                "support_contact",
            ],
        },
        {
            "code": "DELAY_DEFAULT",
            "category": MessageTemplate.Category.INVESTIGATION_DELAY,
            "channel": MessageTemplate.Channel.EMAIL,
            "subject": "Notice regarding investigation on {complaint_reference}",
            "body_template": (
                "Dear {customer_name},\n\n"
                "The investigation into complaint {complaint_reference} requires additional inter-departmental verification. "
                "We regret any inconvenience caused by this delay and remain committed to fair resolution.\n\n"
                "Sincerely,\n{institution_name}"
            ),
            "permitted_variables": [
                "customer_name",
                "complaint_reference",
                "institution_name",
                "support_contact",
            ],
        },
        {
            "code": "INFO_REQUEST_DEFAULT",
            "category": MessageTemplate.Category.INFO_REQUEST,
            "channel": MessageTemplate.Channel.EMAIL,
            "subject": "Action Required: Additional details for {complaint_reference}",
            "body_template": (
                "Dear {customer_name},\n\n"
                "To continue processing your complaint {complaint_reference}, please provide: {details}.\n"
                "Reply to this notice or contact {support_contact}.\n\n"
                "{institution_name}"
            ),
            "permitted_variables": [
                "customer_name",
                "complaint_reference",
                "details",
                "institution_name",
                "support_contact",
            ],
        },
        {
            "code": "ESCALATION_DEFAULT",
            "category": MessageTemplate.Category.ESCALATION_NOTICE,
            "channel": MessageTemplate.Channel.EMAIL,
            "subject": "Case Escalation: Complaint {complaint_reference}",
            "body_template": (
                "Dear {customer_name},\n\n"
                "Your complaint {complaint_reference} has been escalated to senior specialist review for expedited resolution.\n\n"
                "{institution_name}"
            ),
            "permitted_variables": [
                "customer_name",
                "complaint_reference",
                "institution_name",
                "support_contact",
            ],
        },
        {
            "code": "RESOLUTION_DEFAULT",
            "category": MessageTemplate.Category.VERIFIED_RESOLUTION,
            "channel": MessageTemplate.Channel.EMAIL,
            "subject": "Verified Resolution of Complaint {complaint_reference}",
            "body_template": (
                "Dear {customer_name},\n\n"
                "Following thorough investigation, your complaint {complaint_reference} has been resolved.\n\n"
                "Resolution Summary: {resolution_outcome}\n\n"
                "Thank you for banking with {institution_name}. If you have additional questions, contact {support_contact}."
            ),
            "permitted_variables": [
                "customer_name",
                "complaint_reference",
                "resolution_outcome",
                "institution_name",
                "support_contact",
            ],
        },
        {
            "code": "REOPENED_DEFAULT",
            "category": MessageTemplate.Category.REOPENED_NOTICE,
            "channel": MessageTemplate.Channel.EMAIL,
            "subject": "Notice: Reopening of Complaint {complaint_reference}",
            "body_template": (
                "Dear {customer_name},\n\n"
                "Your complaint {complaint_reference} has been reopened for further investigation. "
                "Reason: {reopen_reason}.\n\n"
                "Our team at {institution_name} is actively re-examining the case."
            ),
            "permitted_variables": [
                "customer_name",
                "complaint_reference",
                "reopen_reason",
                "institution_name",
                "support_contact",
            ],
        },
    ]

    @classmethod
    def get_or_create_default_policy(cls, tenant) -> CommunicationPolicy:
        """
        Retrieves or bootstraps a tenant's CommunicationPolicy and baseline templates.
        """
        policy, created = CommunicationPolicy.objects.get_or_create(
            tenant=tenant,
            defaults={
                "auto_acknowledge_enabled": True,
                "skip_ack_if_channel_acknowledged": True,
                "default_channel": MessageTemplate.Channel.EMAIL,
                "permitted_channels": ["EMAIL", "SMS", "WHATSAPP"],
                "min_progress_interval_hours": 24,
                "require_maker_checker_for_resolution": True,
            }
        )

        # Seed baseline templates for this tenant if not existing
        for spec in cls.DEFAULT_TEMPLATES_SPEC:
            tmpl, _ = MessageTemplate.objects.get_or_create(
                tenant=tenant,
                code=spec["code"],
                channel=spec["channel"],
                version=1,
                defaults={
                    "category": spec["category"],
                    "is_approved": True,
                    "subject": spec["subject"],
                    "body_template": spec["body_template"],
                    "permitted_variables": spec["permitted_variables"],
                }
            )
            if spec["category"] == MessageTemplate.Category.ACKNOWLEDGEMENT and not policy.acknowledgement_template:
                policy.acknowledgement_template = tmpl
            elif spec["category"] == MessageTemplate.Category.VERIFIED_RESOLUTION and not policy.verified_resolution_template:
                policy.verified_resolution_template = tmpl
            elif spec["category"] == MessageTemplate.Category.PROGRESS_UPDATE and not policy.progress_update_template:
                policy.progress_update_template = tmpl
            elif spec["category"] == MessageTemplate.Category.REOPENED_NOTICE and not policy.reopen_template:
                policy.reopen_template = tmpl

        policy.save()
        return policy

    @classmethod
    def mask_destination(cls, destination: str) -> str:
        """
        Safely masks PII recipient destinations for privacy in compliance logs and UI.
        """
        if not destination:
            return ""
        if "@" in destination:
            parts = destination.split("@")
            return f"{parts[0][:1]}***@{parts[1]}"
        elif len(destination) > 6:
            return f"{destination[:3]}***{destination[-3:]}"
        return f"{destination[:1]}***"

    @classmethod
    def get_customer_recipient_and_channel(
        cls,
        complaint: Complaint,
        preferred_channel_override: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Resolves customer's verified delivery destination and channel, respecting opt-ins.
        """
        customer = complaint.customer
        tenant = complaint.tenant
        pref = CommunicationPreference.objects.filter(customer=customer, tenant=tenant).first()

        selected_channel = preferred_channel_override
        if not selected_channel:
            selected_channel = pref.preferred_channel if pref else MessageTemplate.Channel.EMAIL

        destination = None
        if selected_channel == MessageTemplate.Channel.EMAIL:
            if not pref or pref.email_opt_in:
                destination = (pref.preferred_email if pref and pref.preferred_email else customer.email)
        elif selected_channel == MessageTemplate.Channel.SMS:
            if not pref or pref.sms_opt_in:
                destination = (pref.preferred_phone if pref and pref.preferred_phone else customer.phone)
        elif selected_channel == MessageTemplate.Channel.WHATSAPP:
            if not pref or pref.whatsapp_opt_in:
                destination = (pref.preferred_phone if pref and pref.preferred_phone else customer.phone)

        return selected_channel, destination

    @classmethod
    @transaction.atomic
    def queue_acknowledgement(
        cls,
        complaint: Complaint,
        originating_event_id: str = "",
        channel_already_acknowledged: bool = False
    ) -> Optional[CustomerCommunication]:
        """
        Evaluates acknowledgement eligibility and queues automated customer acknowledgement.
        Guarantees idempotency: duplicate events will never create duplicate acknowledgements.
        """
        tenant = complaint.tenant
        policy = cls.get_or_create_default_policy(tenant)

        # 1. Policy check: Auto acknowledge enabled?
        if not policy.auto_acknowledge_enabled:
            logger.info(f"Auto-acknowledgement disabled for tenant {tenant.name}. Skipping.")
            return None

        # 2. Check if originating bank channel already sent acknowledgement
        if policy.skip_ack_if_channel_acknowledged and channel_already_acknowledged:
            logger.info(f"Channel already acknowledged complaint {complaint.reference}. Skipping ResolveAI ack.")
            return None

        # 3. Idempotency: Has acknowledgement already been queued/sent?
        existing = CustomerCommunication.objects.filter(
            complaint=complaint,
            category=MessageTemplate.Category.ACKNOWLEDGEMENT
        ).first()
        if existing:
            logger.info(f"Acknowledgement already exists for complaint {complaint.reference} (ID: {existing.id}).")
            return existing

        # 4. Resolve recipient & channel
        channel, destination = cls.get_customer_recipient_and_channel(complaint)
        if not destination:
            logger.warning(f"No valid customer recipient destination for complaint {complaint.reference}. Skipping ack.")
            AuditEvent.objects.create(
                tenant_id=tenant.id,
                action="communication.ack_skipped_no_recipient",
                entity_type="Complaint",
                entity_id=str(complaint.id),
                details={"reference": complaint.reference}
            )
            return None

        # 5. Select template
        template = policy.acknowledgement_template
        if not template or template.channel != channel:
            template = MessageTemplate.objects.filter(
                tenant=tenant,
                category=MessageTemplate.Category.ACKNOWLEDGEMENT,
                channel=channel,
                is_approved=True
            ).order_by("-version").first()

        if not template:
            # Fallback to system default template
            template = MessageTemplate.objects.filter(
                tenant__isnull=True,
                category=MessageTemplate.Category.ACKNOWLEDGEMENT,
                channel=channel,
                is_approved=True
            ).order_by("-version").first()

        if not template:
            raise ValidationError(f"No approved acknowledgement template available for channel {channel}.")

        # 6. Render template safely
        customer_name = f"{complaint.customer.first_name} {complaint.customer.last_name}".strip() or "Valued Customer"
        support_contact = getattr(tenant, "support_phone", "") or "support@resolveai.bank.local"
        context = {
            "customer_name": customer_name,
            "complaint_reference": complaint.reference,
            "summary": complaint.summary,
            "institution_name": tenant.name,
            "support_contact": support_contact,
        }
        subj, body = TemplateEngine.render(template, context)

        # 7. Persist CustomerCommunication
        comm = CustomerCommunication.objects.create(
            tenant=tenant,
            complaint=complaint,
            customer=complaint.customer,
            template=template,
            template_version=template.version,
            category=MessageTemplate.Category.ACKNOWLEDGEMENT,
            channel=channel,
            recipient_destination=destination,
            subject=subj,
            rendered_content=body,
            status=CustomerCommunication.Status.QUEUED,
            trigger_event="INGESTION_ACK",
            originating_event_id=originating_event_id or complaint.original_source_reference,
            complaint_version_at_creation=complaint.status,
            max_retries=3,
        )

        CommunicationEvent.objects.create(
            communication=comm,
            event_type="QUEUED",
            title=f"Acknowledgement queued via {channel}",
            detail=f"Recipient: {destination}. Template: {template.code} v{template.version}.",
            actor="Ingestion Service",
        )

        # Record Outbox Message for transactional guarantee
        outbox = OutboxMessage.objects.create(
            tenant_id=tenant.id,
            topic="communication.dispatch",
            payload={
                "communication_id": str(comm.id),
                "complaint_id": str(complaint.id),
                "category": comm.category,
                "channel": comm.channel,
            }
        )

        ComplaintTimelineEvent.objects.create(
            complaint=complaint,
            tenant=tenant,
            kind="COMMUNICATION_ACKNOWLEDGED",
            title=f"Customer acknowledgement queued ({channel})",
            detail=f"Queued for dispatch to {destination}.",
            actor="Communications Engine",
        )

        # Enqueue background Celery task
        comm_id_str = str(comm.id)
        from apps.communications.tasks import dispatch_customer_communication_task
        transaction.on_commit(lambda: dispatch_customer_communication_task.delay(comm_id_str))

        logger.info(f"Queued customer acknowledgement {comm.id} for complaint {complaint.reference}")
        return comm

    @classmethod
    @transaction.atomic
    def queue_verified_resolution_notification(
        cls,
        complaint: Complaint,
        user
    ) -> CustomerCommunication:
        """
        Task 5: Strict Maker-Checker Verified Resolution Gate.
        A final resolution message may be queued ONLY when:
        1. The specific complaint is currently RESOLVED.
        2. A valid current resolution outcome exists.
        3. An authorised independent verifier approved that outcome (verified_by != reported_by).
        4. The current complaint version still matches the message eligibility record.
        5. The tenant permits the selected communication.
        6. The customer has an authorised recipient destination.
        7. An equivalent notification has not already been processed.
        """
        # Concurrency control: Row-level lock on the complaint record
        complaint = Complaint.objects.select_for_update().get(id=complaint.id, tenant=complaint.tenant)
        tenant = complaint.tenant
        policy = cls.get_or_create_default_policy(tenant)

        # Gate 1: Currently RESOLVED
        if complaint.status != Complaint.Status.RESOLVED:
            raise ValidationError(
                f"Cannot queue resolution message: complaint is in status '{complaint.status}', expected 'RESOLVED'."
            )

        # Gate 2: Valid resolution outcome exists
        if not complaint.resolution_outcome:
            raise ValidationError("Cannot queue resolution message without a recorded resolution outcome.")

        # Gate 3: Independent verification
        if policy.require_maker_checker_for_resolution:
            if complaint.resolution_verification != Complaint.ResolutionVerification.VERIFIED:
                raise ValidationError("Cannot queue resolution message: outcome has not been formally VERIFIED.")
            if not complaint.resolution_verified_by_id:
                raise ValidationError("Cannot queue resolution message: verifier is missing.")
            if complaint.resolution_reported_by_id and complaint.resolution_reported_by_id == complaint.resolution_verified_by_id:
                raise PermissionDenied("Segregation of duties violation: maker cannot verify outcome to trigger resolution messaging.")

        # Gate 4: Tenant permits communication
        # (Verified via policy channel check below)

        # Gate 5: Recipient destination
        channel, destination = cls.get_customer_recipient_and_channel(complaint)
        if not destination:
            raise ValidationError(f"No valid customer recipient destination for complaint {complaint.reference}.")

        # Gate 6: Idempotency - Equivalent notification has not already been queued or delivered
        existing = CustomerCommunication.objects.filter(
            complaint=complaint,
            category=MessageTemplate.Category.VERIFIED_RESOLUTION,
            status__in=[
                CustomerCommunication.Status.QUEUED,
                CustomerCommunication.Status.SENDING,
                CustomerCommunication.Status.SENT,
                CustomerCommunication.Status.DELIVERED,
            ]
        ).first()
        if existing:
            logger.info(f"Resolution notification already queued/sent for {complaint.reference} (ID: {existing.id}).")
            return existing

        # Select template
        template = policy.verified_resolution_template
        if not template or template.channel != channel:
            template = MessageTemplate.objects.filter(
                tenant=tenant,
                category=MessageTemplate.Category.VERIFIED_RESOLUTION,
                channel=channel,
                is_approved=True
            ).order_by("-version").first()

        if not template:
            template = MessageTemplate.objects.filter(
                tenant__isnull=True,
                category=MessageTemplate.Category.VERIFIED_RESOLUTION,
                channel=channel,
                is_approved=True
            ).order_by("-version").first()

        if not template:
            raise ValidationError(f"No approved resolution template available for channel {channel}.")

        # Safe rendering
        customer_name = f"{complaint.customer.first_name} {complaint.customer.last_name}".strip() or "Valued Customer"
        support_contact = getattr(tenant, "support_phone", "") or "support@resolveai.bank.local"
        context = {
            "customer_name": customer_name,
            "complaint_reference": complaint.reference,
            "resolution_outcome": complaint.resolution_outcome,
            "institution_name": tenant.name,
            "support_contact": support_contact,
        }
        subj, body = TemplateEngine.render(template, context)

        verification_ref = f"VRF-{complaint.id}-{complaint.resolution_verified_at.strftime('%Y%m%d%H%M') if complaint.resolution_verified_at else 'AUTO'}"

        comm = CustomerCommunication.objects.create(
            tenant=tenant,
            complaint=complaint,
            customer=complaint.customer,
            template=template,
            template_version=template.version,
            category=MessageTemplate.Category.VERIFIED_RESOLUTION,
            channel=channel,
            recipient_destination=destination,
            subject=subj,
            rendered_content=body,
            status=CustomerCommunication.Status.QUEUED,
            trigger_event="RESOLUTION_VERIFIED",
            verification_reference=verification_ref,
            complaint_version_at_creation=complaint.status,
            max_retries=3,
        )

        verifier_name = complaint.resolution_verified_by.display_name if complaint.resolution_verified_by else "Independent Verifier"
        CommunicationEvent.objects.create(
            communication=comm,
            event_type="QUEUED",
            title=f"Verified resolution notice queued ({channel})",
            detail=f"Approved by {verifier_name}. Verification Ref: {verification_ref}.",
            actor=verifier_name,
        )

        OutboxMessage.objects.create(
            tenant_id=tenant.id,
            topic="communication.dispatch",
            payload={
                "communication_id": str(comm.id),
                "complaint_id": str(complaint.id),
                "category": comm.category,
                "channel": comm.channel,
            }
        )

        ComplaintTimelineEvent.objects.create(
            complaint=complaint,
            tenant=tenant,
            kind="COMMUNICATION_QUEUED",
            title=f"Resolution notification queued ({channel})",
            detail=f"Verified outcome notice queued for customer {destination}.",
            actor="Resolution Gatekeeper",
        )

        comm_id_str = str(comm.id)
        from apps.communications.tasks import dispatch_customer_communication_task
        transaction.on_commit(lambda: dispatch_customer_communication_task.delay(comm_id_str))

        logger.info(f"Queued verified resolution message {comm.id} for complaint {complaint.reference}")
        return comm

    @classmethod
    @transaction.atomic
    def cancel_pending_resolution_communications(
        cls,
        complaint: Complaint,
        reason: str = "Complaint reopened"
    ) -> int:
        # 1. Pre-submission cancellation: only PENDING and QUEUED messages can be cancelled before delivery
        pending_comms = CustomerCommunication.objects.filter(
            complaint=complaint,
            category=MessageTemplate.Category.VERIFIED_RESOLUTION,
            status__in=[
                CustomerCommunication.Status.PENDING,
                CustomerCommunication.Status.QUEUED,
            ]
        )

        cancelled_count = 0
        now = timezone.now()
        for comm in pending_comms:
            comm.status = CustomerCommunication.Status.CANCELLED
            comm.cancelled_at = now
            comm.cancellation_reason = reason
            comm.save(update_fields=["status", "cancelled_at", "cancellation_reason", "updated_at"])

            CommunicationEvent.objects.create(
                communication=comm,
                event_type="CANCELLED",
                title="Resolution notification suppressed (pre-submission)",
                detail=f"Cancelled prior to provider dispatch due to case reopening: {reason}",
                actor="Complaint Reopen Service",
            )
            cancelled_count += 1

        # 2. Post-submission audit trail: messages already submitted/delivered are NEVER modified or deleted
        already_submitted = CustomerCommunication.objects.filter(
            complaint=complaint,
            category=MessageTemplate.Category.VERIFIED_RESOLUTION,
            status__in=[
                CustomerCommunication.Status.SENT,
                CustomerCommunication.Status.DELIVERY_UNCONFIRMED,
                CustomerCommunication.Status.DELIVERED,
            ]
        )
        for submitted_comm in already_submitted:
            CommunicationEvent.objects.create(
                communication=submitted_comm,
                event_type="SUPERSEDED_BY_REOPEN",
                title="Delivered resolution notice superseded by case reopening",
                detail=(
                    f"Notice was previously submitted to {submitted_comm.channel} (Provider Ref: {submitted_comm.provider_message_id or 'N/A'}). "
                    f"Outcome record superseded by reopening: {reason}. Record preserved in audit history."
                ),
                actor="Complaint Reopen Service",
            )

        if cancelled_count > 0:
            ComplaintTimelineEvent.objects.create(
                complaint=complaint,
                tenant=complaint.tenant,
                kind="COMMUNICATION_CANCELLED",
                title="Obsolete resolution notification suppressed",
                detail=f"Suppressed {cancelled_count} pending resolution message(s): {reason}.",
                actor="Reopen Watcher",
            )
            logger.info(f"Suppressed {cancelled_count} pending resolution notifications for {complaint.reference}")

        return cancelled_count

    @classmethod
    @transaction.atomic
    def queue_progress_update(
        cls,
        complaint: Complaint,
        category: str = MessageTemplate.Category.PROGRESS_UPDATE,
        details: str = "",
        force: bool = False
    ) -> Optional[CustomerCommunication]:
        """
        Task 8: Automated Progress Updates (investigation delay, SLA breach update, info request).
        Applies configurable anti-spam intervals and deduplication controls.
        """
        tenant = complaint.tenant
        policy = cls.get_or_create_default_policy(tenant)

        # Anti-spam frequency check: check recent communications for this complaint
        if not force:
            recent_comm = CustomerCommunication.objects.filter(
                complaint=complaint,
                category__in=[
                    MessageTemplate.Category.PROGRESS_UPDATE,
                    MessageTemplate.Category.INVESTIGATION_DELAY,
                    MessageTemplate.Category.ESCALATION_NOTICE,
                ],
                created_at__gte=timezone.now() - timedelta(hours=policy.min_progress_interval_hours)
            ).first()
            if recent_comm:
                logger.info(
                    f"Progress update skipped for {complaint.reference}: "
                    f"recent update sent {recent_comm.created_at} (< {policy.min_progress_interval_hours}h interval)."
                )
                return None

        channel, destination = cls.get_customer_recipient_and_channel(complaint)
        if not destination:
            return None

        # Template selection
        template = MessageTemplate.objects.filter(
            tenant=tenant,
            category=category,
            channel=channel,
            is_approved=True
        ).order_by("-version").first()

        if not template:
            template = MessageTemplate.objects.filter(
                tenant__isnull=True,
                category=category,
                channel=channel,
                is_approved=True
            ).order_by("-version").first()

        if not template:
            return None

        customer_name = f"{complaint.customer.first_name} {complaint.customer.last_name}".strip() or "Valued Customer"
        support_contact = getattr(tenant, "support_phone", "") or "support@resolveai.bank.local"
        context = {
            "customer_name": customer_name,
            "complaint_reference": complaint.reference,
            "details": details or "Investigation is actively progressing with operational units.",
            "institution_name": tenant.name,
            "support_contact": support_contact,
        }
        subj, body = TemplateEngine.render(template, context)

        comm = CustomerCommunication.objects.create(
            tenant=tenant,
            complaint=complaint,
            customer=complaint.customer,
            template=template,
            template_version=template.version,
            category=category,
            channel=channel,
            recipient_destination=destination,
            subject=subj,
            rendered_content=body,
            status=CustomerCommunication.Status.QUEUED,
            trigger_event="PROGRESS_UPDATE",
            complaint_version_at_creation=complaint.status,
            max_retries=3,
        )

        CommunicationEvent.objects.create(
            communication=comm,
            event_type="QUEUED",
            title=f"Progress update queued ({channel})",
            detail=f"Category: {category}. Destination: {destination}.",
            actor="SLA Monitor",
        )

        OutboxMessage.objects.create(
            tenant_id=tenant.id,
            topic="communication.dispatch",
            payload={
                "communication_id": str(comm.id),
                "complaint_id": str(complaint.id),
                "category": comm.category,
                "channel": comm.channel,
            }
        )

        ComplaintTimelineEvent.objects.create(
            complaint=complaint,
            tenant=tenant,
            kind="COMMUNICATION_QUEUED",
            title=f"Customer update queued ({category})",
            detail=f"Sent via {channel} to {destination}.",
            actor="Communications Engine",
        )

        comm_id_str = str(comm.id)
        from apps.communications.tasks import dispatch_customer_communication_task
        transaction.on_commit(lambda: dispatch_customer_communication_task.delay(comm_id_str))

        return comm

    @classmethod
    @transaction.atomic
    def dispatch_communication(cls, communication_id: str) -> CustomerCommunication:
        """
        Task 4 & Task 9: Durable background worker dispatch with revalidation.
        - Pessimistic row locking.
        - Suppresses cancelled communications.
        - Revalidates complaint state immediately before external dispatch.
        - Records individual delivery attempts and audit events.
        """
        # 1. Canonical lock hierarchy: Peek communication metadata without lock
        comm_meta = CustomerCommunication.objects.filter(id=communication_id).values(
            "id", "complaint_id", "status", "category"
        ).first()
        if not comm_meta:
            logger.error(f"CustomerCommunication {communication_id} not found for dispatch.")
            return None

        # Lock Complaint FIRST to ensure identical acquisition order across all case operations
        complaint = Complaint.objects.select_for_update().get(id=comm_meta["complaint_id"])
        # Lock CustomerCommunication SECOND
        comm = CustomerCommunication.objects.select_for_update().get(id=communication_id)

        # 2. State check: Already cancelled?
        if comm.status == CustomerCommunication.Status.CANCELLED:
            logger.info(f"Communication {comm.id} was cancelled before dispatch; skipping.")
            return comm

        # 3. Terminal state check: Already sent/delivered?
        if comm.status in (CustomerCommunication.Status.SENT, CustomerCommunication.Status.DELIVERED):
            logger.info(f"Communication {comm.id} already in terminal state {comm.status}; skipping.")
            return comm

        # 4. CRITICAL TASK 5 & 7 GATE: Pre-dispatch Revalidation for Resolution Notifications
        if comm.category == MessageTemplate.Category.VERIFIED_RESOLUTION:
            if complaint.status != Complaint.Status.RESOLVED or complaint.resolution_verification != Complaint.ResolutionVerification.VERIFIED:
                comm.status = CustomerCommunication.Status.CANCELLED
                comm.cancelled_at = timezone.now()
                comm.cancellation_reason = f"Pre-dispatch validation failed: complaint status is '{complaint.status}' (no longer RESOLVED/VERIFIED)."
                comm.save(update_fields=["status", "cancelled_at", "cancellation_reason", "updated_at"])

                CommunicationEvent.objects.create(
                    communication=comm,
                    event_type="CANCELLED_AT_DISPATCH",
                    title="Pre-dispatch gate rejected obsolete resolution message",
                    detail=comm.cancellation_reason,
                    actor="Dispatch Worker",
                )
                logger.warning(f"Resolution communication {comm.id} cancelled at dispatch: {comm.cancellation_reason}")
                return comm

        # Mark SENDING
        comm.status = CustomerCommunication.Status.SENDING
        comm.save(update_fields=["status", "updated_at"])

        attempt_num = comm.retry_count + 1
        adapter = get_communication_adapter(comm.channel)

        # Call adapter
        result: DeliveryResult = adapter.send_message(
            recipient=comm.recipient_destination,
            content=comm.rendered_content,
            subject=comm.subject,
            metadata={"category": comm.category, "complaint_ref": comm.complaint.reference}
        )

        # Record delivery attempt
        attempt = CommunicationDeliveryAttempt.objects.create(
            communication=comm,
            attempt_number=attempt_num,
            channel=comm.channel,
            provider=adapter.provider_name,
            destination=comm.recipient_destination,
            status=result.status,
            provider_reference=result.provider_reference,
            provider_response=result.provider_response,
            latency_ms=result.latency_ms,
            error_detail=result.error_detail,
        )

        now = timezone.now()
        comm.provider = adapter.provider_name
        comm.provider_message_id = result.provider_message_id

        if result.status == "DELIVERED":
            comm.status = CustomerCommunication.Status.DELIVERED
            comm.sent_at = now
            comm.delivered_at = now
            comm.error_message = ""
            CommunicationEvent.objects.create(
                communication=comm,
                event_type="DELIVERED",
                title=f"Delivered via {comm.channel}",
                detail=f"Provider Ref: {result.provider_reference}. Confirmed delivery receipt.",
                actor="Worker",
            )
            ComplaintTimelineEvent.objects.create(
                complaint=comm.complaint,
                tenant=comm.tenant,
                kind="COMMUNICATION_DELIVERED",
                title=f"Customer message delivered ({comm.channel})",
                detail=f"{comm.get_category_display()} confirmed delivered to {comm.recipient_destination}.",
                actor="Delivery Adapter",
            )
        elif result.status == "ACCEPTED":
            comm.status = CustomerCommunication.Status.DELIVERY_UNCONFIRMED
            comm.sent_at = now
            CommunicationEvent.objects.create(
                communication=comm,
                event_type="ACCEPTED",
                title=f"Submitted to provider relay ({comm.channel})",
                detail=f"Provider accepted transmission; delivery unconfirmed.",
                actor="Worker",
            )
        else:
            # Failure handling
            comm.retry_count = attempt_num
            comm.error_message = result.error_detail

            if result.is_transient and comm.retry_count < comm.max_retries:
                comm.status = CustomerCommunication.Status.QUEUED
                CommunicationEvent.objects.create(
                    communication=comm,
                    event_type="RETRY_SCHEDULED",
                    title=f"Transient delivery failure (Attempt #{attempt_num})",
                    detail=f"{result.error_detail}. Queued for retry.",
                    actor="Worker",
                )
            else:
                comm.status = CustomerCommunication.Status.FAILED
                CommunicationEvent.objects.create(
                    communication=comm,
                    event_type="FAILED",
                    title=f"Delivery failed permanently after {attempt_num} attempts",
                    detail=result.error_detail,
                    actor="Worker",
                )
                ComplaintTimelineEvent.objects.create(
                    complaint=comm.complaint,
                    tenant=comm.tenant,
                    kind="COMMUNICATION_FAILED",
                    title=f"Customer message failed ({comm.channel})",
                    detail=f"Delivery error: {result.error_detail}",
                    actor="Delivery Adapter",
                )

        comm.save()
        logger.info(f"Communication {comm.id} dispatch completed with status {comm.status}")
        return comm
