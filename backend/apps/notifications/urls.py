from django.urls import path
from .views import (
    NotificationListView,
    NotificationMarkReadView,
    NotificationMarkAllReadView,
    NotificationPreferencesView,
)

urlpatterns = [
    path("notifications", NotificationListView.as_view(), name="notification-list"),
    path("notifications/<uuid:pk>/read", NotificationMarkReadView.as_view(), name="notification-mark-read"),
    path("notifications/read-all", NotificationMarkAllReadView.as_view(), name="notification-mark-all-read"),
    path("me/notification-preferences", NotificationPreferencesView.as_view(), name="notification-preferences"),
]
