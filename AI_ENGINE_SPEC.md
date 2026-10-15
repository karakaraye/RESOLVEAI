# ResolveAI AI Engine & Machine Learning Architecture Specification

> **Document Version:** 2.0.0  
> **Subsystem:** `apps.intelligence`  
> **Technologies:** Python, Sentence Transformers, pgvector / Cosine Similarity, OpenAI API / Local Fallbacks  
> **Design Pattern:** Strategy / Replaceable Provider Interfaces  
> **Status:** APPROVED / IMPLEMENTATION-READY  

---

## 1. Architectural Principles & Resilience Invariants

The ResolveAI AI subsystem operates under five non-negotiable architectural invariants:

1. **Server Resilience / Zero-Downtime Fallback:** The Django core backend and operator case management workspace **must never crash or block** when OpenAI, external LLMs, or the PostgreSQL `pgvector` extension are unavailable.
2. **Provider & Dimension Independence:** Vector dimensions (e.g. 384 vs 1536) and specific model names (`gpt-4o`, `text-embedding-3-small`) are strictly decoupled from database schemas and business logic.
3. **Truth vs. Hypothesis Boundary:** The system strictly separates confirmed facts (derived from authoritative core banking ledger records) from speculative AI hypotheses.
4. **Human-in-the-Loop Authority:** AI suggestions (such as incident clustering or forwarding recommendations) can be confirmed, dismissed, or overridden by operators.
5. **Privacy & Data Minimization:** Customer PII (Full Account Numbers, BVN/NIN, PINs) is masked prior to sending data to external LLM providers.

```
+----------------------------------------------------------------------------------------------------+
|                                    AI SUBSYSTEM ARCHITECTURE                                       |
+----------------------------------------------------------------------------------------------------+

                          [ Complaint Narrative & Transaction Facts ]
                                               |
                                               v
                          +-----------------------------------------+
                          |      PII Tokenization & Sanitizer       |
                          +-----------------------------------------+
                                               |
                     +-------------------------+-------------------------+
                     |                                                   |
                     v                                                   v
        [ Embedding Subsystem ]                             [ Reasoning Subsystem ]
        - apps.intelligence.interfaces                      - apps.intelligence.interfaces
          .EmbeddingProvider                                  .LLMProvider
                     |                                                   |
        +------------+------------+                         +------------+------------+
        |                         |                         |                         |
        v                         v                         v                         v
 [ SentenceTransformer ]   [ OpenAIProvider ]       [ OpenAILLMProvider ]    [ HeuristicRuleProvider ]
 (Local CPU, 384 dims)     (Remote, 1536 dims)      (GPT-4o JSON Schema)     (Offline Regex/Rules)
        |                         |                         |                         |
        +------------+------------+                         +------------+------------+
                     |                                                   |
                     v                                                   v
          [ pgvector / InMemory ]                           [ Pydantic FindingDTO Schema ]
          - Semantic Similarity                             - Category, Possible Cause
          - Incident Clustering                             - Confirmed Facts vs Hypotheses
          - Duplicate Detection                             - Confidence Calibration
```

---

## 2. Replaceable Provider Interfaces

All AI operations are governed by abstract base classes defined in `apps/intelligence/interfaces.py`.

### 2.1 Embedding Provider Interface
```python
# apps/intelligence/interfaces.py
from abc import ABC, abstractmethod

class EmbeddingProvider(ABC):
    """Abstract contract for text vectorization."""
    
    @abstractmethod
    def generate_embedding(self, text: str) -> list[float]:
        """Convert input text into a dense vector."""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the vector dimension produced by this model."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Identifier of the active model."""
        pass
```

#### Concrete Implementations
1. **`SentenceTransformerProvider` (Default Local):**
   - Model: `sentence-transformers/all-MiniLM-L6-v2`
   - Dimension: `384`
   - Execution: Local CPU inference inside the Celery AI worker (~15ms per ticket). No network dependencies.
2. **`OpenAIEmbeddingProvider` (High Capacity):**
   - Model: `text-embedding-3-small`
   - Dimension: `1536`
   - Execution: Remote API call over HTTPS with exponential backoff.
3. **`NullEmbeddingProvider` (Offline Fallback):**
   - Active when embedding models are completely disabled or installing dependencies is constrained.
   - Returns empty vector; skips vector clustering and engages keyword matching.

---

### 2.2 Reasoning & Root-Cause Analysis (LLM) Interface
```python
# apps/intelligence/interfaces.py
from pydantic import BaseModel, Field

class FindingDTO(BaseModel):
    availability: str = Field(..., description="AVAILABLE, UNAVAILABLE, or LOW_CONFIDENCE")
    category: str | None = None
    possible_cause: str | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    recommended_next_step: str | None = None
    facts: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)

class LLMProvider(ABC):
    """Abstract contract for root cause investigation and structured extraction."""
    
    @abstractmethod
    def analyze_complaint(self, narrative: str, transaction_facts: list[dict], source_status: str) -> FindingDTO:
        """Analyze grievance and transaction logs to produce root cause findings."""
        pass
```

