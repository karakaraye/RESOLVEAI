import uuid
from datetime import timedelta
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasTenantAccess, RequirePermission
from apps.accounts.models import User
from apps.common.services import IdempotentAPIViewMixin
from apps.tenants.models import Tenant
from .models import Complaint, ComplaintCategory
from .serializers import (
    CategorySerializer,
    ComplaintSummarySerializer,
    ComplaintDetailSerializer,
)
from .services import (
    ComplaintWorkflowService,
    ComplaintIngestionService,
    WorkspaceSummaryService,
)


class CategoriesReferenceView(APIView):
    """
    Returns reference list of categories available for complaint classification.
    """
    permission_classes = [HasTenantAccess]

    def get(self, request):
        tenant = request.user.tenant
        categories = ComplaintCategory.objects.filter(
            Q(tenant=tenant) | Q(tenant__isnull=True),
            is_active=True
        ).order_by("label")
        serializer = CategorySerializer(categories, many=True)
        return Response(serializer.data)


class ComplaintListView(APIView):
    """
    Paginated search and filter endpoint for complaints.
    GET /api/v1/complaints
    """
    permission_classes = [HasTenantAccess, RequirePermission("complaints.read")]

    def get(self, request):
        tenant = request.user.tenant
        user = request.user

        qs = Complaint.objects.filter(tenant=tenant).select_related(
            "category", "assigned_operator", "customer", "source_data_source"
        )

        scope = request.query_params.get("scope", "all")
        if scope == "mine":
            qs = qs.filter(assigned_operator=user)

        # Keyword search
        q = request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(reference__icontains=q)
                | Q(customer_reference__icontains=q)
                | Q(customer__first_name__icontains=q)
                | Q(customer__last_name__icontains=q)
                | Q(summary__icontains=q)
                | Q(narrative__icontains=q)
            )

        # Status filter
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        # Priority filter
        priority_filter = request.query_params.get("priority")
        if priority_filter:
            qs = qs.filter(priority=priority_filter)

        # Category filter
        category_code = request.query_params.get("category")
        if category_code:
            qs = qs.filter(category__code=category_code)

        now = timezone.now()

        # Due date filter
        due_filter = request.query_params.get("due")
        if due_filter == "overdue":
            qs = qs.filter(due_at__lt=now).exclude(status=Complaint.Status.RESOLVED)
        elif due_filter == "today":
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)
            qs = qs.filter(due_at__range=(today_start, today_end)).exclude(status=Complaint.Status.RESOLVED)
        elif due_filter == "soon":
            qs = qs.filter(due_at__range=(now, now + timedelta(hours=24))).exclude(status=Complaint.Status.RESOLVED)
        elif due_filter == "week":
            qs = qs.filter(due_at__range=(now, now + timedelta(days=7))).exclude(status=Complaint.Status.RESOLVED)
        elif due_filter == "none":
            qs = qs.filter(due_at__isnull=True)

        # Received date filter
        received_filter = request.query_params.get("received")
        if received_filter == "today":
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            qs = qs.filter(received_at__gte=today_start)
        elif received_filter == "7d":
            qs = qs.filter(received_at__gte=now - timedelta(days=7))
        elif received_filter == "30d":
            qs = qs.filter(received_at__gte=now - timedelta(days=30))
        elif received_filter == "90d":
            qs = qs.filter(received_at__gte=now - timedelta(days=90))

        # Pagination
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except ValueError:
            page = 1

        try:
            page_size = int(request.query_params.get("pageSize", 25))
            page_size = 50 if page_size == 50 else 25
        except ValueError:
            page_size = 25

        total = qs.count()
        start = (page - 1) * page_size
        items = qs[start : start + page_size]

        serializer = ComplaintSummarySerializer(items, many=True, context={"request": request})

        return Response({
            "items": serializer.data,
            "total": total,
            "page": page,
            "pageSize": page_size,
        })


class ComplaintDetailView(APIView):
    """
    Detailed complaint view with audit timeline, notes, and actions.
    GET /api/v1/complaints/{id}
    """
    permission_classes = [HasTenantAccess, RequirePermission("complaints.read")]

    def get(self, request, pk):
        tenant = request.user.tenant
        try:
            complaint = Complaint.objects.select_related(
                "category",
                "assigned_operator",
                "customer",
                "source_data_source",
                "resolution_reported_by",
                "resolution_verified_by"
            ).prefetch_related("notes", "timeline_events").get(
                id=pk,
                tenant=tenant
            )
        except (Complaint.DoesNotExist, ValueError):
            raise NotFound(detail=f"Complaint '{pk}' was not found.")

        serializer = ComplaintDetailSerializer(complaint, context={"request": request})
        return Response(serializer.data)


