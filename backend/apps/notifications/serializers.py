from rest_framework import serializers
from .models import Notification, NotificationPreference


class NotificationItemSerializer(serializers.ModelSerializer):
    occurredAt = serializers.DateTimeField(source="occurred_at")
    complaint = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "kind",
            "title",
            "occurredAt",
            "read",
            "complaint",
        ]

    def get_complaint(self, obj: Notification):
        if not obj.complaint:
            return None
        return {
            "id": str(obj.complaint.id),
            "reference": obj.complaint.reference,
        }


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = ["key", "label", "description", "enabled"]
