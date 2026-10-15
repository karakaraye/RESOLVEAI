from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health_check(request):
    return JsonResponse(
        {
            "status": "healthy",
            "service": "RESOLVEIQ API",
            "version": "1.0.0",
        }
    )


urlpatterns = [
    path("", health_check, name="root-health"),
    path("healthz", health_check, name="healthz"),
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

