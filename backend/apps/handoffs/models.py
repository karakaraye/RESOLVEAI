import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class ReceivingTeam(models.Model):
    """
    Internal bank operations department eligible to receive forwarded complaint handoffs.
    Does NOT require individual operator user accounts in ResolveAI to receive handoffs.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="receiving_teams"
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=64, db_index=True)
    channel = models.CharField(
        max_length=128,
        help_text="Primary transmission channel (e.g. Bank case-management queue, Secure email)"
    )
    fallback_channel = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Approved fallback channel if primary fails"
    )
    response_due_hours = models.PositiveIntegerField(
        default=24,
        help_text="Default SLA response turnaround in hours"
    )
    allowed_categories = models.ManyToManyField(
        "complaints.ComplaintCategory",
        blank=True,
        related_name="eligible_teams",
        help_text="Categories this team is authorised to investigate"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "handoffs_receivingteam"
        verbose_name = "Receiving Team"
        verbose_name_plural = "Receiving Teams"
        unique_together = ("tenant", "code")
        indexes = [
            models.Index(fields=["tenant", "is_active"], name="idx_team_tenant_active"),
        ]

    def __str__(self):
        return f"{self.name} ({self.channel})"


class TeamRecipient(models.Model):
    """
    Named operational contact or duty lead within a receiving team.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team = models.ForeignKey(
        ReceivingTeam,
        on_delete=models.CASCADE,
        related_name="recipients"
    )
    name = models.CharField(max_length=255)
    role_or_title = models.CharField(max_length=128, blank=True, default="")
    contact_address = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Queue routing tag or notification email"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "handoffs_teamrecipient"
        verbose_name = "Team Recipient"
        verbose_name_plural = "Team Recipients"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.team.name})"


