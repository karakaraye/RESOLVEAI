import uuid
from django.conf import settings
from django.db import models

class IdempotencyRecord(models.Model):
    """
    Stores idempotency tokens and cached response payloads to prevent
    duplicate operations across network retries.
    """
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Completed"

    key = models.UUIDField(primary_key=True)
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="idempotency_records",
        null=True,
        blank=True
    )
    request_path = models.CharField(max_length=255)
    request_hash = models.CharField(max_length=64)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True
    )
    response_status = models.IntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "common_idempotencyrecord"
        verbose_name = "Idempotency Record"
        verbose_name_plural = "Idempotency Records"

    def __str__(self):
        return f"{self.key} [{self.status}] {self.request_path}"


class OutboxMessage(models.Model):
    """
    Transactional Outbox model to ensure state changes and event dispatch
    remain atomic within a single database transaction.
    """
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        PUBLISHED = "PUBLISHED", "Published"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    topic = models.CharField(max_length=128, db_index=True)
    payload = models.JSONField()
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True
    )
    retry_count = models.IntegerField(default=0)
    last_error = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "common_outboxmessage"
        verbose_name = "Outbox Message"
        verbose_name_plural = "Outbox Messages"
        indexes = [
            models.Index(fields=["status", "created_at"], name="idx_outbox_status_created"),
        ]

    def __str__(self):
        return f"{self.topic} [{self.status}] ({self.id})"


class AuditEvent(models.Model):
    """
    Append-only security and operational audit event stream.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events"
    )
    action = models.CharField(max_length=128, db_index=True)
    entity_type = models.CharField(max_length=64, db_index=True)
    entity_id = models.CharField(max_length=128, db_index=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "common_auditevent"
        verbose_name = "Audit Event"
        verbose_name_plural = "Audit Events"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.created_at}] {self.action} on {self.entity_type}:{self.entity_id}"
