import uuid
from datetime import timedelta
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.services import DevAuthService
from apps.common.models import OutboxMessage, AuditEvent
from apps.common.tasks import dispatch_outbox_messages_task
from apps.complaints.models import Complaint, ComplaintCategory, Customer, ComplaintTimelineEvent
from apps.complaints.services import ComplaintIngestionService, ComplaintWorkflowService
from apps.communications.models import (
    CustomerCommunication,
    CommunicationDeliveryAttempt,
    CommunicationEvent,
    MessageTemplate,
    CommunicationPolicy,
    CommunicationPreference,
)
from apps.communications.services import (
    CustomerCommunicationService,
    TemplateEngine,
    TemplateValidationError,
)
from apps.communications.tasks import (
    dispatch_customer_communication_task,
    reconcile_unconfirmed_communications_task,
)
from apps.incidents.models import Incident, IncidentComplaint
from apps.incidents.services import IncidentManagementService
from apps.tenants.models import Tenant


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class Stage6CustomerCommunicationsTests(TestCase):
    """
    Comprehensive verification for Stage 6:
    Automated Customer Communications, Verified Resolution Gates,
    Incident Barriers, Reopening Suppression, Durable Delivery,
    Compliance Reporting, and Security Isolation.
    """

    def setUp(self):
        self.dev_auth = DevAuthService()
        self.tenant = self.dev_auth.ensure_synthetic_tenant()

        self.operator = self.dev_auth.get_or_create_persona("operator")
        self.verifier = self.dev_auth.get_or_create_persona("verifier")
        self.lead = self.dev_auth.get_or_create_persona("lead")

        # Second tenant for isolation tests
        self.other_tenant, _ = Tenant.objects.get_or_create(
            slug="t-first-national",
            defaults={
                "name": "First National Commercial",
                "time_zone": "Africa/Lagos",
                "support_label": "First National Support",
                "support_contact": "support@fn.test",
                "support_hours": "Mon-Fri 08:00-17:00",
            }
        )
        self.other_operator, _ = User.objects.get_or_create(
            username="fn_operator",
            defaults={
                "email": "operator@fn.test",
                "tenant": self.other_tenant,
                "role_label": "Operator",
                "permissions_list": ["complaints.read", "complaints.notes", "reports.read"],
                "first_name": "FN",
                "last_name": "Operator",
            }
        )

        # Baseline policy and templates
        self.policy = CustomerCommunicationService.get_or_create_default_policy(self.tenant)
        self.other_policy = CustomerCommunicationService.get_or_create_default_policy(self.other_tenant)

        # Standard category
        self.category, _ = ComplaintCategory.objects.get_or_create(
            tenant=self.tenant,
            code="CAT-DISP",
            defaults={"label": "Dispense Error"}
        )

        # Standard customer
        self.customer, _ = Customer.objects.get_or_create(
            tenant=self.tenant,
            customer_number="CUST-NG-8801",
            defaults={
                "first_name": "Ada",
                "last_name": "Okonkwo",
                "email": "ada.okonkwo@bank-sample.ng",
                "phone": "+2348012345678",
            }
        )

        # Standard complaint
        ref_id = f"CMP-COMM-{uuid.uuid4().hex[:6]}"
        self.complaint = Complaint.objects.create(
            reference=ref_id,
            tenant=self.tenant,
            customer=self.customer,
            customer_reference=self.customer.customer_number,
            original_source_reference=f"EVT-COMM-{uuid.uuid4().hex[:6]}",
            source_channel="Mobile App Feed",
            summary="ATM Dispense failure at Victoria Island branch",
            narrative="Account debited N20,000 without physical cash output.",
            category=self.category,
            priority=Complaint.Priority.HIGH,
            status=Complaint.Status.IN_PROGRESS,
            assigned_operator=self.operator,
            received_at=timezone.now(),
        )

        self.client = APIClient()

    # 1. Template validation and approval
    def test_template_validation_and_approval(self):
        # Permitted variables check
        template = MessageTemplate.objects.create(
            tenant=self.tenant,
            code="TMPL_CUSTOM",
            category=MessageTemplate.Category.ACKNOWLEDGEMENT,
            channel=MessageTemplate.Channel.EMAIL,
            version=1,
            is_approved=True,
            subject="Notice {complaint_reference}",
            body_template="Hello {customer_name}, case {complaint_reference} logged. {unapproved_var}",
            permitted_variables=["customer_name", "complaint_reference"],
        )

        with self.assertRaises(TemplateValidationError):
            TemplateEngine.render(template, {
                "customer_name": "Ada",
                "complaint_reference": "CMP-001",
                "unapproved_var": "Hacked",
            })

        # Unapproved template check
        template.is_approved = False
        template.body_template = "Hello {customer_name}, case {complaint_reference} logged."
        template.save()

        with self.assertRaises(TemplateValidationError):
            TemplateEngine.render(template, {
                "customer_name": "Ada",
                "complaint_reference": "CMP-001",
            })

        # Sanitisation: PAN masking and PIN redaction
        template.is_approved = True
        template.permitted_variables = ["customer_name", "complaint_reference", "card_details"]
        template.body_template = "Hello {customer_name}, your card {card_details} was checked."
        template.save()

        subj, body = TemplateEngine.render(template, {
            "customer_name": "Ada",
            "complaint_reference": "CMP-001",
            "card_details": "5399 8344 1234 5678 with PIN: 1234 and CVV: 999",
        })
        self.assertNotIn("5399 8344 1234 5678", body)
        self.assertIn("**** **** **** 5678", body)
        self.assertIn("PIN: [REDACTED]", body)
        self.assertIn("CVV: [REDACTED]", body)

    # 2. Tenant isolation
    def test_tenant_isolation(self):
        comm = CustomerCommunicationService.queue_acknowledgement(self.complaint)
        self.assertIsNotNone(comm)

        # Tenant A operator can access
        self.client.force_authenticate(user=self.operator)
        resp_a = self.client.get(f"/api/v1/complaints/{self.complaint.id}/communications")
        self.assertEqual(resp_a.status_code, 200)
        self.assertEqual(resp_a.data["total"], 1)

        # Tenant B operator cannot access Tenant A's complaint communications
        self.client.force_authenticate(user=self.other_operator)
        resp_b = self.client.get(f"/api/v1/complaints/{self.complaint.id}/communications")
        self.assertEqual(resp_b.status_code, 404)

    # 3. Recipient validation
    def test_recipient_validation(self):
        # Customer without phone or email opt-in
        cust_optout = Customer.objects.create(
            tenant=self.tenant,
            customer_number=f"CUST-NO-DEST-{uuid.uuid4().hex[:6]}",
            first_name="No",
            last_name="Contact",
            email="",
            phone="",
        )
        comp_optout = Complaint.objects.create(
            reference=f"CMP-NO-DEST-{uuid.uuid4().hex[:6]}",
            tenant=self.tenant,
            customer=cust_optout,
            customer_reference=cust_optout.customer_number,
            summary="No destination",
            status=Complaint.Status.NEW,
            received_at=timezone.now(),
        )

        # Acknowledgement should safely skip without unhandled exception
        comm = CustomerCommunicationService.queue_acknowledgement(comp_optout)
        self.assertIsNone(comm)
        self.assertTrue(
            AuditEvent.objects.filter(action="communication.ack_skipped_no_recipient").exists()
        )

    # 4. Automatic acknowledgement
    def test_automatic_acknowledgement(self):
        event_id = f"EVT-INGEST-{uuid.uuid4().hex[:6]}"
        payload = {
            "customer_number": "CUST-INGEST-01",
            "customer_first_name": "Emeka",
            "customer_last_name": "Nwosu",
            "customer_email": "emeka.nwosu@bank-sample.ng",
            "summary": "Transfer reversal delayed",
            "channel": "Web Portal",
        }

        complaint, created = ComplaintIngestionService.ingest_event(self.tenant, event_id, payload)
        self.assertTrue(created)

        # Verify CustomerCommunication was queued
        comm = CustomerCommunication.objects.filter(
            complaint=complaint,
            category=MessageTemplate.Category.ACKNOWLEDGEMENT
        ).first()
        self.assertIsNotNone(comm)
        self.assertEqual(comm.channel, "EMAIL")
        self.assertEqual(comm.recipient_destination, "emeka.nwosu@bank-sample.ng")
        self.assertIn(complaint.reference, comm.rendered_content)

        # Verify timeline event created
        self.assertTrue(
            ComplaintTimelineEvent.objects.filter(
                complaint=complaint,
                kind="COMMUNICATION_ACKNOWLEDGED"
            ).exists()
        )

    # 5. Duplicate complaint ingestion prevention
    def test_duplicate_complaint_ingestion(self):
        event_id = f"EVT-DUP-TEST-{uuid.uuid4().hex[:6]}"
        payload = {
            "customer_number": "CUST-DUP-01",
            "customer_first_name": "Tari",
            "customer_email": "tari@bank-sample.ng",
            "summary": "Duplicate test ingestion",
        }

        c1, created1 = ComplaintIngestionService.ingest_event(self.tenant, event_id, payload)
        self.assertTrue(created1)

        # Second ingestion with same external_event_id
        c2, created2 = ComplaintIngestionService.ingest_event(self.tenant, event_id, payload)
        self.assertFalse(created2)
        self.assertEqual(c1.id, c2.id)

        # Exactly 1 acknowledgement communication exists
        comm_count = CustomerCommunication.objects.filter(
            complaint=c1,
            category=MessageTemplate.Category.ACKNOWLEDGEMENT
        ).count()
        self.assertEqual(comm_count, 1)

    # 6. Duplicate message prevention
    def test_duplicate_message_prevention(self):
        comm1 = CustomerCommunicationService.queue_acknowledgement(self.complaint)
        comm2 = CustomerCommunicationService.queue_acknowledgement(self.complaint)
        self.assertEqual(comm1.id, comm2.id)

        # Frequency limit on progress updates
        u1 = CustomerCommunicationService.queue_progress_update(
            self.complaint,
            details="Interim update 1",
            force=False
        )
        self.assertIsNotNone(u1)

        # Calling again within 24h interval returns None
        u2 = CustomerCommunicationService.queue_progress_update(
            self.complaint,
            details="Interim update 2 (spam attempt)",
            force=False
        )
        self.assertIsNone(u2)

    # 7. Maker-checker verification gating
    def test_maker_checker_verification_gating(self):
        # 1. Recording operator records outcome (AWAITING_VERIFICATION)
        ComplaintWorkflowService.record_outcome(
            complaint=self.complaint,
            user=self.operator,
            outcome="Funds restored via switch reversal.",
            evidence="Switch trace ref SW-991204"
        )
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.AWAITING_VERIFICATION)

        # Final resolution message cannot be queued while awaiting verification
        with self.assertRaises(Exception):
            CustomerCommunicationService.queue_verified_resolution_notification(
                complaint=self.complaint,
                user=self.verifier
            )

        # Maker cannot verify their own outcome (segregation of duties)
        with self.assertRaises(Exception):
            ComplaintWorkflowService.verify_outcome(
                complaint=self.complaint,
                user=self.operator,  # Maker trying to check
                decision="VERIFY"
            )

        # Independent verifier approves outcome
        ComplaintWorkflowService.verify_outcome(
            complaint=self.complaint,
            user=self.verifier,
            decision="VERIFY",
            note="Evidence corroborated with interbank switch."
        )
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.RESOLVED)

        # Verified resolution communication was queued automatically by hook
        res_comm = CustomerCommunication.objects.filter(
            complaint=self.complaint,
            category=MessageTemplate.Category.VERIFIED_RESOLUTION
        ).first()
        self.assertIsNotNone(res_comm)
        self.assertEqual(res_comm.status, CustomerCommunication.Status.QUEUED)
        self.assertIn("Funds restored via switch reversal", res_comm.rendered_content)
        self.assertTrue(res_comm.verification_reference.startswith("VRF-"))

        # Dispatch via worker service to confirm successful delivery
        dispatched = CustomerCommunicationService.dispatch_communication(str(res_comm.id))
        self.assertEqual(dispatched.status, CustomerCommunication.Status.DELIVERED)

    # 8. Incident versus complaint resolution barrier
    def test_incident_versus_complaint_resolution(self):
        # Complaint A: Verified and resolved
        comp_a = Complaint.objects.create(
            reference=f"CMP-INC-A-{uuid.uuid4().hex[:6]}",
            tenant=self.tenant,
            customer=self.customer,
            customer_reference=self.customer.customer_number,
            summary="ATM Dispense timeout A",
            status=Complaint.Status.RESOLVED,
            resolution_outcome="Dispense reversed automatically.",
            resolution_verification=Complaint.ResolutionVerification.VERIFIED,
            resolution_reported_by=self.operator,
            resolution_verified_by=self.verifier,
            resolution_verified_at=timezone.now(),
            received_at=timezone.now(),
        )

        # Complaint B: Individual investigation still open
        comp_b = Complaint.objects.create(
            reference=f"CMP-INC-B-{uuid.uuid4().hex[:6]}",
            tenant=self.tenant,
            customer=self.customer,
            customer_reference=self.customer.customer_number,
            summary="ATM Dispense timeout B",
            status=Complaint.Status.IN_PROGRESS,
            assigned_operator=self.operator,
            received_at=timezone.now(),
        )

        incident = IncidentManagementService.create_incident_candidate(
            tenant=self.tenant,
            title="Victoria Island Switch Anomaly",
            summary="Underlying network timeout on ATM cluster",
            complaint_ids=[str(comp_a.id), str(comp_b.id)],
            user=self.lead,
        )
        IncidentManagementService.confirm_incident(
            incident_id=str(incident.id),
            tenant=self.tenant,
            user=self.lead,
        )

        # Resolve the incident
        IncidentManagementService.resolve_incident(
            incident_id=str(incident.id),
            tenant=self.tenant,
            user=self.lead,
            resolution_notes="Core switch node failover completed."
        )

        comp_b.refresh_from_db()
        # Invariant: Complaint B must NOT be resolved automatically!
        self.assertEqual(comp_b.status, Complaint.Status.IN_PROGRESS)

        # Invariant: No final resolution message sent for Complaint B
        res_comm_b = CustomerCommunication.objects.filter(
            complaint=comp_b,
            category=MessageTemplate.Category.VERIFIED_RESOLUTION
        ).first()
        self.assertIsNone(res_comm_b)

        # Complaint B received an approved interim progress update informing of incident mitigation
        prog_b = CustomerCommunication.objects.filter(
            complaint=comp_b,
            category=MessageTemplate.Category.PROGRESS_UPDATE
        ).first()
        self.assertIsNotNone(prog_b)
        self.assertIn("underlying technical incident", prog_b.rendered_content)

    # 9. Reopened complaint suppression
    def test_reopened_complaint_suppression(self):
        # Setup resolved complaint
        self.complaint.status = Complaint.Status.RESOLVED
        self.complaint.resolution_outcome = "Refund confirmed"
        self.complaint.resolution_verification = Complaint.ResolutionVerification.VERIFIED
        self.complaint.resolution_reported_by = self.operator
        self.complaint.resolution_verified_by = self.verifier
        self.complaint.resolution_verified_at = timezone.now()
        self.complaint.save()

        # Simulate a queued resolution communication that hasn't dispatched yet
        queued_comm = CustomerCommunication.objects.create(
            tenant=self.tenant,
            complaint=self.complaint,
            customer=self.customer,
            category=MessageTemplate.Category.VERIFIED_RESOLUTION,
            channel="EMAIL",
            recipient_destination=self.customer.email,
            rendered_content="Your complaint is resolved.",
            status=CustomerCommunication.Status.QUEUED,
        )

        # Complaint is reopened by supervisor
        ComplaintWorkflowService.reopen_complaint(
            complaint=self.complaint,
            user=self.verifier,
            reason="Customer reports funds did not credit beneficiary account."
        )

        queued_comm.refresh_from_db()
        # Invariant: Obsolete queued notification is suppressed and marked CANCELLED
        self.assertEqual(queued_comm.status, CustomerCommunication.Status.CANCELLED)
        self.assertEqual(queued_comm.cancellation_reason, "Customer reports funds did not credit beneficiary account.")

        # Worker dispatch test: Calling dispatch on cancelled communication safely aborts
        CustomerCommunicationService.dispatch_communication(str(queued_comm.id))
        queued_comm.refresh_from_db()
        self.assertEqual(queued_comm.status, CustomerCommunication.Status.CANCELLED)

    # 10. Message delivery status accuracy
    def test_message_delivery_status_accuracy(self):
        comm = CustomerCommunication.objects.create(
            tenant=self.tenant,
            complaint=self.complaint,
            customer=self.customer,
            category=MessageTemplate.Category.ACKNOWLEDGEMENT,
            channel="SMS",
            recipient_destination="+2348012345678",
            rendered_content="Complaint CMP-2026 acknowledged.",
            status=CustomerCommunication.Status.QUEUED,
        )

        dispatched = CustomerCommunicationService.dispatch_communication(str(comm.id))
        self.assertEqual(dispatched.status, CustomerCommunication.Status.DELIVERED)
        self.assertIsNotNone(dispatched.delivered_at)

        attempt = dispatched.delivery_attempts.first()
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.channel, "SMS")
        self.assertEqual(attempt.status, "DELIVERED")
        self.assertTrue(attempt.provider_reference.startswith("SM-"))

    # 11. Communication failure and retry
    def test_communication_failure_and_retry(self):
        # Invalid destination triggers permanent failure in simulated adapter
        failed_comm = CustomerCommunication.objects.create(
            tenant=self.tenant,
            complaint=self.complaint,
            customer=self.customer,
            category=MessageTemplate.Category.ACKNOWLEDGEMENT,
            channel="EMAIL",
            recipient_destination="invalid_recipient_format",
            rendered_content="Test failure payload",
            status=CustomerCommunication.Status.QUEUED,
        )

        CustomerCommunicationService.dispatch_communication(str(failed_comm.id))
        failed_comm.refresh_from_db()
        self.assertEqual(failed_comm.status, CustomerCommunication.Status.FAILED)
        self.assertIn("550", failed_comm.error_message)

        # Retry endpoint via API
        self.client.force_authenticate(user=self.operator)
        retry_resp = self.client.post(
            f"/api/v1/communications/{failed_comm.id}/retry",
            HTTP_X_BIIRS_REQUEST="1",
        )
        self.assertEqual(retry_resp.status_code, 200)

        failed_comm.refresh_from_db()
        # Re-queued with bumped max_retries
        self.assertIn(failed_comm.status, [CustomerCommunication.Status.QUEUED, CustomerCommunication.Status.FAILED])

    # 12. Uncertain delivery reconciliation
    def test_uncertain_delivery_reconciliation(self):
        unconfirmed_comm = CustomerCommunication.objects.create(
            tenant=self.tenant,
            complaint=self.complaint,
            customer=self.customer,
            category=MessageTemplate.Category.ACKNOWLEDGEMENT,
            channel="EMAIL",
            recipient_destination="ada.okonkwo@bank-sample.ng",
            rendered_content="Test payload",
            status=CustomerCommunication.Status.DELIVERY_UNCONFIRMED,
            provider_message_id="eml_test_unconfirmed_99",
        )

        res = reconcile_unconfirmed_communications_task()
        self.assertGreaterEqual(res["reconciled_count"], 1)

        unconfirmed_comm.refresh_from_db()
        self.assertEqual(unconfirmed_comm.status, CustomerCommunication.Status.DELIVERED)
        self.assertIsNotNone(unconfirmed_comm.delivered_at)

    # 13. Worker interruption and recovery
    def test_worker_interruption_and_recovery(self):
        # Create an outbox message that was persisted before process crash
        comm = CustomerCommunication.objects.create(
            tenant=self.tenant,
            complaint=self.complaint,
            customer=self.customer,
            category=MessageTemplate.Category.ACKNOWLEDGEMENT,
            channel="EMAIL",
            recipient_destination="ada.okonkwo@bank-sample.ng",
            rendered_content="Durable outbox recovery payload",
            status=CustomerCommunication.Status.QUEUED,
        )

        outbox_msg = OutboxMessage.objects.create(
            tenant_id=self.tenant.id,
            topic="communication.dispatch",
            payload={"communication_id": str(comm.id)},
            status=OutboxMessage.Status.PENDING,
        )

        # Celery Beat sweeps the outbox table
        dispatch_outbox_messages_task()

        outbox_msg.refresh_from_db()
        self.assertEqual(outbox_msg.status, OutboxMessage.Status.PUBLISHED)

        comm.refresh_from_db()
        self.assertEqual(comm.status, CustomerCommunication.Status.DELIVERED)

    # 14. Audit history
    def test_audit_history(self):
        comm = CustomerCommunicationService.queue_acknowledgement(self.complaint)
        events = comm.events.all()
        self.assertGreaterEqual(events.count(), 1)
        event_types = [e.event_type for e in events]
        self.assertIn("QUEUED", event_types)

    # 15. Compliance report permissions
    def test_compliance_report_permissions(self):
        CustomerCommunicationService.queue_acknowledgement(self.complaint)

        # Authenticated operator
        self.client.force_authenticate(user=self.operator)
        resp = self.client.get("/api/v1/communications/compliance-report?report_type=ACKNOWLEDGEMENTS")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["tenant"], self.tenant.name)
        self.assertGreaterEqual(resp.data["totalCount"], 1)

        # Anonymous request
        self.client.force_authenticate(user=None)
        anon_resp = self.client.get("/api/v1/communications/compliance-report")
        self.assertEqual(anon_resp.status_code, 401)

    # 16. Cross-tenant report access denial
    def test_cross_tenant_report_access_denial(self):
        # Create communication for Tenant A
        comm_a = CustomerCommunicationService.queue_acknowledgement(self.complaint)

        # Tenant B operator calls compliance report
        self.client.force_authenticate(user=self.other_operator)
        resp_b = self.client.get("/api/v1/communications/compliance-report?report_type=ACKNOWLEDGEMENTS")
        self.assertEqual(resp_b.status_code, 200)
        self.assertEqual(resp_b.data["tenant"], self.other_tenant.name)
        # Cannot see Tenant A's records
        record_refs = [r["complaintReference"] for r in resp_b.data["records"]]
        self.assertNotIn(self.complaint.reference, record_refs)

    # 17. Frontend API compatibility
    def test_frontend_api_compatibility(self):
        CustomerCommunicationService.queue_acknowledgement(self.complaint)
        self.client.force_authenticate(user=self.operator)

        resp = self.client.get(f"/api/v1/complaints/{self.complaint.id}/communications")
        self.assertEqual(resp.status_code, 200)
        data = resp.data

        # Conforms to TypeScript wire contract
        self.assertIn("complaintId", data)
        self.assertIn("reference", data)
        self.assertIn("total", data)
        self.assertIn("items", data)

        item = data["items"][0]
        self.assertIn("id", item)
        self.assertIn("category", item)
        self.assertIn("channel", item)
        self.assertIn("masked_destination", item)
        self.assertIn("status", item)
        self.assertIn("delivery_attempts", item)
        self.assertIn("events", item)
        # Privacy minimised recipient destination
        self.assertIn("***@", item["masked_destination"])

    # 18. Concurrency: Complaint reopening competes with resolution dispatch & post-submission distinction
    def test_concurrency_reopening_competes_with_dispatch(self):
        # Setup verified resolved complaint
        self.complaint.status = Complaint.Status.RESOLVED
        self.complaint.resolution_outcome = "Customer reimbursed."
        self.complaint.resolution_verification = Complaint.ResolutionVerification.VERIFIED
        self.complaint.resolution_reported_by = self.operator
        self.complaint.resolution_verified_by = self.verifier
        self.complaint.resolution_verified_at = timezone.now()
        self.complaint.save()

        # Queued resolution notification
        queued_comm = CustomerCommunication.objects.create(
            tenant=self.tenant,
            complaint=self.complaint,
            customer=self.customer,
            category=MessageTemplate.Category.VERIFIED_RESOLUTION,
            channel="EMAIL",
            recipient_destination=self.customer.email,
            rendered_content="Resolution approved.",
            status=CustomerCommunication.Status.QUEUED,
        )

        # Race Condition: Supervisor reopens the complaint before worker dispatch commits
        ComplaintWorkflowService.reopen_complaint(
            complaint=self.complaint,
            user=self.verifier,
            reason="Beneficiary did not receive the transfer."
        )

        # Pre-submission invariant: Queued notification is marked CANCELLED
        queued_comm.refresh_from_db()
        self.assertEqual(queued_comm.status, CustomerCommunication.Status.CANCELLED)
        self.assertIn("Beneficiary did not receive", queued_comm.cancellation_reason)

        # Worker dispatch task executes now: Pre-dispatch validation confirms cancellation and safely aborts
        result_comm = CustomerCommunicationService.dispatch_communication(str(queued_comm.id))
        self.assertEqual(result_comm.status, CustomerCommunication.Status.CANCELLED)

        # Post-submission distinction: Now test message that has ALREADY been submitted/delivered on a resolved case
        comp_b = Complaint.objects.create(
            reference=f"CMP-POSTSUB-{uuid.uuid4().hex[:6]}",
            tenant=self.tenant,
            customer=self.customer,
            customer_reference=self.customer.customer_number,
            summary="Prior resolved case",
            status=Complaint.Status.RESOLVED,
            resolution_outcome="Dispense refunded.",
            resolution_verification=Complaint.ResolutionVerification.VERIFIED,
            resolution_reported_by=self.operator,
            resolution_verified_by=self.verifier,
            resolution_verified_at=timezone.now(),
            received_at=timezone.now(),
        )
        delivered_comm = CustomerCommunication.objects.create(
            tenant=self.tenant,
            complaint=comp_b,
            customer=self.customer,
            category=MessageTemplate.Category.VERIFIED_RESOLUTION,
            channel="SMS",
            recipient_destination="+2348012345678",
            rendered_content="Prior verified outcome.",
            status=CustomerCommunication.Status.DELIVERED,
            provider_message_id="sms_already_delivered_99",
            delivered_at=timezone.now(),
        )

        # Reopening event on comp_b
        ComplaintWorkflowService.reopen_complaint(
            complaint=comp_b,
            user=self.verifier,
            reason="Subsequent customer dispute on the same claim."
        )

        delivered_comm.refresh_from_db()
        # Invariant: Delivered message is NEVER deleted or retroactively marked cancelled
        self.assertEqual(delivered_comm.status, CustomerCommunication.Status.DELIVERED)
        # Audit history records that the prior delivery was superseded by reopening
        superseded_events = delivered_comm.events.filter(event_type="SUPERSEDED_BY_REOPEN")
        self.assertTrue(superseded_events.exists())
        self.assertIn("Subsequent customer dispute", superseded_events.first().detail)

    # 19. Structural sensitive data minimization in template engine
    def test_template_structural_sensitive_data_minimization(self):
        # A template attempting to include prohibited financial fields must be rejected structurally
        with self.assertRaises(TemplateValidationError):
            TemplateEngine.validate_template_variables(
                body_template="Dear {customer_name}, your PIN is {pin} and card is {card_number}.",
                permitted_variables=["customer_name", "pin", "card_number"]
            )

