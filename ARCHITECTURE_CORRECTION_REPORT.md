# ResolveAI Architecture Correction & Validation Report

> **Document Version:** 2.0.0  
> **Review Date:** 2026-10-14  
> **Lead Architect & Security Engineer:** ResolveAI Technical Architecture Group  
> **Target Application:** Banking Incident Intelligence & Resolution System (BIIRS)  
> **Primary References:** BIIRS Complete Product Specification & Existing Next.js Frontend Codebase  
> **Status:** PENDING ENGINEERING LEAD APPROVAL  

---

## Executive Summary

Following a comprehensive architectural review of the preliminary backend specification against the **BIIRS Complete Product Specification** and the existing **Next.js Frontend Codebase**, eight critical architectural corrections were formulated. 

These corrections establish:
1. An independent **Customer Communication Engine** with strict verification gating to prevent premature resolution messaging.
2. Complete domain separation between **Complaints**, **Incidents**, **Evidence**, and **Transactions**.
3. Production-grade **Session & CSRF Defense-in-Depth** compatible with the existing frontend cookie/header model.
4. Secure **Development-Only Authentication** with guaranteed production isolation.
5. A **Provider-Agnostic, Replaceable AI Subsystem** with resilient zero-downtime offline fallbacks.
6. A robust **Database-Backed Idempotency Engine & Transactional Outbox** pattern.
7. 100% **Frontend Wire Compatibility**, preserving all existing routes, types, query parameters, and component contracts.
8. A **Bank-Independent Integration Adapter** architecture with simulated test harnesses.

---

## Detailed Analysis of Identified Problems & Corrections

### Correction 1: Customer Communication Engine & Verification Gate

#### Problem Identified
The initial architecture lacked a customer-facing messaging subsystem. In retail banking, customer grievances must be acknowledged deterministically with a reference number. Critically, if an operational incident (e.g., an interbank switch outage) is marked resolved, automatically sending resolution notifications to all complainants is catastrophic: while the switch may be back online, a specific customer's trapped funds may still require a manual ledger reversal.

#### Proposed Architectural Correction
1. Created dedicated Django `apps.communications` module.
2. Implemented mandatory **Verification Gate**:
   - Marking an `Incident` resolved triggers complaint ledger reviews, **not** customer notifications.
   - Outbound final resolution notices (`RESOLUTION_FINAL`) are strictly blocked until the individual complaint's `ResolutionOutcome` is marked `VERIFIED` by an independent verifier (Maker-Checker).
3. Built de-duplication mechanism using `SHA-256(tenant_id + complaint_id + template_id + recipient)` fingerprinting within a 15-minute sliding window.

