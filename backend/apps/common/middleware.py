import hashlib
import json
import logging
import uuid
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from .models import IdempotencyRecord

logger = logging.getLogger("resolveai.security")

class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Applies security headers and enforces the custom X-BIIRS-Request anti-automation
    header on state-changing API endpoints.
    """
    EXEMPT_PATHS = [
        "/admin/",
        "/api/v1/auth/dev-login",
        "/api/v1/session/sign-in",
    ]

    def process_request(self, request):
        # Enforce on mutating API calls (/api/v1/)
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            path = request.path
            if path.startswith("/api/v1/"):
                for exempt in self.EXEMPT_PATHS:
                    if path.startswith(exempt):
                        return None

                biirs_header = request.headers.get("X-BIIRS-Request")
                if biirs_header != "1":
                    logger.warning(
                        f"Blocked state-changing request to {path} lacking X-BIIRS-Request header (IP: {request.META.get('REMOTE_ADDR')})"
                    )
                    return JsonResponse(
                        {"message": "State-changing requests must include the X-BIIRS-Request header."},
                        status=403
                    )
        return None

    def process_response(self, request, response):
        response["X-Content-Type-Options"] = "nosniff"
        response["X-Frame-Options"] = "DENY"
        response["Referrer-Policy"] = "same-origin"
        return response


from .services import IdempotencyService

logger = logging.getLogger("resolveai.security")


class IdempotencyMiddleware(MiddlewareMixin):
    """
    Database-backed idempotency protection for mutating requests.
    Inspects the Idempotency-Key header, delegates to IdempotencyService,
    and supports delegation to view-level mixins for fine-grained permission enforcement.
    """
    def process_request(self, request):
        if request.method not in ("POST", "PUT", "PATCH"):
            return None

        # Only process /api/v1/ endpoints
        if not request.path.startswith("/api/v1/"):
            return None

        key_str = request.headers.get("Idempotency-Key")
        if not key_str:
            return None

        try:
            key = uuid.UUID(key_str)
        except (ValueError, TypeError):
            return JsonResponse({"message": "Invalid Idempotency-Key format. Expected UUIDv4."}, status=400)

        # If a DRF view declares it handles idempotency after permission checks, bypass middleware replay
        if getattr(request, "_skip_middleware_idempotency", False):
            return None

        early_response, record = IdempotencyService.start_or_replay_operation(request, key)
        if early_response is not None:
            return early_response

        request._idempotency_record = record
        return None

    def process_response(self, request, response):
        record = getattr(request, "_idempotency_record", None)
        if record:
            IdempotencyService.complete_operation(record, response)
        return response

    def process_exception(self, request, exception):
        record = getattr(request, "_idempotency_record", None)
        if record:
            IdempotencyService.fail_operation(record)
        return None
