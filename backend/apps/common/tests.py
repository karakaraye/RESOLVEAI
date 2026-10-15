import json
import uuid
from datetime import timedelta
from django.test import TestCase, RequestFactory
from django.http import JsonResponse
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, PermissionDenied
from apps.common.models import IdempotencyRecord, OutboxMessage, AuditEvent
from apps.common.middleware import SecurityHeadersMiddleware, IdempotencyMiddleware
from apps.common.services import IdempotencyService, IdempotentAPIViewMixin
from apps.common.exceptions import custom_exception_handler
from apps.accounts.services import DevAuthService
from apps.accounts.permissions import RequirePermission
from apps.accounts.models import User
from apps.tenants.models import Tenant

class SecurityHeadersAndCSRFTests(TestCase):
    def setUp(self):
        self.auth_service = DevAuthService()
        self.user = self.auth_service.get_or_create_persona("operator")
        self.user.set_password("SecureOperatorPass123!")
        self.user.save()
        self.factory = RequestFactory()
        self.middleware = SecurityHeadersMiddleware(get_response=lambda r: JsonResponse({"status": "ok"}))

    def test_security_headers_present(self):
        """Verify baseline security headers are injected."""
        request = self.factory.get("/api/v1/session")
        response = self.middleware(request)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["Referrer-Policy"], "same-origin")

    def test_mutating_request_requires_biirs_header(self):
        """Verify state-changing API request without X-BIIRS-Request is blocked."""
        request = self.factory.post("/api/v1/complaints/c-1/notes")
        response = self.middleware(request)
        self.assertEqual(response.status_code, 403)
        self.assertIn("X-BIIRS-Request", response.content.decode())

    def test_mutating_request_with_biirs_header_allowed(self):
        """Verify state-changing API request with X-BIIRS-Request: 1 is permitted."""
        request = self.factory.post("/api/v1/complaints/c-1/notes", HTTP_X_BIIRS_REQUEST="1")
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    def test_dev_login_exempt_from_biirs_header(self):
        """Verify dev login endpoint is accessible for initial handshake without custom header."""
        request = self.factory.post("/api/v1/auth/dev-login")
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    def test_csrf_protection_enforced_on_session_authenticated_client(self):
        """
        Verify Django CSRF protection is active on mutating requests when enforce_csrf_checks=True.
        A session-authenticated POST without a valid CSRF token is rejected with 403 Forbidden.
        """
        csrf_client = APIClient(enforce_csrf_checks=True)
        login_success = csrf_client.login(username="operator", password="SecureOperatorPass123!")
        self.assertTrue(login_success)

        # POST without CSRF token
        response = csrf_client.post(
            "/api/v1/session/sign-out",
            HTTP_X_BIIRS_REQUEST="1"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("CSRF", response.content.decode())


class IdempotencyMiddlewareTests(TestCase):
    def setUp(self):
        self.auth_service = DevAuthService()
        self.user = self.auth_service.get_or_create_persona("operator")
        self.factory = RequestFactory()

    def test_invalid_uuid_rejected(self):
        """Verify malformed Idempotency-Key returns HTTP 400."""
        middleware = IdempotencyMiddleware(get_response=lambda r: JsonResponse({"ok": True}))
        request = self.factory.post("/api/v1/test", HTTP_IDEMPOTENCY_KEY="invalid-uuid")
        request.user = self.user
        response = middleware(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid Idempotency-Key", response.content.decode())

    def test_idempotent_duplicate_request_returns_cached_response(self):
        """Verify repeated request returns cached status and payload."""
        key = uuid.uuid4()
        middleware = IdempotencyMiddleware(
            get_response=lambda r: JsonResponse({"created": "note_123"}, status=201)
        )

        # First execution
        request1 = self.factory.post(
            "/api/v1/complaints/c-1/notes",
            data='{"text": "Hello"}',
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(key)
        )
        request1.user = self.user
        response1 = middleware(request1)
        self.assertEqual(response1.status_code, 201)

        # Second execution (Replay with same key)
        request2 = self.factory.post(
            "/api/v1/complaints/c-1/notes",
            data='{"text": "Hello"}',
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(key)
        )
        request2.user = self.user
        response2 = middleware(request2)

        self.assertEqual(response2.status_code, 201)
        self.assertEqual(response2["X-Cache-Lookup"], "HIT-IDEMPOTENT")
        self.assertIn("note_123", response2.content.decode())

    def test_concurrent_idempotent_request_returns_409_conflict(self):
        """Verify in-flight duplicate key returns HTTP 409 Conflict."""
        key = uuid.uuid4()
        IdempotencyRecord.objects.create(
            key=key,
            user=self.user,
            request_path="/api/v1/complaints/c-1/notes",
            request_hash="hash123",
            status=IdempotencyRecord.Status.PENDING
        )

        middleware = IdempotencyMiddleware(get_response=lambda r: JsonResponse({"ok": True}))
        request = self.factory.post(
            "/api/v1/complaints/c-1/notes",
            HTTP_IDEMPOTENCY_KEY=str(key)
        )
        request.user = self.user
        response = middleware(request)

        self.assertEqual(response.status_code, 409)
        self.assertIn("currently being processed", response.content.decode())

    def test_reusing_key_with_different_payload_is_rejected(self):
        """Verify reusing same key with different payload returns HTTP 422."""
        key = uuid.uuid4()
        middleware = IdempotencyMiddleware(
            get_response=lambda r: JsonResponse({"created": "note_1"}, status=201)
        )

        # Initial request
        req1 = self.factory.post(
            "/api/v1/complaints/c-1/notes",
            data='{"text": "Original text"}',
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(key)
        )
        req1.user = self.user
        resp1 = middleware(req1)
        self.assertEqual(resp1.status_code, 201)

        # Subsequent request with different payload under SAME key
        req2 = self.factory.post(
            "/api/v1/complaints/c-1/notes",
            data='{"text": "Tampered or changed payload"}',
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(key)
        )
        req2.user = self.user
        resp2 = middleware(req2)
        self.assertEqual(resp2.status_code, 422)
        self.assertIn("payload mismatch", resp2.content.decode().lower())

    def test_reusing_key_on_different_endpoint_is_rejected(self):
        """Verify reusing same key on a different endpoint returns HTTP 422."""
        key = uuid.uuid4()
        middleware = IdempotencyMiddleware(
            get_response=lambda r: JsonResponse({"created": "note_1"}, status=201)
        )

        req1 = self.factory.post(
            "/api/v1/complaints/c-1/notes",
            data='{"text": "Note content"}',
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(key)
        )
        req1.user = self.user
        resp1 = middleware(req1)
        self.assertEqual(resp1.status_code, 201)

        # Reusing same key on different URL
        req2 = self.factory.post(
            "/api/v1/complaints/c-2/notes",
            data='{"text": "Note content"}',
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(key)
        )
        req2.user = self.user
        resp2 = middleware(req2)
        self.assertEqual(resp2.status_code, 422)
        self.assertIn("scope mismatch", resp2.content.decode().lower())

    def test_interrupted_request_cleans_up_for_recovery(self):
        """Verify unhandled exception clears pending lock record for safe client retry."""
        key = uuid.uuid4()

        def failing_view(r):
            raise RuntimeError("Database connection dropped unexpectedly")

        middleware = IdempotencyMiddleware(get_response=failing_view)
        req = self.factory.post(
            "/api/v1/complaints/c-1/notes",
            data='{"text": "Test"}',
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(key)
        )
        req.user = self.user

        # Run process_request
        middleware.process_request(req)
        self.assertTrue(IdempotencyRecord.objects.filter(key=key).exists())

        # Simulate exception handling
        middleware.process_exception(req, RuntimeError("Simulated failure"))

        # Pending record must be wiped so user can retry immediately
        self.assertFalse(IdempotencyRecord.objects.filter(key=key).exists())


class OutboxAndAuditModelsTests(TestCase):
    def test_outbox_message_creation(self):
        """Verify OutboxMessage persistence with atomic pending state."""
        tenant_id = uuid.uuid4()
        msg = OutboxMessage.objects.create(
            tenant_id=tenant_id,
            topic="communications.customer_ack",
            payload={"complaint_id": "c-100", "reference": "TST-1044"}
        )
        self.assertEqual(msg.status, OutboxMessage.Status.PENDING)
        self.assertEqual(msg.retry_count, 0)
        self.assertEqual(msg.topic, "communications.customer_ack")

    def test_audit_event_creation(self):
        """Verify AuditEvent logs user and tenant activity."""
        auth_service = DevAuthService()
        user = auth_service.get_or_create_persona("operator")
        event = AuditEvent.objects.create(
            tenant_id=user.tenant_id,
            user=user,
            action="COMPLAINT_ASSIGNED",
            entity_type="Complaint",
            entity_id="c-1001",
            details={"assigned_to": str(user.id)},
            ip_address="127.0.0.1"
        )
        self.assertIsNotNone(event.id)
        self.assertEqual(event.action, "COMPLAINT_ASSIGNED")
        self.assertEqual(event.user, user)


class ExceptionHandlerTests(TestCase):
    def test_validation_error_formatted_as_message(self):
        """Verify DRF validation errors format to {'message': '...' }."""
        exc = ValidationError({"email": ["Enter a valid email address."]})
        response = custom_exception_handler(exc, {})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"message": "email: Enter a valid email address."})

    def test_permission_denied_formatted_as_message(self):
        """Verify permission errors format to {'message': '...' }."""
        exc = PermissionDenied("You do not have access to this record.")
        response = custom_exception_handler(exc, {})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data, {"message": "You do not have access to this record."})


