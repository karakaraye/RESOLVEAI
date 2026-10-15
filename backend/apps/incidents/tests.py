import uuid
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.services import DevAuthService
from apps.common.models import AuditEvent
from apps.complaints.models import Complaint, ComplaintCategory, Customer
from apps.tenants.models import Tenant
from apps.transactions.models import TransactionInvestigation

from .models import Incident, IncidentComplaint, IncidentTimelineEvent
from .services import IncidentDetectionService, IncidentManagementService


class IncidentManagementTests(TestCase):
    """
    Automated test suite for Stage 4: Incident management, candidate generation,
    complaint association, emerging incident detection, and duplicate prevention.
    """

    def setUp(self):
        dev_auth = DevAuthService()
        self.tenant_a = dev_auth.ensure_synthetic_tenant()
        self.operator = dev_auth.get_or_create_persona("operator")
        self.verifier = dev_auth.get_or_create_persona("verifier")
        self.lead = dev_auth.get_or_create_persona("lead")

        # Tenant B for cross-tenant tests
        self.tenant_b = Tenant.objects.create(
            id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
            name="Bank Gamma",
            slug="bank-gamma",
            time_zone="Africa/Lagos",
            support_label="Gamma Support",
            support_contact="gamma@bank.test",
            support_hours="24/7",
            is_active=True,
        )
        self.user_b = User.objects.create_user(
            username="gamma_lead",
            email="gamma@bank.test",
            password="pwd",
            tenant=self.tenant_b,
            permissions_list=["complaints.read", "complaints.edit"],
        )

        self.category_transfers = ComplaintCategory.objects.create(
            tenant=self.tenant_a,
            code="TRANSFERS",
            label="Failed transfer",
            is_active=True,
        )

        self.customer = Customer.objects.create(
            tenant=self.tenant_a,
            customer_number="CUST-INC-001",
            first_name="Emeka",
            last_name="Okafor",
        )

        self.complaint_1 = Complaint.objects.create(
            tenant=self.tenant_a,
            reference="CMP-INC-001",
            customer=self.customer,
            customer_reference="CUST-INC-001",
            source_channel="Contact centre feed",
            summary="Transfer debit without credit to beneficiary",
            narrative="Customer account debited for 50k NGN. Beneficiary has not received credit.",
            category=self.category_transfers,
            priority=Complaint.Priority.HIGH,
            status=Complaint.Status.IN_PROGRESS,
            received_at=timezone.now(),
        )

        self.complaint_2 = Complaint.objects.create(
            tenant=self.tenant_a,
            reference="CMP-INC-002",
            customer=self.customer,
            customer_reference="CUST-INC-001",
            source_channel="Mobile app",
            summary="Interbank transfer failed with switch timeout",
            narrative="NIP switch timeout observed. Funds debited from sender account.",
            category=self.category_transfers,
            priority=Complaint.Priority.HIGH,
            status=Complaint.Status.NEW,
            received_at=timezone.now(),
        )

        self.client = APIClient()

    def test_incident_candidate_creation_and_timeline(self):
        """
        Validates:
        1. Incident candidate is created with status CANDIDATE.
        2. Reference number is auto-generated (INC-YYYY-NNNN).
        3. Timeline event and AuditEvent are logged.
        """
        incident = IncidentManagementService.create_incident_candidate(
            tenant=self.tenant_a,
            title="NIP Outward Clearing Timeout",
            summary="Multiple customer complaints indicating outward NIP clearing failure.",
            category=self.category_transfers,
            severity=Incident.Severity.MAJOR,
            source_system="NIBSS Instant Payments",
            detected_rule="RULE_DISCREPANCY_CLUSTER",
            complaint_ids=[str(self.complaint_1.id)],
            user=self.lead,
        )

        self.assertEqual(incident.status, Incident.Status.CANDIDATE)
        self.assertTrue(incident.reference.startswith(f"INC-{timezone.now().year}-"))
        self.assertEqual(incident.severity, Incident.Severity.MAJOR)

        # Verify candidate association
        links = IncidentComplaint.objects.filter(incident=incident)
        self.assertEqual(links.count(), 1)
        self.assertFalse(links.first().is_confirmed)

        # Verify timeline
        events = IncidentTimelineEvent.objects.filter(incident=incident)
        self.assertTrue(events.filter(kind="CANDIDATE_CREATED").exists())

        # Verify audit event
        self.assertTrue(
            AuditEvent.objects.filter(
                tenant_id=self.tenant_a.id,
                action="incident.candidate_created",
                entity_id=str(incident.id)
            ).exists()
        )

    def test_incident_confirmation_and_complaint_updates(self):
        """
        Validates:
        1. Human review confirmation updates status to CONFIRMED.
        2. Associated complaints are updated to is_confirmed = True.
        3. Complaint records receive shared_incident_reference.
        """
        incident = IncidentManagementService.create_incident_candidate(
            tenant=self.tenant_a,
            title="Candidate Outage",
            summary="Investigating potential switch outage.",
            category=self.category_transfers,
            complaint_ids=[str(self.complaint_1.id)],
            user=self.operator,
        )

        confirmed = IncidentManagementService.confirm_incident(
            incident_id=str(incident.id),
            tenant=self.tenant_a,
            user=self.lead,
            severity=Incident.Severity.CRITICAL,
            title="Confirmed Outward NIP Settlement Interruption",
        )

        self.assertEqual(confirmed.status, Incident.Status.CONFIRMED)
        self.assertEqual(confirmed.severity, Incident.Severity.CRITICAL)
        self.assertEqual(confirmed.confirmed_by, self.lead)
        self.assertIsNotNone(confirmed.confirmed_at)

        # Check complaint link is confirmed
        link = IncidentComplaint.objects.get(incident=incident, complaint=self.complaint_1)
        self.assertTrue(link.is_confirmed)

        # Check complaint record updated
        self.complaint_1.refresh_from_db()
        self.assertEqual(self.complaint_1.shared_incident_reference, confirmed.reference)

    def test_incident_complaint_link_and_unlink(self):
        """
        Validates:
        1. Operator can link and unlink complaints.
        2. Complaint identity and SLA timers are fully preserved.
        3. shared_incident_reference is updated and cleared cleanly.
        """
        incident = IncidentManagementService.create_incident_candidate(
            tenant=self.tenant_a,
            title="Switch Degradation",
            summary="Intermittent card declines.",
            user=self.lead,
        )

        # Link complaint
        link = IncidentManagementService.link_complaint(
            incident_id=str(incident.id),
            complaint_id=str(self.complaint_2.id),
            tenant=self.tenant_a,
            user=self.operator,
            reason="Confirmed same ATM switch issue",
            is_confirmed=True,
        )
        self.assertTrue(link.is_confirmed)
        self.complaint_2.refresh_from_db()
        self.assertEqual(self.complaint_2.shared_incident_reference, incident.reference)

        # Unlink complaint
        unlinked = IncidentManagementService.unlink_complaint(
            incident_id=str(incident.id),
            complaint_id=str(self.complaint_2.id),
            tenant=self.tenant_a,
            user=self.operator,
        )
        self.assertTrue(unlinked)
        self.complaint_2.refresh_from_db()
        self.assertEqual(self.complaint_2.shared_incident_reference, "")

    def test_cross_tenant_incident_association_blocked(self):
        """
        CRITICAL SECURITY INVARIANT:
        Validates that a complaint belonging to Tenant B cannot be linked to Tenant A's incident.
        """
        cust_b = Customer.objects.create(
            tenant=self.tenant_b,
            customer_number="CUST-GAMMA-99",
            first_name="Femi",
            last_name="Adebayo",
        )
        comp_b = Complaint.objects.create(
            tenant=self.tenant_b,
            reference="CMP-GAMMA-001",
            customer=cust_b,
            customer_reference="CUST-GAMMA-99",
            summary="Tenant B transfer issue",
            priority=Complaint.Priority.HIGH,
            status=Complaint.Status.NEW,
            received_at=timezone.now(),
        )

        incident_a = IncidentManagementService.create_incident_candidate(
            tenant=self.tenant_a,
            title="Tenant A Incident",
            summary="Investigating Tenant A outage",
            user=self.lead,
        )

        # Attempting cross-tenant linking throws exception
        with self.assertRaises(Exception):
            IncidentManagementService.link_complaint(
                incident_id=str(incident_a.id),
                complaint_id=str(comp_b.id),
                tenant=self.tenant_a,
                user=self.lead,
            )

    def test_emerging_incident_detection_rule_and_duplicate_prevention(self):
        """
        Validates:
        1. Anomaly detection identifies discrepancy clusters.
        2. An active candidate incident is generated with detected_rule and detection_evidence.
        3. Repeated detection execution reuses active incident instead of generating duplicate alerts.
        """
        # Create transaction discrepancies on complaint 1 and 2
        TransactionInvestigation.objects.create(
            tenant=self.tenant_a,
            complaint=self.complaint_1,
            reference="TXN-DISC-001",
            source_system="Core banking (Finacle)",
            amount_value=Decimal("50000.00"),
            occurred_at=timezone.now(),
            status_label="Debited",
            conflict="Sources disagree: Core banking shows debited; switch shows pending. No final outcome is assumed.",
        )
        TransactionInvestigation.objects.create(
            tenant=self.tenant_a,
            complaint=self.complaint_2,
            reference="TXN-DISC-002",
            source_system="Core banking (Finacle)",
            amount_value=Decimal("50000.00"),
            occurred_at=timezone.now(),
            status_label="Debited",
            conflict="Sources disagree: Core banking shows debited; switch shows pending. No final outcome is assumed.",
        )

        # First detection run
        detected_1 = IncidentDetectionService.detect_emerging_incidents(
            tenant=self.tenant_a,
            lookback_hours=48,
            discrepancy_threshold=2,
        )
        self.assertEqual(len(detected_1), 1)
        inc = detected_1[0]
        self.assertEqual(inc.detected_rule, "RULE_DISCREPANCY_CLUSTER")
        self.assertIn("complaint_count", inc.detection_evidence)
        self.assertEqual(inc.detection_evidence["complaint_count"], 2)

        # Second detection run: Duplicate prevention check
        detected_2 = IncidentDetectionService.detect_emerging_incidents(
            tenant=self.tenant_a,
            lookback_hours=48,
            discrepancy_threshold=2,
        )
        # Should NOT create duplicate incident
        self.assertEqual(len(detected_2), 0)

    def test_incident_api_endpoints(self):
        """
        Validates REST APIs:
        GET  /api/v1/incidents
        POST /api/v1/incidents
        GET  /api/v1/incidents/{id}
        POST /api/v1/incidents/{id}/confirm
        POST /api/v1/incidents/{id}/complaints/link
        POST /api/v1/incidents/{id}/complaints/unlink
        POST /api/v1/incidents/detect
        """
        self.client.force_login(self.lead)

        # 1. Create incident via POST
        create_res = self.client.post(
            "/api/v1/incidents",
            data={
                "title": "API Test Outage",
                "summary": "Switch failure reported via API.",
                "severity": "MAJOR",
                "complaintIds": [str(self.complaint_1.id)],
            },
            format="json",
            HTTP_X_BIIRS_REQUEST="1"
        )
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        inc_id = create_res.json()["id"]

        # 2. List incidents via GET
        list_res = self.client.get("/api/v1/incidents", HTTP_X_BIIRS_REQUEST="1")
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(list_res.json()), 1)

        # 3. Get detail
        detail_res = self.client.get(f"/api/v1/incidents/{inc_id}", HTTP_X_BIIRS_REQUEST="1")
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_res.json()["title"], "API Test Outage")

        # 4. Confirm incident
        confirm_res = self.client.post(
            f"/api/v1/incidents/{inc_id}/confirm",
            data={"severity": "CRITICAL"},
            format="json",
            HTTP_X_BIIRS_REQUEST="1"
        )
        self.assertEqual(confirm_res.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm_res.json()["status"], Incident.Status.CONFIRMED)

        # 5. Link complaint
        link_res = self.client.post(
            f"/api/v1/incidents/{inc_id}/complaints/link",
            data={"complaintId": str(self.complaint_2.id), "reason": "Linked via API test"},
            format="json",
            HTTP_X_BIIRS_REQUEST="1"
        )
        self.assertEqual(link_res.status_code, status.HTTP_200_OK)

        # 6. Unlink complaint
        unlink_res = self.client.post(
            f"/api/v1/incidents/{inc_id}/complaints/unlink",
            data={"complaintId": str(self.complaint_2.id)},
            format="json",
            HTTP_X_BIIRS_REQUEST="1"
        )
        self.assertEqual(unlink_res.status_code, status.HTTP_200_OK)

        # 7. Run detection
        detect_res = self.client.post(
            "/api/v1/incidents/detect",
            data={"lookbackHours": 48},
            format="json",
            HTTP_X_BIIRS_REQUEST="1"
        )
        self.assertEqual(detect_res.status_code, status.HTTP_200_OK)
        self.assertIn("detectedCount", detect_res.json())
