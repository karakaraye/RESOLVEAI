import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class MessageTemplate(models.Model):
    """
    Approved, versioned templates for customer communications.
    Enforces safe variable substitution, regulatory review audit trails,
    and prohibition of unapproved AI-generated assertions.
    """
    class Category(models.TextChoices):
        ACKNOWLEDGEMENT = "ACKNOWLEDGEMENT", "Complaint Acknowledgement"
        PROGRESS_UPDATE = "PROGRESS_UPDATE", "Investigation Progress Update"
        INVESTIGATION_DELAY = "INVESTIGATION_DELAY", "Investigation Delay"
        INFO_REQUEST = "INFO_REQUEST", "Additional Information Request"
        ESCALATION_NOTICE = "ESCALATION_NOTICE", "Approved Escalation Notice"
        VERIFIED_RESOLUTION = "VERIFIED_RESOLUTION", "Verified Complaint Resolution"
        REOPENED_NOTICE = "REOPENED_NOTICE", "Complaint Reopening Notification"

    class Channel(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        SMS = "SMS", "SMS"
        WHATSAPP = "WHATSAPP", "WhatsApp"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="message_templates"
    )
    code = models.CharField(max_length=64, db_index=True)
    category = models.CharField(max_length=64, choices=Category.choices, db_index=True)
    channel = models.CharField(max_length=32, choices=Channel.choices, default=Channel.EMAIL, db_index=True)
    version = models.IntegerField(default=1)
    is_approved = models.BooleanField(default=True, db_index=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_templates"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    subject = models.CharField(max_length=255, blank=True)
    body_template = models.TextField(help_text="Standardized text with permitted placeholders e.g. {complaint_reference}")
    permitted_variables = models.JSONField(
        default=list,
        help_text="List of permitted replacement tokens (e.g. ['complaint_reference', 'customer_name', 'summary'])"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communications_messagetemplate"
        verbose_name = "Message Template"
        verbose_name_plural = "Message Templates"
        unique_together = ("tenant", "code", "channel", "version")
        ordering = ["category", "channel", "-version"]

    def __str__(self):
        tenant_name = self.tenant.name if self.tenant else "System Default"
        return f"{self.code} v{self.version} [{self.channel}] ({tenant_name})"


class CommunicationPolicy(models.Model):
    """
    Tenant-level policy defining automatic acknowledgement rules,
    channel permissions, anti-spam intervals, and verification requirements.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.OneToOneField(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="communication_policy"
    )
    auto_acknowledge_enabled = models.BooleanField(default=True)
    skip_ack_if_channel_acknowledged = models.BooleanField(
        default=True,
        help_text="Do not send ResolveAI acknowledgement if the bank's ingest channel already acknowledged."
    )
    default_channel = models.CharField(
        max_length=32,
        choices=MessageTemplate.Channel.choices,
        default=MessageTemplate.Channel.EMAIL
    )
    permitted_channels = models.JSONField(
        default=list,
        help_text="Permitted channels for this tenant e.g. ['EMAIL', 'SMS', 'WHATSAPP']"
    )
    acknowledgement_template = models.ForeignKey(
        MessageTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+"
    )
    verified_resolution_template = models.ForeignKey(
        MessageTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+"
    )
    progress_update_template = models.ForeignKey(
        MessageTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+"
    )
    reopen_template = models.ForeignKey(
        MessageTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+"
    )
    min_progress_interval_hours = models.IntegerField(
        default=24,
        help_text="Minimum hours between progress updates to prevent duplicate/spam messaging."
    )
    require_maker_checker_for_resolution = models.BooleanField(
        default=True,
        help_text="Enforce independent maker-checker verification before any resolution notification can be queued."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communications_policy"
        verbose_name = "Communication Policy"
        verbose_name_plural = "Communication Policies"

    def __str__(self):
        return f"Communication Policy - {self.tenant.name}"


class CommunicationPreference(models.Model):
    """
    Customer notification preferences and opt-in choices per tenant.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)
    customer = models.ForeignKey(
        "complaints.Customer",
        on_delete=models.CASCADE,
        related_name="communication_preferences"
    )
    preferred_channel = models.CharField(
        max_length=32,
        choices=MessageTemplate.Channel.choices,
        default=MessageTemplate.Channel.EMAIL
    )
    email_opt_in = models.BooleanField(default=True)
    sms_opt_in = models.BooleanField(default=True)
    whatsapp_opt_in = models.BooleanField(default=True)
    preferred_email = models.CharField(max_length=255, blank=True)
    preferred_phone = models.CharField(max_length=32, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communications_preference"
        verbose_name = "Communication Preference"
        verbose_name_plural = "Communication Preferences"
        unique_together = ("tenant", "customer")

    def __str__(self):
        return f"{self.customer.customer_number} Preference: {self.preferred_channel}"


class CustomerCommunication(models.Model):
    """
    Durable record of a customer-facing message, tracking its lifecycle,
    delivery attempts, provider tokens, and linkage to complaint & verification.
    """
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        QUEUED = "QUEUED", "Queued"
        SENDING = "SENDING", "Sending"
        SENT = "SENT", "Sent"
        DELIVERY_UNCONFIRMED = "DELIVERY_UNCONFIRMED", "Delivery Unconfirmed"
        DELIVERED = "DELIVERED", "Delivered"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="customer_communications"
    )
    complaint = models.ForeignKey(
        "complaints.Complaint",
        on_delete=models.CASCADE,
        related_name="customer_communications"
    )
    customer = models.ForeignKey(
        "complaints.Customer",
        on_delete=models.CASCADE,
        related_name="customer_communications"
    )
    template = models.ForeignKey(
        MessageTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="communications"
    )
    template_version = models.IntegerField(default=1)
    category = models.CharField(max_length=64, choices=MessageTemplate.Category.choices, db_index=True)
    channel = models.CharField(max_length=32, choices=MessageTemplate.Channel.choices, db_index=True)
    recipient_destination = models.CharField(max_length=255)
    subject = models.CharField(max_length=255, blank=True)
    rendered_content = models.TextField()
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True
    )
    trigger_event = models.CharField(max_length=64, db_index=True)
    verification_reference = models.CharField(max_length=128, blank=True, db_index=True)
    originating_event_id = models.CharField(max_length=128, blank=True, db_index=True)
    complaint_version_at_creation = models.CharField(max_length=64, blank=True)
    provider = models.CharField(max_length=64, default="SimulatedDeliveryProvider")
    provider_message_id = models.CharField(max_length=128, blank=True, null=True, db_index=True)
    error_message = models.TextField(blank=True)
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)
    queued_at = models.DateTimeField(default=timezone.now, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communications_customercommunication"
        verbose_name = "Customer Communication"
        verbose_name_plural = "Customer Communications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "status", "created_at"], name="idx_comm_tenant_stat_created"),
            models.Index(fields=["complaint", "category", "status"], name="idx_comm_comp_cat_stat"),
        ]

    def __str__(self):
        return f"{self.category} [{self.channel}] -> {self.recipient_destination} ({self.status})"