class ForwardingPolicy(models.Model):
    """
    Tenant-configurable operational routing and information-sharing rules.
    Governs automated routing permissions, SLA deadlines, and permitted data sharing.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="forwarding_policies"
    )
    category = models.ForeignKey(
        "complaints.ComplaintCategory",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="forwarding_policies"
    )
    default_team = models.ForeignKey(
        ReceivingTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="policy_defaults"
    )
    auto_route_permitted = models.BooleanField(
        default=False,
        help_text="Explicit policy permitting automated routing without manual operator confirmation"
    )
    sla_response_hours = models.PositiveIntegerField(
        default=24,
        help_text="SLA hours allowed for team to respond"
    )
    reminder_lead_hours = models.PositiveIntegerField(
        default=4,
        help_text="Hours before deadline to trigger approaching-deadline warning"
    )
    max_retry_attempts = models.PositiveIntegerField(
        default=3,
        help_text="Maximum automated retry attempts on transient delivery failures"
    )
    shared_fields = models.JSONField(
        default=list,
        blank=True,
        help_text="List of data attributes proposed and permitted for cross-team sharing"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "handoffs_forwardingpolicy"
        verbose_name = "Forwarding Policy"
        verbose_name_plural = "Forwarding Policies"


class ForwardingHandoff(models.Model):
    """
    Tracks cross-team operational dispatch, delivery lifecycle, evidence,
    SLA timers, and receiving team responses.
    """
    class State(models.TextChoices):
        PREPARED = "PREPARED", "Prepared"
        RETRY_SCHEDULED = "RETRY_SCHEDULED", "Retry scheduled"
        FALLBACK_IN_PROGRESS = "FALLBACK_IN_PROGRESS", "Trying approved fallback"
        SEND_FAILED = "SEND_FAILED", "Send failed"
        SENT = "SENT", "Sent"
        DELIVERY_UNCONFIRMED = "DELIVERY_UNCONFIRMED", "Sent · delivery unconfirmed"
        DELIVERED = "DELIVERED", "Delivered"
        ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged"
        ACCEPTED = "ACCEPTED", "Accepted"
        AWAITING_RESPONSE = "AWAITING_RESPONSE", "Awaiting response"
        RESPONDED = "RESPONDED", "Responded"
        OVERDUE = "OVERDUE", "Overdue"
        CLOSED = "CLOSED", "Closed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="handoffs"
    )
    complaint = models.ForeignKey(
        "complaints.Complaint",
        on_delete=models.CASCADE,
        related_name="handoffs"
    )
    incident = models.ForeignKey(
        "incidents.Incident",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="handoffs",
        help_text="Optional link to shared incident without collapsing complaint identity"
    )
    team = models.ForeignKey(
        ReceivingTeam,
        on_delete=models.PROTECT,
        related_name="handoffs"
    )
    recipient = models.CharField(max_length=255, blank=True, default="")
    channel = models.CharField(max_length=128)
    state = models.CharField(
        max_length=32,
        choices=State.choices,
        default=State.PREPARED,
        db_index=True
    )
    message = models.TextField(
        help_text="Minimised, privacy-filtered operational message transmitted to the team"
    )
    shared_fields = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_handoffs"
    )
    created_by_name = models.CharField(max_length=255, blank=True, default="Staff")
    response_due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    max_retries = models.PositiveIntegerField(default=3)
    delivery_evidence = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    last_updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "handoffs_forwardinghandoff"
        verbose_name = "Forwarding Handoff"
        verbose_name_plural = "Forwarding Handoffs"
        indexes = [
            models.Index(fields=["tenant", "state", "created_at"], name="idx_hndf_tenant_st_cr"),
            models.Index(fields=["state", "response_due_at"], name="idx_hndf_state_due"),
            models.Index(fields=["complaint", "created_at"], name="idx_hndf_comp_created"),
        ]

    def __str__(self):
        return f"Handoff({self.complaint.reference} -> {self.team.name} [{self.state}])"

    @property
    def retry_allowed(self) -> bool:
        """
        Determines whether the operator can manually or automatically retry dispatch.
        Allowed when in SEND_FAILED, RETRY_SCHEDULED, or FALLBACK_IN_PROGRESS.
        """
        if self.state == self.State.SEND_FAILED:
            return True
        if self.state in (self.State.RETRY_SCHEDULED, self.State.FALLBACK_IN_PROGRESS):
            return self.retry_count < self.max_retries
        return False


class HandoffAttempt(models.Model):
    """
    Immutable audit record of each transmission attempt, delivery outcome, and evidence.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    handoff = models.ForeignKey(
        ForwardingHandoff,
        on_delete=models.CASCADE,
        related_name="attempts"
    )
    attempt_number = models.PositiveIntegerField(default=1)
    channel = models.CharField(max_length=128)
    outcome = models.CharField(max_length=255)
    evidence = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=64, blank=True, default="")
    is_uncertain = models.BooleanField(
        default=False,
        help_text="True if transmission timed out without conclusive ACK or NACK"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "handoffs_handoffattempt"
        verbose_name = "Handoff Attempt"
        verbose_name_plural = "Handoff Attempts"
        ordering = ["created_at"]

    def __str__(self):
        return f"Attempt #{self.attempt_number} ({self.channel}): {self.outcome}"


class HandoffEvent(models.Model):
    """
    Domain event log for handoff lifecycle tracking and timeline integration.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    handoff = models.ForeignKey(
        ForwardingHandoff,
        on_delete=models.CASCADE,
        related_name="events"
    )
    event_type = models.CharField(max_length=64, db_index=True)
    title = models.CharField(max_length=255)
    detail = models.TextField(blank=True, default="")
    actor = models.CharField(max_length=255, blank=True, default="System")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "handoffs_handoffevent"
        verbose_name = "Handoff Event"
        verbose_name_plural = "Handoff Events"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event_type} on {self.handoff_id}: {self.title}"


class HandoffResponse(models.Model):
    """
    Stores substantive investigation response from the receiving team.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    handoff = models.OneToOneField(
        ForwardingHandoff,
        on_delete=models.CASCADE,
        related_name="response"
    )
    summary = models.TextField()
    details = models.JSONField(default=dict, blank=True)
    responder_name = models.CharField(max_length=255, blank=True, default="")
    responder_contact = models.CharField(max_length=255, blank=True, default="")
    received_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "handoffs_handoffresponse"
        verbose_name = "Handoff Response"
        verbose_name_plural = "Handoff Responses"

    def __str__(self):
        return f"Response for {self.handoff_id}: {self.summary[:50]}"
