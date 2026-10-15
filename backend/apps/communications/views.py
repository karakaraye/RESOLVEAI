import logging
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.complaints.models import Complaint
from .models import (
    CustomerCommunication,
    MessageTemplate,
    CommunicationPolicy,
)
from .serializers import (
    CustomerCommunicationSerializer,
    MessageTemplateSerializer,
    CommunicationPolicySerializer,
)
from .services import CustomerCommunicationService

logger = logging.getLogger("resolveai.communications.views")


class ComplaintCommunicationsListView(APIView):
    """
    GET /api/v1/complaints/{id}/communications
    Returns all customer-facing communications and delivery records for a specific complaint.
    Guarantees strict tenant isolation.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, complaint_id):
        tenant = getattr(request.user, "tenant", None)
        if not tenant:
            raise PermissionDenied("User is not associated with an institution.")

        try:
            complaint = Complaint.objects.get(id=complaint_id, tenant=tenant)
        except Complaint.DoesNotExist:
            raise NotFound("Complaint was not found.")

        comms = CustomerCommunication.objects.filter(
            complaint=complaint,
            tenant=tenant
        ).prefetch_related("delivery_attempts", "events").order_by("-created_at")

        serializer = CustomerCommunicationSerializer(comms, many=True)
        return Response({
            "complaintId": str(complaint.id),
            "reference": complaint.reference,
            "total": comms.count(),
            "items": serializer.data,
        })


class CommunicationComplianceReportView(APIView):
    """
    GET /api/v1/communications/compliance-report
    Task 10: Compliance & Audit Reporting.
    Provides tenant-scoped filters, date ranges, and privacy-minimised records for:
    1. ACKNOWLEDGEMENTS - Customer acknowledgement history
    2. RESOLUTIONS - Resolution notification history
    3. SLA_COMPLIANCE - SLA delay communications
    4. FAILURES - Failed or delayed communications
    5. VERIFICATION_LINKAGE - Resolution verification and communication linkage
    6. EXCEPTIONS - Overrides, cancellations, and suppressions
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        tenant = getattr(request.user, "tenant", None)
        if not tenant:
            raise PermissionDenied("User is not associated with an institution.")

        # Permission check: must have case read or report read permission
        if not (request.user.has_case_permission("complaints.read") or request.user.has_case_permission("reports.read")):
            raise PermissionDenied("You do not have permission to view communication audit reports.")

        report_type = request.query_params.get("report_type", "ACKNOWLEDGEMENTS").upper()
        from_date = request.query_params.get("from_date")
        to_date = request.query_params.get("to_date")
        channel = request.query_params.get("channel")
        comm_status = request.query_params.get("status")

        qs = CustomerCommunication.objects.filter(tenant=tenant).select_related(
            "complaint", "customer", "template"
        ).prefetch_related("delivery_attempts", "events")

        if from_date:
            qs = qs.filter(created_at__gte=from_date)
        if to_date:
            qs = qs.filter(created_at__lte=to_date)
        if channel:
            qs = qs.filter(channel=channel.upper())
        if comm_status:
            qs = qs.filter(status=comm_status.upper())

        # Filter by compliance report facet
        if report_type == "ACKNOWLEDGEMENTS":
            qs = qs.filter(category=MessageTemplate.Category.ACKNOWLEDGEMENT)
        elif report_type == "RESOLUTIONS":
            qs = qs.filter(category=MessageTemplate.Category.VERIFIED_RESOLUTION)
        elif report_type == "SLA_COMPLIANCE":
            qs = qs.filter(category__in=[
                MessageTemplate.Category.PROGRESS_UPDATE,
                MessageTemplate.Category.INVESTIGATION_DELAY,
                MessageTemplate.Category.ESCALATION_NOTICE,
            ])
        elif report_type == "FAILURES":
            qs = qs.filter(status__in=[
                CustomerCommunication.Status.FAILED,
                CustomerCommunication.Status.DELIVERY_UNCONFIRMED,
            ])
        elif report_type == "VERIFICATION_LINKAGE":
            qs = qs.filter(category=MessageTemplate.Category.VERIFIED_RESOLUTION).exclude(
                verification_reference=""
            )
        elif report_type == "EXCEPTIONS":
            qs = qs.filter(status=CustomerCommunication.Status.CANCELLED)

        qs = qs.order_by("-created_at")[:100]

        items = []
        for c in qs:
            # Privacy minimised recipient masking
            dest = c.recipient_destination or ""
            if "@" in dest:
                parts = dest.split("@")
                masked_dest = f"{parts[0][:1]}***@{parts[1]}"
            elif len(dest) >= 8:
                masked_dest = f"{dest[:4]}****{dest[-3:]}"
            else:
                masked_dest = "***"

            items.append({
                "id": str(c.id),
                "complaintReference": c.complaint.reference,
                "customerReference": c.customer.customer_number,
                "category": c.category,
                "channel": c.channel,
                "maskedDestination": masked_dest,
                "status": c.status,
                "triggerEvent": c.trigger_event,
                "verificationReference": c.verification_reference,
                "templateCode": c.template.code if c.template else "DEFAULT",
                "templateVersion": c.template_version,
                "provider": c.provider,
                "providerMessageId": c.provider_message_id,
                "retryCount": c.retry_count,
                "queuedAt": c.queued_at.isoformat() if c.queued_at else None,
                "deliveredAt": c.delivered_at.isoformat() if c.delivered_at else None,
                "cancelledAt": c.cancelled_at.isoformat() if c.cancelled_at else None,
                "cancellationReason": c.cancellation_reason,
                "errorMessage": c.error_message,
                "deliveryAttemptsCount": c.delivery_attempts.count(),
            })

        return Response({
            "tenant": tenant.name,
            "reportType": report_type,
            "totalCount": len(items),
            "generatedAt": timezone.now().isoformat(),
            "regulatoryNotice": "Internal communication compliance audit extract. Does not claim external regulatory certification.",
            "records": items,
        })


