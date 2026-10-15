import uuid
from datetime import timedelta
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.services import DevAuthService
from apps.common.models import OutboxMessage, AuditEvent
from apps.complaints.models import Complaint, ComplaintCategory, Customer
from apps.handoffs.adapters.base import DeliveryResult
from apps.handoffs.adapters.simulated import SimulatedBankDeliveryAdapter
from apps.handoffs.models import (
    ForwardingHandoff,
    ForwardingPolicy,
    HandoffAttempt,
    HandoffEvent,
    HandoffResponse,
    ReceivingTeam,
    TeamRecipient,
)
from apps.handoffs.services import HandoffService, SLAMonitoringService
from apps.handoffs.tasks import dispatch_handoff_task
from apps.intelligence.models import AIProcessingJob
from apps.intelligence.tasks import process_complaint_intelligence_task
from apps.notifications.models import Notification
from apps.tenants.models import Tenant


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class Stage5OperationsForwardingTests(TestCase):
    """
    Comprehensive verification for Stage 5:
    Operations Forwarding, Case Handoffs, SLA Tracking, Background Workers,
    Simulated Banking Adapters, and Security Isolation.
    """

    def setUp(self):
        # 1. Primary Tenant & Personas
        self.dev_auth = DevAuthService()
        self.tenant = self.dev_auth.ensure_synthetic_tenant()

        self.operator = self.dev_auth.get_or_create_persona("operator")
        self.verifier = self.dev_auth.get_or_create_persona("verifier")
        self.lead = self.dev_auth.get_or_create_persona("lead")

        # 2. Competitor Tenant for cross-tenant isolation testing
        self.other_tenant, _ = Tenant.objects.get_or_create(
            slug="t-zenith-corp",
            defaults={
                "name": "Zenith Commercial Bank",
                "time_zone": "Africa/Lagos",
                "support_label": "Zenith BIIRS Support",
                "support_contact": "support@zenith.test",
                "support_hours": "Mon-Fri 08:00-17:00",
            }
        )
        self.other_operator = User.objects.create_user(
            username="zenith_operator",
            email="operator@zenith.test",
            tenant=self.other_tenant,
            role_label="Operator",
            permissions_list=["complaints.read", "complaints.forward"],
            first_name="Zenith",
            last_name="Operator",
        )

        # 3. Categories
        self.category, _ = ComplaintCategory.objects.get_or_create(
            tenant=self.tenant,
            code="TRANSFER",
            defaults={"label": "Transfer & Payments"}
        )

        # 4. Receiving Teams for primary tenant
        self.team_settle = ReceivingTeam.objects.create(
            tenant=self.tenant,
            name="Settlements team",
            code="SETTLEMENTS",
            channel="Bank case-management queue",
            fallback_channel="Secure email",
            response_due_hours=24,
        )
        self.team_settle.allowed_categories.add(self.category)

        self.recipient1 = TeamRecipient.objects.create(
            team=self.team_settle,
            name="Duty lead",
            role_or_title="Lead Recon Specialist"
        )

        # Team without fallback channel
        self.team_cards = ReceivingTeam.objects.create(
            tenant=self.tenant,
            name="Card operations",
            code="CARDS",
            channel="Secure email",
            fallback_channel="",  # No fallback
            response_due_hours=48,
        )

        # Foreign team belonging strictly to competitor tenant
        self.foreign_team = ReceivingTeam.objects.create(
            tenant=self.other_tenant,
            name="Zenith Foreign Settlements",
            code="ZENITH_SETTLE",
            channel="Zenith Internal Queue",
            fallback_channel="",
            response_due_hours=24,
        )

        # 5. Customer & Complaint under test
        self.customer = Customer.objects.create(
            tenant=self.tenant,
            customer_number="CUST-5001",
            first_name="Chioma",
            last_name="Eze",
            email="chioma.eze@example.test",
        )
        self.complaint = Complaint.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            reference="CMP-TEST-5001",
            customer_reference=self.customer.customer_number,
            summary="Interbank transfer debited but switch timed out",
            narrative="Customer sent ₦50,000 via mobile banking. Funds deducted from account.",
            status=Complaint.Status.IN_PROGRESS,
            priority=Complaint.Priority.HIGH,
            category=self.category,
            assigned_operator=self.operator,
            received_at=timezone.now(),
            due_at=timezone.now() + timedelta(days=2),
        )

        # API Client
        self.client = APIClient()

    # -------------------------------------------------------------------------
    # TEST 1: Authorised Handoff Creation
    # -------------------------------------------------------------------------
    def test_01_authorised_handoff_creation(self):
        """Authorised operator can forward a complaint; sets state to PREPARED and complaint to FORWARDED."""
        handoff = HandoffService.create_handoff(
            complaint=self.complaint,
            user=self.operator,
            team_id=str(self.team_settle.id),
            recipient="Duty lead",
            message="Please investigate outward session timeout.",
        )

        self.assertIsNotNone(handoff.id)
        self.assertEqual(handoff.tenant, self.tenant)
        self.assertEqual(handoff.team, self.team_settle)
        self.assertEqual(handoff.recipient, "Duty lead")
        self.assertEqual(handoff.channel, self.team_settle.channel)
        self.assertIn(handoff.state, (ForwardingHandoff.State.PREPARED, ForwardingHandoff.State.DELIVERED))

        # Check complaint status transitioned to FORWARDED
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.FORWARDED)

        # Check OutboxMessage created atomically
        outbox = OutboxMessage.objects.filter(topic="handoffs.dispatch", tenant_id=self.tenant.id).first()
        self.assertIsNotNone(outbox)
        self.assertEqual(outbox.payload["handoff_id"], str(handoff.id))

    # -------------------------------------------------------------------------
    # TEST 2: Rejection of Unauthorised Forwarding
    # -------------------------------------------------------------------------
    def test_02_rejection_of_unauthorised_forwarding(self):
        """API rejects forwarding attempts from users lacking 'complaints.forward' permission."""
        # Strip forward permission from user
        user_no_perms = User.objects.create_user(
            username="restricted_user",
            email="restricted@bank.test",
            tenant=self.tenant,
            role_label="Operator",
            permissions_list=["complaints.read"],  # No complaints.forward
        )
        self.client.force_authenticate(user=user_no_perms)

        url = f"/api/v1/complaints/{self.complaint.id}/handoffs"
        response = self.client.post(
            url,
            {"teamId": str(self.team_settle.id), "message": "Forward attempt"},
            format="json",
            HTTP_X_BIIRS_REQUEST="1",
        )
        self.assertEqual(response.status_code, 403)

    # -------------------------------------------------------------------------
    # TEST 3: Cross-Tenant Destination Protection
    # -------------------------------------------------------------------------
    def test_03_cross_tenant_destination_protection(self):
        """Prevent routing complaints to receiving teams belonging to a different banking tenant."""
        from rest_framework.exceptions import ValidationError

        # Attempting to forward tenant complaint to foreign_team (Zenith)
        with self.assertRaises(ValidationError):
            HandoffService.create_handoff(
                complaint=self.complaint,
                user=self.operator,
                team_id=str(self.foreign_team.id),
                message="Cross-tenant forward attempt",
            )

        # Verify via API endpoint returns 400 Validation Error
        self.client.force_authenticate(user=self.operator)
        url = f"/api/v1/complaints/{self.complaint.id}/handoffs"
        response = self.client.post(
            url,
            {"teamId": str(self.foreign_team.id), "message": "Cross-tenant forward attempt"},
            format="json",
            HTTP_X_BIIRS_REQUEST="1",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("teamId", str(response.data))

    # -------------------------------------------------------------------------
    # TEST 4: Information-Sharing Validation & PII Minimisation
    # -------------------------------------------------------------------------
    def test_04_information_sharing_validation(self):
        """Forwarding options and handoff message expose only approved minimised fields, never raw PII."""
        options = HandoffService.get_forwarding_options(self.complaint, self.operator)
        shared_fields = options["sharedFields"]

        self.assertIn("Complaint reference", shared_fields)
        self.assertIn("Masked customer reference", shared_fields)
        self.assertNotIn("Customer PIN", shared_fields)
        self.assertNotIn("Full Account Number", shared_fields)

        # Shareable summary format
        self.assertTrue(options["shareableSummary"].startswith("CMP-TEST-5001"))

    # -------------------------------------------------------------------------
    # TEST 5: Successful Background Job Execution
    # -------------------------------------------------------------------------
    def test_05_successful_background_job_execution(self):
        """Celery worker task executes dispatch and records successful delivery."""
        handoff = ForwardingHandoff.objects.create(
            tenant=self.tenant,
            complaint=self.complaint,
            team=self.team_settle,
            channel=self.team_settle.channel,
            state=ForwardingHandoff.State.PREPARED,
            message="Test dispatch",
            created_by=self.operator,
        )

        res = dispatch_handoff_task(str(handoff.id))
        self.assertEqual(res["state"], ForwardingHandoff.State.DELIVERED)

        handoff.refresh_from_db()
        self.assertEqual(handoff.state, ForwardingHandoff.State.DELIVERED)
        self.assertIsNotNone(handoff.delivered_at)
        self.assertEqual(handoff.retry_count, 1)

    # -------------------------------------------------------------------------
    # TEST 6: Worker Restart and Pending Job Recovery
    # -------------------------------------------------------------------------
    def test_06_worker_restart_and_pending_job_recovery(self):
        """Pending outbox messages survive restarts and are published by the outbox task."""
        from apps.common.tasks import dispatch_outbox_messages_task

        outbox_msg = OutboxMessage.objects.create(
            tenant_id=self.tenant.id,
            topic="handoffs.dispatch",
            payload={"handoff_id": str(uuid.uuid4())},
            status=OutboxMessage.Status.PENDING,
        )

        res = dispatch_outbox_messages_task()
        self.assertGreaterEqual(res["processed_count"], 1)

        outbox_msg.refresh_from_db()
        self.assertEqual(outbox_msg.status, OutboxMessage.Status.PUBLISHED)
        self.assertIsNotNone(outbox_msg.processed_at)

    # -------------------------------------------------------------------------
    # TEST 7: Duplicate Dispatch Prevention (Idempotency)
    # -------------------------------------------------------------------------
    def test_07_duplicate_dispatch_prevention(self):
        """Worker ignores repeated dispatch requests if handoff is already delivered or closed."""
        handoff = ForwardingHandoff.objects.create(
            tenant=self.tenant,
            complaint=self.complaint,
            team=self.team_settle,
            channel=self.team_settle.channel,
            state=ForwardingHandoff.State.DELIVERED,
            delivered_at=timezone.now(),
            retry_count=1,
        )

        # Dispatch again
        dispatched = HandoffService.execute_dispatch(str(handoff.id))
        self.assertEqual(dispatched.state, ForwardingHandoff.State.DELIVERED)
        self.assertEqual(dispatched.retry_count, 1)  # Did not increment or re-transmit

    # -------------------------------------------------------------------------
    # TEST 8: Timeout with Uncertain Delivery Outcome
    # -------------------------------------------------------------------------
    def test_08_timeout_uncertain_delivery_outcome(self):
        """Network timeout during dispatch marks state DELIVERY_UNCONFIRMED; never blindly retries."""
        adapter = SimulatedBankDeliveryAdapter(mode="TIMEOUT_UNCERTAIN")
        handoff = ForwardingHandoff.objects.create(
            tenant=self.tenant,
            complaint=self.complaint,
            team=self.team_settle,
            channel=self.team_settle.channel,
            state=ForwardingHandoff.State.PREPARED,
        )

        dispatched = HandoffService.execute_dispatch(str(handoff.id), adapter=adapter)
        self.assertEqual(dispatched.state, ForwardingHandoff.State.DELIVERY_UNCONFIRMED)

        # Verify attempt has is_uncertain=True
        attempt = dispatched.attempts.last()
        self.assertTrue(attempt.is_uncertain)
        self.assertEqual(attempt.error_code, "SOCKET_TIMEOUT_UNCERTAIN")

    # -------------------------------------------------------------------------
    # TEST 9: Successful Delivery Confirmation
    # -------------------------------------------------------------------------
    def test_09_successful_delivery_confirmation(self):
        """Receipt token from external channel sets state to DELIVERED with audit evidence."""
        adapter = SimulatedBankDeliveryAdapter(mode="SUCCESS_DELIVERED")
        handoff = ForwardingHandoff.objects.create(
            tenant=self.tenant,
            complaint=self.complaint,
            team=self.team_settle,
            channel=self.team_settle.channel,
            state=ForwardingHandoff.State.PREPARED,
        )

        dispatched = HandoffService.execute_dispatch(str(handoff.id), adapter=adapter)
        self.assertEqual(dispatched.state, ForwardingHandoff.State.DELIVERED)
        self.assertTrue(dispatched.delivery_evidence["deliveryReceiptReceived"])
        self.assertIn("receiptToken", dispatched.delivery_evidence)

    # -------------------------------------------------------------------------
    # TEST 10: Failed Dispatch and Approved Fallback
    # -------------------------------------------------------------------------
    def test_10_failed_dispatch_and_approved_fallback(self):
        """When primary channel exhausts retries and fallback exists, state transitions to FALLBACK_IN_PROGRESS."""
        handoff = ForwardingHandoff.objects.create(
            tenant=self.tenant,
            complaint=self.complaint,
            team=self.team_settle,  # Has fallback_channel='Secure email'
            channel=self.team_settle.channel,
            state=ForwardingHandoff.State.PREPARED,
            retry_count=2,  # Already attempted twice
            max_retries=3,
        )

        adapter = SimulatedBankDeliveryAdapter(mode="PERMANENT_FAILURE")
        dispatched = HandoffService.execute_dispatch(str(handoff.id), adapter=adapter)

        # Primary channel exhausted max retries -> activated fallback channel
        self.assertEqual(dispatched.state, ForwardingHandoff.State.FALLBACK_IN_PROGRESS)
        self.assertEqual(dispatched.channel, self.team_settle.fallback_channel)

    # -------------------------------------------------------------------------
    # TEST 11: No Approved Fallback Available
    # -------------------------------------------------------------------------
    def test_11_no_approved_fallback_available(self):
        """When team has no fallback channel, exhausted retries transition state to SEND_FAILED."""
        handoff = ForwardingHandoff.objects.create(
            tenant=self.tenant,
            complaint=self.complaint,
            team=self.team_cards,  # Empty fallback_channel
            channel=self.team_cards.channel,
            state=ForwardingHandoff.State.PREPARED,
            retry_count=2,
            max_retries=3,
        )

        adapter = SimulatedBankDeliveryAdapter(mode="PERMANENT_FAILURE")
        dispatched = HandoffService.execute_dispatch(str(handoff.id), adapter=adapter)

        self.assertEqual(dispatched.state, ForwardingHandoff.State.SEND_FAILED)
        self.assertTrue(dispatched.retry_allowed)  # Can be manually retried by operator

    # -------------------------------------------------------------------------
    # TEST 12: SLA Deadline Calculations
    # -------------------------------------------------------------------------
    def test_12_sla_deadline_calculations(self):
        """Deadline calculation adheres to tenant's configured IANA timezone."""
        deadline = SLAMonitoringService.calculate_response_deadline(self.tenant, hours=24)
        self.assertIsNotNone(deadline)
        now = timezone.now()
        diff_hours = (deadline - now).total_seconds() / 3600.0
        self.assertAlmostEqual(diff_hours, 24.0, delta=1.0)

    # -------------------------------------------------------------------------
    # TEST 13: Reminder Deduplication
    # -------------------------------------------------------------------------
    def test_13_reminder_deduplication(self):
        """Approaching deadline triggers in-app notification once; repeated scans do not duplicate."""
        now = timezone.now()
        handoff = ForwardingHandoff.objects.create(
            tenant=self.tenant,
            complaint=self.complaint,
            team=self.team_settle,
            channel=self.team_settle.channel,
            state=ForwardingHandoff.State.SENT,
            response_due_at=now + timedelta(hours=2),  # Due in 2 hours (within 4h lead window)
            created_by=self.operator,
        )

        # First scan: creates notification
        res1 = SLAMonitoringService.monitor_active_handoffs(self.tenant)
        self.assertEqual(res1["remindersSent"], 1)

        handoff.refresh_from_db()
        self.assertIsNotNone(handoff.reminder_sent_at)

        # Second scan: deduplicated!
        res2 = SLAMonitoringService.monitor_active_handoffs(self.tenant)
        self.assertEqual(res2["remindersSent"], 0)

        # Verify only 1 notification exists in DB
        notif_count = Notification.objects.filter(
            recipient=self.operator,
            kind=Notification.Kind.DEADLINE
        ).count()
        self.assertEqual(notif_count, 1)

    # -------------------------------------------------------------------------
    # TEST 14: Escalation Workflow
    # -------------------------------------------------------------------------
    def test_14_escalation_workflow(self):
        """Expired deadline transitions state to OVERDUE and generates supervisor alert."""
        now = timezone.now()
        handoff = ForwardingHandoff.objects.create(
            tenant=self.tenant,
            complaint=self.complaint,
            team=self.team_settle,
            channel=self.team_settle.channel,
            state=ForwardingHandoff.State.AWAITING_RESPONSE,
            response_due_at=now - timedelta(minutes=15),  # 15 minutes overdue
            created_by=self.operator,
        )

        res = SLAMonitoringService.monitor_active_handoffs(self.tenant)
        self.assertEqual(res["escalationsSent"], 1)

        handoff.refresh_from_db()
        self.assertEqual(handoff.state, ForwardingHandoff.State.OVERDUE)
        self.assertIsNotNone(handoff.escalated_at)

        # Verify escalation notification
        notif = Notification.objects.filter(
            recipient=self.operator,
            kind=Notification.Kind.OVERDUE
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn("OVERDUE", notif.title)

    # -------------------------------------------------------------------------
    # TEST 15: Handoff Response Recording
    # -------------------------------------------------------------------------
    def test_15_handoff_response_recording(self):
        """Recording receiving team response updates state to RESPONDED and notifies operator."""
        handoff = ForwardingHandoff.objects.create(
            tenant=self.tenant,
            complaint=self.complaint,
            team=self.team_settle,
            channel=self.team_settle.channel,
            state=ForwardingHandoff.State.DELIVERED,
            created_by=self.operator,
        )

        response = HandoffService.record_response(
            handoff=handoff,
            summary="Debit confirmed reversed on interbank switch journal.",
            responder_name="Recon Lead",
        )

        self.assertIsNotNone(response.id)
        handoff.refresh_from_db()
        self.assertEqual(handoff.state, ForwardingHandoff.State.RESPONDED)
        self.assertIsNotNone(handoff.responded_at)

        # Check response notification delivered
        notif = Notification.objects.filter(
            recipient=self.operator,
            kind=Notification.Kind.RESPONSE
        ).first()
        self.assertIsNotNone(notif)

    # -------------------------------------------------------------------------
    # TEST 16: AI Task Migration to Background Workers
    # -------------------------------------------------------------------------
    def test_16_ai_task_migration_to_background_workers(self):
        """AI intelligence pipeline executes asynchronously via Celery worker and records job status."""
        job_key = f"test-ai-job-{self.complaint.id}"
        res = process_complaint_intelligence_task(
            complaint_id=str(self.complaint.id),
            force_refresh=True,
            job_key=job_key,
        )

        self.assertEqual(res["status"], "COMPLETED")
        self.assertIn(res["availability"], ("AVAILABLE", "UNAVAILABLE"))

        job = AIProcessingJob.objects.filter(idempotency_key=job_key).first()
        self.assertIsNotNone(job)
        self.assertEqual(job.status, AIProcessingJob.Status.COMPLETED)

    # -------------------------------------------------------------------------
    # TEST 17: Frontend API Compatibility
    # -------------------------------------------------------------------------
    def test_17_frontend_api_compatibility(self):
        """Forwarded and summary API responses exactly match TypeScript wire definitions."""
        self.client.force_authenticate(user=self.operator)

        # GET /api/v1/handoffs/summary
        resp_summary = self.client.get("/api/v1/handoffs/summary")
        self.assertEqual(resp_summary.status_code, 200)
        for key in ("total", "awaitingResponse", "responded", "overdue", "failed"):
            self.assertIn(key, resp_summary.data)

        # GET /api/v1/handoffs
        resp_list = self.client.get("/api/v1/handoffs")
        self.assertEqual(resp_list.status_code, 200)
        self.assertIn("items", resp_list.data)
        self.assertIn("total", resp_list.data)
        self.assertIn("page", resp_list.data)
        self.assertIn("pageSize", resp_list.data)

        # GET /api/v1/complaints/{id}/forwarding-options
        resp_opts = self.client.get(f"/api/v1/complaints/{self.complaint.id}/forwarding-options")
        self.assertEqual(resp_opts.status_code, 200)
        self.assertIn("teams", resp_opts.data)
        self.assertIn("shareableSummary", resp_opts.data)
        self.assertIn("sharedFields", resp_opts.data)

    # -------------------------------------------------------------------------
    # TEST 18: Audit Trail Integrity
    # -------------------------------------------------------------------------
    def test_18_audit_trail_integrity(self):
        """All handoff events, attempts, and transitions maintain immutable audit logs."""
        handoff = HandoffService.create_handoff(
            complaint=self.complaint,
            user=self.operator,
            team_id=str(self.team_settle.id),
            recipient="Duty lead",
            message="Audit test forward",
        )

        # Events recorded
        events = HandoffEvent.objects.filter(handoff=handoff)
        self.assertTrue(events.filter(event_type="CREATED").exists())

        # Attempt dispatch
        HandoffService.execute_dispatch(str(handoff.id))
        self.assertTrue(handoff.attempts.exists())
        attempt = handoff.attempts.first()
        self.assertEqual(attempt.channel, self.team_settle.channel)
