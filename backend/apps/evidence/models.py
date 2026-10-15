import uuid
from django.db import models


class EvidenceRecord(models.Model):
    """
    Authoritative proof supporting transaction investigations and case resolutions.
    Preserves document references, source timestamps, evidence provenance,
    and immutable raw payloads.
    """
    class EvidenceKind(models.TextChoices):
        LEDGER_ENTRY = "LEDGER_ENTRY", "Core Ledger Entry"
        SWITCH_LOG = "SWITCH_LOG", "Switch Session Log"
        REVERSAL_SLIP = "REVERSAL_SLIP", "Reversal Journal Slip"
        CUSTOMER_RECEIPT = "CUSTOMER_RECEIPT", "Customer Receipt / Statement"
        AUDIT_SNAPSHOT = "AUDIT_SNAPSHOT", "Audit Snapshot"
        SYSTEM_TRACE = "SYSTEM_TRACE", "System Network Trace"

    class DataFreshness(models.TextChoices):
        FRESH = "FRESH", "Fresh (Real-time)"
        STALE = "STALE", "Stale (Delayed Sync)"
        HISTORICAL = "HISTORICAL", "Historical Archive"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="evidence_records"
    )
    complaint = models.ForeignKey(
        "complaints.Complaint",
        on_delete=models.CASCADE,
        related_name="evidence_records"
    )
    transaction_investigation = models.ForeignKey(
        "transactions.TransactionInvestigation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidence_records",
        help_text="Optional link to a specific transaction investigation."
    )

    kind = models.CharField(
        max_length=64,
        choices=EvidenceKind.choices,
        default=EvidenceKind.LEDGER_ENTRY,
        help_text="Classification of the authoritative evidence."
    )
    document_reference = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Authoritative journal number, switch session ID, or trace sequence (e.g., JRN-FIN-20261012-9844)."
    )
    title = models.CharField(
        max_length=255,
        help_text="Human-readable title describing the evidence document."
    )
    summary = models.TextField(
        null=True,
        blank=True,
        help_text="Summary of factual findings contained in this document."
    )
    source_system = models.CharField(
        max_length=128,
        help_text="Name of the originating bank system (e.g. 'Finacle Core Banking Journal', 'NIBSS Settlement Switch Log')."
    )
    source_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Original posting or event timestamp from the external ledger or switch."
    )
    provenance = models.TextField(
        null=True,
        blank=True,
        help_text="Chain of custody and extraction provenance (e.g. 'Extracted via Core Banking Read-Only Journal Feed at 2026-10-14T08:00:00Z by Batch #4412')."
    )
    data_freshness = models.CharField(
        max_length=32,
        choices=DataFreshness.choices,
        default=DataFreshness.FRESH,
        help_text="Indicator of data freshness at time of retrieval."
    )
    is_verified = models.BooleanField(
        default=False,
        help_text="True if this evidence document has been verified by a qualified compliance or verification officer."
    )
    verified_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_evidence_records",
        help_text="User who verified the authenticity of this evidence."
    )
    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when verification was performed."
    )
    raw_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Complete, immutable raw JSON payload from the banking adapter."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "evidence_evidencerecord"
        verbose_name = "Evidence Record"
        verbose_name_plural = "Evidence Records"
        ordering = ["-source_timestamp", "-created_at"]
        indexes = [
            models.Index(fields=["tenant", "complaint"], name="idx_evd_tenant_comp"),
            models.Index(fields=["tenant", "document_reference"], name="idx_evd_tenant_docref"),
            models.Index(fields=["complaint", "kind"], name="idx_evd_comp_kind"),
        ]

    def compute_payload_hash(self) -> str:
        """
        Computes a SHA-256 digest of the canonical raw JSON payload to detect
        post-ingestion tampering or bit-rot.

        CRITICAL INTEGRITY ARCHITECTURE NOTE:
        A SHA-256 hash guarantees data integrity (tamper-detection of the stored record),
        but does NOT independently prove that the record originated from an authentic
        banking source. Source authenticity in ResolveAI is established collectively through:
          1. Source system identity & verified integration credentials (source_system)
          2. External source event timestamps and authoritative identifiers (source_timestamp, document_reference)
          3. Independent maker-checker review and attestation (is_verified, verified_by, verified_at)
          4. Immutable audit logs tracking extraction provenance and chain of custody
        """
        import hashlib, json
        canonical = json.dumps(self.raw_payload or {}, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def __str__(self):
        status = "VERIFIED" if self.is_verified else "UNVERIFIED"
        return f"[{self.kind}] {self.document_reference} ({status}) - {self.title}"
