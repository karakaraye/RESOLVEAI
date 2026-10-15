import uuid
from django.conf import settings
from django.db import models


class Incident(models.Model):
    """
    Core banking incident entity representing a verified or candidate widespread outage,
    degraded service, or systematic reconciliation failure affecting multiple customer complaints.
    """
    class Severity(models.TextChoices):
        MINOR = "MINOR", "Minor"
        MODERATE = "MODERATE", "Moderate"
        MAJOR = "MAJOR", "Major"
        CRITICAL = "CRITICAL", "Critical"

    class Status(models.TextChoices):
        CANDIDATE = "CANDIDATE", "Candidate (Under Review)"
        INVESTIGATING = "INVESTIGATING", "Investigating"
        CONFIRMED = "CONFIRMED", "Confirmed Active Incident"
        MITIGATED = "MITIGATED", "Mitigated"
        RESOLVED = "RESOLVED", "Resolved"
        FALSE_POSITIVE = "FALSE_POSITIVE", "False Positive / Dismissed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="incidents"
    )
    reference = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Human-readable incident reference (e.g. INC-2026-0001)."
    )
    title = models.CharField(max_length=255)
    summary = models.TextField()
    category = models.ForeignKey(
        "complaints.ComplaintCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incidents"
    )
    severity = models.CharField(
        max_length=16,
        choices=Severity.choices,
        default=Severity.MODERATE,
        db_index=True
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.CANDIDATE,
        db_index=True
    )
    source_system = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Primary affected banking infrastructure (e.g. NIBSS Instant Payments, Finacle Core)."
    )
    detected_rule = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Rule or clustering model identifier that triggered incident candidate."
    )
    detection_evidence = models.JSONField(
        default=dict,
        blank=True,
        help_text="Metrics and factual evidence behind incident detection."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_incidents"
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_incidents"
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "incidents_incident"
        verbose_name = "Incident"
        verbose_name_plural = "Incidents"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "reference"],
                name="unique_tenant_incident_reference"
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "status"], name="idx_inc_tenant_st"),
            models.Index(fields=["tenant", "severity"], name="idx_inc_tenant_sev"),
        ]

    def __str__(self):
        return f"{self.reference} [{self.status} - {self.severity}]: {self.title}"


class IncidentComplaint(models.Model):
    """
    Associates individual complaints to an incident candidate or confirmed incident.
    Preserves individual complaint SLA timers and identities without destructive merging.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="incident_complaint_links"
    )
    incident = models.ForeignKey(
        Incident,
        on_delete=models.CASCADE,
        related_name="complaint_associations"
    )
    complaint = models.ForeignKey(
        "complaints.Complaint",
        on_delete=models.CASCADE,
        related_name="incident_associations"
    )
    confidence = models.FloatField(
        default=1.0,
        help_text="Confidence of association (0.0 to 1.0)."
    )
    relation_reason = models.CharField(
        max_length=255,
        default="Associated via shared error pattern",
        help_text="Human-readable explanation of why this complaint is linked to the incident."
    )
    is_confirmed = models.BooleanField(
        default=False,
        help_text="True if confirmed by an incident lead or operator; False if suggested candidate."
    )
    associated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_incident_complaints"
    )
    associated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "incidents_incidentcomplaint"
        verbose_name = "Incident Complaint Link"
        verbose_name_plural = "Incident Complaint Links"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "incident", "complaint"],
                name="unique_tenant_incident_complaint"
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "incident"], name="idx_inc_cmp_tenant_inc"),
            models.Index(fields=["tenant", "complaint"], name="idx_inc_cmp_tenant_cmp"),
        ]

    def __str__(self):
        confirmed_tag = "CONFIRMED" if self.is_confirmed else "CANDIDATE"
        return f"{self.incident.reference} <-> {self.complaint.reference} ({confirmed_tag})"


class IncidentFinding(models.Model):
    """
    Investigation findings, root cause deductions, and remediation notes for an incident.
    """
    class Kind(models.TextChoices):
        ROOT_CAUSE = "ROOT_CAUSE", "Root Cause"
        IMPACT_ANALYSIS = "IMPACT_ANALYSIS", "Impact Analysis"
        AFFECTED_SERVICES = "AFFECTED_SERVICES", "Affected Services"
        REMEDIATION_STEP = "REMEDIATION_STEP", "Remediation Step"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident = models.ForeignKey(
        Incident,
        on_delete=models.CASCADE,
        related_name="findings"
    )
    kind = models.CharField(max_length=32, choices=Kind.choices, default=Kind.ROOT_CAUSE)
    title = models.CharField(max_length=255)
    detail = models.TextField()
    confidence = models.FloatField(default=1.0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "incidents_incidentfinding"
        verbose_name = "Incident Finding"
        verbose_name_plural = "Incident Findings"

    def __str__(self):
        return f"[{self.kind}] {self.title}"


class IncidentTimelineEvent(models.Model):
    """
    Audit and lifecycle timeline history for an incident.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident = models.ForeignKey(
        Incident,
        on_delete=models.CASCADE,
        related_name="timeline_events"
    )
    kind = models.CharField(max_length=64, default="STATE_CHANGED")
    title = models.CharField(max_length=255)
    detail = models.TextField(blank=True, default="")
    actor = models.CharField(max_length=128, default="System")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "incidents_incidenttimelineevent"
        verbose_name = "Incident Timeline Event"
        verbose_name_plural = "Incident Timeline Events"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.incident.reference} · {self.title} by {self.actor}"
