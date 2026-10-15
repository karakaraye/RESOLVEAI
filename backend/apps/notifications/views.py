from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification, NotificationPreference
from .serializers import NotificationItemSerializer, NotificationPreferenceSerializer


class NotificationListView(APIView):
    """
    GET /api/v1/notifications
    Paginated notification list with unread counter.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        qs = Notification.objects.filter(recipient=user).select_related("complaint")

        unread_filter = request.query_params.get("unread")
        if unread_filter in ("true", "1", "True"):
            qs = qs.filter(read=False)

        total = qs.count()
        unread_count = Notification.objects.filter(recipient=user, read=False).count()

        page = max(1, int(request.query_params.get("page", 1)))
        page_size = max(1, min(100, int(request.query_params.get("pageSize", 25))))
        offset = (page - 1) * page_size

        items = list(qs[offset : offset + page_size])
        serializer = NotificationItemSerializer(items, many=True)

        return Response({
            "items": serializer.data,
            "total": total,
            "page": page,
            "pageSize": page_size,
            "unreadCount": unread_count,
        })


class NotificationMarkReadView(APIView):
    """
    POST /api/v1/notifications/{id}/read
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        Notification.objects.filter(id=pk, recipient=request.user).update(read=True)
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationMarkAllReadView(APIView):
    """
    POST /api/v1/notifications/read-all
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Notification.objects.filter(recipient=request.user, read=False).update(read=True)
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationPreferencesView(APIView):
    """
    GET /api/v1/me/notification-preferences
    PUT /api/v1/me/notification-preferences
    """
    permission_classes = [IsAuthenticated]

    DEFAULT_PREFERENCES = [
        {"key": "assigned", "label": "Case assignments", "description": "Alert when a case is assigned to you"},
        {"key": "responses", "label": "Team responses", "description": "Alert when a receiving team replies to a handoff"},
        {"key": "deadlines", "label": "Approaching deadlines", "description": "Alert 4 hours before SLA expiration"},
        {"key": "overdue", "label": "Overdue cases", "description": "Alert when a handoff or follow-up deadline is breached"},
    ]

    def _ensure_defaults(self, user):
        existing = {p.key: p for p in NotificationPreference.objects.filter(user=user)}
        to_create = []
        for default in self.DEFAULT_PREFERENCES:
            if default["key"] not in existing:
                to_create.append(NotificationPreference(
                    user=user,
                    key=default["key"],
                    label=default["label"],
                    description=default["description"],
                    enabled=True
                ))
        if to_create:
            NotificationPreference.objects.bulk_create(to_create)

    def get(self, request):
        self._ensure_defaults(request.user)
        prefs = NotificationPreference.objects.filter(user=request.user).order_by("key")
        serializer = NotificationPreferenceSerializer(prefs, many=True)
        return Response(serializer.data)

    def put(self, request):
        self._ensure_defaults(request.user)
        updates = request.data if isinstance(request.data, list) else []
        for item in updates:
            key = item.get("key")
            enabled = item.get("enabled", True)
            if key:
                NotificationPreference.objects.filter(user=request.user, key=key).update(enabled=bool(enabled))

        prefs = NotificationPreference.objects.filter(user=request.user).order_by("key")
        serializer = NotificationPreferenceSerializer(prefs, many=True)
        return Response(serializer.data)
