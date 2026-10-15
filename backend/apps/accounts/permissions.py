from rest_framework import permissions

class HasTenantAccess(permissions.BasePermission):
    """
    Ensures that the authenticated user belongs to an active tenant
    and restricts object access strictly to objects belonging to that tenant.
    """
    message = "You do not have access to data outside your bank tenant."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return user.tenant is not None and user.tenant.is_active

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser:
            return True

        # Check tenant on target entity
        target_tenant_id = getattr(obj, "tenant_id", None)
        if target_tenant_id is None and hasattr(obj, "tenant"):
            target_tenant = getattr(obj, "tenant", None)
            target_tenant_id = target_tenant.id if target_tenant else None

        if target_tenant_id is not None:
            return str(target_tenant_id) == str(user.tenant_id)

        return True


class RequirePermission:
    """
    Permission helper that validates the user possesses a specific fine-grained permission string.
    Usage: permission_classes = [RequirePermission("complaints.verify_outcome")]
    """
    def __init__(self, permission_name: str):
        self.permission_name = permission_name

    def __call__(self):
        class DynamicPermission(permissions.BasePermission):
            message = f"Your role does not include the '{self.permission_name}' permission."

            def has_permission(inner_self, request, view):
                user = request.user
                if not user or not user.is_authenticated:
                    return False
                return user.has_case_permission(self.permission_name)

        return DynamicPermission()
