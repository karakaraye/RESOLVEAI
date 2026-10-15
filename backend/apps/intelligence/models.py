import uuid
from django.db import models
from django.utils import timezone
from pgvector.django import VectorField


class ComplaintEmbedding(models.Model):
    """
    Stores semantic vector representations of customer complaints using pgvector.
    Enforces tenant isolation and dimension validation.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="complaint_embeddings"
    )
    complaint = models.OneToOneField(
        "complaints.Complaint",
        on_delete=models.CASCADE,
        related_name="embedding"
    )
    embedding = VectorField(
        dimensions=384,
        help_text="Dense vector representation (e.g. 384-dimensional for all-MiniLM-L6-v2)."
    )
    model_identifier = models.CharField(
        max_length=128,
        default="all-MiniLM-L6-v2",
        help_text="Identifier of the model used to produce the vector."
    )
    model_version = models.CharField(
        max_length=64,
        default="1.0.0",
        help_text="Version string of the embedding model."
    )
    dimension = models.PositiveIntegerField(
        default=384,
        help_text="Dimension count of the vector."
    )
    content_fingerprint = models.CharField(
        max_length=64,
        db_index=True,
        help_text="SHA-256 fingerprint of the source text used to avoid redundant computation."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "intelligence_complaintembedding"
        verbose_name = "Complaint Embedding"
        verbose_name_plural = "Complaint Embeddings"
        indexes = [
            models.Index(fields=["tenant", "complaint"], name="idx_emb_tenant_comp"),
            models.Index(fields=["tenant", "content_fingerprint"], name="idx_emb_tenant_fprint"),
        ]

    def __str__(self):
        return f"Embedding({self.complaint.reference}, dim={self.dimension}, model={self.model_identifier})"


class ComplaintIntelligenceFinding(models.Model):
    """
    Structured findings produced by the intelligence engine for a complaint:
    classification, root-cause facts/hypotheses, and recommendations.
    """
    class Availability(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        UNAVAILABLE = "UNAVAILABLE", "Unavailable"
        LOW_CONFIDENCE = "LOW_CONFIDENCE", "Low confidence"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="intelligence_findings"
    )
    complaint = models.OneToOneField(
        "complaints.Complaint",
        on_delete=models.CASCADE,
        related_name="intelligence_finding"
    )
    availability = models.CharField(
        max_length=32,
        choices=Availability.choices,
        default=Availability.AVAILABLE,
        db_index=True
    )
    confidence = models.FloatField(
        null=True,
        blank=True,
        help_text="Confidence indicator (0.0 to 1.0)."
    )

    # Classification recommendations
    suggested_category = models.ForeignKey(
        "complaints.ComplaintCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suggested_complaints"
    )
    suggested_category_code = models.CharField(max_length=64, blank=True, default="")
    suggested_priority = models.CharField(max_length=16, blank=True, default="")
    possible_responsible_team = models.CharField(max_length=128, blank=True, default="")
    explanation = models.TextField(blank=True, default="")

    # Root cause analysis
    possible_cause = models.TextField(blank=True, default="")
    recommended_next_step = models.TextField(blank=True, default="")
    facts = models.JSONField(
        default=list,
        blank=True,
        help_text="List of confirmed factual observations grounded in evidence."
    )
    hypotheses = models.JSONField(
        default=list,
        blank=True,
        help_text="List of working hypotheses not yet confirmed."
    )
    evidence_references = models.JSONField(
        default=list,
        blank=True,
        help_text="List of authoritative document references cited in findings."
    )
    missing_information = models.JSONField(
        default=list,
        blank=True,
        help_text="Gaps in evidence required before confirmed resolution."
    )
    conflicting_information = models.JSONField(
        default=list,
        blank=True,
        help_text="Discrepancies identified across banking ledgers or payment switches."
    )

    # Metadata & Auditing
    model_identifier = models.CharField(max_length=128, default="resolveai-intelligence-v1")
    model_version = models.CharField(max_length=64, default="1.0.0")
    content_fingerprint = models.CharField(max_length=64, blank=True, default="")
    processing_timestamp = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "intelligence_complaintintelligencefinding"
        verbose_name = "Complaint Intelligence Finding"
        verbose_name_plural = "Complaint Intelligence Findings"
        indexes = [
            models.Index(fields=["tenant", "complaint"], name="idx_find_tenant_comp"),
            models.Index(fields=["tenant", "availability"], name="idx_find_tenant_avail"),
        ]

    def __str__(self):
        return f"Findings({self.complaint.reference}, {self.availability}, conf={self.confidence})"


class AIProcessingJob(models.Model):
    """
    Durable, idempotent tracking record for asynchronous and synchronous AI processing jobs.
    Prevents duplicate runs on unchanged complaints and supports bounded retry backoff.
    """
    class JobType(models.TextChoices):
        CLASSIFICATION = "CLASSIFICATION", "Classification"
        EMBEDDING = "EMBEDDING", "Embedding"
        ROOT_CAUSE_ANALYSIS = "ROOT_CAUSE_ANALYSIS", "Root Cause Analysis"
        FULL_INTELLIGENCE = "FULL_INTELLIGENCE", "Full Intelligence Pipeline"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"
        RETRYING = "RETRYING", "Retrying"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="ai_jobs"
    )
    complaint = models.ForeignKey(
        "complaints.Complaint",
        on_delete=models.CASCADE,
        related_name="ai_jobs"
    )
    job_type = models.CharField(max_length=32, choices=JobType.choices, default=JobType.FULL_INTELLIGENCE)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING, db_index=True)
    idempotency_key = models.CharField(max_length=255, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "intelligence_aiprocessingjob"
        verbose_name = "AI Processing Job"
        verbose_name_plural = "AI Processing Jobs"
        indexes = [
            models.Index(fields=["tenant", "idempotency_key"], name="idx_aijob_tenant_idem"),
            models.Index(fields=["tenant", "complaint", "status"], name="idx_aijob_tenant_comp_st"),
        ]

    def __str__(self):
        return f"AIJob({self.job_type}, {self.complaint.reference}, {self.status})"
