import logging
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.complaints.models import Complaint
from .models import EvidenceRecord
from .serializers import EvidenceRecordSerializer
from .services import EvidenceManagementService

logger = logging.getLogger("resolveai.evidence")


class HasTenantAccess(permissions.BasePermission):
    """Enforces authentication and tenant isolation."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.tenant)


class ComplaintEvidenceListView(APIView):
    """
    GET /api/v1/complaints/{complaint_id}/evidence
    Lists all authoritative evidence documents attached to the complaint.
    """
    permission_classes = [HasTenantAccess]

    def get(self, request, complaint_id):
        if not request.user.has_case_permission("complaints.read") and not request.user.has_case_permission("evidence.read"):
            return Response({"message": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        complaint = get_object_or_404(
            Complaint,
            id=complaint_id,
            tenant=request.user.tenant,
        )

        evidence_list = complaint.evidence_records.all().order_by("-source_timestamp", "-created_at")
        serializer = EvidenceRecordSerializer(evidence_list, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ComplaintEvidenceCreateView(APIView):
    """
    POST /api/v1/complaints/{complaint_id}/evidence
    Attaches an authoritative evidence document (e.g. core ledger snapshot, reversal slip) to the case.
    """
    permission_classes = [HasTenantAccess]

    def post(self, request, complaint_id):
        if not request.user.has_case_permission("evidence.create") and not request.user.has_case_permission("complaints.notes"):
            return Response({"message": "Permission denied to attach evidence."}, status=status.HTTP_403_FORBIDDEN)

        complaint = get_object_or_404(
            Complaint,
            id=complaint_id,
            tenant=request.user.tenant,
        )

        try:
            evidence = EvidenceManagementService.attach_evidence(
                complaint=complaint,
                evidence_data=request.data,
                user=request.user,
            )
        except ValidationError as e:
            msg = e.messages[0] if hasattr(e, "messages") else str(e)
            return Response({"message": msg}, status=status.HTTP_400_BAD_REQUEST)

        serializer = EvidenceRecordSerializer(evidence)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class EvidenceVerifyView(APIView):
    """
    POST /api/v1/evidence/{evidence_id}/verify
    Verifies the authenticity of an evidence document (Maker-Checker / Compliance role).
    """
    permission_classes = [HasTenantAccess]

    def post(self, request, evidence_id):
        if not request.user.has_case_permission("evidence.verify"):
            return Response({"message": "Permission denied to verify evidence records."}, status=status.HTTP_403_FORBIDDEN)

        is_verified = request.data.get("isVerified", True)
        if isinstance(is_verified, str):
            is_verified = is_verified.lower() in ("true", "1")

        evidence = EvidenceManagementService.verify_evidence(
            evidence_id=evidence_id,
            tenant=request.user.tenant,
            user=request.user,
            is_verified=bool(is_verified),
        )

        serializer = EvidenceRecordSerializer(evidence)
        return Response(serializer.data, status=status.HTTP_200_OK)
