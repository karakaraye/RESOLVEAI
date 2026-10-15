import uuid
from abc import ABC, abstractmethod
from django.contrib.auth import login
from django.utils import timezone
from apps.tenants.models import Tenant
from .models import User

# Standard Synthetic Personas for Development & E2E Testing
SYNTHETIC_TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")

SYNTHETIC_PERSONAS = {
    "operator": {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "username": "operator",
        "first_name": "Test",
        "last_name": "Operator",
        "email": "operator@bank.test",
        "department": "Customer Care",
        "role_label": "Operator",
        "permissions": [
            "complaints.read",
            "complaints.assign",
            "complaints.forward",
            "complaints.notes",
            "complaints.follow_up",
            "complaints.record_outcome",
            "investigations.read",
            "investigations.manage",
            "evidence.read",
            "evidence.create",
            "reports.read",
        ],
    },
    "verifier": {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000002"),
        "username": "verifier",
        "first_name": "Senior",
        "last_name": "Verifier",
        "email": "verifier@bank.test",
        "department": "Compliance",
        "role_label": "Senior Verifier",
        "permissions": [
            "complaints.read",
            "complaints.notes",
            "complaints.verify_outcome",
            "complaints.reopen",
            "investigations.read",
            "evidence.read",
            "evidence.verify",
            "reports.read",
        ],
    },
    "lead": {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000003"),
        "username": "lead",
        "first_name": "Operations",
        "last_name": "Lead",
        "email": "lead@bank.test",
        "department": "Operations",
        "role_label": "Team Lead",
        "permissions": [
            "complaints.read",
            "complaints.assign",
            "complaints.forward",
            "complaints.notes",
            "complaints.follow_up",
            "complaints.record_outcome",
            "complaints.verify_outcome",
            "complaints.reopen",
            "investigations.read",
            "investigations.manage",
            "evidence.read",
            "evidence.create",
            "evidence.verify",
            "reports.read",
            "settings.manage",
        ],
    },
}

class AuthService(ABC):
    """Abstract authentication service contract for enterprise SSO and Dev Auth."""
    @abstractmethod
    def authenticate(self, request, **kwargs) -> User | None:
        pass


class DevAuthService(AuthService):
    """
    Development-only authentication service providing persona switching for testing.
    Strictly isolated to development environments.
    """
    def ensure_synthetic_tenant(self) -> Tenant:
        tenant, _ = Tenant.objects.get_or_create(
            id=SYNTHETIC_TENANT_ID,
            defaults={
                "name": "Test Bank",
                "slug": "test-bank",
                "time_zone": "Africa/Lagos",
                "support_label": "Test Bank BIIRS desk",
                "support_contact": "biirs-support@bank.test",
                "support_hours": "Mon–Fri 08:00–18:00",
                "is_active": True,
            }
        )
        return tenant

    def get_or_create_persona(self, persona_key: str) -> User:
        if persona_key not in SYNTHETIC_PERSONAS:
            persona_key = "operator"

        data = SYNTHETIC_PERSONAS[persona_key]
        tenant = self.ensure_synthetic_tenant()

        user, created = User.objects.get_or_create(
            id=data["id"],
            defaults={
                "username": data["username"],
                "first_name": data["first_name"],
                "last_name": data["last_name"],
                "email": data["email"],
                "department": data["department"],
                "role_label": data["role_label"],
                "permissions_list": data["permissions"],
                "tenant": tenant,
                "is_active": True,
            }
        )

        if not created:
            # Keep attributes synced
            user.permissions_list = data["permissions"]
            user.role_label = data["role_label"]
            user.department = data["department"]
            user.tenant = tenant
            user.save(update_fields=["permissions_list", "role_label", "department", "tenant"])

        return user

    def authenticate(self, request, persona: str = "operator") -> User:
        user = self.get_or_create_persona(persona)
        login(request, user)
        # Store sign-in timestamp in session
        request.session["signed_in_at"] = timezone.now().isoformat()
        request.session["identity_provider"] = "ResolveAI Development Authenticator"
        return user