class IdempotencySecurityAndPermissionTests(TestCase):
    def setUp(self):
        self.auth_service = DevAuthService()
        self.tenant_a = self.auth_service.ensure_synthetic_tenant()
        self.user_a = self.auth_service.get_or_create_persona("operator")
        self.user_a.permissions_list = ["complaints.read", "complaints.record_outcome"]
        self.user_a.save()

        # Create Tenant B and User B for cross-tenant replay tests
        self.tenant_b = Tenant.objects.create(
            id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
            name="Second Bank",
            slug="second-bank"
        )
        self.user_b = User.objects.create(
            id=uuid.UUID("00000000-0000-0000-0000-000000000030"),
            username="user_b",
            tenant=self.tenant_b,
            email="user_b@secondbank.test"
        )
        self.factory = APIRequestFactory()

    def test_permission_revoked_after_original_request_rejects_replay(self):
        """
        Verify that replaying a completed request cannot bypass current permissions.
        If a user has permission during the original request, but it is subsequently revoked,
        the replay attempt is rejected with HTTP 403 Forbidden.
        """
        key = uuid.uuid4()

        class OutcomeView(IdempotentAPIViewMixin, APIView):
            permission_classes = [permissions.IsAuthenticated, RequirePermission("complaints.record_outcome")]

            def post(self, request):
                return Response({"outcome": "RECORDED"}, status=status.HTTP_201_CREATED)

        view = OutcomeView.as_view()

        # 1. First execution: user_a has 'complaints.record_outcome' -> succeeds (201)
        req1 = self.factory.post(
            "/api/v1/complaints/c-1/resolution",
            data=json.dumps({"outcome": "RECORDED"}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(key)
        )
        force_authenticate(req1, user=self.user_a)
        resp1 = view(req1)
        self.assertEqual(resp1.status_code, 201)
        self.assertEqual(resp1.data, {"outcome": "RECORDED"})

        # Verify record was marked completed
        record = IdempotencyRecord.objects.get(key=key)
        self.assertEqual(record.status, IdempotencyRecord.Status.COMPLETED)

        # 2. Revoke 'complaints.record_outcome' permission from user_a
        self.user_a.permissions_list = ["complaints.read"]
        self.user_a.save()

        # 3. Second execution (Replay with same key): permission check MUST block the replay
        req2 = self.factory.post(
            "/api/v1/complaints/c-1/resolution",
            data=json.dumps({"outcome": "RECORDED"}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(key)
        )
        force_authenticate(req2, user=self.user_a)
        resp2 = view(req2)

        # Must be rejected with 403 Forbidden!
        self.assertEqual(resp2.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("permission", resp2.data.get("message", "").lower())

    def test_cross_tenant_replay_attempt_rejected(self):
        """
        Verify that an idempotency key created by Tenant A cannot be replayed by Tenant B.
        Cross-tenant replay attempts must be rejected with HTTP 403 Forbidden.
        """
        key = uuid.uuid4()

        # Tenant A completes an idempotent operation
        req_a = self.factory.post(
            "/api/v1/complaints/c-1/notes",
            data=json.dumps({"text": "Confidential Tenant A note"}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(key)
        )
        req_a.user = self.user_a
        early_resp, record = IdempotencyService.start_or_replay_operation(req_a, key)
        self.assertIsNone(early_resp)
        self.assertIsNotNone(record)

        # Complete Tenant A operation
        dummy_resp = JsonResponse({"note_id": "note_a_1"}, status=201)
        IdempotencyService.complete_operation(record, dummy_resp)

        # Tenant B user tries to replay Tenant A's idempotency key
        req_b = self.factory.post(
            "/api/v1/complaints/c-1/notes",
            data=json.dumps({"text": "Confidential Tenant A note"}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(key)
        )
        req_b.user = self.user_b
        resp_b, _ = IdempotencyService.start_or_replay_operation(req_b, key)

        self.assertIsNotNone(resp_b)
        self.assertEqual(resp_b.status_code, 403)
        self.assertIn("tenant mismatch", resp_b.content.decode().lower())

    def test_different_request_payload_using_same_key_rejected(self):
        """
        Verify that reusing an existing idempotency key with a different request payload
        is rejected with HTTP 422 Unprocessable Entity.
        """
        key = uuid.uuid4()
        req1 = self.factory.post(
            "/api/v1/complaints/c-1/notes",
            data=json.dumps({"text": "Original payload"}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(key)
        )
        req1.user = self.user_a
        _, record = IdempotencyService.start_or_replay_operation(req1, key)
        IdempotencyService.complete_operation(record, JsonResponse({"created": True}, status=201))

        # Reusing same key with altered payload
        req2 = self.factory.post(
            "/api/v1/complaints/c-1/notes",
            data=json.dumps({"text": "Tampered payload"}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(key)
        )
        req2.user = self.user_a
        resp2, _ = IdempotencyService.start_or_replay_operation(req2, key)

        self.assertIsNotNone(resp2)
        self.assertEqual(resp2.status_code, 422)
        self.assertIn("payload mismatch", resp2.content.decode().lower())

    def test_duplicate_concurrent_requests_returns_409(self):
        """
        Verify that an incoming request whose key is currently in PENDING status
        returns HTTP 409 Conflict.
        """
        key = uuid.uuid4()
        req1 = self.factory.post(
            "/api/v1/complaints/c-1/notes",
            data=json.dumps({"text": "In flight"}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(key)
        )
        req1.user = self.user_a
        _, record = IdempotencyService.start_or_replay_operation(req1, key)
        self.assertEqual(record.status, IdempotencyRecord.Status.PENDING)

        # Concurrent request with same key
        req2 = self.factory.post(
            "/api/v1/complaints/c-1/notes",
            data=json.dumps({"text": "In flight"}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(key)
        )
        req2.user = self.user_a
        resp2, _ = IdempotencyService.start_or_replay_operation(req2, key)

        self.assertIsNotNone(resp2)
        self.assertEqual(resp2.status_code, 409)
        self.assertIn("currently being processed", resp2.content.decode().lower())

    def test_pending_operation_recovery_after_crash(self):
        """
        Verify that if an operation remained in PENDING status due to an unhandled
        worker crash (> PENDING_TIMEOUT_SECONDS ago), a subsequent retry recovers
        the lock and allows the operation to proceed.
        """
        key = uuid.uuid4()
        crashed_time = timezone.now() - timedelta(minutes=10)

        # Simulate orphaned lock from crashed process
        record = IdempotencyRecord.objects.create(
            key=key,
            tenant_id=self.tenant_a.id,
            user=self.user_a,
            request_path="/api/v1/complaints/c-1/notes",
            request_hash=IdempotencyService.compute_payload_hash(
                self.factory.post("/api/v1/complaints/c-1/notes", data=json.dumps({"text": "Retry after crash"}), content_type="application/json")
            ),
            status=IdempotencyRecord.Status.PENDING
        )
        # Update created_at to past timestamp
        IdempotencyRecord.objects.filter(key=key).update(created_at=crashed_time)

        # Retry request
        req_retry = self.factory.post(
            "/api/v1/complaints/c-1/notes",
            data=json.dumps({"text": "Retry after crash"}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(key)
        )
        req_retry.user = self.user_a

        early_resp, recovered_record = IdempotencyService.start_or_replay_operation(req_retry, key)
        # Must NOT return 409 Conflict; must recover and allow operation to proceed
        self.assertIsNone(early_resp)
        self.assertIsNotNone(recovered_record)
        self.assertEqual(recovered_record.key, key)

