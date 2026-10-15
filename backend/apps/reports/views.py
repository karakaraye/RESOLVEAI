from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasTenantAccess, RequirePermission
from .services import ReportService


class ReportDetailView(APIView):
    """
    Operational reporting and aggregate analytics endpoint for BIIRS.
    GET /api/v1/reports/{report_type}?range=30d
    GET /api/v1/reports/{report_type}?range=custom&from=YYYY-MM-DD&to=YYYY-MM-DD
    """
    permission_classes = [HasTenantAccess, RequirePermission("reports.read")]

    def get(self, request, report_type):
        tenant = request.user.tenant
        range_code = request.query_params.get("range", "30d")
        from_str = request.query_params.get("from")
        to_str = request.query_params.get("to")

        data = ReportService.get_report(
            tenant=tenant,
            report_slug=report_type,
            range_code=range_code,
            from_str=from_str,
            to_str=to_str,
        )
        return Response(data, status=status.HTTP_200_OK)
