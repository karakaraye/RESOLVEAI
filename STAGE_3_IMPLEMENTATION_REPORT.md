# ResolveAI — Stage 3 Implementation Report
## Transaction Investigation, Evidence Management, and Simulated Banking Integration

**Author:** Antigravity (Senior Software Architect & Backend Engineer)  
**Audience:** Full-Stack Developer & Technical Lead  
**Date:** October 14, 2026  
**Status:** Complete & Reconciled — Awaiting Stage 4 Approval  
**Database Engine:** PostgreSQL 17.11 (Supabase Dedicated Cloud Instance)  
**Test Suite Status:** 68 / 68 Automated Tests PASSING (100% Green on `test_postgres`)

---

## Executive Summary

Stage 3 of the **Bank Internal Incident Resolution System (ResolveAI)** has been implemented, validated, and reconciled. This stage introduces specialized domain capabilities for **Transaction Investigation**, **Authoritative Evidence Management**, and a realistic **Simulated Banking Integration** layer without modifying or rebuilding any existing Next.js frontend components.

All core operational constraints specified for Stage 3 have been satisfied:
1. **Pessimistic Concurrency Controls:** Implemented row-level locking (`select_for_update`) across all state-changing complaint and evidence operations to prevent race conditions or contradictory case updates.
2. **Reopened Lifecycle Safety:** Enforced an invariant where reopening a resolved case completely invalidates and purges prior resolution outcomes, mandating a newly recorded and independently verified outcome before returning to `RESOLVED`.
3. **Domain Separation:** Maintained strict relational separation among `Complaint`, `TransactionInvestigation`, `EvidenceRecord`, and future `Incident` entities.
4. **Data Integrity vs. Source Authenticity:**
   - **Tamper Detection (Data Integrity):** SHA-256 payload hashing (`compute_payload_hash()`) detects any post-ingestion tampering or bit-rot in stored evidence payloads.
   - **Multi-Attribute Source Authenticity:** Recognizes that a hash alone cannot prove external origin. ResolveAI establishes source authenticity by preserving verified source system identity, authoritative external sequence numbers, external source timestamps, immutable ingestion audit trails, and independent maker-checker attestation.
5. **Discrepancy vs. Confirmed Failure:** Formalized reconciliation logic ensuring source discrepancies (`"Sources disagree: Core banking shows debited; switch shows pending. No final outcome is assumed."`) are never prematurely classified as confirmed transaction failures.
6. **Read-Only / Simulation Invariant:** Strictly read-only investigative integration; no real or mock financial reversals, transfers, or fund movements are permitted.
7. **Frontend API Contract Preservation:** Complaint detail endpoint (`GET /api/v1/complaints/{id}`) seamlessly populates `transactions` adhering to the frontend's exact `TransactionRecord` TypeScript interface.

---

## 1. Domain Architecture & Database Models

Two new Django applications were established under `backend/apps/`:

### 1.1 `apps.transactions` (Transaction Investigation)

Located at `backend/apps/transactions/models.py`, `TransactionInvestigation` manages external banking ledger and payment switch records linked to an active case:

- **Model:** `TransactionInvestigation` (`db_table = "transactions_investigation"`)
  - `id`: UUID (Primary Key)
  - `tenant`: Foreign Key to `tenants.Tenant` (Multi-tenant isolation)
  - `complaint`: Foreign Key to `complaints.Complaint` (Related name: `transaction_investigations`)
  - `reference`: External or system transaction reference (e.g., `TXN-90311`, `NIP-SES-999014261012`)
  - `source_system`: Originating banking infrastructure (e.g., `Core banking (Finacle)`, `NIBSS Instant Payments`, `Interswitch Card Switch`)
  - `amount_value`: DecimalField (`max_digits=15, decimal_places=2`)
  - `amount_currency`: CharField (`max_length=3`, default `NGN`)
  - `occurred_at`: DateTimeField with source timezone preservation
  - `status_label`: Human-readable label (e.g., `Debited`, `Successful`, `Pending switch acknowledgment`)
  - `status`: Source availability state (`AVAILABLE`, `UNAVAILABLE`, `PENDING_RETRY`)
  - `conflict`: Text description of any discrepancy across systems, explicitly stating that no outcome is assumed
  - `match_evidence`: Reasoning string explaining why this transaction was matched to the complaint
  - `last_updated_at`: Timestamp of latest poll or reconciliation
- **Database Migrations:** `transactions.0001_initial` applied cleanly to Supabase PostgreSQL.

### 1.2 `apps.evidence` (Authoritative Evidence Management)

