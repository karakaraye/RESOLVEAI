import hashlib
import logging
from typing import Tuple

from django.db import transaction
from django.utils import timezone

from apps.complaints.models import Complaint, ComplaintCategory
from ..models import AIProcessingJob, ComplaintEmbedding, ComplaintIntelligenceFinding
from .classifier import ComplaintClassificationService
from .embeddings import ComplaintEmbeddingService
from .root_cause import RootCauseAnalysisService
from .similarity import SimilaritySearchService

logger = logging.getLogger("resolveai.intelligence.coordinator")


class ComplaintIntelligenceCoordinator:
    """
    Coordinates end-to-end intelligence pipeline for a complaint:
    embedding generation, semantic similarity search, AI classification,
    and grounded root-cause analysis.
    Ensures idempotency, durable job tracking, and caching across unchanged cases.
    """

    def __init__(
        self,
        embedding_service: ComplaintEmbeddingService = None,
        similarity_service: SimilaritySearchService = None,
        classification_service: ComplaintClassificationService = None,
        root_cause_service: RootCauseAnalysisService = None,
    ):
        self.embedding_service = embedding_service or ComplaintEmbeddingService()
        self.similarity_service = similarity_service or SimilaritySearchService(self.embedding_service)
        self.classification_service = classification_service or ComplaintClassificationService()
        self.root_cause_service = root_cause_service or RootCauseAnalysisService()

    @classmethod
    def compute_fingerprint(cls, complaint: Complaint) -> str:
        # Changes when complaint text, linked transactions, or attached evidence change
        txn_refs = list(complaint.transaction_investigations.values_list("reference", flat=True))
        ev_refs = list(complaint.evidence_records.values_list("document_reference", flat=True))
        raw = f"{complaint.summary}|{complaint.narrative}|{sorted(txn_refs)}|{sorted(ev_refs)}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @transaction.atomic
    def process_complaint_intelligence(
        self,
        complaint: Complaint,
        force_refresh: bool = False,
        idempotency_key: str = None,
    ) -> Tuple[ComplaintIntelligenceFinding, AIProcessingJob]:
        """
        Executes or updates the intelligence pipeline for a complaint.
        Idempotent and durable: logs an AIProcessingJob record.
        """
        fprint = self.compute_fingerprint(complaint)
        job_key = idempotency_key or f"job-{complaint.id}-{fprint[:16]}"

        # 1. Check or create job
        job, created = AIProcessingJob.objects.select_for_update().get_or_create(
            tenant=complaint.tenant,
            idempotency_key=job_key,
            defaults={
                "complaint": complaint,
                "job_type": AIProcessingJob.JobType.FULL_INTELLIGENCE,
                "status": AIProcessingJob.Status.PROCESSING,
                "attempts": 1,
            }
        )

        # 2. Check if cached findings exist and are fresh
        existing_finding = ComplaintIntelligenceFinding.objects.filter(
            tenant=complaint.tenant,
            complaint=complaint
        ).first()

        if existing_finding and not force_refresh and existing_finding.content_fingerprint == fprint:
            if job.status != AIProcessingJob.Status.COMPLETED:
                job.status = AIProcessingJob.Status.COMPLETED
                job.save(update_fields=["status", "updated_at"])
            return existing_finding, job

        try:
            job.status = AIProcessingJob.Status.PROCESSING
            job.attempts += 1
            job.save(update_fields=["status", "attempts", "updated_at"])

            # Step A: Ensure embedding
            self.embedding_service.ensure_complaint_embedding(complaint, force_refresh=force_refresh)

            # Step B: Semantic similarity
            similar_candidates = self.similarity_service.find_similar_complaints(complaint, limit=5)

            # Step C: Classification
            classification = self.classification_service.classify_complaint(complaint)

            # Match category entity if available
            suggested_cat = ComplaintCategory.objects.filter(
                code=classification.suggested_category_code
            ).first()

            # Step D: Root Cause Analysis
            root_cause = self.root_cause_service.analyze_complaint(complaint, similar_candidates)

            # Step E: Upsert findings record
            if existing_finding:
                finding = existing_finding
                finding.availability = root_cause.availability
                finding.confidence = root_cause.confidence
                finding.suggested_category = suggested_cat
                finding.suggested_category_code = classification.suggested_category_code
                finding.suggested_priority = classification.suggested_priority
                finding.possible_responsible_team = classification.possible_responsible_team
                finding.explanation = classification.explanation
                finding.possible_cause = root_cause.possible_cause
                finding.recommended_next_step = root_cause.recommended_next_step
                finding.facts = root_cause.facts
                finding.hypotheses = root_cause.hypotheses
                finding.evidence_references = root_cause.evidence_references
                finding.missing_information = root_cause.missing_information
                finding.conflicting_information = root_cause.conflicting_information
                finding.model_identifier = root_cause.model_identifier
                finding.model_version = root_cause.model_version
                finding.content_fingerprint = fprint
                finding.processing_timestamp = timezone.now()
                finding.save()
            else:
                finding = ComplaintIntelligenceFinding.objects.create(
                    tenant=complaint.tenant,
                    complaint=complaint,
                    availability=root_cause.availability,
                    confidence=root_cause.confidence,
                    suggested_category=suggested_cat,
                    suggested_category_code=classification.suggested_category_code,
                    suggested_priority=classification.suggested_priority,
                    possible_responsible_team=classification.possible_responsible_team,
                    explanation=classification.explanation,
                    possible_cause=root_cause.possible_cause,
                    recommended_next_step=root_cause.recommended_next_step,
                    facts=root_cause.facts,
                    hypotheses=root_cause.hypotheses,
                    evidence_references=root_cause.evidence_references,
                    missing_information=root_cause.missing_information,
                    conflicting_information=root_cause.conflicting_information,
                    model_identifier=root_cause.model_identifier,
                    model_version=root_cause.model_version,
                    content_fingerprint=fprint,
                    processing_timestamp=timezone.now(),
                )

            job.status = AIProcessingJob.Status.COMPLETED
            job.error_message = ""
            job.save(update_fields=["status", "error_message", "updated_at"])

            logger.info(f"Intelligence processing completed for complaint {complaint.reference}")
            return finding, job

        except Exception as e:
            job.status = AIProcessingJob.Status.FAILED
            job.error_message = str(e)
            job.save(update_fields=["status", "error_message", "updated_at"])
            logger.error(f"Intelligence processing failed for complaint {complaint.reference}: {e}", exc_info=True)
            raise
