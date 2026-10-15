import logging
from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasTenantAccess, RequirePermission
from apps.common.services import IdempotentAPIViewMixin
from apps.complaints.models import Complaint
from .models import ForwardingHandoff
from .serializers import (
    ForwardingOptionsSerializer,
    HandoffCreateRequestSerializer,
    HandoffSerializer,
    HandoffSummarySerializer,
)
from .services import HandoffService

logger = logging.getLogger("resolveai.handoffs.views")


class ComplaintForwardingOptionsView(APIView):
    """
    GET /api/v1/complaints/{id}/forwarding-options
    Returns eligible receiving teams, suggested destination, and shareable preview.
    """
    permission_classes = [HasTenantAccess, RequirePermission("complaints.forward")]

    def get(self, request, pk):
        complaint = get_object_or_404(Complaint, id=pk, tenant=request.user.tenant)
        options = HandoffService.get_forwarding_options(complaint, request.user)
        serializer = ForwardingOptionsSerializer(options)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ComplaintHandoffCreateView(IdempotentAPIViewMixin, APIView):
    """
    POST /api/v1/complaints/{id}/handoffs
    Creates a new handoff record, validates destination, and dispatches background worker.
    """
    permission_classes = [HasTenantAccess, RequirePermission("complaints.forward")]

    def post(self, request, pk):
        complaint = get_object_or_404(Complaint, id=pk, tenant=request.user.tenant)

        req_serializer = HandoffCreateRequestSerializer(data=request.data)
        req_serializer.is_valid(raise_exception=True)
        data = req_serializer.validated_data

        handoff = HandoffService.create_handoff(
            complaint=complaint,
            user=request.user,
            team_id=data["teamId"],
            recipient=data.get("recipient", ""),
            message=data.get("message", ""),
        )

        resp_serializer = HandoffSerializer(handoff)
        return Response(resp_serializer.data, status=status.HTTP_200_OK)


class HandoffListView(APIView):
    """
    GET /api/v1/handoffs
    Search, filter, and paginate cross-team handoffs across the tenant.
    """
    permission_classes = [HasTenantAccess, RequirePermission("complaints.read")]

    def get(self, request):
        tenant = request.user.tenant
        qs = ForwardingHandoff.objects.filter(tenant=tenant).select_related(
            "team", "complaint", "response"
        ).prefetch_related("attempts").order_by("-created_at")

        # 1. State filter
        state_filter = request.query_params.get("state")
        if state_filter:
            qs = qs.filter(state=state_filter)

        # 2. Search query (reference, customer, team name, recipient)
        q = request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(complaint__reference__icontains=q)
                | Q(complaint__customer_reference__icontains=q)
                | Q(complaint__summary__icontains=q)
                | Q(team__name__icontains=q)
                | Q(recipient__icontains=q)
            )

        total = qs.count()
        page = max(1, int(request.query_params.get("page", 1)))
        page_size = max(1, min(100, int(request.query_params.get("pageSize", 25))))
        offset = (page - 1) * page_size

        items = list(qs[offset : offset + page_size])
        serializer = HandoffSummarySerializer(items, many=True)

        return Response({
            "items": serializer.data,
            "total": total,
            "page": page,
            "pageSize": page_size,
        }, status=status.HTTP_200_OK)


class HandoffSummaryCountsView(APIView):
    """
    GET /api/v1/handoffs/summary
    Workload aggregate metrics for the Forwarded view header strip.
    """
    permission_classes = [HasTenantAccess, RequirePermission("complaints.read")]

    def get(self, request):
        tenant = request.user.tenant
        qs = ForwardingHandoff.objects.filter(tenant=tenant)

        total = qs.count()
        awaiting = qs.filter(state__in=[
            ForwardingHandoff.State.SENT,
            ForwardingHandoff.State.DELIVERED,
            ForwardingHandoff.State.ACKNOWLEDGED,
            ForwardingHandoff.State.ACCEPTED,
            ForwardingHandoff.State.AWAITING_RESPONSE,
            ForwardingHandoff.State.DELIVERY_UNCONFIRMED,
        ]).count()
        responded = qs.filter(state__in=[
            ForwardingHandoff.State.RESPONDED,
            ForwardingHandoff.State.CLOSED,
        ]).count()
        overdue = qs.filter(state=ForwardingHandoff.State.OVERDUE).count()
        failed = qs.filter(state=ForwardingHandoff.State.SEND_FAILED).count()

        return Response({
            "total": total,
            "awaitingResponse": awaiting,
            "responded": responded,
            "overdue": overdue,
            "failed": failed,
        }, status=status.HTTP_200_OK)


class HandoffRetryView(IdempotentAPIViewMixin, APIView):
    """
    POST /api/v1/handoffs/{id}/retry
    Retries transmission of a failed or fallback handoff.
    """
    permission_classes = [HasTenantAccess, RequirePermission("complaints.forward")]

    def post(self, request, pk):
        handoff = get_object_or_404(ForwardingHandoff, id=pk, tenant=request.user.tenant)
        updated_handoff = HandoffService.retry_handoff(handoff, request.user)
        serializer = HandoffSerializer(updated_handoff)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OperationsHealthView(APIView):
    """
    GET /api/v1/operations/health
    Operational health check for background workers, database, and Redis broker.
    """
    permission_classes = [HasTenantAccess]

    def get(self, request):
        from apps.common.models import OutboxMessage
        from django.db import connection

        # 1. Database check
        db_ok = False
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                db_ok = bool(cursor.fetchone())
        except Exception:
            pass

        # 2. Redis broker check
        redis_ok = False
        try:
            import redis
            r = redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_timeout=2.0)
            redis_ok = bool(r.ping())
        except Exception as e:
            logger.warning(f"Redis health check failed: {e}")

        # 3. Pending outbox messages
        pending_outbox = OutboxMessage.objects.filter(status=OutboxMessage.Status.PENDING).count()

        # 4. Overdue handoffs
        overdue_handoffs = ForwardingHandoff.objects.filter(
            tenant=request.user.tenant,
            state=ForwardingHandoff.State.OVERDUE
        ).count()

        overall_healthy = db_ok and redis_ok

        return Response({
            "status": "HEALTHY" if overall_healthy else "DEGRADED",
            "database": "CONNECTED" if db_ok else "DISCONNECTED",
            "redisBroker": "CONNECTED" if redis_ok else "DISCONNECTED",
            "pendingOutboxCount": pending_outbox,
            "tenantOverdueHandoffs": overdue_handoffs,
        }, status=status.HTTP_200_OK if overall_healthy else status.HTTP_503_SERVICE_UNAVAILABLE)
