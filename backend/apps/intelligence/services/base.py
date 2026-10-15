from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class ClassificationResult:
    suggested_category_code: str
    suggested_subcategory: Optional[str]
    suggested_priority: str
    possible_responsible_team: str
    explanation: str
    model_identifier: str
    model_version: str
    confidence: float
    is_low_confidence: bool
    processed_at: datetime


@dataclass
class RootCauseResult:
    availability: str  # "AVAILABLE", "UNAVAILABLE", "LOW_CONFIDENCE"
    possible_cause: str
    recommended_next_step: str
    confidence: float
    facts: List[str] = field(default_factory=list)
    hypotheses: List[str] = field(default_factory=list)
    evidence_references: List[str] = field(default_factory=list)
    missing_information: List[str] = field(default_factory=list)
    conflicting_information: List[str] = field(default_factory=list)
    model_identifier: str = "resolveai-root-cause-v1"
    model_version: str = "1.0.0"
    processed_at: Optional[datetime] = None


@dataclass
class SimilarComplaintCandidate:
    complaint_id: str
    reference: str
    summary: str
    category_code: str
    category_label: str
    similarity_score: float
    reason: str
    comparison_details: str


class BaseComplaintClassifier(ABC):
    @abstractmethod
    def classify(
        self,
        summary: str,
        narrative: str,
        valid_categories: List[str],
        valid_priorities: List[str],
    ) -> ClassificationResult:
        """Classifies a complaint into a valid banking category and priority."""
        pass


class BaseEmbeddingProvider(ABC):
    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimension produced by this provider."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Identifier of the embedding model."""
        pass

    @property
    @abstractmethod
    def model_version(self) -> str:
        """Version string of the embedding model."""
        pass

    @abstractmethod
    def generate_embedding(self, text: str) -> List[float]:
        """Produces a dense normalized float vector from text."""
        pass


class BaseRootCauseAnalyzer(ABC):
    @abstractmethod
    def analyze(
        self,
        complaint,
        similar_complaints: List[SimilarComplaintCandidate],
        transactions: list,
        evidence: list,
    ) -> RootCauseResult:
        """Performs evidence-grounded root-cause investigation."""
        pass
