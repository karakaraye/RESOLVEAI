import logging
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.complaints.models import Complaint
from .models import TransactionInvestigation
from .serializers import TransactionRecordSerializer
from .services import TransactionInvestigationService

logger = logging.getLogger("resolveai.transactions")


class HasTenantAccess(permissions.BasePermission):
    """Enforces authentication and tenant isolation."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.tenant)


class ComplaintTransactionsListView(APIView):
    """
    GET /api/v1/complaints/{complaint_id}/transactions
    Returns all transaction investigation records linked to the specified complaint.
    """
    permission_classes = [HasTenantAccess]

    def get(self, request, complaint_id):
        if not request.user.has_case_permission("complaints.read") and not request.user.has_case_permission("investigations.read"):
            return Response({"message": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        complaint = get_object_or_404(
            Complaint,
            id=complaint_id,
            tenant=request.user.tenant,
        )

        investigations = complaint.transaction_investigations.all().order_by("-occurred_at", "-created_at")
        serializer = TransactionRecordSerializer(investigations, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ComplaintTransactionSearchView(APIView):
    """
    POST /api/v1/complaints/{complaint_id}/transactions/search
    Triggers automated lookup against SimulatedBankAdapter and links matching transactions.
    """
    permission_classes = [HasTenantAccess]

    def post(self, request, complaint_id):
        if not request.user.has_case_permission("investigations.manage") and not request.user.has_case_permission("complaints.notes"):
            return Response({"message": "Permission denied to perform transaction investigations."}, status=status.HTTP_403_FORBIDDEN)

        complaint = get_object_or_404(
            Complaint,
            id=complaint_id,
            tenant=request.user.tenant,
        )

        linked = TransactionInvestigationService.search_and_link_from_bank_adapter(
            complaint=complaint,
            user=request.user,
        )

        serializer = TransactionRecordSerializer(linked, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ComplaintTransactionLinkView(APIView):
    """
    POST /api/v1/complaints/{complaint_id}/transactions
    Allows manual linking or updating of a specific transaction record.
    """
    permission_classes = [HasTenantAccess]

    def post(self, request, complaint_id):
        if not request.user.has_case_permission("investigations.manage") and not request.user.has_case_permission("complaints.notes"):
            return Response({"message": "Permission denied to link transactions."}, status=status.HTTP_403_FORBIDDEN)

        complaint = get_object_or_404(
            Complaint,
            id=complaint_id,
            tenant=request.user.tenant,
        )

        txn = TransactionInvestigationService.link_transaction(
            complaint=complaint,
            txn_data=request.data,
            user=request.user,
        )

        serializer = TransactionRecordSerializer(txn)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
