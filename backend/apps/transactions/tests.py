import uuid
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.services import DevAuthService
from apps.common.models import AuditEvent
from apps.complaints.models import Complaint, ComplaintCategory, ComplaintTimelineEvent, Customer
from apps.tenants.models import Tenant
from .adapters.simulated import SimulatedBankAdapter
from .models import TransactionInvestigation
from .services import TransactionInvestigationService


class TransactionInvestigationTests(TestCase):
    """
    Automated test suite for TransactionInvestigation, SimulatedBankAdapter,
    conflict detection engine, and transaction APIs against PostgreSQL.
    """

    def setUp(self):
        dev_auth = DevAuthService()
        self.tenant = dev_auth.ensure_synthetic_tenant()
        self.operator = dev_auth.get_or_create_persona("operator")
        self.verifier = dev_auth.get_or_create_persona("verifier")
        self.lead = dev_auth.get_or_create_persona("lead")

        # Create secondary tenant for isolation testing
        self.tenant_b = Tenant.objects.create(
            id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
            name="Second Bank",
            slug="second-bank",
            time_zone="Africa/Lagos",
            support_label="Support",
            support_contact="b@bank.test",
            support_hours="9-5",
            is_active=True,
        )
        self.user_b = User.objects.create_user(
            username="user_b",
            email="b@bank.test",
            password="pwd",
            tenant=self.tenant_b,
            permissions_list=["complaints.read", "investigations.read"],
        )

        self.category = ComplaintCategory.objects.create(
            tenant=self.tenant,
            code="TRANSFERS",
            label="Failed transfer",
            is_active=True,
        )

        self.customer = Customer.objects.create(
            tenant=self.tenant,
            customer_number="CUST-782101",
            first_name="Amina",
            last_name="Bello",
            email="amina.bello@example.test",
            account_number="0123456789",
        )

        self.complaint = Complaint.objects.create(
            tenant=self.tenant,
            reference="CMP-2026-TEST-001",
            customer=self.customer,
            customer_reference="•••• 1234",
            received_at=timezone.now(),
            summary="Interbank transfer debited but beneficiary not credited",
            narrative="Customer sent ₦50,000 via NIP. Account debited, but beneficiary uncredited. Ref TXN-TEST-90311.",
            category=self.category,
            priority=Complaint.Priority.HIGH,
            status=Complaint.Status.IN_PROGRESS,
            assigned_operator=self.operator,
            due_at=timezone.now() + timezone.timedelta(hours=24),
        )

        self.client = APIClient()

    def test_simulated_bank_adapter_fetch_account(self):
        """Validates that SimulatedBankAdapter fetches account metadata."""
        adapter = SimulatedBankAdapter()
        account = adapter.fetch_account("0123456789")
        self.assertIsNotNone(account)
        self.assertEqual(account["account_name"], "Amina Bello")
        self.assertEqual(account["currency"], "NGN")

        # Unknown account returns fallback simulation
        unknown = adapter.fetch_account("9988776655")
        self.assertIsNotNone(unknown)
        self.assertEqual(unknown["account_number"], "9988776655")

    def test_simulated_bank_adapter_fetch_transactions(self):
        """Validates querying transactions by account and reference."""
        adapter = SimulatedBankAdapter()
        # Query by account
        txns = adapter.fetch_transactions(account_number="0123456789")
        self.assertTrue(len(txns) >= 1)
        references = [t["reference"] for t in txns]
        self.assertIn("TXN-TEST-90311", references)

        # Query by reference
        ref_txns = adapter.fetch_transactions(reference="ATM-JRNL-8402")
        self.assertEqual(len(ref_txns), 1)
        self.assertEqual(ref_txns[0]["amount_value"], Decimal("20000.00"))

    def test_simulated_bank_adapter_check_switch_status(self):
        """Validates switch query using session ID."""
        adapter = SimulatedBankAdapter()
        switch_res = adapter.check_switch_status(session_id="999014261012142231001")
        self.assertIsNotNone(switch_res)
        self.assertEqual(switch_res["reference"], "TXN-TEST-90311")
        self.assertEqual(switch_res["status_label"], "Debited")

    def test_conflict_detection_engine_discrepancy_vs_confirmed_failure(self):
        """
        CRITICAL REQUIREMENT 7:
        Validates that an interbank conflict (Core banking = DEBITED, Switch = PENDING)
        is flagged with explicit discrepancy phrasing ("Sources disagree: ... No final outcome is assumed.")
        and is NOT treated as a confirmed failed transaction.
        """
        txn_data = {
            "reference": "TXN-NIP-CONFLICT-01",
            "source_system": "Core banking (Finacle)",
            "amount_value": "45000.00",
            "amount_currency": "NGN",
            "occurred_at": timezone.now().isoformat(),
            "status_label": "Debited",
            "status": "AVAILABLE",
            "conflict": "Core banking shows DEBITED; switch shows PENDING (session inward credit unconfirmed).",
            "match_evidence": "Account match 0123456789.",
        }

        inv = TransactionInvestigationService.link_transaction(
            complaint=self.complaint,
            txn_data=txn_data,
            user=self.operator,
        )

        self.assertIsNotNone(inv)
        self.assertIn("Sources disagree:", inv.conflict)
        self.assertIn("No final outcome is assumed.", inv.conflict)
        # Verify status is Debited, NOT failed
        self.assertEqual(inv.status_label, "Debited")
        # Verify timeline event was recorded
        timeline_event = ComplaintTimelineEvent.objects.filter(
            complaint=self.complaint, kind="TRANSACTION_LINKED"
        ).first()
        self.assertIsNotNone(timeline_event)

    def test_source_timestamps_and_freshness_preserved(self):
        """
        CRITICAL REQUIREMENT 6:
        Preserves original source timestamps, ledger sync timestamp,
        and data freshness (AVAILABLE, STALE).
        """
        posting_time = timezone.now() - timezone.timedelta(days=2)
        inv = TransactionInvestigation.objects.create(
            tenant=self.tenant,
            complaint=self.complaint,
            reference="TXN-STALE-001",
            source_system="Instant payment switch (NIBSS)",
            amount_value=Decimal("50000.00"),
            occurred_at=posting_time,
            status=TransactionInvestigation.SourceStatus.STALE,
            last_updated_at=timezone.now() - timezone.timedelta(hours=5),
            status_label="Switch Pending",
            conflict="Sources disagree: NIBSS delayed over 48 hours. No final outcome is assumed.",
        )

        self.assertEqual(inv.occurred_at, posting_time)
        self.assertEqual(inv.status, "STALE")

    def test_search_and_link_from_bank_adapter(self):
        """Validates automated search and linking from SimulatedBankAdapter."""
        linked = TransactionInvestigationService.search_and_link_from_bank_adapter(
            complaint=self.complaint,
            user=self.operator,
        )
        self.assertTrue(len(linked) >= 1)
        linked_refs = [t.reference for t in linked]
        self.assertIn("TXN-TEST-90311", linked_refs)

        # Audit event generated
        audit_event = AuditEvent.objects.filter(
            tenant_id=self.tenant.id,
            action="complaint.transaction_investigation_updated",
            entity_id=str(self.complaint.id),
        ).first()
        self.assertIsNotNone(audit_event)

    def test_complaint_transactions_list_api(self):
        """
        Verifies GET /api/v1/complaints/{id}/transactions returns wire format
        matching TransactionRecord in src/lib/api/types.ts.
        """
        TransactionInvestigation.objects.create(
            tenant=self.tenant,
            complaint=self.complaint,
            reference="TXN-API-TEST",
            source_system="Core banking (Finacle)",
            amount_value=Decimal("25000.00"),
            amount_currency="NGN",
            occurred_at=timezone.now(),
            status_label="Debited",
            status=TransactionInvestigation.SourceStatus.AVAILABLE,
            last_updated_at=timezone.now(),
            conflict="Sources disagree: Core shows debited; switch shows pending. No final outcome is assumed.",
            match_evidence="Matched by account 0123456789.",
        )

        self.client.force_login(self.operator)
        url = f"/api/v1/complaints/{self.complaint.id}/transactions"
        response = self.client.get(url, HTTP_X_BIIRS_REQUEST="1")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(len(data) >= 1)
        txn = data[0]
        # Validate wire schema against TransactionRecord interface
        self.assertIn("reference", txn)
        self.assertIn("sourceSystem", txn)
        self.assertIn("amount", txn)
        self.assertEqual(txn["amount"]["value"], "25,000.00")
        self.assertEqual(txn["amount"]["currency"], "NGN")
        self.assertIn("occurredAt", txn)
        self.assertIn("statusLabel", txn)
        self.assertIn("status", txn)
        self.assertIn("lastUpdatedAt", txn)
        self.assertIn("conflict", txn)
        self.assertIn("matchEvidence", txn)

    def test_complaint_transaction_search_api_authorisation(self):
        """Verifies POST /api/v1/complaints/{id}/transactions/search requires permission."""
        url = f"/api/v1/complaints/{self.complaint.id}/transactions/search"

        # Operator with investigations.manage succeeds
        self.client.force_login(self.operator)
        res_op = self.client.post(url, HTTP_X_BIIRS_REQUEST="1")
        self.assertEqual(res_op.status_code, status.HTTP_200_OK)

        # User without permission is rejected with 403
        unauthorized_user = User.objects.create_user(
            username="unauthorized_op",
            email="noperm@bank.test",
            password="pwd",
            tenant=self.tenant,
            permissions_list=[],
        )
        self.client.force_login(unauthorized_user)
        res_fail = self.client.post(url, HTTP_X_BIIRS_REQUEST="1")
        self.assertEqual(res_fail.status_code, status.HTTP_403_FORBIDDEN)

    def test_tenant_isolation_on_transactions(self):
        """Validates that Tenant B cannot query Tenant A transactions."""
        self.client.force_login(self.user_b)
        url = f"/api/v1/complaints/{self.complaint.id}/transactions"
        response = self.client.get(url, HTTP_X_BIIRS_REQUEST="1")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
