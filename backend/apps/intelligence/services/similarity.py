import logging
from typing import List

from django.db.models import F
from pgvector.django import CosineDistance

from apps.complaints.models import Complaint
from ..models import ComplaintEmbedding
from .base import SimilarComplaintCandidate
from .embeddings import ComplaintEmbeddingService

logger = logging.getLogger("resolveai.intelligence.similarity")


class SimilaritySearchService:
    """
    Performs tenant-isolated vector similarity search against PostgreSQL pgvector.
    Distinguishes semantic similarity from confirmed shared root cause.
    Never merges, alters, or deletes complaint records.
    """

    def __init__(self, embedding_service: ComplaintEmbeddingService = None):
        self.embedding_service = embedding_service or ComplaintEmbeddingService()

    def find_similar_complaints(
        self,
        complaint: Complaint,
        limit: int = 5,
        threshold: float = 0.50
    ) -> List[SimilarComplaintCandidate]:
        """
        Finds semantically similar complaints for the same bank tenant.
        Uses pgvector CosineDistance: similarity = 1.0 - cosine_distance.
        Strictly isolates results to complaint.tenant.
        """
        # Ensure target complaint has an embedding
        target_emb_record = self.embedding_service.ensure_complaint_embedding(complaint)
        target_vector = target_emb_record.embedding

        # Perform query on pgvector:
        # Distance ranges from 0.0 (identical) to 2.0 (opposite). Cosine similarity = 1 - distance.
        # Enforce strict multi-tenant filtering:
        similar_records = (
            ComplaintEmbedding.objects.filter(
                tenant=complaint.tenant
            )
            .exclude(complaint=complaint)
            .select_related("complaint", "complaint__category")
            .annotate(distance=CosineDistance("embedding", target_vector))
            .order_by("distance")[:limit * 2]
        )

        candidates: List[SimilarComplaintCandidate] = []
        for rec in similar_records:
            # In pgvector: similarity = 1.0 - distance
            # For unit vectors, distance in [0, 2], similarity in [-1, 1]
            similarity = round(max(0.0, 1.0 - float(rec.distance)), 4)
            if similarity < threshold:
                continue

            comp = rec.complaint
            cat_code = comp.category.code if comp.category else "UNCATEGORIZED"
            cat_label = comp.category.label if comp.category else "Uncategorized"

            # Generate transparent reason explaining association
            shared_category = (
                comp.category_id == complaint.category_id
                if comp.category and complaint.category
                else False
            )
            reason_parts = [f"Semantic narrative similarity ({int(similarity * 100)}% match)"]
            if shared_category:
                reason_parts.append(f"shared category '{cat_label}'")
            if comp.source_channel == complaint.source_channel:
                reason_parts.append(f"same channel ({comp.source_channel})")

            reason = " · ".join(reason_parts)
            comparison_details = (
                f"Candidate {comp.reference} reported on {comp.received_at.strftime('%Y-%m-%d')}: "
                f"'{comp.summary}'. Similar patterns detected in transaction and failure description."
            )

            candidates.append(
                SimilarComplaintCandidate(
                    complaint_id=str(comp.id),
                    reference=comp.reference,
                    summary=comp.summary,
                    category_code=cat_code,
                    category_label=cat_label,
                    similarity_score=similarity,
                    reason=reason,
                    comparison_details=comparison_details,
                )
            )

            if len(candidates) >= limit:
                break

        return candidates
