from rest_framework import serializers
from .models import EvidenceRecord


class EvidenceRecordSerializer(serializers.ModelSerializer):
    """
    Serializes EvidenceRecord instances with camelCase attributes.
    """
    id = serializers.CharField(read_only=True)
    complaintId = serializers.CharField(source="complaint_id", read_only=True)
    transactionInvestigationId = serializers.CharField(
        source="transaction_investigation_id", allow_null=True, required=False
    )
    documentReference = serializers.CharField(source="document_reference")
    sourceSystem = serializers.CharField(source="source_system")
    sourceTimestamp = serializers.SerializerMethodField()
    dataFreshness = serializers.CharField(source="data_freshness")
    isVerified = serializers.BooleanField(source="is_verified", read_only=True)
    verifiedBy = serializers.SerializerMethodField()
    verifiedAt = serializers.SerializerMethodField()
    rawPayload = serializers.JSONField(source="raw_payload", required=False)
    createdAt = serializers.SerializerMethodField()

    class Meta:
        model = EvidenceRecord
        fields = [
            "id",
            "complaintId",
            "transactionInvestigationId",
            "kind",
            "documentReference",
            "title",
            "summary",
            "sourceSystem",
            "sourceTimestamp",
            "provenance",
            "dataFreshness",
            "isVerified",
            "verifiedBy",
            "verifiedAt",
            "rawPayload",
            "createdAt",
        ]

    def get_sourceTimestamp(self, obj: EvidenceRecord) -> str | None:
        return obj.source_timestamp.isoformat() if obj.source_timestamp else None

    def get_verifiedBy(self, obj: EvidenceRecord) -> str | None:
        if obj.verified_by:
            return getattr(obj.verified_by, "display_name", str(obj.verified_by))
        return None

    def get_verifiedAt(self, obj: EvidenceRecord) -> str | None:
        return obj.verified_at.isoformat() if obj.verified_at else None

    def get_createdAt(self, obj: EvidenceRecord) -> str | None:
        return obj.created_at.isoformat() if obj.created_at else None
