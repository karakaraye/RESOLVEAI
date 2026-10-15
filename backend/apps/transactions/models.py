import uuid
from django.db import models


class TransactionInvestigation(models.Model):
    """
    Represents core banking transactions and switch records under investigation
    for a specific customer complaint.
    Preserves authoritative ledger reference, posting timestamps, source freshness,
    and detected reconciliation discrepancies.
    """
    class SourceStatus(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        STALE = "STALE", "Stale"
        UNAVAILABLE = "UNAVAILABLE", "Unavailable"
        UNKNOWN = "UNKNOWN", "Unknown"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="transaction_investigations"
    )
    complaint = models.ForeignKey(
        "complaints.Complaint",
        on_delete=models.CASCADE,
        related_name="transaction_investigations"
    )

    reference = models.CharField(
        max_length=128,
        db_index=True,
        help_text="Core transaction ID or switch reference (e.g., TXN-TEST-90311, STAN-771092)."
    )
    source_system = models.CharField(
        max_length=128,
        help_text="Originating system (e.g., 'Core banking (Finacle)', 'Instant payment switch (NIBSS)')."
    )
    amount_value = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Monetary transaction amount."
    )
    amount_currency = models.CharField(
        max_length=8,
        default="NGN",
        help_text="ISO currency code (e.g., NGN, USD, GBP)."
    )
    occurred_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Original posting timestamp reported by the source banking ledger."
    )
    status_label = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="System-reported status (e.g., 'Debited', 'Pending', 'Successful', 'Failed')."
    )
    status = models.CharField(
        max_length=32,
        choices=SourceStatus.choices,
        default=SourceStatus.AVAILABLE,
        help_text="Source data availability and freshness status."
    )
    last_updated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when this transaction record was last fetched or refreshed from the source."
    )
    conflict = models.TextField(
        null=True,
        blank=True,
        help_text="Explicit discrepancy explanation across systems (e.g. 'Core banking shows debited; switch shows pending. No final outcome is assumed.')."
    )
    match_evidence = models.TextField(
        null=True,
        blank=True,
        help_text="Deterministic rationale explaining why this transaction was matched to the complaint."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "transactions_transactioninvestigation"
        verbose_name = "Transaction Investigation"
        verbose_name_plural = "Transaction Investigations"
        ordering = ["-occurred_at", "-created_at"]
        indexes = [
            models.Index(fields=["tenant", "complaint"], name="idx_txn_tenant_complaint"),
            models.Index(fields=["tenant", "reference"], name="idx_txn_tenant_ref"),
            models.Index(fields=["complaint", "source_system"], name="idx_txn_comp_source"),
        ]

    def __str__(self):
        amount_str = f"{self.amount_currency} {self.amount_value:,.2f}" if self.amount_value is not None else "No Amount"
        return f"{self.reference} ({self.source_system}) - {amount_str}"
