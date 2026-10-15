import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class Notification(models.Model):
    """
    In-app alert delivered to bank operators and supervisors.
    """
    class Kind(models.TextChoices):
        ASSIGNED = "ASSIGNED", "Assigned"
        RESPONSE = "RESPONSE", "Response"
        DEADLINE = "DEADLINE", "Deadline"
        OVERDUE = "OVERDUE", "Overdue"
        REOPENED = "REOPENED", "Reopened"
        EXCEPTION = "EXCEPTION", "Exception"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="notifications"
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications"
    )
    kind = models.CharField(max_length=64, choices=Kind.choices, default=Kind.DEADLINE, db_index=True)
    title = models.CharField(max_length=255)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    read = models.BooleanField(default=False, db_index=True)
    complaint = models.ForeignKey(
        "complaints.Complaint",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications_notification"
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["recipient", "read", "occurred_at"], name="idx_notif_user_read_occ"),
        ]

    def __str__(self):
        return f"[{self.kind}] {self.title} -> {self.recipient}"


class NotificationPreference(models.Model):
    """
    User notification preferences for in-app alert categories.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences"
    )
    key = models.CharField(max_length=64)
    label = models.CharField(max_length=128)
    description = models.CharField(max_length=255)
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notifications_userpreference"
        verbose_name = "Notification Preference"
        verbose_name_plural = "Notification Preferences"
        unique_together = ("user", "key")

    def __str__(self):
        return f"{self.user}: {self.key} = {self.enabled}"
