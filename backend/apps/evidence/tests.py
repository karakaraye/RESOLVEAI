import uuid
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.services import DevAuthService
from apps.common.models import AuditEvent
from apps.complaints.models import Complaint, ComplaintCategory, ComplaintTimelineEvent
from apps.tenants.models import Tenant
from apps.transactions.models import TransactionInvestigation
from .models import EvidenceRecord
from .services import EvidenceManagementService


class EvidenceManagementTests(TestCase):
    """
    Automated test suite for EvidenceRecord, EvidenceManagementService,
    provenance preservation, maker-checker verification, and evidence APIs against PostgreSQL.
    """

    def setUp(self):
        dev_auth = DevAuthService()
        self.tenant = dev_auth.ensure_synthetic_tenant()
        self.operator = dev_auth.get_or_create_persona("operator")
        self.verifier = dev_auth.get_or_create_persona("verifier")
        self.lead = dev_auth.get_or_create_persona("lead")

        # Create secondary tenant for isolation testing
        self.tenant_b = Tenant.objects.create(
            id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
            name="Third Bank",
            slug="third-bank",
            time_zone="Africa/Lagos",
            support_label="Support",
            support_contact="c@bank.test",
            support_hours="9-5",
            is_active=True,
        )
        self.user_b = User.objects.create_user(
            username="user_c",
            email="c@bank.test",
            password="pwd",
            tenant=self.tenant_b,
            permissions_list=["complaints.read", "evidence.read"],
        )

        self.category = ComplaintCategory.objects.create(
            tenant=self.tenant,
            code="CARDS_ATM",
            label="Card & ATM debit",
            is_active=True,
        )

        from apps.complaints.models import Customer
        self.customer = Customer.objects.create(
            tenant=self.tenant,
            customer_number="CUST-914022",
            first_name="Chidi",
            last_name="Okonkwo",
            email="chidi.okonkwo@example.test",
            account_number="0987654321",
        )

        self.complaint = Complaint.objects.create(
            tenant=self.tenant,
            reference="CMP-2026-EVD-001",
            customer=self.customer,
            customer_reference="•••• 5678",
            received_at=timezone.now(),
            summary="ATM undispensed cash with debit",
            narrative="Customer attempted withdrawal of ₦20,000 at Victoria Island ATM 2. Cash unretrieved, account debited.",
            category=self.category,
            priority=Complaint.Priority.HIGH,
            status=Complaint.Status.IN_PROGRESS,
            assigned_operator=self.operator,
            due_at=timezone.now() + timezone.timedelta(hours=24),
        )

        self.txn = TransactionInvestigation.objects.create(
            tenant=self.tenant,
            complaint=self.complaint,
            reference="ATM-JRNL-8402",
            source_system="Core banking (Finacle)",
            amount_value=20000.00,
            amount_currency="NGN",
            status_label="Debited",
            status=TransactionInvestigation.SourceStatus.AVAILABLE,
        )

        self.client = APIClient()

    def test_attach_evidence_record_preserves_provenance_and_timestamps(self):
        """
        CRITICAL REQUIREMENT 6:
        Preserves original document reference, source timestamps,
        evidence provenance, and raw JSON payload.
        """
        source_time = timezone.now() - timezone.timedelta(days=1)
        raw_data = {
            "terminal_id": "ATM-VI-02",
            "stan": "881204",
            "error_code": "BILL_PRESENTER_PICK_FAILURE",
            "presented_notes": 0,
        }

        evidence = EvidenceManagementService.attach_evidence(
            complaint=self.complaint,
            evidence_data={
                "kind": EvidenceRecord.EvidenceKind.SYSTEM_TRACE,
                "document_reference": "ATM-TRACE-881204",
                "title": "ATM Hardware Presenter Diagnostic Log",
                "summary": "Bill presenter pick failure code 42. Zero cassette notes presented.",
                "source_system": "Wincor Nixdorf ATM Terminal Journal",
                "source_timestamp": source_time,
                "provenance": "Retrieved from Branch ATM Electronic Journal Server via automated probe",
                "data_freshness": EvidenceRecord.DataFreshness.FRESH,
                "raw_payload": raw_data,
                "transaction_investigation_id": str(self.txn.id),
            },
            user=self.operator,
        )

        self.assertIsNotNone(evidence)
        self.assertEqual(evidence.document_reference, "ATM-TRACE-881204")
        self.assertEqual(evidence.source_timestamp, source_time)
        self.assertEqual(evidence.raw_payload["stan"], "881204")
        self.assertEqual(evidence.transaction_investigation, self.txn)
        self.assertFalse(evidence.is_verified)

        # Timeline event created
        timeline_event = ComplaintTimelineEvent.objects.filter(
            complaint=self.complaint, kind="EVIDENCE_ATTACHED"
        ).first()
        self.assertIsNotNone(timeline_event)

        # Audit event created
        audit_event = AuditEvent.objects.filter(
            tenant_id=self.tenant.id,
            action="complaint.evidence_attached",
            entity_id=str(self.complaint.id),
        ).first()
        self.assertIsNotNone(audit_event)

    def test_verify_evidence_maker_checker(self):
        """
        Validates maker-checker verification:
        Only users with evidence.verify permission can verify authoritative evidence.
        """
        evidence = EvidenceRecord.objects.create(
            tenant=self.tenant,
            complaint=self.complaint,
            kind=EvidenceRecord.EvidenceKind.LEDGER_ENTRY,
            document_reference="JRN-FIN-TEST-001",
            title="Core Ledger Outward Journal",
            source_system="Finacle Core Banking",
            is_verified=False,
        )

        # Operator lacks evidence.verify -> raises PermissionDenied
        with self.assertRaises(Exception):
            EvidenceManagementService.verify_evidence(
                evidence_id=str(evidence.id),
                tenant=self.tenant,
                user=self.operator,
                is_verified=True,
            )

        # Verifier with evidence.verify succeeds
        verified_evidence = EvidenceManagementService.verify_evidence(
            evidence_id=str(evidence.id),
            tenant=self.tenant,
            user=self.verifier,
            is_verified=True,
        )

        self.assertTrue(verified_evidence.is_verified)
        self.assertEqual(verified_evidence.verified_by, self.verifier)
        self.assertIsNotNone(verified_evidence.verified_at)

        # Timeline event created
        timeline_event = ComplaintTimelineEvent.objects.filter(
            complaint=self.complaint, kind="EVIDENCE_VERIFIED"
        ).first()
        self.assertIsNotNone(timeline_event)

    def test_complaint_evidence_list_and_create_apis(self):
        """Verifies GET and POST /api/v1/complaints/{id}/evidence."""
        self.client.force_login(self.operator)
        url = f"/api/v1/complaints/{self.complaint.id}/evidence"

        # 1. Attach evidence via POST
        create_payload = {
            "kind": "CUSTOMER_RECEIPT",
            "documentReference": "RCPT-2026-9901",
            "title": "Customer ATM Card Slip Receipt",
            "summary": "ATM printed slip showing error code 058.",
            "sourceSystem": "Customer Scan",
            "provenance": "Customer uploaded via branch mobile app",
        }
        create_res = self.client.post(
            f"{url}/create",
            data=create_payload,
            format="json",
            HTTP_X_BIIRS_REQUEST="1",
        )
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        created_data = create_res.json()
        self.assertEqual(created_data["documentReference"], "RCPT-2026-9901")

        # 2. List evidence via GET
        list_res = self.client.get(url, HTTP_X_BIIRS_REQUEST="1")
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        items = list_res.json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["documentReference"], "RCPT-2026-9901")
        self.assertFalse(items[0]["isVerified"])

    def test_evidence_verify_api(self):
        """Verifies POST /api/v1/evidence/{id}/verify."""
        evidence = EvidenceRecord.objects.create(
            tenant=self.tenant,
            complaint=self.complaint,
            kind=EvidenceRecord.EvidenceKind.LEDGER_ENTRY,
            document_reference="JRN-API-TEST",
            title="Core Ledger Journal",
            source_system="Finacle Core Banking",
            is_verified=False,
        )

        url = f"/api/v1/evidence/{evidence.id}/verify"

        # Operator (lacks evidence.verify) -> 403
        self.client.force_login(self.operator)
        res_op = self.client.post(url, data={"isVerified": True}, format="json", HTTP_X_BIIRS_REQUEST="1")
        self.assertEqual(res_op.status_code, status.HTTP_403_FORBIDDEN)

        # Verifier (has evidence.verify) -> 200
        self.client.force_login(self.verifier)
        res_ver = self.client.post(url, data={"isVerified": True}, format="json", HTTP_X_BIIRS_REQUEST="1")
        self.assertEqual(res_ver.status_code, status.HTTP_200_OK)
        self.assertTrue(res_ver.json()["isVerified"])
        self.assertEqual(res_ver.json()["verifiedBy"], self.verifier.display_name)

    def test_tenant_isolation_on_evidence(self):
        """Validates that Tenant B cannot query Tenant A evidence."""
        self.client.force_login(self.user_b)
        url = f"/api/v1/complaints/{self.complaint.id}/evidence"
        response = self.client.get(url, HTTP_X_BIIRS_REQUEST="1")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_evidence_tamper_detection_and_source_authenticity_invariants(self):
        """
        Validates:
        1. SHA-256 detects post-ingestion record tampering/modification.
        2. Source authenticity is established via multi-attribute provenance:
           source_system, source_timestamp, document_reference, audit events,
           and maker-checker attestation — not by hash alone.
        """
        import hashlib, json

        payload = {"journal_id": "JRN-8801", "ledger_status": "POSTED", "amount": 50000.0}
        evidence = EvidenceRecord.objects.create(
            tenant=self.tenant,
            complaint=self.complaint,
            kind=EvidenceRecord.EvidenceKind.LEDGER_ENTRY,
            document_reference="JRN-8801",
            title="Core Banking Ledger Snapshot",
            source_system="Finacle Core Banking Journal",
            source_timestamp=timezone.now(),
            provenance="Extracted via authenticated read-only adapter by batch worker at 2026-10-14T18:00:00Z",
            data_freshness=EvidenceRecord.DataFreshness.FRESH,
            raw_payload=payload,
            is_verified=False,
        )

        # 1. Tamper detection verification
        initial_hash = evidence.compute_payload_hash()
        expected_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        self.assertEqual(initial_hash, expected_hash)

        # Tampering with payload alters the hash
        evidence.raw_payload["ledger_status"] = "REVERSED"
        tampered_hash = evidence.compute_payload_hash()
        self.assertNotEqual(initial_hash, tampered_hash)

        # 2. Source authenticity envelope verification
        # The system requires verified source identity, timestamp, and maker-checker signoff
        self.assertEqual(evidence.source_system, "Finacle Core Banking Journal")
        self.assertIsNotNone(evidence.source_timestamp)
        self.assertEqual(evidence.document_reference, "JRN-8801")
        self.assertFalse(evidence.is_verified)  # Unverified by default

        # Maker-checker independent verification establishes attestation
        EvidenceManagementService.verify_evidence(
            evidence_id=str(evidence.id),
            tenant=self.tenant,
            user=self.verifier,
            is_verified=True,
        )
        evidence.refresh_from_db()
        self.assertTrue(evidence.is_verified)
        self.assertEqual(evidence.verified_by, self.verifier)
        self.assertIsNotNone(evidence.verified_at)
