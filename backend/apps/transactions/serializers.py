from rest_framework import serializers
from .models import TransactionInvestigation


class TransactionRecordSerializer(serializers.ModelSerializer):
    """
    Serializes TransactionInvestigation instances to match the exact
    frontend TransactionRecord interface in src/lib/api/types.ts.
    """
    id = serializers.CharField(read_only=True)
    sourceSystem = serializers.CharField(source="source_system")
    amount = serializers.SerializerMethodField()
    occurredAt = serializers.SerializerMethodField()
    statusLabel = serializers.CharField(source="status_label", allow_null=True)
    lastUpdatedAt = serializers.SerializerMethodField()
    matchEvidence = serializers.CharField(source="match_evidence", allow_null=True)

    class Meta:
        model = TransactionInvestigation
        fields = [
            "id",
            "reference",
            "sourceSystem",
            "amount",
            "occurredAt",
            "statusLabel",
            "status",
            "lastUpdatedAt",
            "conflict",
            "matchEvidence",
        ]

    def get_amount(self, obj: TransactionInvestigation) -> dict | None:
        if obj.amount_value is None:
            return None
        return {
            "value": f"{obj.amount_value:,.2f}",
            "currency": obj.amount_currency or "NGN",
        }

    def get_occurredAt(self, obj: TransactionInvestigation) -> str | None:
        return obj.occurred_at.isoformat() if obj.occurred_at else None

    def get_lastUpdatedAt(self, obj: TransactionInvestigation) -> str | None:
        return obj.last_updated_at.isoformat() if obj.last_updated_at else None
