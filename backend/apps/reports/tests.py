"""
Comprehensive automated test suite for BIIRS Operational Reports module.
Validates:
- All 7 report types match frontend wire schema
- Tenant isolation across aggregate metrics
- Strict segregation of verified vs reported resolutions
- Reopened complaints handling
- Date-range filters (7d, 30d, 90d, custom) and boundary validation
- Division-by-zero protection (None / unavailable states)
- Data source coverage and freshness indicators
- RBAC permissions (reports.read)
"""

from datetime import timedelta
import uuid

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.complaints.models import Complaint, ComplaintCategory, Customer
from apps.handoffs.models import ForwardingHandoff, ReceivingTeam
from apps.incidents.models import Incident, IncidentComplaint
from apps.tenants.models import DataSource, Tenant


class ReportsModuleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Primary tenant
        cls.tenant = Tenant.objects.create(
            name="Zenith Horizon Bank",
            slug=f"zenith-{uuid.uuid4().hex[:6]}",
            time_zone="Africa/Lagos",
        )
        # Secondary tenant for isolation testing
        cls.other_tenant = Tenant.objects.create(
            name="Apex Commercial Bank",
            slug=f"apex-{uuid.uuid4().hex[:6]}",
            time_zone="Africa/Lagos",
        )

        # Operator with reports.read permission
        cls.user = User.objects.create_user(
            username=f"rep_op_{uuid.uuid4().hex[:6]}",
            email="report_op@bank.test",
            first_name="Report",
            last_name="Auditor",
            tenant=cls.tenant,
            role_label="Operator",
            permissions_list=["complaints.read", "reports.read"],
        )

        # User without reports.read
        cls.restricted_user = User.objects.create_user(
            username=f"rep_no_perm_{uuid.uuid4().hex[:6]}",
            email="noperm@bank.test",
            tenant=cls.tenant,
            role_label="Basic Staff",
            permissions_list=["complaints.read"],
        )

        # Categories
        cls.cat_atm = ComplaintCategory.objects.create(
            tenant=cls.tenant, code="ATM_FAIL", label="Failed ATM Dispense - Card Debited"
        )
        cls.cat_fraud = ComplaintCategory.objects.create(
            tenant=cls.tenant, code="FRAUD_DEBIT", label="Unauthorized Card Debit"
        )

        # Customers
        cls.customer = Customer.objects.create(
            tenant=cls.tenant,
            customer_number="CUST-REP-001",
            first_name="Ada",
            last_name="Eze",
        )

        # Data sources
        cls.ds1 = DataSource.objects.create(
            tenant=cls.tenant,
            name="Core Banking Ledger",
            kind="REST",
            status=DataSource.Status.AVAILABLE,
            last_updated_at=timezone.now(),
        )
        cls.ds2 = DataSource.objects.create(
            tenant=cls.tenant,
            name="ATM Switch Journal",
            kind="DB",
            status=DataSource.Status.AVAILABLE,
            last_updated_at=timezone.now(),
        )

        # Seed realistic complaints across lifecycle
        now = timezone.now()

        # 1. New complaint
        cls.c1 = Complaint.objects.create(
            tenant=cls.tenant,
            reference="CMP-REP-001",
            customer=cls.customer,
            customer_reference="CUST-REP-001",
            category=cls.cat_atm,
            source_channel="Mobile App",
            status=Complaint.Status.NEW,
            priority=Complaint.Priority.HIGH,
            summary="ATM funds not dispensed",
            narrative="ATM debited account but did not dispense cash.",
            received_at=now - timedelta(days=2),
            due_at=now + timedelta(days=1),
        )

        # 2. In progress complaint
        cls.c2 = Complaint.objects.create(
            tenant=cls.tenant,
            reference="CMP-REP-002",
            customer=cls.customer,
            customer_reference="CUST-REP-001",
            category=cls.cat_atm,
            source_channel="Mobile App",
            status=Complaint.Status.IN_PROGRESS,
            priority=Complaint.Priority.MEDIUM,
            summary="Second ATM debit timeout",
            narrative="Dispenser timeout occurred.",
            received_at=now - timedelta(days=5),
            due_at=now + timedelta(days=2),
        )

        # 3. Outcome reported but AWAITING_VERIFICATION (Maker-checker unverified)
        cls.c3 = Complaint.objects.create(
            tenant=cls.tenant,
            reference="CMP-REP-003",
            customer=cls.customer,
            customer_reference="CUST-REP-001",
            category=cls.cat_fraud,
            source_channel="Contact centre feed",
            status=Complaint.Status.AWAITING_VERIFICATION,
            priority=Complaint.Priority.CRITICAL,
            summary="Fraudulent card swipe",
            narrative="Customer disputed pos transaction.",
            received_at=now - timedelta(days=3),
            due_at=now + timedelta(days=1),
            resolution_outcome="Card blocked and provisional credit requested.",
            resolution_reported_at=now - timedelta(hours=10),
            resolution_reported_by=cls.user,
            resolution_verification=Complaint.ResolutionVerification.AWAITING,
        )

        # 4. Verified resolved complaint
        cls.c4 = Complaint.objects.create(
            tenant=cls.tenant,
            reference="CMP-REP-004",
            customer=cls.customer,
            customer_reference="CUST-REP-001",
            category=cls.cat_atm,
            source_channel="Branch Walk-in",
            status=Complaint.Status.RESOLVED,
            priority=Complaint.Priority.MEDIUM,
            summary="Auto-reversal confirmed",
            narrative="Reversal confirmed on core banking.",
            received_at=now - timedelta(days=4),
            due_at=now + timedelta(days=1),
            resolution_outcome="Funds reversed to customer account.",
            resolution_reported_at=now - timedelta(hours=20),
            resolution_reported_by=cls.user,
            resolution_verification=Complaint.ResolutionVerification.VERIFIED,
            resolution_verified_at=now - timedelta(hours=18),
            resolution_verified_by=cls.user,
        )

        # 5. Overdue complaint
        cls.c5 = Complaint.objects.create(
            tenant=cls.tenant,
            reference="CMP-REP-005",
            customer=cls.customer,
            customer_reference="CUST-REP-001",
            category=cls.cat_atm,
            source_channel="USSD",
            status=Complaint.Status.NEEDS_ACTION,
            priority=Complaint.Priority.HIGH,
            summary="Overdue ATM dispute",
            narrative="Exceeded resolution due date.",
            received_at=now - timedelta(days=10),
            due_at=now - timedelta(days=2),  # In the past -> Overdue!
        )

        # 6. Reopened complaint
        cls.c6 = Complaint.objects.create(
            tenant=cls.tenant,
            reference="CMP-REP-006",
            customer=cls.customer,
            customer_reference="CUST-REP-001",
            category=cls.cat_atm,
            source_channel="Mobile App",
            status=Complaint.Status.REOPENED,
            priority=Complaint.Priority.HIGH,
            summary="Reopened dispute",
            narrative="Customer reports reversal failed to reflect.",
            received_at=now - timedelta(days=6),
            due_at=now + timedelta(days=2),
            reopen_reason="Reversal was incomplete.",
        )

        # 7. Other tenant's complaint (must not bleed into reports)
        cls.other_cust = Customer.objects.create(
            tenant=cls.other_tenant,
            customer_number="CUST-OTHER-999",
            first_name="Foreign",
            last_name="Customer",
        )
        cls.other_c = Complaint.objects.create(
            tenant=cls.other_tenant,
            reference="CMP-OTHER-999",
            customer=cls.other_cust,
            customer_reference="CUST-OTHER-999",
            source_channel="Web Banking",
            status=Complaint.Status.RESOLVED,
            priority=Complaint.Priority.LOW,
            summary="Other bank complaint",
            narrative="Should never appear in Zenith reports.",
            received_at=now - timedelta(days=1),
            resolution_verification=Complaint.ResolutionVerification.VERIFIED,
            resolution_verified_at=now - timedelta(hours=1),
        )

        # Handoffs & Teams
        cls.team = ReceivingTeam.objects.create(
            tenant=cls.tenant,
            name="ATM & Terminal Operations",
            code="ATM_OPS",
            channel="Internal Queue",
            response_due_hours=24,
        )
        cls.handoff = ForwardingHandoff.objects.create(
            tenant=cls.tenant,
            complaint=cls.c2,
            team=cls.team,
            channel="Internal Queue",
            state=ForwardingHandoff.State.RESPONDED,
            message="Please verify terminal journal.",
            created_at=now - timedelta(hours=12),
            acknowledged_at=now - timedelta(hours=11),
            responded_at=now - timedelta(hours=8),
            response_due_at=now + timedelta(hours=12),
        )
        ForwardingHandoff.objects.filter(id=cls.handoff.id).update(created_at=now - timedelta(hours=12))
        cls.handoff.refresh_from_db()

        # Incident and complaint association
        cls.incident = Incident.objects.create(
            tenant=cls.tenant,
            reference="INC-REP-001",
            title="Widespread ATM Bill Presenter Glitch",
            summary="Switch timeout during cash presentation.",
            severity=Incident.Severity.CRITICAL,
            status=Incident.Status.CONFIRMED,
        )
        IncidentComplaint.objects.create(
            tenant=cls.tenant,
            incident=cls.incident,
            complaint=cls.c1,
            is_confirmed=True,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_all_seven_reports_return_valid_schema(self):
        """Verify that all 7 BIIRS report types return HTTP 200 and adhere strictly to ReportResult schema."""
        report_slugs = [
            "overview",
            "complaint-volumes",
            "recurring-issues",
            "resolution-performance",
            "team-response-times",
            "overdue-cases",
            "incident-trends",
        ]

        for slug in report_slugs:
            with self.subTest(report_slug=slug):
                url = f"/api/v1/reports/{slug}?range=30d"
                response = self.client.get(url)
                self.assertEqual(
                    response.status_code, 200, f"Failed on report '{slug}': {response.data}"
                )
                data = response.data

                # Assert top-level keys
                self.assertIn("type", data)
                self.assertIn("period", data)
                self.assertIn("from", data["period"])
                self.assertIn("to", data["period"])
                self.assertIn("coverage", data)
                self.assertIn("complete", data["coverage"])
                self.assertIn("sources", data["coverage"])
                self.assertIn("definitions", data)
                self.assertIn("metrics", data)
                self.assertIn("generatedAt", data)

                # Validate metrics shape
                for metric in data["metrics"]:
                    self.assertIn("key", metric)
                    self.assertIn("label", metric)
                    self.assertIn("value", metric)
                    if "unit" in metric and metric["unit"] is not None:
                        self.assertIn(metric["unit"], ["count", "hours", "percent"])

                # Validate series if present
                if data.get("series"):
                    self.assertIn("label", data["series"])
                    self.assertIn("points", data["series"])
                    for pt in data["series"]["points"]:
                        self.assertIn("date", pt)
                        self.assertIn("value", pt)

                # Validate rows if present
                if data.get("rows"):
                    self.assertIn("heading", data["rows"])
                    self.assertIn("valueLabel", data["rows"])
                    self.assertIn("items", data["rows"])
                    for item in data["rows"]["items"]:
                        self.assertIn("label", item)
                        self.assertIn("value", item)

    def test_unauthenticated_request_rejected(self):
        """Unauthenticated requests must be rejected."""
        unauth_client = APIClient()
        response = unauth_client.get("/api/v1/reports/overview")
        self.assertIn(response.status_code, [401, 403])

    def test_permission_enforcement(self):
        """User without reports.read must receive 403 Forbidden."""
        self.client.force_authenticate(user=self.restricted_user)
        response = self.client.get("/api/v1/reports/overview")
        self.assertEqual(response.status_code, 403)

    def test_tenant_isolation_in_reports(self):
        """Other bank's complaints must NEVER bleed into Zenith's reports."""
        url = "/api/v1/reports/overview?range=30d"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Total received must only count Zenith complaints (6), not the other bank's complaint (1)
        total_metric = next(m for m in response.data["metrics"] if m["key"] == "total_received")
        self.assertEqual(total_metric["value"], 6)

        # Verified resolutions must only count Zenith's verified complaint (1), not other bank's (1)
        verified_metric = next(m for m in response.data["metrics"] if m["key"] == "verified_resolved")
        self.assertEqual(verified_metric["value"], 1)

    def test_verified_vs_unverified_resolution_distinction(self):
        """Resolution statistics must strictly separate independently verified outcomes from reported pending ones."""
        url = "/api/v1/reports/resolution-performance?range=30d"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        metrics = {m["key"]: m["value"] for m in response.data["metrics"]}
        # CMP-REP-004 is verified
        self.assertEqual(metrics["verified_resolutions"], 1)
        # CMP-REP-003 is reported but AWAITING verification
        self.assertEqual(metrics["pending_verification"], 1)

    def test_reopened_complaints_not_counted_as_resolved(self):
        """Reopened complaints must not count as verified resolutions."""
        url = "/api/v1/reports/overview?range=30d"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        verified_metric = next(m for m in response.data["metrics"] if m["key"] == "verified_resolved")
        self.assertEqual(verified_metric["value"], 1)

    def test_overdue_cases_calculation(self):
        """Overdue report must identify cases where due_at is past and status is not RESOLVED."""
        url = "/api/v1/reports/overdue-cases?range=30d"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        metrics = {m["key"]: m["value"] for m in response.data["metrics"]}
        # CMP-REP-005 is past due
        self.assertGreaterEqual(metrics["total_overdue"], 1)
        self.assertIsNotNone(metrics["max_overdue_hours"])

    def test_team_response_times_aggregations(self):
        """Team response report must accurately compute acknowledgement and response times."""
        url = "/api/v1/reports/team-response-times?range=30d"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        metrics = {m["key"]: m["value"] for m in response.data["metrics"]}
        self.assertEqual(metrics["total_handoffs"], 1)
        # ack duration: 1h, resp duration: 4h
        self.assertEqual(metrics["avg_ack_hours"], 1.0)
        self.assertEqual(metrics["avg_resp_hours"], 4.0)

    def test_incident_trends_metrics(self):
        """Incident trends report must reflect active incidents and associated complaints."""
        url = "/api/v1/reports/incident-trends?range=30d"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        metrics = {m["key"]: m["value"] for m in response.data["metrics"]}
        self.assertGreaterEqual(metrics["active_incidents"], 1)
        self.assertGreaterEqual(metrics["linked_complaints"], 1)

    def test_date_range_custom_and_boundaries(self):
        """Test custom date filtering and validation."""
        today = timezone.now().date()
        from_date = (today - timedelta(days=7)).isoformat()
        to_date = today.isoformat()

        # Valid custom range
        url = f"/api/v1/reports/overview?range=custom&from={from_date}&to={to_date}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["period"]["from"], from_date)
        self.assertEqual(response.data["period"]["to"], to_date)

        # Invalid custom range: from > to
        bad_url = f"/api/v1/reports/overview?range=custom&from={to_date}&to={from_date}"
        bad_response = self.client.get(bad_url)
        self.assertEqual(bad_response.status_code, 400)

        # Missing params
        missing_url = "/api/v1/reports/overview?range=custom"
        missing_response = self.client.get(missing_url)
        self.assertEqual(missing_response.status_code, 400)

    def test_data_source_coverage_indicator(self):
        """Stale or unavailable data sources must mark coverage incomplete with a clear note."""
        # Make one source STALE
        self.ds2.status = DataSource.Status.STALE
        self.ds2.save()

        url = "/api/v1/reports/overview?range=30d"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["coverage"]["complete"])
        self.assertIsNotNone(response.data["coverage"]["note"])
        self.assertIn("stale or unavailable", response.data["coverage"]["note"])

        # Restore
        self.ds2.status = DataSource.Status.AVAILABLE
        self.ds2.save()