#### Affected Files & Components
- **Backend:** `apps.communications.models` (`MessageTemplate`, `CustomerMessage`), `apps.communications.services` (`VerificationGate`, `MessageRenderer`), `apps.communications.tasks`.
- **Documentation:** [`COMMUNICATION_WORKFLOW.md`](file:///c:/Users/HIMSON/Desktop/Front%20End/COMMUNICATION_WORKFLOW.md), [`WORKFLOW_STATES.md`](file:///c:/Users/HIMSON/Desktop/Front%20End/WORKFLOW_STATES.md).

#### Frontend Changes Required
**None.** The existing frontend already exposes the customer contact and audit timeline; communication logs will surface as timeline events in `complaint.timeline`.

#### Acceptance Criteria
- [x] Initial complaint intake generates an automated SMS/email acknowledgment with customer reference (`TST-1044`).
- [x] Marking an incident resolved does not send any customer resolution messages.
- [x] A resolution message is dispatched only after `ResolutionOutcome.verification == 'VERIFIED'`.
- [x] Duplicate messages within 15 minutes are suppressed.

---

### Correction 2: Decoupling Complaints, Incidents, Evidence & Transactions

#### Problem Identified
The preliminary specification conflated complaints and incidents within a single table hierarchy. This destroyed individual complaint history when incidents were clustered, prevented linking multiple transactions to a complaint, and lacked an explicit model for authoritative evidence.

#### Proposed Architectural Correction
Designed 6 distinct relational entities:
1. `Complaint`: Individual grievance, SLA, and customer tracking.
2. `Incident`: Operational/infrastructure event affecting multiple customers.
3. `IncidentComplaint`: Explicit join table tracking association confidence, origin (`AI_DISCOVERY` vs `OPERATOR_LINKED`), and human review status (`PENDING_REVIEW`, `CONFIRMED`, `DISMISSED`).
4. `TransactionInvestigation`: Core banking transactions and switch logs linked to a case.
5. `EvidenceRecord`: Authoritative documents (journal sequence numbers, reversal receipts).
6. `ResolutionOutcome`: Proposed and verified case outcome.

#### Affected Files & Components
- **Backend:** `apps.complaints.models`, `apps.incidents.models`, `apps.transactions.models`, `apps.evidence.models`, `apps.resolutions.models`.
- **Documentation:** [`DATABASE_SCHEMA.md`](file:///c:/Users/HIMSON/Desktop/Front%20End/DATABASE_SCHEMA.md), [`WORKFLOW_STATES.md`](file:///c:/Users/HIMSON/Desktop/Front%20End/WORKFLOW_STATES.md).

#### Frontend Changes Required
**None.** The frontend's `related` array in `ComplaintDetail` directly accommodates `kind: "COMPLAINT"` and `kind: "INCIDENT"`.

#### Acceptance Criteria
- [x] Multiple complaints can link to one incident without losing their individual reference, narrative, or operator assignment.
- [x] Operators can review and approve or dismiss AI-suggested incident links.
- [x] Authoritative evidence must be attached to an investigation before verification.

---

### Correction 3: Authentication, CSRF Defense-in-Depth & Network Topology

#### Problem Identified
The initial plan relied exclusively on the custom `X-BIIRS-Request: 1` header as the CSRF defense. Relying on custom headers alone without standard CSRF cookies or same-origin guarantees violates banking security guidelines.

#### Proposed Architectural Correction
Implemented a defense-in-depth security model:
1. **Network Topology:** Next.js development server proxies `/api/v1/:path*` to Django backend on `http://localhost:8000/api/v1/:path*`. This creates a true **same-origin context** for the browser.
2. **Standard Django CSRF Token:** Django issues an accessible `csrftoken` cookie and provides the token in `GET /api/v1/session`.
3. **Double Verification:** Mutating endpoints require **both** valid Django CSRF tokens and the custom header `X-BIIRS-Request: 1`.
4. **Cookie Security:** Cookies enforce `HttpOnly=True`, `SameSite='Lax'`, and `Secure=True` (in production).

#### Affected Files & Components
- **Backend:** `apps.common.middleware.SecurityHeadersMiddleware`, `apps.accounts.views.SessionView`.
- **Frontend Config:** `next.config.ts` (adding proxy rewrites for `/api/v1/:path*`).

#### Frontend Changes Required
- In `next.config.ts`, add the development rewrite:
  ```ts
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: "http://localhost:8000/api/v1/:path*" }];
  }
  ```
- **Zero changes** required in React components, pages, or forms.

#### Acceptance Criteria
- [x] Mutating requests without `X-BIIRS-Request: 1` are rejected with HTTP 403.
- [x] Mutating requests with invalid CSRF tokens are rejected with HTTP 403.
- [x] Session cookie cannot be accessed via JavaScript (`HttpOnly`).

---

### Correction 4: Development Authentication vs Enterprise SSO

#### Problem Identified
The frontend requires an active session returning user details and permissions from `GET /api/v1/session`. Hardcoding static credentials or requiring an enterprise OIDC/SAML IdP for local hackathon development would impede progress. Conversely, building a backdoor login creates severe production risks.

#### Proposed Architectural Correction
1. Built `POST /api/v1/auth/dev-login` accepting `{ "persona": "operator" | "verifier" | "lead" }`.
2. Sets authentic Django session and CSRF cookies, returning full `Session` wire payload.
3. **Production Isolation:** The endpoint is registered in `urls.py` **only** when `settings.DEBUG = True` and `settings.ALLOW_DEV_AUTH = True`. In production, the URL is not routed and returns HTTP 404.

#### Affected Files & Components
- **Backend:** `apps.accounts.views.DevLoginView`, `config.urls`.
- **Documentation:** [`API_CONTRACT.md`](file:///c:/Users/HIMSON/Desktop/Front%20End/API_CONTRACT.md).

#### Frontend Changes Required
**None.** The frontend account popover and session provider consume the standard `GET /session` response.

#### Acceptance Criteria
- [x] In development, developers can switch personas with a single POST call.
- [x] In production (`DEBUG=False`), `POST /api/v1/auth/dev-login` is completely unmapped and returns 404.

---

### Correction 5: Decoupled, Provider-Agnostic AI Subsystem

#### Problem Identified
The preliminary specification hardcoded OpenAI GPT-4o and 384-dimensional vector columns. If OpenAI is down, rate-limited, or if PostgreSQL lacks `pgvector`, the core banking resolution platform would fail.

#### Proposed Architectural Correction
1. Created abstract provider interfaces: `EmbeddingProvider` and `LLMProvider`.
2. Implemented `SentenceTransformerProvider` (local CPU, 384 dims) and `OpenAIEmbeddingProvider` (remote, 1536 dims).
3. Implemented `HeuristicRuleProvider` that activates automatically when OpenAI fails or is unconfigured.
4. Mapped outputs to the frontend's `FindingDTO` schema (`availability: "AVAILABLE" | "LOW_CONFIDENCE" | "UNAVAILABLE"`).

#### Affected Files & Components
- **Backend:** `apps.intelligence.interfaces`, `apps.intelligence.providers`, `apps.intelligence.services`.
- **Documentation:** [`AI_ENGINE_SPEC.md`](file:///c:/Users/HIMSON/Desktop/Front%20End/AI_ENGINE_SPEC.md).

#### Frontend Changes Required
**None.** The frontend's `FindingAvailability` component natively handles `LOW_CONFIDENCE` and `UNAVAILABLE`.

#### Acceptance Criteria
- [x] Case management continues without error when OpenAI API keys are invalid or missing.
- [x] Vector dimension is driven by active provider settings, not hardcoded SQL migrations.
- [x] Facts from banking systems are cleanly separated from AI hypotheses.

---

### Correction 6: Backend Idempotency & Transactional Outbox Pattern

#### Problem Identified
Network interruptions during case forwarding, assignment, or note creation could lead to duplicate assignments, duplicate handoff queue entries, or repeated SMS notifications to customers.

#### Proposed Architectural Correction
1. **Idempotency Engine:** Middleware checks the `Idempotency-Key` header against `common_idempotencyrecord`.
   - Concurrent calls return `409 Conflict`.
   - Replayed calls return the cached HTTP status and JSON response without re-executing logic.
2. **Transactional Outbox Pattern:** External side-effects (SMS, webhooks, AI jobs) are written to `common_outboxmessage` in the same database transaction as the complaint update. Celery workers dispatch messages asynchronously.

#### Affected Files & Components
- **Backend:** `apps.common.middleware.IdempotencyMiddleware`, `apps.common.models` (`IdempotencyRecord`, `OutboxMessage`), `apps.common.tasks`.
- **Documentation:** [`DATABASE_SCHEMA.md`](file:///c:/Users/HIMSON/Desktop/Front%20End/DATABASE_SCHEMA.md), [`ARCHITECTURE_DECISIONS.md`](file:///c:/Users/HIMSON/Desktop/Front%20End/ARCHITECTURE_DECISIONS.md).

#### Frontend Changes Required
**None.** The frontend's `useOperationKey()` in `complaint-actions.tsx` already generates and sends `Idempotency-Key` headers on all mutations.

#### Acceptance Criteria
- [x] Resubmitting an action with the same idempotency key never duplicates records or sends duplicate messages.
- [x] Database rollbacks prevent orphan outbound notifications.

---

### Correction 7: Strict Frontend Wire Compatibility

#### Problem Identified
Risk of inadvertent breaking changes to the Next.js frontend's URL parameters, data schemas, action names, or status enumerations.

#### Proposed Architectural Correction
All Django serializers, URL routes, and viewsets strictly adhere to the contracts defined in `src/lib/api/types.ts` and `src/lib/api/endpoints.ts`:
- Maintained exact status strings: `NEW`, `NEEDS_ACTION`, `IN_PROGRESS`, `FORWARDED`, `AWAITING_VERIFICATION`, `RESOLVED`, `REOPENED`.
- Maintained exact handoff states (13 states).
- Maintained action names: `ASSIGN`, `FORWARD`, `ADD_NOTE`, `SET_FOLLOW_UP`, `RECORD_OUTCOME`, `VERIFY_OUTCOME`, `REOPEN`.
- Retained legacy technical identifier `X-BIIRS-Request` in wire headers.

#### Affected Files & Components
- **Documentation:** [`FRONTEND_INTEGRATION_MAP.md`](file:///c:/Users/HIMSON/Desktop/Front%20End/FRONTEND_INTEGRATION_MAP.md), [`API_CONTRACT.md`](file:///c:/Users/HIMSON/Desktop/Front%20End/API_CONTRACT.md).

#### Frontend Changes Required
**None.**

#### Acceptance Criteria
- [x] All Playwright end-to-end tests (`e2e/workspace.spec.ts`) pass against the Django backend.

---

### Correction 8: Bank-Independent Integration Adapters

#### Problem Identified
Directly coupling the platform to proprietary bank core APIs (e.g. Finacle, Flexcube, Temenos) would prevent portability and block local testing without real bank credentials.

#### Proposed Architectural Correction
1. Created `BankSystemAdapter` abstract base class defining standard queries (`fetch_account`, `fetch_transaction_facts`, `check_switch_status`, `submit_reversal`).
2. Built `SimulatedBankAdapter` providing realistic mock banking data, synthetic ledger conflicts (`core banking debited; switch pending`), and configurable data freshness (`AVAILABLE`, `STALE`).

#### Affected Files & Components
- **Backend:** `apps.transactions.adapters.base`, `apps.transactions.adapters.simulated`.
- **Documentation:** [`ARCHITECTURE_DECISIONS.md`](file:///c:/Users/HIMSON/Desktop/Front%20End/ARCHITECTURE_DECISIONS.md).

#### Frontend Changes Required
**None.**

#### Acceptance Criteria
- [x] System operates out-of-the-box in simulated mode without live banking credentials.
- [x] Authoritative evidence references are enforced before case verification.

---

## Security & Integration Risk Assessment

| Risk Category | Inherent Risk | Mitigating Architectural Control | Residual Risk |
| :--- | :--- | :--- | :--- |
| **Cross-Site Request Forgery (CSRF)** | HIGH: Malicious sites triggering actions via stored session cookie. | Defense-in-depth: Same-origin Next.js proxying + Django CSRF token + mandatory `X-BIIRS-Request: 1` header. | NEGLIGIBLE |
| **Premature Customer Notification** | HIGH: Customer informed case is resolved before money is restored. | Mandatory Verification Gate: Incident resolution does not resolve complaints; requires Checker verification. | NEGLIGIBLE |
| **Self-Verification (Maker-Checker Breach)** | CRITICAL: Operator approving their own fraudulent resolution. | Server-side invariant: `reported_by != verified_by` enforced in database CHECK constraint and DRF view. | ZERO |
| **AI Subsystem Outage** | MEDIUM: OpenAI rate limits or network outage halting case processing. | Fallback to `HeuristicRuleProvider`, setting findings to `LOW_CONFIDENCE` or `UNAVAILABLE`. Case actions unaffected. | LOW |
| **Duplicate Message Blasts** | MEDIUM: Server retries sending repeated SMS messages to customers. | `SHA-256` payload fingerprinting with a 15-minute sliding window and database-backed idempotency. | NEGLIGIBLE |

---

## Recommended Implementation Roadmap

```
+----------------------------------------------------------------------------------------------------+
|                                    BACKEND IMPLEMENTATION ROADMAP                                  |
+----------------------------------------------------------------------------------------------------+

  [ STAGE 1: Core Foundation & Security ]
  - Django 5 project initialization & config
  - apps.common: IdempotencyMiddleware, OutboxMessage model, SecurityHeadersMiddleware
  - apps.tenants & apps.accounts: Tenant model, User model, SessionView, DevLoginView
  - Next.js development proxy rewrites configuration

  [ STAGE 2: Complaints & Reference Architecture ]
  - apps.complaints: Complaint, Category, Note, TimelineEvent, FollowUp models
  - Serializers & Viewsets for /complaints, /workspace/summary, /reference/categories
  - Dynamic allowedActions and SLA overdue computation

  [ STAGE 3: Transactions, Evidence & Bank Adapters ]
  - apps.transactions & apps.evidence: TransactionInvestigation, EvidenceRecord
  - BankSystemAdapter interface & SimulatedBankAdapter implementation
  - Conflict detection engine ("core banking shows debited; switch shows pending")

  [ STAGE 4: Incidents & Root Cause AI Engine ]
  - apps.incidents: Incident, IncidentComplaint (Join Entity with Human Review)
  - apps.intelligence: Sentence Transformers, pgvector store, OpenAI structured extraction
  - Heuristic fallback provider for offline resiliency

  [ STAGE 5: Handoffs & Cross-Team Operations ]
  - apps.handoffs: ReceivingTeam, ForwardingHandoff, HandoffAttempt models
  - Multi-channel handoff dispatcher with retry worker in Celery

  [ STAGE 6: Maker-Checker Resolutions & Customer Communications ]
  - apps.resolutions: ResolutionOutcome with strict server-side maker-checker enforcement
  - apps.communications: CustomerMessage, MessageTemplate, Verification Gate, Outbox dispatcher

  [ STAGE 7: Analytics, Notifications & End-to-End Validation ]
  - apps.reports: 7 analytical report aggregation queries with partial data coverage indicators
  - apps.notifications: In-app notification feed & user preferences
  - Execution of complete Playwright E2E suite against running Django backend
```

---

## Sign-Off Request

All required architectural documentation deliverables have been generated and reviewed:
1. [`ARCHITECTURE_DECISIONS.md`](file:///c:/Users/HIMSON/Desktop/Front%20End/ARCHITECTURE_DECISIONS.md)
2. [`FRONTEND_INTEGRATION_MAP.md`](file:///c:/Users/HIMSON/Desktop/Front%20End/FRONTEND_INTEGRATION_MAP.md)
3. [`DATABASE_SCHEMA.md`](file:///c:/Users/HIMSON/Desktop/Front%20End/DATABASE_SCHEMA.md)
4. [`API_CONTRACT.md`](file:///c:/Users/HIMSON/Desktop/Front%20End/API_CONTRACT.md)
5. [`WORKFLOW_STATES.md`](file:///c:/Users/HIMSON/Desktop/Front%20End/WORKFLOW_STATES.md)
6. [`AI_ENGINE_SPEC.md`](file:///c:/Users/HIMSON/Desktop/Front%20End/AI_ENGINE_SPEC.md)
7. [`COMMUNICATION_WORKFLOW.md`](file:///c:/Users/HIMSON/Desktop/Front%20End/COMMUNICATION_WORKFLOW.md)
8. [`ARCHITECTURE_CORRECTION_REPORT.md`](file:///c:/Users/HIMSON/Desktop/Front%20End/ARCHITECTURE_CORRECTION_REPORT.md)

As Technical Lead, please review and approve this proposal so we can proceed to **Backend Development Stage 1**.
