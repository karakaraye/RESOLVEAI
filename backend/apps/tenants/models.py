import uuid
from django.db import models

class Tenant(models.Model):
    """
    Multi-tenant isolation boundary representing an onboarded bank.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=64, unique=True)
    time_zone = models.CharField(max_length=64, default="Africa/Lagos")
    support_label = models.CharField(max_length=255, default="BIIRS Operations Desk")
    support_contact = models.CharField(max_length=255, default="biirs-support@bank.test")
    support_hours = models.CharField(max_length=128, default="Mon–Fri 08:00–18:00")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenants_tenant"
        verbose_name = "Tenant"
        verbose_name_plural = "Tenants"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.slug})"


class DataSource(models.Model):
    """
    Connected data feeds and transaction systems with live freshness indicators.
    """
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Current"
        STALE = "STALE", "Stale"
        UNAVAILABLE = "UNAVAILABLE", "Unavailable"
        UNKNOWN = "UNKNOWN", "Unknown"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="data_sources")
    name = models.CharField(max_length=255)
    kind = models.CharField(max_length=128)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.AVAILABLE)
    last_updated_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenants_datasource"
        verbose_name = "Data Source"
        verbose_name_plural = "Data Sources"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} [{self.status}] ({self.tenant.name})"
