from rest_framework import serializers
from .models import Complaint, ComplaintCategory, ComplaintNote, ComplaintTimelineEvent
from .services import ComplaintWorkflowService


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplaintCategory
        fields = ["code", "label"]


class ComplaintSummarySerializer(serializers.ModelSerializer):
    receivedAt = serializers.SerializerMethodField()
    customerReference = serializers.CharField(source="customer_reference")
    category = serializers.SerializerMethodField()
    assignedOperator = serializers.SerializerMethodField()
    assignedAt = serializers.SerializerMethodField()
    dueAt = serializers.SerializerMethodField()
    overdue = serializers.SerializerMethodField()
    allowedActions = serializers.SerializerMethodField()

    class Meta:
        model = Complaint
        fields = [
            "id",
            "reference",
            "receivedAt",
            "customerReference",
            "summary",
            "category",
            "priority",
            "status",
            "assignedOperator",
            "assignedAt",
            "dueAt",
            "overdue",
            "allowedActions",
        ]

    def get_receivedAt(self, obj: Complaint) -> str:
        return obj.received_at.isoformat() if obj.received_at else None

    def get_category(self, obj: Complaint) -> dict | None:
        if not obj.category:
            return None
        return {"code": obj.category.code, "label": obj.category.label}

    def get_assignedOperator(self, obj: Complaint) -> dict | None:
        if not obj.assigned_operator:
            return None
        return {
            "id": str(obj.assigned_operator.id),
            "displayName": getattr(obj.assigned_operator, "display_name", str(obj.assigned_operator)),
        }

    def get_assignedAt(self, obj: Complaint) -> str | None:
        return obj.assigned_at.isoformat() if obj.assigned_at else None

    def get_dueAt(self, obj: Complaint) -> str | None:
        return obj.due_at.isoformat() if obj.due_at else None

    def get_overdue(self, obj: Complaint) -> bool:
        return obj.is_overdue

    def get_allowedActions(self, obj: Complaint) -> list[str]:
        request = self.context.get("request")
        user = request.user if request else None
        return ComplaintWorkflowService.compute_allowed_actions(obj, user)


class ComplaintDetailSerializer(ComplaintSummarySerializer):
    narrative = serializers.CharField()
    sourceChannel = serializers.CharField(source="source_channel")
    sourceReference = serializers.CharField(source="original_source_reference")
    source = serializers.SerializerMethodField()
    transactions = serializers.SerializerMethodField()
    related = serializers.SerializerMethodField()
    findings = serializers.SerializerMethodField()
    notes = serializers.SerializerMethodField()
    handoffs = serializers.SerializerMethodField()
    resolution = serializers.SerializerMethodField()
    reopenReason = serializers.SerializerMethodField()
    timeline = serializers.SerializerMethodField()

    class Meta(ComplaintSummarySerializer.Meta):
        fields = ComplaintSummarySerializer.Meta.fields + [
            "narrative",
            "sourceChannel",
            "sourceReference",
            "source",
            "transactions",
            "related",
            "findings",
            "notes",
            "handoffs",
            "resolution",
            "reopenReason",
            "timeline",
        ]

    def get_source(self, obj: Complaint) -> dict:
        if obj.source_data_source:
            return {
                "name": obj.source_data_source.name,
                "status": obj.source_data_source.status,
                "lastUpdatedAt": obj.source_data_source.last_synced_at.isoformat() if hasattr(obj.source_data_source, "last_synced_at") and obj.source_data_source.last_synced_at else None,
            }
        return {
            "name": obj.source_channel or "Contact centre feed",
            "status": "AVAILABLE",
            "lastUpdatedAt": obj.received_at.isoformat() if obj.received_at else None,
        }

    def get_transactions(self, obj: Complaint) -> list[dict]:
        from apps.transactions.serializers import TransactionRecordSerializer
        investigations = obj.transaction_investigations.all().order_by("-occurred_at", "-created_at")
        return TransactionRecordSerializer(investigations, many=True).data

    def get_related(self, obj: Complaint) -> list:
        related_records = []
        # 1. Linked incidents from apps.incidents
        if hasattr(obj, "incident_associations"):
            for assoc in obj.incident_associations.select_related("incident").all()[:3]:
                inc = assoc.incident
                related_records.append({
                    "id": str(inc.id),
                    "kind": "INCIDENT",
                    "reference": inc.reference,
                    "title": inc.title,
                    "relation": f"Linked incident ({inc.get_severity_display()})",
                })
        # 2. Top semantically similar complaints
        try:
            from apps.intelligence.services.similarity import SimilaritySearchService
            sim_candidates = SimilaritySearchService().find_similar_complaints(obj, limit=2, threshold=0.60)
            for sim in sim_candidates:
                related_records.append({
                    "id": sim.complaint_id,
                    "kind": "COMPLAINT",
                    "reference": sim.reference,
                    "title": sim.summary,
                    "relation": f"Similar complaint ({int(sim.similarity_score * 100)}% match)",
                })
        except Exception:
            pass

        return related_records

    def get_findings(self, obj: Complaint) -> dict:
        try:
            finding = getattr(obj, "intelligence_finding", None)
            if finding:
                from apps.intelligence.serializers import FindingSerializer
                return FindingSerializer(finding).data
        except Exception:
            pass

        return {
            "availability": "UNAVAILABLE",
            "facts": [],
            "hypotheses": [],
            "evidence": [],
        }

    def get_notes(self, obj: Complaint) -> list[dict]:
        return [
            {
                "id": str(note.id),
                "author": note.author_display_name,
                "createdAt": note.created_at.isoformat(),
                "text": note.text,
            }
            for note in obj.notes.all().order_by("created_at")
        ]

    def get_handoffs(self, obj: Complaint) -> list:
        try:
            from apps.handoffs.serializers import HandoffSerializer
            handoffs = obj.handoffs.all().select_related("team", "response").prefetch_related("attempts").order_by("-created_at")
            return HandoffSerializer(handoffs, many=True).data
        except Exception:
            return []

    def get_resolution(self, obj: Complaint) -> dict | None:
        if not obj.resolution_reported_at:
            return None
        reported_by_name = (
            getattr(obj.resolution_reported_by, "display_name", str(obj.resolution_reported_by))
            if obj.resolution_reported_by else "Staff"
        )
        verified_by_name = (
            getattr(obj.resolution_verified_by, "display_name", str(obj.resolution_verified_by))
            if obj.resolution_verified_by else None
        )
        return {
            "outcome": obj.resolution_outcome,
            "evidence": obj.resolution_evidence or None,
            "reportedAt": obj.resolution_reported_at.isoformat(),
            "reportedBy": reported_by_name,
            "verification": obj.resolution_verification,
            "verifiedAt": obj.resolution_verified_at.isoformat() if obj.resolution_verified_at else None,
            "verifiedBy": verified_by_name,
        }

    def get_reopenReason(self, obj: Complaint) -> str | None:
        return obj.reopen_reason if obj.reopen_reason else None

    def get_timeline(self, obj: Complaint) -> list[dict]:
        return [
            {
                "id": str(event.id),
                "at": event.at.isoformat(),
                "kind": event.kind,
                "title": event.title,
                "detail": event.detail or None,
                "actor": event.actor or None,
            }
            for event in obj.timeline_events.all().order_by("-at")
        ]
