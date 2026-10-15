import uuid
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from apps.tenants.models import Tenant, DataSource
from apps.accounts.services import DevAuthService
from apps.accounts.models import User

class TenantAndDataSourceTests(TestCase):
    def setUp(self):
        self.auth_service = DevAuthService()
        self.tenant_a = self.auth_service.ensure_synthetic_tenant()
        self.user_a = self.auth_service.get_or_create_persona("operator")

        # Create Tenant B and User B for tenant isolation testing
        self.tenant_b = Tenant.objects.create(
            id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
            name="Second Commercial Bank",
            slug="second-bank",
            time_zone="Africa/Accra",
            support_label="Second Bank Desk",
            support_contact="support@secondbank.test"
        )
        self.user_b = User.objects.create(
            id=uuid.UUID("00000000-0000-0000-0000-000000000020"),
            username="user_b",
            tenant=self.tenant_b,
            email="user_b@secondbank.test",
            role_label="Operator"
        )

        # Create Data Sources for both tenants
        self.source_a1 = DataSource.objects.create(
            tenant=self.tenant_a,
            name="Contact centre feed",
            kind="Complaint intake",
            status=DataSource.Status.AVAILABLE
        )
        self.source_a2 = DataSource.objects.create(
            tenant=self.tenant_a,
            name="Core banking",
            kind="Transactions",
            status=DataSource.Status.STALE,
            note="Delay of 9 hours"
        )
        self.source_b1 = DataSource.objects.create(
            tenant=self.tenant_b,
            name="Second Bank Core Finacle",
            kind="Transactions",
            status=DataSource.Status.AVAILABLE
        )

        self.client = APIClient()

    def test_datasource_list_unauthenticated_returns_401(self):
        """Verify unauthenticated access to /data-sources is rejected."""
        response = self.client.get("/api/v1/data-sources")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data, {"message": "Sign in to continue."})

    def test_datasource_list_scoped_to_tenant_a(self):
        """Verify Tenant A user only receives Tenant A data sources."""
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get("/api/v1/data-sources")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        self.assertEqual(len(data), 2)
        names = [item["name"] for item in data]
        self.assertIn("Contact centre feed", names)
        self.assertIn("Core banking", names)
        self.assertNotIn("Second Bank Core Finacle", names)

    def test_tenant_isolation_cross_tenant_access_blocked(self):
        """Verify Tenant B user only receives Tenant B data sources and never Tenant A data."""
        self.client.force_authenticate(user=self.user_b)
        response = self.client.get("/api/v1/data-sources")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["name"], "Second Bank Core Finacle")
        self.assertNotEqual(data[0]["name"], "Contact centre feed")
