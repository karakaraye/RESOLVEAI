import uuid
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User
from apps.accounts.services import DevAuthService
from apps.complaints.models import (
    Customer,
    ComplaintCategory,
    Complaint,
    ComplaintNote,
    ComplaintTimelineEvent,
    ComplaintFollowUp,
    SourceEvent,
)
from apps.complaints.services import (
    ComplaintWorkflowService,
    ComplaintIngestionService,
    WorkspaceSummaryService,
    InvalidStateTransitionError,
)
from apps.tenants.models import Tenant


class ComplaintDomainAndWorkflowTests(TestCase):
    """
    Test suite covering Complaint models, validated state transitions,
    tenant isolation, and timeline immutability.
    """
    def setUp(self):
        self.dev_auth = DevAuthService()
        self.tenant_a = self.dev_auth.ensure_synthetic_tenant()
        self.tenant_b = Tenant.objects.create(name="Second Bank", is_active=True)

        self.operator = self.dev_auth.get_or_create_persona("operator")
        self.verifier = self.dev_auth.get_or_create_persona("verifier")
        self.lead = self.dev_auth.get_or_create_persona("lead")

        self.category = ComplaintCategory.objects.create(
            tenant=self.tenant_a,
            code="TRANSFERS",
            label="Failed transfer"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant_a,
            customer_number="CUST-TEST-001",
            first_name="Jane",
            last_name="Doe",
            email="jane.doe@example.test"
        )
        self.complaint = Complaint.objects.create(
            reference="CMP-TEST-001",
            tenant=self.tenant_a,
            customer=self.customer,
            customer_reference=self.customer.customer_number,
            summary="Interbank transfer failed",
            narrative="Customer sent 10,000 NGN; funds debited but not delivered.",
            category=self.category,
            priority=Complaint.Priority.HIGH,
            status=Complaint.Status.NEW,
            received_at=timezone.now(),
            due_at=timezone.now() + timedelta(hours=24),
        )

    def test_complaint_creation_and_attributes(self):
        self.assertEqual(self.complaint.status, Complaint.Status.NEW)
        self.assertEqual(self.complaint.priority, Complaint.Priority.HIGH)
        self.assertFalse(self.complaint.is_overdue)
        self.assertEqual(self.complaint.customer.full_name, "Jane Doe")

    def test_arbitrary_direct_resolution_is_forbidden(self):
        """Invariant: Cannot transition directly from NEW to RESOLVED without verification."""
        with self.assertRaises(InvalidStateTransitionError):
            ComplaintWorkflowService.transition_status(
                self.complaint,
                Complaint.Status.RESOLVED,
                self.operator,
                self.operator.display_name
            )

    def test_workflow_state_machine_happy_path(self):
        """
        Valid sequence: NEW -> IN_PROGRESS (assigned) -> AWAITING_VERIFICATION (outcome recorded)
        -> RESOLVED (verified) -> REOPENED (reopened).
        """
        # 1. Assignment moves NEW to IN_PROGRESS
        ComplaintWorkflowService.assign_operator(
            self.complaint,
            self.operator,
            str(self.operator.id),
            "Assigning to me"
        )
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.IN_PROGRESS)
        self.assertEqual(self.complaint.assigned_operator, self.operator)

        # 2. Record outcome moves to AWAITING_VERIFICATION
        ComplaintWorkflowService.record_outcome(
            self.complaint,
            self.operator,
            "Transfer reversed to customer account",
            "Core banking log #REV-100"
        )
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.AWAITING_VERIFICATION)
        self.assertEqual(self.complaint.resolution_verification, Complaint.ResolutionVerification.AWAITING)

        # 3. Verifier verifies outcome -> RESOLVED
        ComplaintWorkflowService.verify_outcome(
            self.complaint,
            self.verifier,
            "VERIFY",
            "Verified reversal on Finacle"
        )
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.RESOLVED)
        self.assertEqual(self.complaint.resolution_verification, Complaint.ResolutionVerification.VERIFIED)

        # 4. Reopen complaint -> REOPENED
        ComplaintWorkflowService.reopen_complaint(
            self.complaint,
            self.verifier,
            "Customer states reversal was subsequently cancelled"
        )
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.REOPENED)
        self.assertIn("cancelled", self.complaint.reopen_reason)

    def test_operator_without_verify_permission_cannot_verify(self):
        """Operator has record_outcome but lacks verify_outcome."""
        self.complaint.status = Complaint.Status.AWAITING_VERIFICATION
        self.complaint.save()

        with self.assertRaises(Exception):
            ComplaintWorkflowService.verify_outcome(
                self.complaint,
                self.operator,
                "VERIFY",
                "Self-verification attempt"
            )

    def test_internal_resolution_without_forwarding(self):
        """
        Branching validation: An internal team can investigate and resolve a case
        directly without requiring external forwarding.
        """
        # Move directly to IN_PROGRESS
        ComplaintWorkflowService.assign_operator(
            self.complaint,
            self.operator,
            str(self.operator.id),
            "Direct internal handling"
        )
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.IN_PROGRESS)

        # Record outcome directly from IN_PROGRESS without forwarding
        ComplaintWorkflowService.record_outcome(
            self.complaint,
            self.operator,
            "Internal ledger reconciliation completed"
        )
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.AWAITING_VERIFICATION)

        # Verifier resolves
        ComplaintWorkflowService.verify_outcome(
            self.complaint,
            self.verifier,
            "VERIFY",
            "Confirmed internal ledger adjustment"
        )
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.RESOLVED)

    def test_forwarded_complaint_can_return_to_in_progress(self):
        """
        Branching validation: A forwarded complaint can return to active investigation
        when a team responds or when further internal evidence is needed.
        """
        # Transition to FORWARDED
        ComplaintWorkflowService.transition_status(
            self.complaint,
            Complaint.Status.FORWARDED,
            self.operator,
            self.operator.display_name,
            "Forwarded to switch team"
        )
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.FORWARDED)

        # Return to IN_PROGRESS upon receiving team response
        ComplaintWorkflowService.transition_status(
            self.complaint,
            Complaint.Status.IN_PROGRESS,
            self.operator,
            self.operator.display_name,
            "Switch team response received; resuming investigation"
        )
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.IN_PROGRESS)

    def test_rejected_outcome_branches_back_to_in_progress(self):
        """
        Branching validation: Maker-checker rejection returns the case to IN_PROGRESS.
        """
        ComplaintWorkflowService.record_outcome(
            self.complaint,
            self.operator,
            "Customer refund recommended",
            "Evidence shows discrepancy between ledger and switch"
        )
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.AWAITING_VERIFICATION)

        ComplaintWorkflowService.verify_outcome(
            self.complaint,
            self.verifier,
            "REJECT",
            "Evidence does not match ledger"
        )
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.IN_PROGRESS)
        self.assertEqual(self.complaint.resolution_verification, Complaint.ResolutionVerification.REJECTED)

    def test_action_transactional_atomicity(self):
        """
        Atomicity validation: If an exception occurs, all database changes rollback.
        """
        initial_status = self.complaint.status
        initial_events_count = self.complaint.timeline_events.count()

        # Attempt assignment to invalid UUID causing failure
        with self.assertRaises(Exception):
            ComplaintWorkflowService.assign_operator(
                self.complaint,
                self.operator,
                str(uuid.uuid4()),  # Non-existent user
                "Should fail"
            )

        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, initial_status)
        self.assertEqual(self.complaint.timeline_events.count(), initial_events_count)

    def test_notes_and_timeline_events(self):
        note = ComplaintWorkflowService.add_note(
            self.complaint,
            self.operator,
            "Customer called back asking for update."
        )
        self.assertEqual(note.text, "Customer called back asking for update.")
        self.assertEqual(self.complaint.notes.count(), 1)

        # Verify timeline event was logged
        timeline_event = self.complaint.timeline_events.filter(kind="NOTE_ADDED").first()
        self.assertIsNotNone(timeline_event)
        self.assertEqual(timeline_event.actor, self.operator.display_name)


