from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.services import DevAuthService
from apps.notifications.models import Notification, NotificationPreference


class NotificationAPITests(TestCase):
    """
    Tests for in-app operations notifications and preferences endpoints.
    """

    def setUp(self):
        self.dev_auth = DevAuthService()
        self.tenant = self.dev_auth.ensure_synthetic_tenant()
        self.operator = self.dev_auth.get_or_create_persona("operator")
        self.verifier = self.dev_auth.get_or_create_persona("verifier")

        # Create notifications
        self.n1 = Notification.objects.create(
            tenant=self.tenant,
            recipient=self.operator,
            kind=Notification.Kind.DEADLINE,
            title="Deadline approaching for CMP-2026-0001",
            read=False,
        )
        self.n2 = Notification.objects.create(
            tenant=self.tenant,
            recipient=self.operator,
            kind=Notification.Kind.RESPONSE,
            title="Response received from Settlements team",
            read=False,
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.operator)

    def test_notification_list_and_unread_count(self):
        """GET /api/v1/notifications returns unreadCount and items."""
        response = self.client.get("/api/v1/notifications?unread=true")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["unreadCount"], 2)
        self.assertEqual(len(response.data["items"]), 2)

    def test_notification_mark_single_read(self):
        """POST /api/v1/notifications/{id}/read marks notification as read."""
        response = self.client.post(
            f"/api/v1/notifications/{self.n1.id}/read",
            HTTP_X_BIIRS_REQUEST="1",
        )
        self.assertEqual(response.status_code, 204)

        self.n1.refresh_from_db()
        self.assertTrue(self.n1.read)

    def test_notification_mark_all_read(self):
        """POST /api/v1/notifications/read-all marks all notifications read."""
        response = self.client.post(
            "/api/v1/notifications/read-all",
            HTTP_X_BIIRS_REQUEST="1",
        )
        self.assertEqual(response.status_code, 204)

        unread = Notification.objects.filter(recipient=self.operator, read=False).count()
        self.assertEqual(unread, 0)

    def test_notification_preferences_get_and_put(self):
        """GET and PUT /api/v1/me/notification-preferences updates operator preferences."""
        resp_get = self.client.get("/api/v1/me/notification-preferences")
        self.assertEqual(resp_get.status_code, 200)
        self.assertGreaterEqual(len(resp_get.data), 4)

        # Update preference
        resp_put = self.client.put(
            "/api/v1/me/notification-preferences",
            [{"key": "deadlines", "enabled": False}],
            format="json",
            HTTP_X_BIIRS_REQUEST="1",
        )
        self.assertEqual(resp_put.status_code, 200)

        pref = NotificationPreference.objects.get(user=self.operator, key="deadlines")
        self.assertFalse(pref.enabled)