class ComplaintEligibleAssigneesView(APIView):
    """
    List operators and leads eligible to be assigned to this case.
    GET /api/v1/complaints/{id}/eligible-assignees
    """
    permission_classes = [HasTenantAccess, RequirePermission("complaints.read")]

    def get(self, request, pk):
        tenant = request.user.tenant
        # Eligible assignees belong to the same tenant and have complaint permissions
        users = User.objects.filter(tenant=tenant, is_active=True).order_by("first_name", "last_name")

        assignees = []
        for u in users:
            if u.has_case_permission("complaints.read") or u.has_case_permission("complaints.assign"):
                open_cases = Complaint.objects.filter(
                    tenant=tenant,
                    assigned_operator=u
                ).exclude(
                    status=Complaint.Status.RESOLVED
                ).count()

                assignees.append({
                    "id": str(u.id),
                    "displayName": u.display_name,
                    "team": u.department or "Operations",
                    "openCases": open_cases,
                })

        return Response(assignees)


class ComplaintAssignmentView(APIView):
    """
    Assign an operator to a complaint.
    POST /api/v1/complaints/{id}/assignment
    """
    permission_classes = [HasTenantAccess, RequirePermission("complaints.assign")]

    def post(self, request, pk):
        tenant = request.user.tenant
        try:
            complaint = Complaint.objects.get(id=pk, tenant=tenant)
        except (Complaint.DoesNotExist, ValueError):
            raise NotFound(detail=f"Complaint '{pk}' was not found.")

        assignee_id = request.data.get("assigneeId")
        if not assignee_id:
            raise ValidationError({"assigneeId": "Assignee ID is required."})

        reason = request.data.get("reason", "")
        ComplaintWorkflowService.assign_operator(complaint, request.user, assignee_id, reason)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ComplaintNotesView(APIView):
    """
    Add confidential internal note to a complaint.
    POST /api/v1/complaints/{id}/notes
    """
    permission_classes = [HasTenantAccess, RequirePermission("complaints.notes")]

    def post(self, request, pk):
        tenant = request.user.tenant
        try:
            complaint = Complaint.objects.get(id=pk, tenant=tenant)
        except (Complaint.DoesNotExist, ValueError):
            raise NotFound(detail=f"Complaint '{pk}' was not found.")

        text = request.data.get("text", "").strip()
        if not text:
            raise ValidationError({"text": "Note text is required."})

        ComplaintWorkflowService.add_note(complaint, request.user, text)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ComplaintFollowUpsView(APIView):
    """
    Set a follow-up schedule on a complaint.
    POST /api/v1/complaints/{id}/follow-ups
    """
    permission_classes = [HasTenantAccess, RequirePermission("complaints.follow_up")]

    def post(self, request, pk):
        tenant = request.user.tenant
        try:
            complaint = Complaint.objects.get(id=pk, tenant=tenant)
        except (Complaint.DoesNotExist, ValueError):
            raise NotFound(detail=f"Complaint '{pk}' was not found.")

        due_at_str = request.data.get("dueAt")
        reason = request.data.get("reason", "").strip()

        if not due_at_str or not reason:
            raise ValidationError("Both dueAt and reason are required.")

        try:
            due_at = timezone.datetime.fromisoformat(due_at_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            raise ValidationError({"dueAt": "Invalid ISO datetime string for dueAt."})

        ComplaintWorkflowService.set_follow_up(complaint, request.user, due_at, reason)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ComplaintResolutionView(APIView):
    """
    Record an outcome on a complaint (transitions to Awaiting Verification).
    POST /api/v1/complaints/{id}/resolution
    """
    permission_classes = [HasTenantAccess, RequirePermission("complaints.record_outcome")]

    def post(self, request, pk):
        tenant = request.user.tenant
        try:
            complaint = Complaint.objects.get(id=pk, tenant=tenant)
        except (Complaint.DoesNotExist, ValueError):
            raise NotFound(detail=f"Complaint '{pk}' was not found.")

        outcome = request.data.get("outcome", "").strip()
        evidence = request.data.get("evidence", "").strip()

        if not outcome:
            raise ValidationError({"outcome": "Reported outcome description is required."})

        ComplaintWorkflowService.record_outcome(complaint, request.user, outcome, evidence)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ComplaintVerificationView(APIView):
    """
    Maker-checker verification of reported complaint outcome.
    POST /api/v1/complaints/{id}/resolution/verification
    """
    permission_classes = [HasTenantAccess, RequirePermission("complaints.verify_outcome")]

    def post(self, request, pk):
        tenant = request.user.tenant
        try:
            complaint = Complaint.objects.get(id=pk, tenant=tenant)
        except (Complaint.DoesNotExist, ValueError):
            raise NotFound(detail=f"Complaint '{pk}' was not found.")

        decision = request.data.get("decision")
        note = request.data.get("note", "").strip()

        if decision not in ("VERIFY", "REJECT"):
            raise ValidationError({"decision": "Decision must be 'VERIFY' or 'REJECT'."})

        if decision == "REJECT" and not note:
            raise ValidationError({"note": "Reason is required when rejecting an outcome."})

        ComplaintWorkflowService.verify_outcome(complaint, request.user, decision, note)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ComplaintReopenView(APIView):
    """
    Reopen a previously resolved complaint.
    POST /api/v1/complaints/{id}/reopen
    """
    permission_classes = [HasTenantAccess, RequirePermission("complaints.reopen")]

    def post(self, request, pk):
        tenant = request.user.tenant
        try:
            complaint = Complaint.objects.get(id=pk, tenant=tenant)
        except (Complaint.DoesNotExist, ValueError):
            raise NotFound(detail=f"Complaint '{pk}' was not found.")

        reason = request.data.get("reason", "").strip()
        if not reason:
            raise ValidationError({"reason": "Reopen reason is required."})

        ComplaintWorkflowService.reopen_complaint(complaint, request.user, reason)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ComplaintForwardingOptionsView(APIView):
    """
    Returns eligible receiving teams, suggested destination, and shareable preview.
    GET /api/v1/complaints/{id}/forwarding-options
    """
    permission_classes = [HasTenantAccess, RequirePermission("complaints.forward")]

    def get(self, request, pk):
        tenant = request.user.tenant
        try:
            complaint = Complaint.objects.get(id=pk, tenant=tenant)
        except (Complaint.DoesNotExist, ValueError):
            raise NotFound(detail=f"Complaint '{pk}' was not found.")

        from apps.handoffs.services import HandoffService
        from apps.handoffs.serializers import ForwardingOptionsSerializer

        options = HandoffService.get_forwarding_options(complaint, request.user)
        serializer = ForwardingOptionsSerializer(options)
        return Response(serializer.data, status=status.HTTP_200_OK)


class WorkspaceSummaryView(APIView):
    """
    Dashboard metrics and next action items for Home and My Cases views.
    GET /api/v1/workspace/summary
    """
    permission_classes = [HasTenantAccess]

    def get(self, request):
        tenant = request.user.tenant
        scope = request.query_params.get("scope", "all")
        summary = WorkspaceSummaryService.get_summary(tenant, request.user, scope=scope)
        return Response(summary)


class IngestionEventsView(APIView):
    """
    Idempotent complaint ingestion webhook endpoint for simulated banking channels.
    Allows external customer portals, webhooks, and simulated channels to ingest events.
    POST /api/v1/ingestion/events
    """
    permission_classes = [AllowAny]

    def post(self, request):
        if request.user and request.user.is_authenticated and hasattr(request.user, "tenant") and request.user.tenant:
            tenant = request.user.tenant
        else:
            tenant = Tenant.objects.filter(is_active=True).first()

        if not tenant:
            return Response({"error": "No active tenant configured"}, status=status.HTTP_400_BAD_REQUEST)

        event_id = request.data.get("eventId") or request.data.get("external_event_id") or str(uuid.uuid4())
        complaint, created = ComplaintIngestionService.ingest_event(tenant, event_id, request.data)

        return Response(
            {
                "complaintId": str(complaint.id),
                "reference": complaint.reference,
                "created": created,
                "status": complaint.status,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )
