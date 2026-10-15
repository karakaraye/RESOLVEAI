# ResolveAI — Frontend Integration Map & Technical Architecture Specification

> **Document Version:** 2.0.0  
> **Target Platform:** ResolveAI Banking Incident Intelligence & Resolution System (BIIRS)  
> **Frontend Stack:** Next.js 16 (App Router, Turbopack, React 19, TypeScript, Vanilla CSS)  
> **Backend Stack:** Python 3.12+, Django 5.x, Django REST Framework, PostgreSQL 16+ (with `pgvector`), Celery, Redis  
> **Architecture Status:** IMPLEMENTATION-READY (Post-Correction Review)  

---

## 1. System Architecture Overview

ResolveAI connects a high-density, real-time Next.js operator workspace to a multi-tenant, event-driven Django backend. The system enforces strict **server-side authority**: the browser does not guess or calculate business transitions, user permissions, or resolution statuses; it renders strictly what the backend API allows.

```
+---------------------------------------------------------------------------------------------------------+
|                                           NEXT.JS FRONTEND                                              |
|  - Workspace UI: / , /complaints, /complaints/[id], /my-cases, /forwarded, /reports, /settings          |
|  - API Client: Credentials Included, Idempotency-Key Header, X-BIIRS-Request, CSRF Token               |
+---------------------------------------------------------------------------------------------------------+
                                          |                     ^
                     Same-Origin Proxy /  |                     | JSON (Wire Typed)
                     Same-Site Subdomain  |                     | HTTP Statuses
                                          v                     |
+---------------------------------------------------------------------------------------------------------+
|                                    DJANGO REST FRAMEWORK BACKEND                                        |
|  +--------------------+  +--------------------+  +--------------------+  +----------------------------+ |
|  |  apps.accounts     |  |  apps.complaints   |  |  apps.incidents    |  |  apps.resolutions          | |
|  |  (SSO & Dev Auth,  |  |  (Intake, State,   |  |  (Shared Root-     |  |  (Two-Person Maker-Checker,| |
|  |   Roles, Tenant)   |  |   Assignment)      |  |   Cause Clusters)  |  |   Audit Invariants)        | |
|  +--------------------+  +--------------------+  +--------------------+  +----------------------------+ |
|  +--------------------+  +--------------------+  +--------------------+  +----------------------------+ |
|  |  apps.transactions |  | apps.communications|  |  apps.handoffs     |  |  apps.intelligence         | |
|  |  (Bank Adapters,   |  | (Customer SMS,     |  |  (Multi-Channel    |  |  (Replaceable Embeddings & | |
|  |   Ledger Conflict) |  |  Status Updates)   |  |   Dispatch Engine) |  |   LLM Providers, Fallback) | |
|  +--------------------+  +--------------------+  +--------------------+  +----------------------------+ |
|  +--------------------+  +--------------------+  +--------------------+  +----------------------------+ |
|  |  apps.reports      |  | apps.notifications |  |  apps.evidence     |  |  apps.common               | |
|  |  (Metrics, SLAs &  |  | (In-App Alerts &   |  |  (Authoritative    |  |  (Idempotency Middleware & | |
|  |   Data Coverage)   |  |  Preferences)      |  |   Proof Store)     |  |   Transactional Outbox)    | |
|  +--------------------+  +--------------------+  +--------------------+  +----------------------------+ |
+---------------------------------------------------------------------------------------------------------+
                |                                    |                                    |
                v                                    v                                    v
+-------------------------------+    +-------------------------------+    +-------------------------------+
|     POSTGRESQL 16+ DATABASE   |    |         REDIS & CELERY        |    |       AI & BANK ADAPTERS      |
|  - Multi-Tenant RLS Scoping   |    |  - Outbox Message Dispatch    |    |  - Sentence Transformers      |
|  - Variable pgvector Store    |    |  - SLA & Escalation Monitors  |    |  - OpenAI Structured Output   |
|  - Idempotency & Outbox Tables|    |  - Retry Workers with Backoff |    |  - Simulated Core Banking/NIBSS|
+-------------------------------+    +-------------------------------+    +-------------------------------+
```

---

## 2. Frontend Inventory & Route Mapping

The frontend consists of 8 primary workspace routes, fully implemented and validated:

| Route | Page File | Core View | Query Parameters | Backend Data Requirement |
| :--- | :--- | :--- | :--- | :--- |
| `/` | `src/app/page.tsx` | `HomeView` | None | Workspace summary counts (`all`), prioritized next actions queue, recent 5 complaints, trend widgets. |
| `/complaints` | `src/app/complaints/page.tsx` | `ComplaintsView` | `q`, `status`, `priority`, `category`, `received`, `page`, `pageSize` | Paginated complaint register with server-side full-text search, multi-field filtering, and dynamic action permissions. |
| `/complaints/[id]` | `src/app/complaints/[id]/page.tsx` | `ComplaintDetailView` | `action` (active drawer form), `from` (return context) | Detailed aggregate: narrative, transactions, conflict markers, AI findings, notes, handoffs, resolution, timeline events. |
| `/my-cases` | `src/app/my-cases/page.tsx` | `MyCasesView` | `q`, `status`, `priority`, `category`, `due`, `page`, `pageSize` | Scoped complaint register filtered to `request.user.id`, with SLA deadline metrics (`overdue`, `today`, `soon`, `week`). |
| `/forwarded` | `src/app/forwarded/page.tsx` | `ForwardedView` | `q`, `state` (13 handoff states), `page`, `pageSize` | Paginated handoff tracker with summary counts (`awaitingResponse`, `responded`, `overdue`, `failed`). |
| `/reports` | `src/app/reports/page.tsx` | `ReportsView` | `type` (7 report types), `range` (`7d`, `30d`, `90d`, `custom`), `from`, `to` | Analytical metrics, SVG line charts (`TrendChart`), horizontal bar breakdowns (`BarList`), source coverage, and definitions. |
| `/notifications` | `src/app/notifications/page.tsx` | `NotificationsView` | `filter` (`unread`), `page`, `pageSize` | Paginated in-app notifications with unread counter and bulk mark-all-read capability. |
| `/settings` | `src/app/settings/page.tsx` | `SettingsView` | `section` (`profile`, `notifications`, `preferences`, `security`, `data-sources`, `help`) | User profile, event preferences, browser settings, connected data source health checks, and support glossary. |

---

## 3. Network Topology, Authentication & CSRF Architecture

### 3.1 Network Topology & Deployment Strategy

To achieve both ease of local development and production-grade security without altering the frontend:

```
DEVELOPMENT (Local):
Browser ---> Next.js Dev Server (localhost:3000)
               |
               |-- / (Pages, CSS, Client JS)
               |-- /api/v1/:path*  (Next.js Proxy Rewrite) ---> Django Backend (localhost:8000/api/v1/:path*)
                   * Same-origin from the browser's perspective. Cookies and headers flow transparently.

PRODUCTION:
Browser ---> Reverse Proxy / Gateway (e.g., Nginx, Cloudflare, AWS ALB)
               |-- workspace.resolveai.bank  ---> Next.js Container
               |-- api.resolveai.bank        ---> Django DRF Gunicorn/Uvicorn
                   * Shared top-level domain (.resolveai.bank).
                   * Cookies configured with SESSION_COOKIE_DOMAIN = ".resolveai.bank", SameSite="Lax", Secure=True.
```

### 3.2 Multi-Layered CSRF & Authentication Protocol

The frontend client in `src/lib/api/client.ts` uses `credentials: "include"` and sets header `X-BIIRS-Request: 1` on non-GET calls. The Django backend establishes a multi-layered defense:

1. **Session Cookie:**
   - Standard Django HTTP-only session cookie (`sessionid`), encrypted and signed.
   - `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SAMESITE = 'Lax'`, `SESSION_COOKIE_SECURE = not settings.DEBUG`.
2. **CSRF Protection:**
   - Django's `CsrfViewMiddleware` generates a standard `csrftoken` cookie.
   - The session bootstrap endpoint (`GET /api/v1/session`) returns the CSRF token in an HTTP header (`X-CSRFToken`) and in the response payload.
   - In Next.js development proxying, Django's standard CSRF cookie verification operates seamlessly on the same origin.
3. **Custom Anti-Automation Header:**
   - The custom header `X-BIIRS-Request: 1` is strictly verified by Django middleware on all mutating methods (`POST`, `PUT`, `PATCH`, `DELETE`). Cross-origin forms submitted via browser exploitation cannot set custom headers.

---

## 4. Development Authentication vs Production SSO

### 4.1 Production Enterprise SSO
- Production authentication relies on enterprise OpenID Connect (OIDC) or SAML 2.0 (Azure AD, Okta, Keycloak).
- `GET /api/v1/session/sign-in?returnTo=<url>`: Redirects to IdP login challenge. Upon callback, Django establishes the session and redirects the user back to `returnTo`.
- `POST /api/v1/session/sign-out`: Destroys the Django session and returns `{ "redirectUrl": "/signed-out" }`.