class ComplaintIngestionAndDeduplicationTests(TestCase):
    """
    Test suite for banking webhook ingestion and duplicate prevention.
    """
    def setUp(self):
        self.tenant = DevAuthService().ensure_synthetic_tenant()

    def test_idempotent_ingestion_prevents_duplicate_records(self):
        payload = {
            "customer_number": "CUST-INGEST-01",
            "customer_first_name": "Samuel",
            "customer_last_name": "Ade",
            "channel": "Contact centre feed",
            "summary": "Delayed card delivery",
            "narrative": "Card requested 3 weeks ago has not arrived at branch.",
            "priority": "MEDIUM",
        }
        event_id = "WEBHOOK-EVENT-998822"

        # First ingestion
        complaint1, created1 = ComplaintIngestionService.ingest_event(self.tenant, event_id, payload)
        self.assertTrue(created1)
        self.assertEqual(complaint1.status, Complaint.Status.NEW)
        self.assertEqual(Complaint.objects.filter(tenant=self.tenant).count(), 1)

        # Duplicate webhook ingestion with same external_event_id
        complaint2, created2 = ComplaintIngestionService.ingest_event(self.tenant, event_id, payload)
        self.assertFalse(created2)
        self.assertEqual(complaint1.id, complaint2.id)
        # Verify no duplicate complaint was created
        self.assertEqual(Complaint.objects.filter(tenant=self.tenant).count(), 1)


