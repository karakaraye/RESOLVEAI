import hashlib
import json
import logging
import uuid
from datetime import timedelta
from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from .models import IdempotencyRecord

logger = logging.getLogger("resolveai.idempotency")

class IdempotencyService:
    """
    Core service managing database-backed idempotency records, payload hash verification,
    tenant isolation, concurrent execution locks, and crash recovery.
    """
    # Pending locks older than this timeout are treated as crashed/abandoned and recovered
    PENDING_TIMEOUT_SECONDS = 120

    @classmethod
    def compute_payload_hash(cls, request) -> str:
        body = request.body or b""
        return hashlib.sha256(body).hexdigest()

    @classmethod
    def start_or_replay_operation(
        cls,
        request,
        key: uuid.UUID
    ) -> tuple[JsonResponse | None, IdempotencyRecord | None]:
        """
        Evaluates an idempotency key AFTER authentication and permission checks have completed.

        Returns:
            (response, None): If the request short-circuits (replay or error).
            (None, record): If the request should proceed to the view handler.
        """
        request_hash = cls.compute_payload_hash(request)
        user = request.user if request.user.is_authenticated else None
        current_tenant_id = getattr(user, "tenant_id", None) or getattr(request, "tenant_id", None)

        record = IdempotencyRecord.objects.filter(key=key).first()

        if record:
            # 1. Endpoint scope check
            if record.request_path != request.path:
                logger.warning(
                    f"Scope mismatch for idempotency key {key}: {record.request_path} vs {request.path}"
                )
                return (
                    JsonResponse(
                        {"message": "Idempotency key scope mismatch. The key was used on a different endpoint."},
                        status=422
                    ),
                    None
                )

            # 2. Cross-tenant isolation check
            if record.tenant_id is not None and current_tenant_id is not None:
                if str(record.tenant_id) != str(current_tenant_id):
                    logger.warning(
                        f"Cross-tenant replay attempt for key {key}: record tenant {record.tenant_id} != caller tenant {current_tenant_id}"
                    )
                    return (
                        JsonResponse({"message": "Idempotency key tenant mismatch."}, status=403),
                        None
                    )

            # 3. User context check (cannot replay another user's key)
            if record.user is not None and user is not None:
                if record.user != user:
                    logger.warning(f"User context mismatch for idempotency key {key}")
                    return (
                        JsonResponse({"message": "Idempotency key authenticated context mismatch."}, status=403),
                        None
                    )

            # 4. Pending lock & crash recovery check (checked before payload check for in-flight requests)
            if record.status == IdempotencyRecord.Status.PENDING:
                now = timezone.now()
                elapsed = (now - record.created_at).total_seconds()
                if elapsed > cls.PENDING_TIMEOUT_SECONDS:
                    # Previous worker/process crashed while holding the pending lock; recover it
                    logger.warning(
                        f"Recovering crashed pending idempotency record {key} (held for {elapsed:.1f}s > {cls.PENDING_TIMEOUT_SECONDS}s)"
                    )
                    record.created_at = now
                    record.save(update_fields=["created_at"])
                    return (None, record)
                else:
                    logger.warning(f"Concurrent request detected for idempotency key {key}")
                    return (
                        JsonResponse(
                            {"message": "A request with this idempotency key is currently being processed."},
                            status=409
                        ),
                        None
                    )

            # 5. Payload tampering check on completed record
            if record.request_hash != request_hash:
                logger.warning(f"Payload mismatch for idempotency key {key}")
                return (
                    JsonResponse(
                        {"message": "Idempotency key payload mismatch. The payload differs from the initial request."},
                        status=422
                    ),
                    None
                )

            # 6. Replay cached response
            elif record.status == IdempotencyRecord.Status.COMPLETED:
                logger.info(f"Replaying cached response for idempotency key {key} to user {user}")
                response_data = record.response_body if record.response_body is not None else {}
                response = JsonResponse(response_data, status=record.response_status, safe=False)
                response["X-Cache-Lookup"] = "HIT-IDEMPOTENT"
                return (response, None)

        # 7. Create new pending record
        try:
            record = IdempotencyRecord.objects.create(
                key=key,
                tenant_id=current_tenant_id,
                user=user,
                request_path=request.path,
                request_hash=request_hash,
                status=IdempotencyRecord.Status.PENDING
            )
            return (None, record)
        except Exception as e:
            logger.error(f"Failed to record pending idempotency key {key}: {e}")
            return (None, None)

    @classmethod
    def complete_operation(cls, record: IdempotencyRecord | None, response) -> None:
        """
        Caches successful/deterministic responses (2xx / 4xx) upon completion.
        Cleans up pending locks on 5xx server errors so clients can safely retry.
        """
        if not record:
            return

        if response.status_code < 500:
            try:
                body_content = None
                if hasattr(response, "data") and response.data is not None:
                    body_content = response.data
                elif getattr(response, "content", None):
                    try:
                        body_content = json.loads(response.content.decode("utf-8"))
                    except Exception:
                        body_content = None

                IdempotencyRecord.objects.filter(key=record.key).update(
                    status=IdempotencyRecord.Status.COMPLETED,
                    response_status=response.status_code,
                    response_body=body_content
                )
            except Exception as e:
                logger.error(f"Failed to update completed idempotency record {record.key}: {e}")
        else:
            # Delete pending record on server errors for safe retry
            IdempotencyRecord.objects.filter(key=record.key).delete()

    @classmethod
    def fail_operation(cls, record: IdempotencyRecord | None) -> None:
        """
        Cleans up in-flight locks when an unhandled exception or crash occurs.
        """
        if record:
            logger.warning(f"Abrupt failure during request {record.key}: clearing pending lock for recovery.")
            IdempotencyRecord.objects.filter(key=record.key).delete()