### 4.2 Development-Only Authentication (`POST /api/v1/auth/dev-login`)
To enable full-stack development and testing without an external SSO server:
- An endpoint `POST /api/v1/auth/dev-login` is provided, accepting `{ "persona": "operator" | "verifier" | "lead" }`.
- Creates an active Django session for pre-seeded test personas:
  - `operator`: Test Operator (`u-1`), Customer Care, permissions: `complaints.read`, `complaints.assign`, `complaints.forward`, `complaints.notes`, `complaints.follow_up`, `complaints.record_outcome`.
  - `verifier`: Senior Verifier (`u-2`), Compliance Dept, permissions: all operator permissions plus `complaints.verify_outcome`.
  - `lead`: Operations Lead (`u-3`), Operations, full administrative permissions.
- **Security Guardrail:** Registered **only** when `settings.DEBUG = True` and `settings.ALLOW_DEV_AUTH = True`. The URL is completely unregistered and inaccessible in production.

---

## 5. Domain Decomposition & Entity Architecture

The backend corrects previous coupling by introducing clean domain boundaries:

```
+---------------------------------------------------------------------------------------------------------+
|                                    RESOLVEAI DOMAIN BOUNDARIES                                          |
+---------------------------------------------------------------------------------------------------------+

  [ TENANTS & ACCOUNTS ]
    - Tenant, DataSource, User, Role, Permission

  [ COMPLAINTS CORE ]
    - Complaint, ComplaintCategory, ComplaintNote, ComplaintTimelineEvent, ComplaintFollowUp

  [ INCIDENTS & ROOT CAUSE ]
    - Incident, IncidentComplaint (Join Entity with Association Confidence & Operator Review Status)

  [ INVESTIGATION & EVIDENCE ]
    - TransactionInvestigation, EvidenceRecord, BankIntegrationAdapter

  [ CROSS-TEAM HANDOFFS ]
    - ReceivingTeam, TeamRecipient, ForwardingHandoff, HandoffAttempt

  [ RESOLUTION & MAKER-CHECKER ]
    - ResolutionOutcome (Individual Outcome Verification)

  [ CUSTOMER COMMUNICATIONS ]
    - MessageTemplate, CustomerMessage, DeliveryAttempt, RateLimiter

  [ AI SUBSYSTEM ]
    - EmbeddingStore (Variable Dimensions), ComplaintFinding, RCAHypothesis

  [ INFRASTRUCTURE & SAFETY ]
    - IdempotencyRecord, OutboxMessage, InAppNotification
```

### 5.1 Complaint vs Incident Decoupling (Correction 2)
- **One Incident, Many Complaints:** An incident (e.g. `INC-2026-007` - "NIBSS Outward Transfer Latency") is linked to multiple `Complaint` instances via `IncidentComplaint`.
- **Individual Complaint Accountability:** Resolving an incident does **not** mark complaints as resolved. It triggers individual complaint ledger reviews.
- **Human Review of AI Links:** When Sentence Transformers or clustering algorithms suggest an incident association, `IncidentComplaint.status` is set to `PENDING_REVIEW`. Operators confirm or dismiss the link via the UI.

### 5.2 Customer Communication Engine (Correction 1)
- Dedicated `apps.communications` module.
- **Intake:** Automatically dispatches SMS/Email with `customerReference` (e.g., `TST-1044`) and safe tracking links.
- **Resolution Gate:** Customer resolution notifications are locked until the individual complaint's `ResolutionOutcome` is marked `VERIFIED` by an independent verifier.

### 5.3 Authoritative Evidence & Banking Adapters (Correction 8)
- Transactions are checked through abstract `BankSystemAdapter` implementations.
- A `SimulatedBankAdapter` produces realistic banking responses, ledger debits, switch delays, and conflict alerts for hackathon/testing without needing live banking credentials.
- Outcomes require authoritative proof (e.g., core banking journal reference, settlement reversal sequence).

---

## 6. Frontend Wire Compatibility & API Endpoint Mapping

The Django REST API implements all 22 existing frontend endpoints exactly as specified in `src/lib/api/types.ts` and `src/lib/api/endpoints.ts`:

