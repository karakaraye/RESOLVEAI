from rest_framework import serializers

from .models import AIProcessingJob, ComplaintIntelligenceFinding


class FindingSerializer(serializers.ModelSerializer):
    """
    Serializes ComplaintIntelligenceFinding strictly conforming to
    the frontend `Finding` TypeScript type in `src/lib/api/types.ts`:
      availability: "AVAILABLE" | "UNAVAILABLE" | "LOW_CONFIDENCE";
      category?: string;
      possibleCause?: string;
      confidence?: number;
      recommendedNextStep?: string;
      facts: string[];
      hypotheses: string[];
      evidence: string[];
    """
    category = serializers.SerializerMethodField()
    possibleCause = serializers.CharField(source="possible_cause", read_only=True)
    recommendedNextStep = serializers.CharField(source="recommended_next_step", read_only=True)
    evidence = serializers.ListField(source="evidence_references", read_only=True)

    class Meta:
        model = ComplaintIntelligenceFinding
        fields = [
            "availability",
            "category",
            "possibleCause",
            "confidence",
            "recommendedNextStep",
            "facts",
            "hypotheses",
            "evidence",
        ]

    def get_category(self, obj) -> str | None:
        if obj.suggested_category:
            return obj.suggested_category.label
        return obj.suggested_category_code or None


class ClassificationSuggestionSerializer(serializers.Serializer):
    suggestedCategory = serializers.CharField(source="suggested_category_code")
    suggestedSubcategory = serializers.CharField(source="suggested_subcategory", allow_null=True)
    suggestedPriority = serializers.CharField(source="suggested_priority")
    possibleResponsibleTeam = serializers.CharField(source="possible_responsible_team")
    explanation = serializers.CharField()
    modelIdentifier = serializers.CharField(source="model_identifier")
    modelVersion = serializers.CharField(source="model_version")
    confidence = serializers.FloatField()
    isLowConfidence = serializers.BooleanField(source="is_low_confidence")
    processedAt = serializers.DateTimeField(source="processed_at")


class SimilarComplaintSerializer(serializers.Serializer):
    complaintId = serializers.CharField(source="complaint_id")
    reference = serializers.CharField()
    summary = serializers.CharField()
    categoryCode = serializers.CharField(source="category_code")
    categoryLabel = serializers.CharField(source="category_label")
    similarityScore = serializers.FloatField(source="similarity_score")
    reason = serializers.CharField()
    comparisonDetails = serializers.CharField(source="comparison_details")


class AIProcessingJobSerializer(serializers.ModelSerializer):
    jobType = serializers.CharField(source="job_type")
    createdAt = serializers.DateTimeField(source="created_at")
    updatedAt = serializers.DateTimeField(source="updated_at")

    class Meta:
        model = AIProcessingJob
        fields = [
            "id",
            "jobType",
            "status",
            "attempts",
            "max_attempts",
            "error_message",
            "createdAt",
            "updatedAt",
        ]