Located at `backend/apps/evidence/models.py`, `EvidenceRecord` stores immutable, audited evidence items supporting investigation and maker-checker outcome decisions:

- **Model:** `EvidenceRecord` (`db_table = "evidence_evidencerecord"`)
  - `id`: UUID (Primary Key)
  - `tenant`: Foreign Key to `tenants.Tenant` (Multi-tenant isolation)
  - `complaint`: Foreign Key to `complaints.Complaint` (Related name: `evidence_records`)
  - `transaction_investigation`: Optional Foreign Key to `TransactionInvestigation`
  - `kind`: Evidence classification (`SWITCH_LOG`, `LEDGER_ENTRY`, `REVERSAL_SLIP`, `CUSTOMER_RECEIPT`, `AUDIT_SNAPSHOT`, `SYSTEM_TRACE`)
  - `document_reference`: Authoritative internal reference (e.g., `NIP-TRACE-999014261012`, `JRN-FIN-20261012-9844`)
  - `title`: Short descriptive title
  - `summary`: Human-readable overview of what the evidence proves
  - `source_system`: Originating institution or system (e.g., `Finacle Core Banking Journal`, `NIBSS Settlement Switch Log`)
  - `source_timestamp`: Original event timestamp at the external source
  - `provenance`: Custody metadata documenting extraction path, batch/session IDs, and ingestion worker
  - `data_freshness`: Explicit retrieval SLA indicator (`FRESH`, `STALE`, `HISTORICAL`)
  - `is_verified`: Boolean maker-checker verification flag
  - `verified_by`: Foreign Key to `accounts.User`
  - `verified_at`: Verification timestamp
  - `raw_payload`: JSONField storing the complete, unedited source payload
  - `compute_payload_hash()`: Method generating a SHA-256 digest of `raw_payload` for post-ingestion tamper detection
- **Database Migrations:** `evidence.0001_initial` and `evidence.0002_initial` applied cleanly to Supabase PostgreSQL.

---

## 2. Evidence Integrity Architecture: Tamper-Detection vs. Source Authenticity