```
+------------------------------------------------------+--------------------------------------------------+
| Frontend Wire Contract (src/lib/api/endpoints.ts)    | Backend Django View & Model Mapping              |
+------------------------------------------------------+--------------------------------------------------+
| GET  /session                                        | apps.accounts.views.SessionView                  |
| POST /session/sign-out                               | apps.accounts.views.SignOutView                  |
| GET  /reference/categories                           | apps.complaints.views.CategoryListView           |
| GET  /workspace/summary?scope=all|mine               | apps.complaints.views.WorkspaceSummaryView       |
| GET  /complaints?...                                 | apps.complaints.views.ComplaintListView          |
| GET  /complaints/{id}                                | apps.complaints.views.ComplaintDetailView        |
| GET  /complaints/{id}/eligible-assignees             | apps.complaints.views.EligibleAssigneesView      |
| POST /complaints/{id}/assignment                     | apps.complaints.views.AssignComplaintView        |
| GET  /complaints/{id}/forwarding-options             | apps.handoffs.views.ForwardingOptionsView        |
| POST /complaints/{id}/handoffs                       | apps.handoffs.views.CreateHandoffView            |
| POST /handoffs/{id}/retry                            | apps.handoffs.views.RetryHandoffView             |
| POST /complaints/{id}/notes                          | apps.complaints.views.AddNoteView                |
| POST /complaints/{id}/follow-ups                     | apps.complaints.views.SetFollowUpView            |
| POST /complaints/{id}/resolution                     | apps.resolutions.views.RecordOutcomeView         |
| POST /complaints/{id}/resolution/verification        | apps.resolutions.views.VerifyOutcomeView         |
| POST /complaints/{id}/reopen                         | apps.resolutions.views.ReopenComplaintView       |
| GET  /handoffs?...                                   | apps.handoffs.views.HandoffListView              |
| GET  /handoffs/summary                               | apps.handoffs.views.HandoffSummaryView           |
| GET  /reports/{type}?...                             | apps.reports.views.ReportDetailView              |
| GET  /notifications?...                              | apps.notifications.views.NotificationListView    |
| POST /notifications/{id}/read                        | apps.notifications.views.MarkNotificationReadView|
| POST /notifications/read-all                         | apps.notifications.views.MarkAllReadView         |
| GET  /me/notification-preferences                    | apps.notifications.views.UserPreferencesView     |
| PUT  /me/notification-preferences                    | apps.notifications.views.UserPreferencesView     |
| GET  /data-sources                                   | apps.tenants.views.DataSourceListView            |
+------------------------------------------------------+--------------------------------------------------+
```

---

## 7. AI & Machine Learning Subsystem Specification

### 7.1 Provider-Agnostic Design (Correction 5)
```python
# apps/intelligence/interfaces.py
class EmbeddingProvider(ABC):
    @abstractmethod
    def generate_embedding(self, text: str) -> list[float]:
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        pass

class LLMProvider(ABC):
    @abstractmethod
    def analyze_complaint(self, narrative: str, transaction_facts: list[dict]) -> FindingDTO:
        pass
```

- **Embedding Implementations:** `SentenceTransformerProvider` (`all-MiniLM-L6-v2`, 384 dims, local CPU) and `OpenAIEmbeddingProvider` (`text-embedding-3-small`, 1536 dims).
- **LLM Implementations:** `OpenAILLMProvider` (GPT-4o with structured Pydantic schema) and `HeuristicRuleProvider` (offline fallback).
- **Graceful Degradation:** If OpenAI is unreachable or rate-limited, the system falls back to `HeuristicRuleProvider`, setting `availability = "LOW_CONFIDENCE"` or `"UNAVAILABLE"`. Case assignment, forwarding, notes, and resolution continue working uninterrupted.

---

## 8. Transactional Outbox & Database Idempotency (Correction 6)

### 8.1 Idempotency Engine
- Mutating endpoints verify the `Idempotency-Key` header.
- `apps.common.middleware.IdempotencyMiddleware`:
  - `PENDING`: Returns HTTP 409 Conflict if a concurrent request with the same key is active.
  - `COMPLETED`: Returns the previously saved HTTP status and JSON response immediately from `IdempotencyRecord`.

### 8.2 Transactional Outbox Pattern
```
[ Incoming HTTP Request ]
       |
       v (PostgreSQL Transaction Start)
   - Update Complaint State
   - Insert Audit Timeline Event
   - Insert OutboxMessage (Payload, Destination Topic, Status='PENDING')
       v (PostgreSQL Transaction Commit)
       |
       +---> [ Celery Outbox Dispatcher Worker ]
                   |
                   v (Dispatches side-effects reliably)
             - Customer SMS / Email via Communications Engine
             - External Core Banking Webhook
             - AI Embedding Generation
```

If the database transaction fails, no outbox message is written, preventing ghost side-effects.

---

## 9. Conclusion & Implementation Readiness

The corrected architecture fully satisfies the BIIRS Product Specification and enterprise banking requirements while preserving 100% compatibility with the existing Next.js frontend codebase.