class ComplaintAPITests(TestCase):
    """
    REST API test suite testing endpoints, permissions, filters, pagination, and multi-tenancy.
    """
    def setUp(self):
        self.client = APIClient()
        self.dev_auth = DevAuthService()
        self.tenant_a = self.dev_auth.ensure_synthetic_tenant()
        self.tenant_b = Tenant.objects.create(name="Other Bank", is_active=True)

        self.operator = self.dev_auth.get_or_create_persona("operator")
        self.verifier = self.dev_auth.get_or_create_persona("verifier")

        # Other tenant user
        self.user_b = User.objects.create_user(
            username="other_op",
            tenant=self.tenant_b,
            permissions_list=["complaints.read", "complaints.notes"]
        )

        self.category = ComplaintCategory.objects.create(
            tenant=self.tenant_a,
            code="CARDS_ATM",
            label="Card & ATM debit"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant_a,
            customer_number="CUST-API-01",
            first_name="Ahmed",
            last_name="Musa"
        )
        self.complaint = Complaint.objects.create(
            reference="CMP-API-001",
            tenant=self.tenant_a,
            customer=self.customer,
            customer_reference=self.customer.customer_number,
            summary="ATM failed to dispense",
            narrative="Machine went offline during transaction.",
            category=self.category,
            priority=Complaint.Priority.HIGH,
            status=Complaint.Status.NEW,
            received_at=timezone.now(),
            due_at=timezone.now() + timedelta(hours=24),
        )

    def test_unauthenticated_complaints_returns_401(self):
        res = self.client.get("/api/v1/complaints")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_complaints_list_pagination_and_wire_format(self):
        self.client.force_authenticate(user=self.operator)
        res = self.client.get("/api/v1/complaints?page=1&pageSize=25")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertIn("items", data)
        self.assertIn("total", data)
        self.assertIn("page", data)
        self.assertIn("pageSize", data)
        self.assertEqual(data["total"], 1)

        item = data["items"][0]
        self.assertEqual(item["reference"], "CMP-API-001")
        self.assertEqual(item["customerReference"], "CUST-API-01")
        self.assertEqual(item["priority"], "HIGH")
        self.assertEqual(item["status"], "NEW")
        self.assertIn("allowedActions", item)

    def test_tenant_isolation_cross_tenant_access_blocked(self):
        """User from Tenant B cannot view complaints of Tenant A."""
        self.client.force_authenticate(user=self.user_b)

        # 1. List query returns only Tenant B complaints (0)
        res = self.client.get("/api/v1/complaints")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["total"], 0)

        # 2. Detail query for Tenant A complaint returns 404
        res_detail = self.client.get(f"/api/v1/complaints/{self.complaint.id}")
        self.assertEqual(res_detail.status_code, status.HTTP_404_NOT_FOUND)

    def test_search_and_filter_parameters(self):
        self.client.force_authenticate(user=self.operator)

        # Keyword search
        res = self.client.get("/api/v1/complaints?q=ATM")
        self.assertEqual(res.json()["total"], 1)

        res_miss = self.client.get("/api/v1/complaints?q=Nonexistent")
        self.assertEqual(res_miss.json()["total"], 0)

        # Status filter
        res_new = self.client.get("/api/v1/complaints?status=NEW")
        self.assertEqual(res_new.json()["total"], 1)

        res_resolved = self.client.get("/api/v1/complaints?status=RESOLVED")
        self.assertEqual(res_resolved.json()["total"], 0)

    def test_add_note_action_requires_biirs_header_and_idempotency(self):
        self.client.force_authenticate(user=self.operator)
        key = str(uuid.uuid4())
        url = f"/api/v1/complaints/{self.complaint.id}/notes"

        # Missing X-BIIRS-Request header returns 403
        res_fail = self.client.post(url, {"text": "Test note"}, format="json")
        self.assertEqual(res_fail.status_code, status.HTTP_403_FORBIDDEN)

        # With X-BIIRS-Request and Idempotency-Key
        headers = {"HTTP_X_BIIRS_REQUEST": "1", "HTTP_IDEMPOTENCY_KEY": key}
        res_ok = self.client.post(url, {"text": "Test note with key"}, format="json", **headers)
        self.assertEqual(res_ok.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.complaint.notes.count(), 1)

        # Replay with same key is idempotent
        res_replay = self.client.post(url, {"text": "Test note with key"}, format="json", **headers)
        self.assertEqual(res_replay.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.complaint.notes.count(), 1)

    def test_workspace_summary_endpoint(self):
        self.client.force_authenticate(user=self.operator)
        res = self.client.get("/api/v1/workspace/summary?scope=all")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertIn("counts", data)
        self.assertIn("nextActions", data)
        self.assertIn("generatedAt", data)
        self.assertEqual(data["counts"]["new"], 1)

    def test_assignment_api_authorisation_and_database_persistence(self):
        """Validates assignment API is properly authorized and persists to the database."""
        url = f"/api/v1/complaints/{self.complaint.id}/assignment"
        headers = {"HTTP_X_BIIRS_REQUEST": "1"}

        # 1. User lacking complaints.assign is rejected (403)
        self.client.force_authenticate(user=self.user_b)
        res_forbidden = self.client.post(url, {"assigneeId": str(self.operator.id)}, format="json", **headers)
        self.assertEqual(res_forbidden.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Authorized user succeeds (204)
        self.client.force_authenticate(user=self.operator)
        res_ok = self.client.post(url, {"assigneeId": str(self.operator.id), "reason": "Self assignment"}, format="json", **headers)
        self.assertEqual(res_ok.status_code, status.HTTP_204_NO_CONTENT)

        # 3. Verify actual database mutation and timeline event
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.assigned_operator, self.operator)
        self.assertEqual(self.complaint.status, Complaint.Status.IN_PROGRESS)
        self.assertTrue(self.complaint.timeline_events.filter(kind="ASSIGNED").exists())

    def test_resolution_and_verification_apis_authorisation_and_database_persistence(self):
        """Validates outcome reporting and maker-checker verification APIs."""
        res_url = f"/api/v1/complaints/{self.complaint.id}/resolution"
        verif_url = f"/api/v1/complaints/{self.complaint.id}/resolution/verification"
        headers = {"HTTP_X_BIIRS_REQUEST": "1"}

        # 1. Operator records outcome
        self.client.force_authenticate(user=self.operator)
        res_outcome = self.client.post(res_url, {"outcome": "Customer funds refunded", "evidence": "Batch #112"}, format="json", **headers)
        self.assertEqual(res_outcome.status_code, status.HTTP_204_NO_CONTENT)

        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.AWAITING_VERIFICATION)
        self.assertEqual(self.complaint.resolution_outcome, "Customer funds refunded")

        # 2. Operator without complaints.verify_outcome cannot verify (403)
        res_unauth_verif = self.client.post(verif_url, {"decision": "VERIFY", "note": "Illegal self-verify"}, format="json", **headers)
        self.assertEqual(res_unauth_verif.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Verifier verifies outcome
        self.client.force_authenticate(user=self.verifier)
        res_verified = self.client.post(verif_url, {"decision": "VERIFY", "note": "Confirmed by auditor"}, format="json", **headers)
        self.assertEqual(res_verified.status_code, status.HTTP_204_NO_CONTENT)

        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.RESOLVED)
        self.assertEqual(self.complaint.resolution_verification, Complaint.ResolutionVerification.VERIFIED)

    def test_reopen_api_authorisation_and_database_persistence(self):
        """Validates reopen API is properly authorized and persists to the database."""
        # Setup complaint as resolved
        self.complaint.status = Complaint.Status.RESOLVED
        self.complaint.save()

        reopen_url = f"/api/v1/complaints/{self.complaint.id}/reopen"
        headers = {"HTTP_X_BIIRS_REQUEST": "1"}

        # 1. Operator lacking complaints.reopen is rejected (403)
        self.client.force_authenticate(user=self.operator)
        res_forbidden = self.client.post(reopen_url, {"reason": "Customer called back"}, format="json", **headers)
        self.assertEqual(res_forbidden.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Verifier possessing complaints.reopen succeeds
        self.client.force_authenticate(user=self.verifier)
        res_ok = self.client.post(reopen_url, {"reason": "Customer dispute returned"}, format="json", **headers)
        self.assertEqual(res_ok.status_code, status.HTTP_204_NO_CONTENT)

        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.REOPENED)
        self.assertEqual(self.complaint.reopen_reason, "Customer dispute returned")

    def test_reopened_complaint_cannot_return_to_resolved_without_new_outcome_and_independent_verification(self):
        """
        CRITICAL REQUIREMENT 2:
        Ensure reopened complaints require a newly recorded and independently verified outcome
        before they can return to RESOLVED.
        """
        headers = {"HTTP_X_BIIRS_REQUEST": "1"}

        # Step 1: Initial resolution
        self.complaint.status = Complaint.Status.IN_PROGRESS
        self.complaint.save()

        # Operator records outcome
        ComplaintWorkflowService.record_outcome(
            complaint=self.complaint,
            user=self.operator,
            outcome="Initial refund processed",
            evidence="Reversal Batch #001",
        )
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.AWAITING_VERIFICATION)

        # Verifier approves resolution
        ComplaintWorkflowService.verify_outcome(
            complaint=self.complaint,
            user=self.verifier,
            decision="VERIFY",
            note="Audit confirmed refund",
        )
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.RESOLVED)

        # Step 2: Supervisor reopens the complaint
        ComplaintWorkflowService.reopen_complaint(
            complaint=self.complaint,
            user=self.verifier,
            reason="Beneficiary bank returned reversal due to wrong account number",
        )
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.REOPENED)
        # Verify previous outcome was completely wiped/invalidated
        self.assertEqual(self.complaint.resolution_outcome, "")
        self.assertIsNone(self.complaint.resolution_reported_at)
        self.assertIsNone(self.complaint.resolution_verified_at)

        # Step 3: Attempting to verify outcome directly while in REOPENED status must fail
        with self.assertRaises(Exception):
            ComplaintWorkflowService.verify_outcome(
                complaint=self.complaint,
                user=self.verifier,
                decision="VERIFY",
                note="Attempting premature verification",
            )

        # Step 4: Operator records a NEW outcome
        self.complaint.status = Complaint.Status.IN_PROGRESS
        self.complaint.save()

        ComplaintWorkflowService.record_outcome(
            complaint=self.complaint,
            user=self.operator,
            outcome="Corrected beneficiary account and re-dispatched funds",
            evidence="Re-dispatched Session #99201",
        )
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.AWAITING_VERIFICATION)
        self.assertEqual(self.complaint.resolution_outcome, "Corrected beneficiary account and re-dispatched funds")

        # Step 5: Independent verifier confirms new outcome
        ComplaintWorkflowService.verify_outcome(
            complaint=self.complaint,
            user=self.verifier,
            decision="VERIFY",
            note="New session verified on switch",
        )
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.RESOLVED)
        self.assertEqual(self.complaint.resolution_verification, Complaint.ResolutionVerification.VERIFIED)
        self.assertEqual(self.complaint.resolution_verified_by, self.verifier)

    def test_complaint_detail_includes_populated_transactions(self):
        """
        CRITICAL REQUIREMENT 10:
        Verifies that GET /api/v1/complaints/{id} returns populated transactions
        matching the frontend TransactionRecord contract.
        """
        from apps.transactions.models import TransactionInvestigation
        from decimal import Decimal

        TransactionInvestigation.objects.create(
            tenant=self.tenant_a,
            complaint=self.complaint,
            reference="TXN-DETAIL-001",
            source_system="Core banking (Finacle)",
            amount_value=Decimal("50000.00"),
            amount_currency="NGN",
            occurred_at=timezone.now(),
            status_label="Debited",
            status=TransactionInvestigation.SourceStatus.AVAILABLE,
            last_updated_at=timezone.now(),
            conflict="Sources disagree: Core banking shows debited; switch shows pending. No final outcome is assumed.",
            match_evidence="Matched because: Customer account 0123456789 exact match.",
        )

        self.client.force_authenticate(user=self.operator)
        url = f"/api/v1/complaints/{self.complaint.id}"
        response = self.client.get(url, HTTP_X_BIIRS_REQUEST="1")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("transactions", data)
        txns = data["transactions"]
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0]["reference"], "TXN-DETAIL-001")
        self.assertEqual(txns[0]["sourceSystem"], "Core banking (Finacle)")
        self.assertEqual(txns[0]["amount"]["value"], "50,000.00")
        self.assertEqual(txns[0]["amount"]["currency"], "NGN")
        self.assertEqual(txns[0]["status"], "AVAILABLE")
        self.assertIn("Sources disagree:", txns[0]["conflict"])
        self.assertIn("Matched because:", txns[0]["matchEvidence"])

