# ResolveAI Architecture Decision Records (ADRs)

> **Document Version:** 2.0.0  
> **System:** Banking Incident Intelligence & Resolution System (BIIRS)  
> **Author:** Senior Software Architect & Security Engineer, ResolveAI  
> **Status:** APPROVED / IMPLEMENTATION-READY  

---

## Index of Architectural Decision Records

- [ADR-001: Separation of Complaints, Incidents, Evidence, and Transactions](#adr-001-separation-of-complaints-incidents-evidence-and-transactions)
- [ADR-002: Customer Communication Engine & Verification-Gated Notifications](#adr-002-customer-communication-engine--verification-gated-notifications)
- [ADR-003: Session Authentication, CSRF Defense-in-Depth & Network Topology](#adr-003-session-authentication-csrf-defense-in-depth--network-topology)
- [ADR-004: Development Authentication vs Production Enterprise SSO](#adr-004-development-authentication-vs-production-enterprise-sso)
- [ADR-005: Decoupled, Provider-Independent AI Architecture with Resilient Fallback](#adr-005-decoupled-provider-independent-ai-architecture-with-resilient-fallback)
- [ADR-006: Transactional Outbox Pattern & Database-Backed Idempotency Engine](#adr-006-transactional-outbox-pattern--database-backed-idempotency-engine)
- [ADR-007: Bank-Agnostic Core Banking & Payment Switch Integration Adapters](#adr-007-bank-agnostic-core-banking--payment-switch-integration-adapters)
- [ADR-008: Frontend Wire Compatibility & Maker-Checker Security Invariants](#adr-008-frontend-wire-compatibility--maker-checker-security-invariants)

---

## ADR-001: Separation of Complaints, Incidents, Evidence, and Transactions

### Context
In retail banking, a single root cause (e.g., an interbank switch timeout between 09:00 and 11:00) can generate hundreds of individual customer complaints. In the initial prototype, complaints and incidents were conflated, risking loss of individual customer accountability, transaction tracking, and compliance timelines.

### Decision
We strictly decouple the domain into separate relational entities:
1. **`Complaint`**: Represents an individual customer's grievance, regulatory timeline, customer reference number, and communication history.
2. **`Incident`**: Represents an operational or infrastructure failure (e.g., "NIBSS Outward Transfer Degraded").
3. **`IncidentComplaint`**: An explicit join entity recording association confidence, discovery source (AI-suggested vs. Operator-linked), and human verification status (`PENDING_REVIEW`, `CONFIRMED`, `DISMISSED`).
4. **`TransactionInvestigation`**: Represents a specific financial movement being investigated, holding core banking ledger data, switch statuses, and detected conflicts.
5. **`Evidence`**: Authoritative proof (e.g., core banking debit logs, reversal receipts, switch ACK/NACK responses) tied to an investigation.
6. **`ResolutionOutcome`**: The verified resolution record requiring independent operator sign-off.

### Consequences
- Resolving an `Incident` does **not** automatically resolve linked `Complaint` records. Each complaint must have its individual outcome verified before closing.
- Operators can review and approve or reject AI-suggested incident clusters without corrupting case histories.
- Full regulatory auditability for the Central Bank and compliance auditors is guaranteed.

---

## ADR-002: Customer Communication Engine & Verification-Gated Notifications

### Context
Banks must communicate transparently with complainants across multiple channels (SMS, Email, WhatsApp). Sending incorrect resolution notices because an underlying system incident was mitigated—when a customer's specific funds remain un-reversed—creates acute regulatory penalties and customer distrust.

### Decision
We introduce a dedicated Django `apps.communications` application:
1. **Automated Event Triggers**:
   - Complaint Ingestion $\rightarrow$ Immediate Customer Acknowledgement with unique Complaint Reference Number.
   - Formal Status Progressions $\rightarrow$ Operator-approved progress notices.
   - Individual Outcome Verified $\rightarrow$ Final Customer Resolution Notice with verified outcome summary.
2. **Incident-to-Complaint Resolution Gate**:
   - An incident being marked `RESOLVED` triggers a background task that transitions linked complaints to `NEEDS_ACTION` or `AWAITING_VERIFICATION`, prompting individual ledger checks.
   - **Outbound final resolution messages are permanently barred** from dispatch until the individual complaint's `ResolutionOutcome` is approved by an authorized verifier (Maker-Checker).
3. **Template Engine & De-duplication**:
   - Dynamic parameter substitution using validated templates.
   - Message fingerprint hashing (`SHA-256(tenant_id + complaint_id + template_id + recipient)`) within a 15-minute sliding window to prevent duplicate dispatch during retries.

### Consequences
- Zero premature customer resolution messages.
- Full delivery status tracking (`QUEUED`, `DISPATCHED`, `DELIVERED`, `FAILED`).
- Audit trail of all outbound customer communications.

---

## ADR-003: Session Authentication, CSRF Defense-in-Depth & Network Topology

### Context
The Next.js frontend uses cookie-based authentication (`credentials: "include"`) and passes `X-BIIRS-Request: 1` on non-GET calls. Relying solely on a custom header is vulnerable to misconfigured reverse proxies and does not meet tier-1 banking security requirements.

### Decision
We implement a defense-in-depth security model:
1. **Network Topology**:
   - **Development**: Next.js development server runs on `http://localhost:3000`. Django backend runs on `http://localhost:8000`. Next.js rewrites `/api/v1/:path*` to `http://localhost:8000/api/v1/:path*`, establishing a **same-origin proxy** environment that eliminates cross-origin browser restrictions.
   - **Production**: Frontend and Backend are hosted on approved same-site subdomains (e.g., `workspace.resolveai.bank` and `api.resolveai.bank`) or behind a unified API gateway (e.g., Cloudflare/AWS ALB) where `/api/` routes directly to Django.
2. **Multi-Layered CSRF Defense**:
   - **Layer 1 (Standard Django CSRF Token):** The backend issues an HTTP-only or accessible `csrftoken` cookie. For SPA compatibility, the Django session endpoint (`/api/v1/session`) returns the CSRF token in an HTTP header (`X-CSRFToken`) and response body, which the frontend API client injects on state-changing requests.
   - **Layer 2 (Custom Request Header):** Enforce `X-BIIRS-Request: 1` as an additional anti-CSRF check. Cross-origin HTML `<form>` submissions cannot attach custom headers.
   - **Layer 3 (Cookie Attributes):** `SameSite=Lax` (or `Strict`), `Secure=True` (in production), and `HttpOnly=True` on session cookies.
3. **Tenant & Record Authorization**:
   - Every database query in Django is scoped to `request.user.tenant`.
   - Record-level permissions check `allowedActions` server-side before executing any mutation.

### Consequences
- Complete mitigation of cross-site request forgery and session hijacking.
- Transparent developer experience in development via Next.js proxy rewrites without requiring complex CORS configurations.

---

## ADR-004: Development Authentication vs Production Enterprise SSO

### Context
Production deployments must integrate with the bank's corporate Identity Provider (Azure AD, Okta, Ping Identity) using OpenID Connect (OIDC) or SAML 2.0. However, during local development and automated CI testing, external SSO is unavailable.

### Decision
1. **Architecture Abstraction**:
   - `apps.accounts.services.AuthService`: Defines abstract authentication contract.
   - `OIDCAuthService`: Production implementation exchanging authorization codes for tokens with enterprise IdPs.
   - `DevAuthService`: Development-only implementation providing instant test persona switching (`Test Operator`, `Senior Verifier`, `Customer Care Lead`).
2. **Security Controls**:
   - The development authentication endpoint (`POST /api/v1/auth/dev-login`) is strictly registered only when `settings.DEBUG = True` and `settings.ALLOW_DEV_AUTH = True`.
   - In production (`DJANGO_ENV=production`), the dev auth URLs are excluded from Django's URL routing at startup, and middleware will reject any invocation with HTTP 404.

### Consequences
- Fast, reliable developer and CI onboarding without mocking external OAuth servers.
- Guaranteed protection against backdoor authentication in production environments.

---

## ADR-005: Decoupled, Provider-Independent AI Architecture with Resilient Fallback

### Context
The AI subsystem performs semantic search, complaint clustering, incident discovery, and root cause investigation. If OpenAI encounters rate limits or if PostgreSQL's `pgvector` extension is absent in a target environment, the core banking case management workflow must continue without degradation.

### Decision
1. **Provider-Agnostic Interfaces**:
   - `apps.intelligence.interfaces.EmbeddingProvider`: Abstract interface for vector generation (implementations: `SentenceTransformerProvider`, `OpenAIEmbeddingProvider`, `NullEmbeddingProvider`).
   - `apps.intelligence.interfaces.LLMProvider`: Abstract interface for reasoning and root cause extraction (implementations: `OpenAILLMProvider`, `AnthropicLLMProvider`, `HeuristicFallbackProvider`).
2. **Dimension-Agnostic Embeddings**:
   - Vector dimensions are not hardcoded. The database model `EmbeddingStore` stores embeddings as variable arrays or dynamically configured `VectorField(dimensions=settings.AI_EMBEDDING_DIMENSION)`.
3. **Graceful Fallback Pipeline**:
   - If vector search or the LLM fails, the system catches the exception and falls back to rule-based keyword matching and heuristic routing.
   - The API returns `findings.availability = "LOW_CONFIDENCE"` or `"UNAVAILABLE"`.
   - The Next.js frontend gracefully renders fallback banners while all case actions (`Assign`, `Forward`, `Add Note`, `Record Outcome`) remain fully operable.

### Consequences
- No vendor lock-in to OpenAI or specific embedding dimensions.
- Zero downtime on case management during AI provider outages.
- Clear separation between unverified AI hypotheses and verified banking facts.

---

## ADR-006: Transactional Outbox Pattern & Database-Backed Idempotency Engine

### Context
Banking operations must guarantee exactly-once processing. Network retries, browser reloads, or Celery worker crashes must never result in duplicate debit investigations, duplicate forwardings, or duplicate customer SMS messages.

### Decision
1. **Database-Backed Idempotency Engine**:
   - Every mutating request supplies an `Idempotency-Key: <UUID>`.
   - `apps.common.middleware.IdempotencyMiddleware` stores the request hash, processing state (`PENDING`, `COMPLETED`), HTTP status, and response payload in the PostgreSQL `IdempotencyRecord` table.
   - Concurrent requests with the same key wait or receive HTTP 409 Conflict.
   - Completed requests return the stored cached response without re-executing business logic.
2. **Transactional Outbox Pattern**:
   - Side effects (sending customer SMS, calling external bank APIs, triggering AI embedding jobs) are **never** executed synchronously inside HTTP request transactions.
   - State mutations write an `OutboxMessage` record within the same PostgreSQL transaction as the complaint update.
   - A dedicated Celery worker polls and publishes outbox messages to Redis/external channels with exponential backoff and dead-letter queueing.

### Consequences
- Atomic state changes: If the database transaction rolls back, no outbound messages are sent.
- Resilient recovery: If external APIs are down, messages remain queued in the outbox and replay upon service restoration.

---

## ADR-007: Bank-Agnostic Core Banking & Payment Switch Integration Adapters

### Context
Every bank uses different core banking systems (Finacle, Flexcube, Temenos T24, BaNCS) and interbank switch networks (NIBSS, Interswitch, GhIPSS). The core ResolveAI platform must not be hardcoded to any proprietary bank interface.

### Decision
1. **Adapter Interface (`BankSystemAdapter`)**:
   - Define a clean interface for querying account status, fetching transaction ledgers, checking switch confirmation, and submitting investigation requests.
2. **Hackathon / Test Simulation Adapter**:
   - Deliver `SimulatedBankAdapter` providing deterministic responses, simulated delays, core banking / switch status conflicts, and stale data indicators without requiring live bank VPNs or credentials.
3. **Authoritative Evidence Requirement**:
   - Transaction outcomes must cite verifiable evidence (journal sequence number, switch session ID). The system rejects closing investigations based on unverified customer claims alone.

### Consequences
- Plug-and-play integration for any banking client by writing a single adapter class.
- Safe, realistic testing and demonstrations during hackathons and technical reviews.

---

## ADR-008: Frontend Wire Compatibility & Maker-Checker Security Invariants

### Context
The Next.js frontend has been developed and validated with Playwright end-to-end tests. Modifying existing routes, wire types, status strings, or component contracts risks breaking the frontend.

### Decision
1. **Frontend Wire Preservation**:
   - The Django API endpoints, query parameters, JSON payloads, and error schemas will strictly mirror the existing contracts in `src/lib/api/types.ts` and `src/lib/api/endpoints.ts`.
   - Technical identifiers (`BIIRS`, `X-BIIRS-Request`) are preserved in the wire protocol to ensure 100% compatibility.
2. **Enforcement of Maker-Checker Principle**:
   - The backend validates that `request.user.id != complaint.resolution.reported_by.id` when calling `POST /complaints/{id}/resolution/verification`.
   - Self-verification is rejected with HTTP 403 Forbidden.
   - The frontend's `allowedActions` array returned by the API dynamically excludes `VERIFY_OUTCOME` if the viewing operator was the reporter.

### Consequences
- Existing frontend works out-of-the-box against the Django backend without code modification.
- Regulatory compliance with tier-1 banking maker-checker separation of duties is cryptographically and logically guaranteed.