class IdempotentAPIViewMixin:
    """
    DRF APIView Mixin that evaluates idempotency in the view layer AFTER authentication,
    tenant scoping, and fine-grained permissions have passed.
    """
    def dispatch(self, request, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        request = self.initialize_request(request, *args, **kwargs)
        self.request = request
        self.headers = self.default_response_headers

        try:
            # 1. DRF initial() executes perform_authentication, check_permissions, and check_throttles
            self.initial(request, *args, **kwargs)

            # Only mutating methods use idempotency keys
            if request.method not in ("POST", "PUT", "PATCH"):
                handler = getattr(self, request.method.lower(), self.http_method_not_allowed)
                response = handler(request, *args, **kwargs)
                self.response = self.finalize_response(request, response, *args, **kwargs)
                return self.response

            key_str = request.headers.get("Idempotency-Key")
            if not key_str:
                handler = getattr(self, request.method.lower(), self.http_method_not_allowed)
                response = handler(request, *args, **kwargs)
                self.response = self.finalize_response(request, response, *args, **kwargs)
                return self.response

            try:
                key = uuid.UUID(key_str)
            except (ValueError, TypeError):
                return JsonResponse({"message": "Invalid Idempotency-Key format. Expected UUIDv4."}, status=400)

            # 2. Idempotency evaluation occurs AFTER check_permissions() has passed!
            early_response, record = IdempotencyService.start_or_replay_operation(request, key)
            if early_response is not None:
                return early_response

            try:
                handler = getattr(self, request.method.lower(), self.http_method_not_allowed)
                response = handler(request, *args, **kwargs)
                final_response = self.finalize_response(request, response, *args, **kwargs)
                IdempotencyService.complete_operation(record, final_response)
                return final_response
            except Exception:
                IdempotencyService.fail_operation(record)
                raise

        except Exception as exc:
            response = self.handle_exception(exc)
            self.response = self.finalize_response(request, response, *args, **kwargs)
            return self.response
