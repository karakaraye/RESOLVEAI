from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.tenants.urls")),
    path("api/v1/", include("apps.complaints.urls")),
    path("api/v1/", include("apps.transactions.urls")),
    path("api/v1/", include("apps.evidence.urls")),
    path("api/v1/", include("apps.intelligence.urls")),
    path("api/v1/", include("apps.incidents.urls")),
    path("api/v1/", include("apps.handoffs.urls")),
    path("api/v1/", include("apps.notifications.urls")),
    path("api/v1/", include("apps.communications.urls")),
    path("api/v1/", include("apps.reports.urls")),
]
