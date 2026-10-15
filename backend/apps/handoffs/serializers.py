from rest_framework import serializers

from .models import (
    ForwardingHandoff,
    HandoffAttempt,
    HandoffResponse,
    ReceivingTeam,
    TeamRecipient,
)


class ReceivingTeamOptionSerializer(serializers.ModelSerializer):
    recipients = serializers.SerializerMethodField()
    responseDueHours = serializers.IntegerField(source="response_due_hours")

    class Meta:
        model = ReceivingTeam
        fields = [
            "id",
            "name",
            "recipients",
            "channel",
            "responseDueHours",
        ]

    def get_recipients(self, obj: ReceivingTeam) -> list[str]:
        return list(obj.recipients.filter(is_active=True).values_list("name", flat=True))


class ForwardingOptionsSerializer(serializers.Serializer):
    recommendedTeamId = serializers.CharField(allow_null=True)
    teams = ReceivingTeamOptionSerializer(many=True)
    shareableSummary = serializers.CharField()
    sharedFields = serializers.ListField(child=serializers.CharField())


class HandoffAttemptSerializer(serializers.ModelSerializer):
    at = serializers.DateTimeField(source="created_at")

    class Meta:
        model = HandoffAttempt
        fields = ["at", "channel", "outcome"]


class HandoffResponseSerializer(serializers.ModelSerializer):
    receivedAt = serializers.DateTimeField(source="received_at")

    class Meta:
        model = HandoffResponse
        fields = ["receivedAt", "summary"]


class HandoffSerializer(serializers.ModelSerializer):
    team = serializers.SerializerMethodField()
    recipient = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source="created_at")
    createdBy = serializers.CharField(source="created_by_name")
    lastUpdatedAt = serializers.DateTimeField(source="last_updated_at")
    responseDueAt = serializers.SerializerMethodField()
    response = HandoffResponseSerializer(read_only=True)
    attempts = HandoffAttemptSerializer(many=True, read_only=True)
    retryAllowed = serializers.BooleanField(source="retry_allowed", read_only=True)

    class Meta:
        model = ForwardingHandoff
        fields = [
            "id",
            "team",
            "recipient",
            "channel",
            "state",
            "createdAt",
            "createdBy",
            "lastUpdatedAt",
            "responseDueAt",
            "response",
            "attempts",
            "retryAllowed",
        ]

    def get_team(self, obj: ForwardingHandoff) -> dict:
        return {"id": str(obj.team.id), "name": obj.team.name}

    def get_recipient(self, obj: ForwardingHandoff) -> str | None:
        return obj.recipient if obj.recipient else None

    def get_responseDueAt(self, obj: ForwardingHandoff) -> str | None:
        return obj.response_due_at.isoformat() if obj.response_due_at else None


class HandoffSummarySerializer(HandoffSerializer):
    complaint = serializers.SerializerMethodField()

    class Meta(HandoffSerializer.Meta):
        fields = HandoffSerializer.Meta.fields + ["complaint"]

    def get_complaint(self, obj: ForwardingHandoff) -> dict:
        comp = obj.complaint
        return {
            "id": str(comp.id),
            "reference": comp.reference,
            "customerReference": comp.customer_reference,
            "summary": comp.summary,
        }


class HandoffCreateRequestSerializer(serializers.Serializer):
    teamId = serializers.CharField()
    recipient = serializers.CharField(required=False, allow_blank=True, default="")
    message = serializers.CharField(max_length=2000)
