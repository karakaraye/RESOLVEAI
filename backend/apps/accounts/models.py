import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    """
    Custom user model representing bank operators, supervisors, and verifiers.
    Anchored to a tenant for multi-tenant isolation.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="users"
    )
    department = models.CharField(max_length=128, default="Customer Care")
    role_label = models.CharField(max_length=128, default="Operator")
    permissions_list = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "accounts_user"
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["username"]

    @property
    def display_name(self) -> str:
        name = f"{self.first_name} {self.last_name}".strip()
        return name if name else self.username

    def has_case_permission(self, perm: str) -> bool:
        if self.is_superuser:
            return True
        return perm in self.permissions_list

    def __str__(self):
        tenant_name = self.tenant.name if self.tenant else "No Tenant"
        return f"{self.display_name} ({self.role_label} - {tenant_name})"
