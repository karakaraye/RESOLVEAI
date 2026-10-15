from rest_framework import serializers
from apps.tenants.serializers import TenantSerializer
from .models import User

class UserSerializer(serializers.ModelSerializer):
    """
    Serializes User model matching the frontend Session['user'] wire structure:
    {
      "id": string,
      "displayName": string,
      "email": string,
      "department"?: string,
      "roleLabel": string
    }
    """
    displayName = serializers.CharField(source="display_name")
    roleLabel = serializers.CharField(source="role_label")

    class Meta:
        model = User
        fields = ["id", "displayName", "email", "department", "roleLabel"]


class SessionSerializer(serializers.Serializer):
    """
    Serializes the complete Session payload required by GET /api/v1/session.
    """
    user = UserSerializer()
    tenant = TenantSerializer()
    permissions = serializers.ListField(child=serializers.CharField())
    session = serializers.DictField()
