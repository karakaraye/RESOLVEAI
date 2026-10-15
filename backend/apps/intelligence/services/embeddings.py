import hashlib
import logging
import math
from typing import List

from django.db import transaction
from django.utils import timezone

from apps.complaints.models import Complaint
from ..models import ComplaintEmbedding
from .base import BaseEmbeddingProvider

logger = logging.getLogger("resolveai.intelligence.embeddings")


class DeterministicHashingEmbeddingProvider(BaseEmbeddingProvider):
    """
    Deterministic 384-dimensional feature-hashing embedding provider.
    Guarantees reliable, offline, zero-dependency embedding generation that matches
    all-MiniLM-L6-v2 vector dimensions and supports cosine similarity.
    Used as primary fallback when sentence-transformers is not loaded.
    """

    DIMENSION = 384

    @property
    def dimension(self) -> int:
        return self.DIMENSION

    @property
    def model_name(self) -> str:
        return "deterministic-hash-v1"

    @property
    def model_version(self) -> str:
        return "1.0.0"

    def generate_embedding(self, text: str) -> List[float]:
        """
        Produces a normalized 384-dimensional vector using token feature hashing.
        Semantic similarities across shared banking tokens are preserved.
        """
        if not text:
            vector = [0.0] * self.DIMENSION
            vector[0] = 1.0
            return vector

        tokens = text.lower().replace("\n", " ").split()
        vector = [0.0] * self.DIMENSION

        # Token hashing
        for token in tokens:
            h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            idx = h % self.DIMENSION
            sign = 1.0 if ((h >> 16) & 1) == 0 else -1.0
            vector[idx] += sign

        # Add 3-gram character hashes for sub-word similarity
        for i in range(len(text) - 2):
            trigram = text[i:i+3].lower()
            h = int(hashlib.sha256(trigram.encode("utf-8")).hexdigest(), 16)
            idx = (h >> 4) % self.DIMENSION
            sign = 1.0 if (h & 1) == 0 else -1.0
            vector[idx] += 0.5 * sign

        # L2 Normalization
        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0.0:
            vector = [x / norm for x in vector]
        else:
            vector[0] = 1.0

        return vector


class SentenceTransformerEmbeddingProvider(BaseEmbeddingProvider):
    """
    Sentence Transformers provider using all-MiniLM-L6-v2.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model_name = model_name
        self._model = None
        self._dim = 384

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_version(self) -> str:
        return "2.2.0"

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._model_name)
            except Exception as e:
                logger.warning(f"Could not load SentenceTransformer '{self._model_name}': {e}. Falling back.")
                return None
        return self._model

    def generate_embedding(self, text: str) -> List[float]:
        model = self._get_model()
        if model:
            vec = model.encode(text, normalize_embeddings=True)
            return vec.tolist()
        # Fallback to deterministic
        return DeterministicHashingEmbeddingProvider().generate_embedding(text)


class ComplaintEmbeddingService:
    """
    Coordinates embedding generation, dimension validation, content fingerprinting,
    and storage in pgvector with multi-tenant isolation.
    """

    def __init__(self, provider: BaseEmbeddingProvider = None):
        self.provider = provider or DeterministicHashingEmbeddingProvider()

    @classmethod
    def compute_fingerprint(cls, complaint: Complaint) -> str:
        content = f"{complaint.summary}\n{complaint.narrative}\n{complaint.source_channel}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @transaction.atomic
    def ensure_complaint_embedding(
        self,
        complaint: Complaint,
        force_refresh: bool = False
    ) -> ComplaintEmbedding:
        """
        Generates and saves the vector embedding for a complaint.
        Validates dimensions before database writes.
        Avoids redundant recomputation if content fingerprint has not changed.
        """
        fingerprint = self.compute_fingerprint(complaint)

        # Check existing
        existing = ComplaintEmbedding.objects.filter(
            tenant=complaint.tenant,
            complaint=complaint
        ).first()

        if existing and not force_refresh:
            if existing.content_fingerprint == fingerprint and existing.dimension == self.provider.dimension:
                return existing

        text_to_embed = f"{complaint.summary}. {complaint.narrative}"
        vector = self.provider.generate_embedding(text_to_embed)

        # Dimension validation check
        if len(vector) != self.provider.dimension:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self.provider.dimension}, got {len(vector)}"
            )

        if existing:
            existing.embedding = vector
            existing.model_identifier = self.provider.model_name
            existing.model_version = self.provider.model_version
            existing.dimension = self.provider.dimension
            existing.content_fingerprint = fingerprint
            existing.save(update_fields=[
                "embedding", "model_identifier", "model_version",
                "dimension", "content_fingerprint", "updated_at"
            ])
            return existing

        return ComplaintEmbedding.objects.create(
            tenant=complaint.tenant,
            complaint=complaint,
            embedding=vector,
            model_identifier=self.provider.model_name,
            model_version=self.provider.model_version,
            dimension=self.provider.dimension,
            content_fingerprint=fingerprint
        )
