from rest_framework import serializers

from .models import Incident, IncidentComplaint, IncidentFinding, IncidentTimelineEvent


class IncidentTimelineEventSerializer(serializers.ModelSerializer):
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = IncidentTimelineEvent
        fields = ["id", "kind", "title", "detail", "actor", "createdAt"]


class IncidentFindingSerializer(serializers.ModelSerializer):
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = IncidentFinding
        fields = ["id", "kind", "title", "detail", "confidence", "createdAt"]


class IncidentComplaintSerializer(serializers.ModelSerializer):
    complaintId = serializers.CharField(source="complaint.id", read_only=True)
    complaintReference = serializers.CharField(source="complaint.reference", read_only=True)
    complaintSummary = serializers.CharField(source="complaint.summary", read_only=True)
    categoryLabel = serializers.CharField(source="complaint.category.label", read_only=True, default="Uncategorized")
    status = serializers.CharField(source="complaint.status", read_only=True)
    isConfirmed = serializers.BooleanField(source="is_confirmed", read_only=True)
    relationReason = serializers.CharField(source="relation_reason", read_only=True)
    associatedAt = serializers.DateTimeField(source="associated_at", read_only=True)

    class Meta:
        model = IncidentComplaint
        fields = [
            "id",
            "complaintId",
            "complaintReference",
            "complaintSummary",
            "categoryLabel",
            "status",
            "isConfirmed",
            "confidence",
            "relationReason",
            "associatedAt",
        ]


class IncidentSerializer(serializers.ModelSerializer):
    categoryLabel = serializers.CharField(source="category.label", read_only=True, default=None)
    complaintCount = serializers.IntegerField(source="complaint_associations.count", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = Incident
        fields = [
            "id",
            "reference",
            "title",
            "summary",
            "categoryLabel",
            "severity",
            "status",
            "source_system",
            "detected_rule",
            "complaintCount",
            "createdAt",
            "updatedAt",
        ]


class IncidentDetailSerializer(serializers.ModelSerializer):
    categoryLabel = serializers.CharField(source="category.label", read_only=True, default=None)
    complaints = IncidentComplaintSerializer(source="complaint_associations", many=True, read_only=True)
    findings = IncidentFindingSerializer(many=True, read_only=True)
    timeline = IncidentTimelineEventSerializer(source="timeline_events", many=True, read_only=True)
    detectionEvidence = serializers.JSONField(source="detection_evidence", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = Incident
        fields = [
            "id",
            "reference",
            "title",
            "summary",
            "categoryLabel",
            "severity",
            "status",
            "source_system",
            "detected_rule",
            "detectionEvidence",
            "complaints",
            "findings",
            "timeline",
            "createdAt",
            "updatedAt",
        ]