class CommunicationDeliveryAttempt(models.Model):
    """
    Log of individual transmission attempts to simulated adapters.
    Records latency, provider payloads, and exact error responses.
    """
    class State(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        ACCEPTED = "ACCEPTED", "Accepted"
        DELIVERED = "DELIVERED", "Delivered"
        FAILED = "FAILED", "Failed"
        TIMED_OUT = "TIMED_OUT", "Timed Out"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    communication = models.ForeignKey(
        CustomerCommunication,
        on_delete=models.CASCADE,
        related_name="delivery_attempts"
    )
    attempt_number = models.IntegerField()
    channel = models.CharField(max_length=32)
    provider = models.CharField(max_length=64)
    destination = models.CharField(max_length=255)
    status = models.CharField(max_length=32, choices=State.choices)
    provider_reference = models.CharField(max_length=128, blank=True)
    provider_response = models.JSONField(default=dict)
    latency_ms = models.IntegerField(default=0)
    error_detail = models.TextField(blank=True)
    attempted_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "communications_deliveryattempt"
        verbose_name = "Delivery Attempt"
        verbose_name_plural = "Delivery Attempts"
        ordering = ["attempt_number"]

    def __str__(self):
        return f"Attempt #{self.attempt_number} for {self.communication_id}: {self.status}"


class CommunicationEvent(models.Model):
    """
    Immutable audit event in the lifecycle of a customer communication.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    communication = models.ForeignKey(
        CustomerCommunication,
        on_delete=models.CASCADE,
        related_name="events"
    )
    event_type = models.CharField(max_length=64, db_index=True)
    title = models.CharField(max_length=255)
    detail = models.TextField(blank=True)
    actor = models.CharField(max_length=128, default="System")
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "communications_event"
        verbose_name = "Communication Event"
        verbose_name_plural = "Communication Events"
        ordering = ["timestamp"]

    def __str__(self):
        return f"[{self.event_type}] {self.title} ({self.timestamp})"