class MessageTemplateListView(APIView):
    """
    GET /api/v1/communications/templates
    Returns approved communication templates for the tenant.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        tenant = getattr(request.user, "tenant", None)
        if not tenant:
            raise PermissionDenied("User is not associated with an institution.")

        templates = MessageTemplate.objects.filter(
            Q(tenant=tenant) | Q(tenant__isnull=True),
            is_approved=True
        ).order_by("category", "channel", "-version")

        serializer = MessageTemplateSerializer(templates, many=True)
        return Response({
            "total": templates.count(),
            "items": serializer.data,
        })


class CustomerCommunicationRetryView(APIView):
    """
    POST /api/v1/communications/{id}/retry
    Allows authorised staff to retry a failed customer communication.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, communication_id):
        tenant = getattr(request.user, "tenant", None)
        if not tenant:
            raise PermissionDenied("User is not associated with an institution.")

        if not (request.user.has_case_permission("complaints.read") or request.user.has_case_permission("complaints.forward")):
            raise PermissionDenied("You do not have permission to retry communications.")

        try:
            comm = CustomerCommunication.objects.select_for_update().get(
                id=communication_id,
                tenant=tenant
            )
        except CustomerCommunication.DoesNotExist:
            raise NotFound("Communication was not found.")

        if comm.status not in (CustomerCommunication.Status.FAILED, CustomerCommunication.Status.DELIVERY_UNCONFIRMED):
            raise ValidationError(f"Cannot retry communication in state '{comm.status}'.")

        # Increment max_retries and re-queue
        comm.max_retries = comm.retry_count + 1
        comm.status = CustomerCommunication.Status.QUEUED
        comm.error_message = ""
        comm.save(update_fields=["max_retries", "status", "error_message", "updated_at"])

        # Import celery task
        from apps.communications.tasks import dispatch_customer_communication_task
        comm_id_str = str(comm.id)
        transaction.on_commit(lambda: dispatch_customer_communication_task.delay(comm_id_str))

        logger.info(f"Operator {request.user} requested manual retry for communication {comm.id}")
        return Response({
            "id": str(comm.id),
            "status": comm.status,
            "message": "Communication queued for retry dispatch.",
        })
