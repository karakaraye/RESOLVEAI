from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status
from apps.accounts.services import DevAuthService
from apps.accounts.models import User
from apps.accounts.permissions import HasTenantAccess, RequirePermission

class AccountsAndSessionTests(TestCase):
    def setUp(self):
        self.auth_service = DevAuthService()
        self.operator = self.auth_service.get_or_create_persona("operator")
        self.verifier = self.auth_service.get_or_create_persona("verifier")
        self.client = APIClient()

    def test_custom_user_display_name_and_permissions(self):
        """Verify Custom User display name and fine-grained permission checks."""
        self.assertEqual(self.operator.display_name, "Test Operator")
        self.assertTrue(self.operator.has_case_permission("complaints.read"))
        self.assertTrue(self.operator.has_case_permission("complaints.record_outcome"))
        self.assertFalse(self.operator.has_case_permission("complaints.verify_outcome"))

        self.assertEqual(self.verifier.display_name, "Senior Verifier")
        self.assertTrue(self.verifier.has_case_permission("complaints.verify_outcome"))

    def test_session_endpoint_unauthenticated_returns_401(self):
        """Verify unauthenticated GET /session returns 401 with exact contract."""
        response = self.client.get("/api/v1/session")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data, {"message": "Sign in to continue."})

    def test_session_endpoint_authenticated_returns_wire_contract(self):
        """Verify authenticated GET /session returns full session wire payload."""
        self.client.force_authenticate(user=self.operator)
        response = self.client.get("/api/v1/session")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        # Validate User structure
        self.assertIn("user", data)
        self.assertEqual(data["user"]["displayName"], "Test Operator")
        self.assertEqual(data["user"]["email"], "operator@bank.test")
        self.assertEqual(data["user"]["department"], "Customer Care")
        self.assertEqual(data["user"]["roleLabel"], "Operator")

        # Validate Tenant structure
        self.assertIn("tenant", data)
        self.assertEqual(data["tenant"]["name"], "Test Bank")
        self.assertEqual(data["tenant"]["timeZone"], "Africa/Lagos")
        self.assertIn("support", data["tenant"])
        self.assertEqual(data["tenant"]["support"]["label"], "Test Bank BIIRS desk")

        # Validate Permissions array
        self.assertIn("permissions", data)
        self.assertIn("complaints.read", data["permissions"])

        # Validate Session metadata
        self.assertIn("session", data)
        self.assertIn("identityProvider", data["session"])

        # Validate CSRF Token header injection
        self.assertTrue(response.has_header("X-CSRFToken"))

    def test_sign_out_endpoint(self):
        """Verify POST /session/sign-out terminates session and returns redirectUrl."""
        self.client.force_authenticate(user=self.operator)
        response = self.client.post("/api/v1/session/sign-out", HTTP_X_BIIRS_REQUEST="1")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"redirectUrl": "/signed-out"})

        # Subsequent session query without credentials should be unauthenticated
        self.client.force_authenticate(user=None)
        response_after = self.client.get("/api/v1/session")
        self.assertEqual(response_after.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(DEBUG=True, ALLOW_DEV_AUTH=True)
    def test_dev_login_endpoint(self):
        """Verify POST /auth/dev-login logs in persona and returns session."""
        response = self.client.post(
            "/api/v1/auth/dev-login",
            {"persona": "verifier"},
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["displayName"], "Senior Verifier")
        self.assertIn("complaints.verify_outcome", response.data["permissions"])
        self.assertTrue(response.has_header("X-CSRFToken"))

    @override_settings(DEBUG=False, ALLOW_DEV_AUTH=False)
    def test_dev_login_blocked_in_production(self):
        """Verify dev-login is completely disabled when DEBUG=False or ALLOW_DEV_AUTH=False."""
        response = self.client.post(
            "/api/v1/auth/dev-login",
            {"persona": "operator"},
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data, {"message": "Development authentication is disabled."})

    @override_settings(DEBUG=True, ALLOW_DEV_AUTH=True)
    def test_dev_browser_sign_in_redirects(self):
        """Verify GET /session/sign-in authenticates and redirects to returnTo."""
        response = self.client.get("/api/v1/session/sign-in?returnTo=/complaints")
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(response["Location"], "/complaints")

        # Verify session is active
        session_resp = self.client.get("/api/v1/session")
        self.assertEqual(session_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(session_resp.data["user"]["displayName"], "Test Operator")

    @override_settings(DEBUG=False, ALLOW_DEV_AUTH=False)
    def test_dev_browser_sign_in_blocked_in_production(self):
        """Verify GET /session/sign-in returns 501 when dev auth is disabled."""
        response = self.client.get("/api/v1/session/sign-in?returnTo=/complaints")
        self.assertEqual(response.status_code, status.HTTP_501_NOT_IMPLEMENTED)

    def test_require_permission_class(self):
        """Verify RequirePermission denies access if fine-grained permission is absent."""
        verifier_only_perm = RequirePermission("complaints.verify_outcome")()

        class DummyRequest:
            def __init__(self, user):
                self.user = user

        # Operator lacks verify_outcome
        req_operator = DummyRequest(self.operator)
        self.assertFalse(verifier_only_perm.has_permission(req_operator, None))

        # Verifier has verify_outcome
        req_verifier = DummyRequest(self.verifier)
        self.assertTrue(verifier_only_perm.has_permission(req_verifier, None))