In banking systems, cryptographic hashing and source authenticity serve distinct, complementary purposes. ResolveAI models this distinction rigorously:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        EVIDENCE RECORD ENVELOPE                        │
├────────────────────────────────────────────────────────────────────────┤
│ 1. SOURCE AUTHENTICITY (Origin Verification)                           │
│    • source_system       : Verified source platform (e.g., Finacle)    │
│    • document_reference  : Authoritative journal ID / STAN / RRN       │
│    • source_timestamp    : Original event timestamp from bank source   │
│    • provenance          : Certified extraction route & worker session │
│    • is_verified         : Independent maker-checker review sign-off   │
│    • verified_by/at      : Compliance officer attestation              │
│    • AuditEvent log      : Immutable ingestion custody trail           │
├────────────────────────────────────────────────────────────────────────┤
│ 2. DATA INTEGRITY (Tamper-Detection)                                   │
│    • raw_payload         : Complete raw JSON document from adapter     │
│    • compute_payload_hash: SHA-256 digest over canonical raw payload  │
│      -> Detects post-ingestion alteration, bit-rot, or tampering       │
│      -> Does NOT alone prove external authenticity                     │
└────────────────────────────────────────────────────────────────────────┘
```

1. **What SHA-256 Solves (Data Integrity):**
   - Detects whether stored evidence data has been changed or corrupted after ingestion.
   - Any modification to `raw_payload` immediately yields a mismatched hash, flagging tampering.
2. **What SHA-256 Does Not Solve (Source Authenticity):**
   - A valid hash can be computed for fraudulent or inaccurate data.
   - Hashing alone does not prove the data originated from an authentic banking system.
3. **How ResolveAI Enforces Source Authenticity:**
   - **Source Identity & Ingestion Channel:** System identity is recorded and restricted to authenticated read-only adapters (`source_system`).
   - **External Event Timestamps & Identifiers:** Preserves the core ledger's posting datetime (`source_timestamp`) and immutable bank transaction references (`document_reference`).
   - **Maker-Checker Validation:** A qualified compliance or verification officer must independently inspect the evidence and record verified attestation (`is_verified = True`, `verified_by = verifier`, `verified_at = timestamp`).
   - **Custody Audit Trail:** Every attachment and verification creates an immutable, append-only `AuditEvent` record logging the tenant, actor, timestamp, and metadata.

---

## 3. Simulated Banking Integration (`SimulatedBankAdapter`)

To prevent dangerous or unpredictable interactions with real banking payment switches and core ledgers, all external banking queries pass through a deterministic adapter pattern:

- **Abstract Base:** `BankSystemAdapter` (`backend/apps/transactions/adapters/base.py`)
  - `query_account(account_number, start_date, end_date) -> List[Dict]`
  - `query_switch(session_id, rrn, stan) -> Optional[Dict]`
  - `search_transactions(account_number, reference, start_date, end_date) -> List[Dict]`
- **Concrete Adapter:** `SimulatedBankAdapter` (`backend/apps/transactions/adapters/simulated.py`)
  - Simulates responses from **Core Banking (Finacle)**, **NIBSS Instant Payments (NIP)**, and **Interswitch Card Switch**.
  - **Reconciliation Engine:** Compares core ledger status against switch responses. When a core ledger shows `DEBITED` while the switch shows `PENDING` or `NOT_RECEIVED`, the adapter automatically generates a conflict finding:
    > *"Sources disagree: Core banking shows debited; switch shows pending/not received. No final outcome is assumed."*
  - **Match Reasoning:** Automatically outputs transparent matching evidence (`"Matched because: Customer account 0123456789 exact match; session ID matches complaint narrative."`).
  - **No Financial Operations:** Purely investigative and idempotent. There are no debit, credit, refund, or transfer capabilities.

---

## 4. Concurrency Controls & Reopened Lifecycle Safety

### 4.1 Pessimistic Database Locking
In high-concurrency banking environments, multiple operators or background jobs could attempt simultaneous actions on the same case. To prevent contradictory updates:
- Mutating methods in `apps.complaints.services.ComplaintWorkflowService`:
  - `assign_operator`
  - `add_note`
  - `set_follow_up`
  - `record_outcome`
  - `verify_outcome`
  - `reopen_complaint`
  - `transition_status`
- All use `Complaint.objects.select_for_update().get(...)` wrapped in `with transaction.atomic():`. This guarantees serial execution at the PostgreSQL row level.
- Similar locking is enforced on `apps.evidence.services.EvidenceManagementService.verify_evidence` and `apps.transactions.services.TransactionInvestigationService.link_transaction`.

### 4.2 Reopened Case State Invariant
To ensure strict regulatory compliance and prevent stale outcomes from contaminating reopened complaints:
- When `reopen_complaint()` is called:
  1. The complaint status is updated to `Complaint.Status.REOPENED`.
  2. The reopen reason is logged.
  3. **All prior resolution fields are explicitly cleared and invalidated**:
     ```python
     complaint.resolution_outcome = ""
     complaint.resolution_evidence = ""
     complaint.resolution_reported_at = None
     complaint.resolution_reported_by = None
     complaint.resolution_verification = Complaint.ResolutionVerification.AWAITING
     complaint.resolution_verified_at = None
     complaint.resolution_verified_by = None
     complaint.resolution_note = ""
     ```
  4. The maker-checker verification handler (`verify_outcome`) asserts:
     - `complaint.status == Complaint.Status.AWAITING_VERIFICATION` (a reopened complaint cannot be verified directly).
     - `bool(complaint.resolution_outcome)` is True (an active resolution outcome must be freshly recorded).
     - `complaint.resolution_reported_by != user` (self-verification is strictly blocked).

---

## 5. API Endpoints and Frontend Integration

### 5.1 REST API Routes

| HTTP Method | Path | Description | Access / Persona |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/complaints/{id}` | Complete complaint detail including populated `transactions` array | Authenticated (Operator, Verifier, Lead) |
| `GET` | `/api/v1/complaints/{id}/transactions` | List all linked transaction investigations | Authenticated (Operator, Verifier, Lead) |
| `POST` | `/api/v1/complaints/{id}/transactions/link` | Manually link a transaction investigation | Authenticated (`can_edit_complaints`) |
| `POST` | `/api/v1/complaints/{id}/transactions/search` | Query simulated bank adapter and auto-link results | Authenticated (`can_edit_complaints`) |
| `GET` | `/api/v1/complaints/{id}/evidence` | List all authoritative evidence records | Authenticated (Operator, Verifier, Lead) |
| `POST` | `/api/v1/complaints/{id}/evidence/create` | Attach new evidence record to complaint | Authenticated (`can_edit_complaints`) |
| `POST` | `/api/v1/evidence/{id}/verify` | Maker-checker independent verification of evidence | Authenticated (`can_verify_resolutions`) |

### 5.2 Frontend Contract Verification (`src/lib/api/types.ts`)

