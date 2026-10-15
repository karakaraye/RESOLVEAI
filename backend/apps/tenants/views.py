from rest_framework import generics, permissions
from .models import DataSource
from .serializers import DataSourceSerializer

class DataSourceListView(generics.ListAPIView):
    """
    GET /api/v1/data-sources
    Returns data sources array scoped strictly to the authenticated user's tenant.
    Unpaginated to match the frontend DataSource[] wire type.
    """
    serializer_class = DataSourceSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        user = self.request.user
        if not user.tenant_id:
            return DataSource.objects.none()
        return DataSource.objects.filter(tenant_id=user.tenant_id).order_by("name")
