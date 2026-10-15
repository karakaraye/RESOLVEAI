from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Incident
from .serializers import IncidentDetailSerializer, IncidentSerializer
from .services import IncidentDetectionService, IncidentManagementService


class IncidentListView(APIView):
    """
    GET  /api/v1/incidents - List all incidents for the tenant.
    POST /api/v1/incidents - Manually create an incident candidate.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        incidents = Incident.objects.filter(
            tenant=request.user.tenant
        ).select_related("category").order_by("-created_at")

        status_param = request.query_params.get("status")
        if status_param:
            incidents = incidents.filter(status=status_param)

        serializer = IncidentSerializer(incidents, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        title = data.get("title", "").strip()
        summary = data.get("summary", "").strip()
        if not title:
            return Response({"error": "Title is required."}, status=status.HTTP_400_BAD_REQUEST)

        severity = data.get("severity", Incident.Severity.MODERATE)
        source_system = data.get("sourceSystem", "")
        complaint_ids = data.get("complaintIds", [])

        incident = IncidentManagementService.create_incident_candidate(
            tenant=request.user.tenant,
            title=title,
            summary=summary,
            severity=severity,
            source_system=source_system,
            complaint_ids=complaint_ids,
            user=request.user,
        )
        serializer = IncidentDetailSerializer(incident)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class IncidentDetailView(APIView):
    """
    GET /api/v1/incidents/{id} - Get complete incident detail.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk=None):
        incident = get_object_or_404(
            Incident.objects.prefetch_related("complaint_associations", "findings", "timeline_events"),
            id=pk,
            tenant=request.user.tenant
        )
        serializer = IncidentDetailSerializer(incident)
        return Response(serializer.data, status=status.HTTP_200_OK)


class IncidentConfirmView(APIView):
    """
    POST /api/v1/incidents/{id}/confirm - Confirm an incident candidate.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk=None):
        incident = get_object_or_404(Incident, id=pk, tenant=request.user.tenant)
        data = request.data
        confirmed = IncidentManagementService.confirm_incident(
            incident_id=str(incident.id),
            tenant=request.user.tenant,
            user=request.user,
            severity=data.get("severity"),
            title=data.get("title"),
            summary=data.get("summary"),
        )
        serializer = IncidentDetailSerializer(confirmed)
        return Response(serializer.data, status=status.HTTP_200_OK)


class IncidentComplaintLinkView(APIView):
    """
    POST /api/v1/incidents/{id}/complaints/link - Link a complaint to an incident.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk=None):
        incident = get_object_or_404(Incident, id=pk, tenant=request.user.tenant)
        complaint_id = request.data.get("complaintId")
        if not complaint_id:
            return Response({"error": "complaintId is required."}, status=status.HTTP_400_BAD_REQUEST)

        reason = request.data.get("reason", "Manually linked by operator")
        is_confirmed = request.data.get("isConfirmed", True)

        IncidentManagementService.link_complaint(
            incident_id=str(incident.id),
            complaint_id=complaint_id,
            tenant=request.user.tenant,
            user=request.user,
            reason=reason,
            is_confirmed=is_confirmed,
        )
        return Response({"status": "LINKED"}, status=status.HTTP_200_OK)


class IncidentComplaintUnlinkView(APIView):
    """
    POST /api/v1/incidents/{id}/complaints/unlink - Unlink a complaint from an incident.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk=None):
        incident = get_object_or_404(Incident, id=pk, tenant=request.user.tenant)
        complaint_id = request.data.get("complaintId")
        if not complaint_id:
            return Response({"error": "complaintId is required."}, status=status.HTTP_400_BAD_REQUEST)

        unlinked = IncidentManagementService.unlink_complaint(
            incident_id=str(incident.id),
            complaint_id=complaint_id,
            tenant=request.user.tenant,
            user=request.user,
        )
        return Response({"status": "UNLINKED", "success": unlinked}, status=status.HTTP_200_OK)


class IncidentDetectView(APIView):
    """
    POST /api/v1/incidents/detect - Run emerging incident detection rules for tenant.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        lookback = int(request.data.get("lookbackHours", 48))
        detected = IncidentDetectionService.detect_emerging_incidents(
            tenant=request.user.tenant,
            lookback_hours=lookback,
        )
        serializer = IncidentSerializer(detected, many=True)
        return Response({
            "detectedCount": len(detected),
            "incidents": serializer.data,
        }, status=status.HTTP_200_OK)
