import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class Customer(models.Model):
    """
    Synthetic or synced bank customer entity, strictly scoped to a tenant.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="customers"
    )
    customer_number = models.CharField(max_length=64, db_index=True)
    first_name = models.CharField(max_length=128)
    last_name = models.CharField(max_length=128)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=32, blank=True, null=True)
    account_number = models.CharField(max_length=32, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "complaints_customer"
        verbose_name = "Customer"
        verbose_name_plural = "Customers"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "customer_number"],
                name="unique_tenant_customer_number"
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "customer_number"]),
            models.Index(fields=["tenant", "email"]),
            models.Index(fields=["tenant", "account_number"]),
        ]

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return f"{self.full_name} ({self.customer_number})"


class ComplaintCategory(models.Model):
    """
    Reference categories for classifying customer banking complaints.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="complaint_categories",
        null=True,
        blank=True
    )
    code = models.CharField(max_length=64, db_index=True)
    label = models.CharField(max_length=128)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "complaints_category"
        verbose_name = "Complaint Category"
        verbose_name_plural = "Complaint Categories"
        ordering = ["label"]

    def __str__(self):
        return f"{self.label} ({self.code})"


class SourceEvent(models.Model):
    """
    Raw incoming event records from banking channels to ensure
    idempotent ingestion and prevent duplicate case creations.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="source_events"
    )
    source_data_source = models.ForeignKey(
        "tenants.DataSource",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_events"
    )
    external_event_id = models.CharField(max_length=128, db_index=True)
    source_channel = models.CharField(max_length=64, default="Contact centre feed")
    payload = models.JSONField(default=dict)
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "complaints_sourceevent"
        verbose_name = "Source Event"
        verbose_name_plural = "Source Events"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "external_event_id"],
                name="unique_tenant_source_event"
            )
        ]

    def __str__(self):
        return f"Event {self.external_event_id} ({self.source_channel})"


class Complaint(models.Model):
    """
    Core complaint record in the Bank Internal Incident Resolution System.
    """
    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"
        CRITICAL = "CRITICAL", "Critical"

    class Status(models.TextChoices):
        NEW = "NEW", "New"
        NEEDS_ACTION = "NEEDS_ACTION", "Needs action"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        FORWARDED = "FORWARDED", "Forwarded"
        AWAITING_VERIFICATION = "AWAITING_VERIFICATION", "Awaiting verification"
        RESOLVED = "RESOLVED", "Resolved"
        REOPENED = "REOPENED", "Reopened"

    class ResolutionVerification(models.TextChoices):
        AWAITING = "AWAITING", "Awaiting"
        VERIFIED = "VERIFIED", "Verified"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=64, unique=True, db_index=True)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="complaints"
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="complaints"
    )
    customer_reference = models.CharField(max_length=64, db_index=True)
    original_source_reference = models.CharField(max_length=128, blank=True, default="")
    source_channel = models.CharField(max_length=64, default="Contact centre feed")
    source_data_source = models.ForeignKey(
        "tenants.DataSource",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="complaints"
    )
    summary = models.CharField(max_length=255)
    narrative = models.TextField()
    category = models.ForeignKey(
        ComplaintCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="complaints"
    )
    priority = models.CharField(
        max_length=16,
        choices=Priority.choices,
        default=Priority.MEDIUM,
        db_index=True
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True
    )
    assigned_operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_complaints"
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(db_index=True)
    due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    reopen_reason = models.TextField(blank=True, default="")

    # Resolution fields
    resolution_outcome = models.TextField(blank=True, default="")
    resolution_evidence = models.TextField(blank=True, default="")
    resolution_reported_at = models.DateTimeField(null=True, blank=True)
    resolution_reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reported_resolutions"
    )
    resolution_verification = models.CharField(
        max_length=16,
        choices=ResolutionVerification.choices,
        default=ResolutionVerification.AWAITING
    )
    resolution_verified_at = models.DateTimeField(null=True, blank=True)
    resolution_verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_resolutions"
    )
    resolution_note = models.TextField(blank=True, default="")

    # Placeholders for future investigation & incident linkage
    shared_incident_reference = models.CharField(max_length=64, blank=True, default="")
    transaction_investigation_reference = models.CharField(max_length=64, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "complaints_complaint"
        verbose_name = "Complaint"
        verbose_name_plural = "Complaints"
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "priority"]),
            models.Index(fields=["tenant", "received_at"]),
            models.Index(fields=["tenant", "assigned_operator", "status"]),
            models.Index(fields=["tenant", "due_at"]),
        ]

    @property
    def is_overdue(self) -> bool:
        if self.status == self.Status.RESOLVED or not self.due_at:
            return False
        return self.due_at < timezone.now()

    def __str__(self):
        return f"{self.reference} [{self.status}] {self.summary[:40]}"


class ComplaintNote(models.Model):
    """
    Internal confidential case notes added by bank staff.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    complaint = models.ForeignKey(
        Complaint,
        on_delete=models.CASCADE,
        related_name="notes"
    )
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="complaint_notes"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="complaint_notes"
    )
    author_display_name = models.CharField(max_length=128)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "complaints_note"
        verbose_name = "Complaint Note"
        verbose_name_plural = "Complaint Notes"
        ordering = ["created_at"]

    def __str__(self):
        return f"Note by {self.author_display_name} on {self.complaint.reference}"


class ComplaintTimelineEvent(models.Model):
    """
    Immutable audit history of significant lifecycle events on a complaint.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    complaint = models.ForeignKey(
        Complaint,
        on_delete=models.CASCADE,
        related_name="timeline_events"
    )
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="complaint_timeline_events"
    )
    at = models.DateTimeField(default=timezone.now)
    kind = models.CharField(max_length=64)
    title = models.CharField(max_length=255)
    detail = models.TextField(blank=True, default="")
    actor = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "complaints_timelineevent"
        verbose_name = "Timeline Event"
        verbose_name_plural = "Timeline Events"
        ordering = ["-at"]

    def __str__(self):
        return f"{self.title} at {self.at} ({self.complaint.reference})"


class ComplaintFollowUp(models.Model):
    """
    Follow-up reminders and scheduled check-ins for active investigations.
    """
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    complaint = models.ForeignKey(
        Complaint,
        on_delete=models.CASCADE,
        related_name="follow_ups"
    )
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="complaint_follow_ups"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_follow_ups"
    )
    due_at = models.DateTimeField()
    reason = models.CharField(max_length=500)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "complaints_followup"
        verbose_name = "Complaint Follow-up"
        verbose_name_plural = "Complaint Follow-ups"
        ordering = ["due_at"]

    def __str__(self):
        return f"Follow-up for {self.complaint.reference} due {self.due_at}"
