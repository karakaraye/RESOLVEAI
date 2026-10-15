from rest_framework import serializers
from .models import (
    CustomerCommunication,
    CommunicationDeliveryAttempt,
    CommunicationEvent,
    MessageTemplate,
    CommunicationPolicy,
    CommunicationPreference,
)


class CommunicationDeliveryAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunicationDeliveryAttempt
        fields = [
            "id",
            "attempt_number",
            "channel",
            "provider",
            "status",
            "provider_reference",
            "latency_ms",
            "error_detail",
            "attempted_at",
        ]


class CommunicationEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunicationEvent
        fields = [
            "id",
            "event_type",
            "title",
            "detail",
            "actor",
            "timestamp",
        ]


class CustomerCommunicationSerializer(serializers.ModelSerializer):
    delivery_attempts = CommunicationDeliveryAttemptSerializer(many=True, read_only=True)
    events = CommunicationEventSerializer(many=True, read_only=True)
    complaint_reference = serializers.CharField(source="complaint.reference", read_only=True)
    customer_reference = serializers.CharField(source="customer.customer_number", read_only=True)
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    masked_destination = serializers.SerializerMethodField()

    class Meta:
        model = CustomerCommunication
        fields = [
            "id",
            "complaint_id",
            "complaint_reference",
            "customer_reference",
            "category",
            "category_label",
            "channel",
            "masked_destination",
            "subject",
            "rendered_content",
            "status",
            "trigger_event",
            "verification_reference",
            "provider",
            "provider_message_id",
            "error_message",
            "retry_count",
            "max_retries",
            "queued_at",
            "sent_at",
            "delivered_at",
            "cancelled_at",
            "cancellation_reason",
            "delivery_attempts",
            "events",
            "created_at",
            "updated_at",
        ]

    def get_masked_destination(self, obj) -> str:
        dest = obj.recipient_destination or ""
        if "@" in dest:
            parts = dest.split("@")
            user_part = parts[0]
            masked_user = user_part[0] + "***" if len(user_part) > 1 else "***"
            return f"{masked_user}@{parts[1]}"
        elif len(dest) >= 8:
            return f"{dest[:4]}****{dest[-3:]}"
        return "***"


class MessageTemplateSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = MessageTemplate
        fields = [
            "id",
            "code",
            "category",
            "category_label",
            "channel",
            "version",
            "is_approved",
            "subject",
            "body_template",
            "permitted_variables",
            "created_at",
            "updated_at",
        ]


class CommunicationPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunicationPolicy
        fields = [
            "id",
            "auto_acknowledge_enabled",
            "skip_ack_if_channel_acknowledged",
            "default_channel",
            "permitted_channels",
            "min_progress_interval_hours",
            "require_maker_checker_for_resolution",
            "updated_at",
        ]