#### Concrete Implementations
1. **`OpenAILLMProvider` (Primary):**
   - Uses OpenAI API (`gpt-4o` or `gpt-4o-mini`) with Structured Output enforcing `FindingDTO` JSON schema.
   - Extracts corroborated facts from core banking transactions and separates unverified customer claims into hypotheses.
2. **`HeuristicRuleProvider` (Automatic Offline Fallback):**
   - Engaged automatically if OpenAI API keys are absent, rate-limited, or network fails.
   - Executes banking regex rules:
     - Keyword `"debit"` + transaction `"pending"` $\rightarrow$ Possible Cause: `"Interbank switch delay"`.
     - Keyword `"atm"` + `"not dispensed"` $\rightarrow$ Possible Cause: `"ATM cash retract error"`.
     - Confidence capped at `0.45` (`availability = "LOW_CONFIDENCE"`).

---

## 3. Storage & Vector Database Independence

To avoid binding the PostgreSQL schema permanently to a fixed vector dimension:

1. **Dynamic Embedding Store (`intelligence_embeddingstore`):**
   - The table stores `model_name` and `dimension` alongside `vector_data`.
   - In PostgreSQL with `pgvector`:
     ```sql
     -- If settings.AI_EMBEDDING_PROVIDER == 'sentence_transformers'
     ALTER TABLE intelligence_embeddingstore ADD COLUMN vector_data vector(384);
     ```
   - In environments where `pgvector` is unavailable:
     - The column falls back to `JSONB` containing float arrays.
     - Cosine similarity is computed in Python/NumPy for small candidate batches.

---

## 4. Semantic Similarity & Incident Clustering Algorithm

### 4.1 Duplicate Complaint Detection
When a new complaint arrives:
1. Generate embedding $v_{new}$ of the complaint narrative.
2. Perform a nearest-neighbor cosine search across open complaints within the tenant over the last 72 hours:
   $$\text{cosine\_distance}(u, v) = 1 - \frac{u \cdot v}{\|u\|_2 \|v\|_2}$$
3. Threshold rules:
   - Distance $< 0.10$: Flagged as **"Probable Duplicate"** from same customer/channel.
   - Distance between $0.10$ and $0.25$: Added as **"Related Record"**.

### 4.2 Shared Incident Clustering
1. Unresolved complaints within a 6-hour sliding window are embedded.
2. If $\ge 5$ complaints share a common high similarity ($> 0.80$) and identical transaction failure codes (e.g. switch timeout code `91`), the system triggers the **Incident Grouping Task**.
3. Creates or links to an `Incident` (e.g., `INC-TEST-7 · Interbank transfers delayed`).
4. Adds complaints to `IncidentComplaint` with `review_status = 'PENDING_REVIEW'`.

---

## 5. Structured Prompt Template & Confidence Calibration

### 5.1 System Prompt (OpenAI Structured Extraction)
```text
You are the senior banking dispute resolution intelligence engine for ResolveAI BIIRS.
Analyze the customer complaint narrative and verified transaction facts from the core banking system.

RULES:
1. Facts must ONLY contain statements directly confirmed by core banking or payment switch logs.
2. If customer claims a debit occurred but core banking shows no debit, do NOT list it as a fact. List it as a hypothesis under investigation.
3. If the core banking source status is STALE or UNAVAILABLE, you MUST cap confidence at <= 0.60.
4. Output valid JSON matching the exact schema.
```

### 5.2 Confidence Calibration Formula
$$\text{Confidence} = w_s \cdot S_{\text{freshness}} + w_t \cdot T_{\text{match}} + w_m \cdot M_{\text{similarity}}$$
Where:
- $S_{\text{freshness}}$: Source status weight (`AVAILABLE`: 1.0, `STALE`: 0.5, `UNAVAILABLE`: 0.0).
- $T_{\text{match}}$: Ledger transaction match strength (exact account, timestamp, and amount: 1.0; no ledger record: 0.2).
- $M_{\text{similarity}}$: Incident cluster embedding similarity score.
- Weights: $w_s = 0.4$, $w_t = 0.4$, $w_m = 0.2$.

#### Confidence UI Mapping
- Confidence $\ge 0.70$: `availability = "AVAILABLE"` (Renders `accent` badge: e.g. `82% confidence`).
- Confidence $0.40 - 0.69$: `availability = "LOW_CONFIDENCE"` (Renders `warning` badge: "BIIRS isn’t confident about these findings. Treat them as leads, not conclusions.").
- Confidence $< 0.40$ or Failure: `availability = "UNAVAILABLE"` (Renders `neutral` badge: "Automated findings aren’t available for this complaint. Review the evidence above manually; every case action still works.").

---

## 6. Safe Synthetic Banking Data for Development & Testing

To avoid using actual cardholder data (PAN) or customer PII, all test fixtures and simulated feeds use synthetic generators following Central Bank masking standards:

- **Customer Identifiers:** Masked tokens `•••• 1234` (last 4 digits only).
- **Accounts:** Simulated 10-digit NUBAN numbers (`0123456789`).
- **Transaction References:** Synthetic prefixes (`TXN-TEST-90311`, `CC-TEST-55821`).
- **Amounts:** Standard denominations with realistic currency codes (`NGN 45,000.00`).