The complaint detail serializer (`ComplaintDetailSerializer`) serializes linked transactions directly into the `transactions` array. The output payload conforms strictly to the existing frontend `TransactionRecord` TypeScript interface:

```json
{
  "reference": "NIP-SES-999014261012",
  "sourceSystem": "NIBSS Instant Payments",
  "amount": {
    "value": "50,000.00",
    "currency": "NGN"
  },
  "occurredAt": "2026-10-12T13:45:00Z",
  "statusLabel": "Debited",
  "conflict": "Sources disagree: NIBSS switch response indicates transaction pending session confirmation; core banking indicates customer account debited. No final outcome is assumed.",
  "matchEvidence": "Matched because: Customer account 0123456789 exact match; session ID matches complaint narrative.",
  "status": "AVAILABLE",
  "lastUpdatedAt": "2026-10-14T14:00:00Z"
}
```

Live HTTP verification confirmed that `complaint-detail-view.tsx` renders this transaction data without errors or console warnings.

---

## 6. Security and Access Controls

1. **Anti-CSRF / Request Origin Validation:** All state-changing transaction and evidence endpoints require the custom `X-BIIRS-Request: 1` header. Missing or forged requests are rejected with HTTP 403.
2. **Idempotency Protection:** All `POST` endpoints inherit tenant-scoped Redis/PostgreSQL idempotency tracking via `IdempotencyMiddleware`.
3. **Multi-Tenant Partitioning:** All transaction and evidence queries filter strictly on `request.user.tenant`. Cross-tenant record leakage is prevented at both the service and database layer.
4. **Maker-Checker Separation:** Evidence verification and complaint resolution verification require the `can_verify_resolutions` permission (`VERIFIER` or `INCIDENT_LEAD` personas). Operators cannot verify evidence or resolution outcomes they proposed.

---

## 7. Reconciled Automated Test Results

All automated tests were executed against the dedicated, isolated PostgreSQL test database (`test_postgres` on Supabase).

### Exact Test Runner Breakdown

The test runner output reconciles exactly as follows:

| App / Test Suite | Tests | Scope & Key Test Cases | Status |
| :--- | :---: | :--- | :---: |
| `apps.accounts` | **9** | DevAuthService, persona attributes, permissions mapping, session endpoint, dev-login authentication | **PASS** |
| `apps.common` | **20** | IdempotencyMiddleware (caching, locking, payload validation, replay, recovery), CSRF security headers, standard API error envelopes, AuditEvent immutability | **PASS** |
| `apps.tenants` | **3** | Tenant slug generation, multi-tenant isolation, data source filtering | **PASS** |
| `apps.complaints` | **21** | Complaint state machine, branching workflows, pessimistic row locking, maker-checker verification, reopening invalidation, detail serialization | **PASS** |
| `apps.transactions` | **9** | SimulatedBankAdapter, Finacle/NIBSS/Interswitch queries, discrepancy vs. failure detection, transaction linking, transaction API endpoints | **PASS** |
| `apps.evidence` | **6** | Evidence attachment, multi-attribute source authenticity, SHA-256 tamper-detection, maker-checker verification, tenant isolation | **PASS** |
| **Total Test Suite** | **68** | **Full End-to-End Coverage (9 + 20 + 3 + 21 + 9 + 6 = 68)** | **100% PASS** |

- **Actual Database Engine Used:** `django.db.backends.postgresql` (PostgreSQL 17.11 on Supabase Cloud)
- **Test Database Isolation:** Confirmed running on `test_postgres`, preserving application database and synthetic seed data.
- **Failures / Errors:** 0 (Zero)

---

## 8. Frontend Integration Limitations & Future Alignment

1. **Live Search Button UI:** The frontend's complaint detail interface currently renders linked transactions from the initial complaint payload. The new `/transactions/search` and `/transactions/link` APIs are fully operational on the backend, ready for a UI "Fetch External Transactions" button in a subsequent iteration.
2. **Evidence Attachment Modal:** Currently, evidence records are displayed via the timeline events and resolution sections. The dedicated `/evidence` endpoints are ready to power a future interactive evidence drawer or upload modal.
3. **No Frontend Code Modified:** As mandated, zero frontend source files were modified during Stage 3.

---

## Conclusion & Next Steps

Stage 3 is complete, thoroughly tested, and reconciled with the test runner and banking domain architecture.

**ANTIGRAVITY HAS PAUSED AS INSTRUCTED.** We await your review and approval before beginning **Stage 4: AI Engine, Vector Search, and Incident Correlation**.
