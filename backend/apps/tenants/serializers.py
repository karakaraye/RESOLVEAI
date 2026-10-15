from rest_framework import serializers
from .models import Tenant, DataSource

class TenantSerializer(serializers.ModelSerializer):
    """
    Serializes Tenant model strictly matching the frontend Session['tenant'] wire structure:
    {
      "id": string,
      "name": string,
      "timeZone": string,
      "support": {
        "label": string,
        "contact": string,
        "hours": string
      }
    }
    """
    timeZone = serializers.CharField(source="time_zone")
    support = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = ["id", "name", "timeZone", "support"]

    def get_support(self, obj):
        return {
            "label": obj.support_label,
            "contact": obj.support_contact,
            "hours": obj.support_hours,
        }


class DataSourceSerializer(serializers.ModelSerializer):
    """
    Serializes DataSource matching the frontend DataSource wire type:
    {
      "id": string,
      "name": string,
      "kind": string,
      "status": SourceStatus,
      "lastUpdatedAt"?: string,
      "note"?: string
    }
    """
    lastUpdatedAt = serializers.DateTimeField(source="last_updated_at", allow_null=True)

    class Meta:
        model = DataSource
        fields = ["id", "name", "kind", "status", "lastUpdatedAt", "note"]
