# ResolveAI Database Schema Specification

> **Document Version:** 2.0.0  
> **Database Engine:** PostgreSQL 16+ (with `pgvector` extension)  
> **ORM Framework:** Django 5.x ORM  
> **Entity Identification:** UUIDv4 for all primary keys  
> **Status:** APPROVED / IMPLEMENTATION-READY  

---

## 1. Schema Overview & Entity Relationship Diagram (ERD)

```
+----------------------------------------------------------------------------------------------------+
|                                    RESOLVEAI RELATIONAL SCHEMA                                     |
+----------------------------------------------------------------------------------------------------+

  [ tenants_tenant ] 1 ----< * [ accounts_user ]
         |                         |
         | 1                       | 1
         |                         |
         *                         *
  [ tenants_datasource ]    [ notifications_userpreference ]
         |                         |
         | 1                       *
         |                  [ notifications_notification ]
         *
  [ complaints_complaintcategory ]
         |
         | 1
         *
  [ complaints_complaint ] 1 ----< * [ complaints_complaintnote ]
         |                 1 ----< * [ complaints_timelineevent ]
         |                 1 ----< * [ complaints_followup ]
         |                 1 ----- 1 [ intelligence_complaintfinding ]
         |                 1 ----- 1 [ resolutions_resolutionoutcome ]
         |                 1 ----< * [ communications_customermessage ]
         |                 1 ----< * [ transactions_transactioninvestigation ]
         |
         | *
         *
  [ incidents_incidentcomplaint ] >---- 1 [ incidents_incident ]
         |
         | 1
         *
  [ evidence_evidencerecord ]

  [ handoffs_receivingteam ] 1 ----< * [ handoffs_teamrecipient ]
         |
         | 1
         *
  [ handoffs_forwardinghandoff ] 1 ----< * [ handoffs_handoffattempt ]

  [ common_idempotencyrecord ]
  [ common_outboxmessage ]
```

---

## 2. Table Specifications by Domain

### 2.1 Multi-Tenancy & External Data Sources (`apps.tenants`)

#### Table: `tenants_tenant`
Represents an onboarded banking institution (e.g., "Fidelity Bank Plc").

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Unique tenant identifier (e.g. `t-fidelity`). |
| `name` | `VARCHAR(255)` | `NOT NULL` | Institution display name. |
| `slug` | `VARCHAR(64)` | `UNIQUE, NOT NULL` | URL-safe identifier. |
| `time_zone` | `VARCHAR(64)` | `NOT NULL, DEFAULT 'Africa/Lagos'` | IANA timezone used for timestamps & SLA calculations. |
| `support_label` | `VARCHAR(255)` | `NOT NULL` | Label for the internal support desk. |
| `support_contact` | `VARCHAR(255)` | `NOT NULL` | Email or internal phone for operations support. |
| `support_hours` | `VARCHAR(128)` | `NOT NULL` | Standard operating hours (e.g. "Mon–Fri 08:00–18:00 WAT"). |
| `is_active` | `BOOLEAN` | `NOT NULL, DEFAULT TRUE` | Active tenant flag. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Record creation timestamp. |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Record last updated timestamp. |

#### Table: `tenants_datasource`
Monitors health and synchronization status of connected banking feeds.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Source identifier. |
| `tenant_id` | `UUID` | `FK(tenants_tenant.id), NOT NULL` | Tenant ownership. |
| `name` | `VARCHAR(255)` | `NOT NULL` | System name (e.g., "Core banking", "Contact centre feed"). |
| `kind` | `VARCHAR(128)` | `NOT NULL` | Category ("Complaint intake", "Transactions", "Switch"). |
| `status` | `VARCHAR(32)` | `NOT NULL, DEFAULT 'AVAILABLE'` | `AVAILABLE`, `STALE`, `UNAVAILABLE`, `UNKNOWN`. |
| `last_updated_at`| `TIMESTAMPTZ` | `NULL` | Timestamp of last received data packet/heartbeat. |
| `note` | `TEXT` | `NULL` | Explanation if stale or degraded. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Record creation timestamp. |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Record last updated timestamp. |

---

### 2.2 Identity, Access Management & Security (`apps.accounts`)

#### Table: `accounts_user`
Standard Django custom user model representing bank operators, supervisors, and compliance verifiers.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Operator UUID (e.g. `u-1`). |
| `tenant_id` | `UUID` | `FK(tenants_tenant.id), NOT NULL` | Multi-tenant isolation anchor. |
| `username` | `VARCHAR(150)` | `UNIQUE, NOT NULL` | System login username / SSO subject ID. |
| `email` | `VARCHAR(254)` | `NOT NULL` | Corporate email address. |
| `first_name` | `VARCHAR(150)` | `NOT NULL` | First name. |
| `last_name` | `VARCHAR(150)` | `NOT NULL` | Surname. |
| `department` | `VARCHAR(128)` | `NOT NULL, DEFAULT 'Customer Care'`| Department unit (e.g., "Customer Care", "Compliance"). |
| `role_label` | `VARCHAR(128)` | `NOT NULL, DEFAULT 'Operator'` | Display role label (e.g., "Senior Resolution Operator"). |
| `permissions_list`| `JSONB` | `NOT NULL, DEFAULT '[]'` | Array of granted permission strings. |
| `is_active` | `BOOLEAN` | `NOT NULL, DEFAULT TRUE` | Active account status. |
| `is_staff` | `BOOLEAN` | `NOT NULL, DEFAULT FALSE` | Django admin access flag. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Record creation timestamp. |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Record last updated timestamp. |

---

### 2.3 Core Complaints Architecture (`apps.complaints`)

#### Table: `complaints_complaintcategory`
Reference categories for complaints.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `code` | `VARCHAR(64)` | `PRIMARY KEY` | Uppercase category code (`TRANSFER`, `CARD`, `CHARGES`, etc.). |
| `tenant_id` | `UUID` | `FK(tenants_tenant.id), NOT NULL` | Scoped to tenant. |
| `label` | `VARCHAR(128)` | `NOT NULL` | Human-readable label (e.g., "Transfer", "Card"). |

#### Table: `complaints_complaint`
Primary complaint record holding customer grievance, assignment, SLA, and lifecycle status.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Internal complaint identifier (`c-1001`). |
| `tenant_id` | `UUID` | `FK(tenants_tenant.id), NOT NULL` | Tenant isolation foreign key. |
| `reference` | `VARCHAR(64)` | `UNIQUE, NOT NULL, INDEX` | Public complaint reference (`TST-1044`). |
| `received_at` | `TIMESTAMPTZ` | `NOT NULL, INDEX` | Timestamp when complaint entered the bank channel. |
| `customer_reference`| `VARCHAR(64)` | `NOT NULL` | Masked customer identifier (`•••• 1234`). |
| `customer_contact`| `VARCHAR(255)` | `NOT NULL` | Encrypted customer phone/email for communications. |
| `summary` | `VARCHAR(500)` | `NOT NULL` | High-level issue summary headline. |
| `narrative` | `TEXT` | `NOT NULL` | Full verbatim customer grievance text. |
| `category_id` | `VARCHAR(64)` | `FK(complaints_complaintcategory.code), NULL` | Assigned category. |
| `priority` | `VARCHAR(32)` | `NOT NULL, DEFAULT 'MEDIUM'` | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`. |
| `status` | `VARCHAR(32)` | `NOT NULL, DEFAULT 'NEW', INDEX` | Current lifecycle state. |
| `assigned_operator_id`| `UUID` | `FK(accounts_user.id), NULL, INDEX`| Currently assigned operator. |
| `assigned_at` | `TIMESTAMPTZ` | `NULL` | Timestamp of current assignment. |
| `due_at` | `TIMESTAMPTZ` | `NULL, INDEX` | Regulatory SLA resolution deadline. |
| `source_channel` | `VARCHAR(128)` | `NOT NULL` | Intake channel ("Contact centre", "Mobile app", "Branch"). |
| `source_reference`| `VARCHAR(128)` | `NOT NULL` | Ingest ticket ID (e.g., "CC-TEST-55821"). |
| `source_id` | `UUID` | `FK(tenants_datasource.id), NOT NULL` | Associated intake feed data source. |
| `reopen_reason` | `TEXT` | `NULL` | Mandatory reason if case was reopened. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Record creation timestamp. |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Record last updated timestamp. |

#### Table: `complaints_complaintnote`
Private case notes created by bank operators.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Note identifier. |
| `complaint_id` | `UUID` | `FK(complaints_complaint.id), NOT NULL` | Parent complaint. |
| `author_id` | `UUID` | `FK(accounts_user.id), NOT NULL` | Operator who wrote the note. |
| `text` | `TEXT` | `NOT NULL` | Note content (max 4000 characters). |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Note creation timestamp. |

#### Table: `complaints_timelineevent`
Immutable audit event log for the complaint lifecycle.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Event identifier. |
| `complaint_id` | `UUID` | `FK(complaints_complaint.id), NOT NULL` | Parent complaint. |
| `at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Timestamp of event occurrence. |
| `kind` | `VARCHAR(64)` | `NOT NULL` | Event category (`RECEIVED`, `ASSIGNED`, `HANDOFF`, `NOTE`, etc.). |
| `title` | `VARCHAR(255)` | `NOT NULL` | Event headline summary. |
| `detail` | `TEXT` | `NULL` | Additional context or failure explanation. |
| `actor` | `VARCHAR(255)` | `NULL` | Human operator or system rule that triggered the event. |

#### Table: `complaints_followup`
Scheduled operator reminders.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Follow-up identifier. |
| `complaint_id` | `UUID` | `FK(complaints_complaint.id), NOT NULL` | Parent complaint. |
| `created_by_id` | `UUID` | `FK(accounts_user.id), NOT NULL` | Operator who scheduled the reminder. |
| `due_at` | `TIMESTAMPTZ` | `NOT NULL, INDEX` | Scheduled alert timestamp (must be in the future). |
| `reason` | `VARCHAR(300)` | `NOT NULL` | Target reason (e.g., "Chase settlement desk"). |
| `completed` | `BOOLEAN` | `NOT NULL, DEFAULT FALSE` | Completion status flag. |

---

### 2.4 Incidents & Incident-Complaint Separation (`apps.incidents`)

#### Table: `incidents_incident`
Represents an underlying banking or infrastructure outage affecting multiple customers.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Incident identifier. |
| `tenant_id` | `UUID` | `FK(tenants_tenant.id), NOT NULL` | Tenant scope. |
| `reference` | `VARCHAR(64)` | `UNIQUE, NOT NULL` | Incident code (`INC-TEST-7`). |
| `title` | `VARCHAR(255)` | `NOT NULL` | Headline (e.g. "Interbank transfers delayed"). |
| `description` | `TEXT` | `NOT NULL` | Incident narrative and technical details. |
| `status` | `VARCHAR(32)` | `NOT NULL, DEFAULT 'DETECTED'` | `DETECTED`, `INVESTIGATING`, `MITIGATED`, `RESOLVED`, `CLOSED`. |
| `severity` | `VARCHAR(32)` | `NOT NULL, DEFAULT 'HIGH'` | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`. |
| `started_at` | `TIMESTAMPTZ` | `NOT NULL` | Estimated onset time of the incident. |
| `mitigated_at` | `TIMESTAMPTZ` | `NULL` | When the incident root cause was corrected. |
| `resolved_at` | `TIMESTAMPTZ` | `NULL` | When the incident was formally closed. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Record creation timestamp. |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Record last updated timestamp. |

#### Table: `incidents_incidentcomplaint`
Explicit link table preserving individual complaint identity while establishing incident association.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Association identifier. |
| `incident_id` | `UUID` | `FK(incidents_incident.id), NOT NULL` | Linked incident. |
| `complaint_id` | `UUID` | `FK(complaints_complaint.id), NOT NULL` | Linked complaint. |
| `relation` | `VARCHAR(128)` | `NOT NULL, DEFAULT 'Possibly part of'`| Semantic description of relation. |
| `confidence` | `FLOAT` | `NOT NULL, DEFAULT 1.0` | Association confidence (0.0 to 1.0). |
| `source` | `VARCHAR(32)` | `NOT NULL, DEFAULT 'AI_DISCOVERY'`| `AI_DISCOVERY`, `OPERATOR_LINKED`. |
| `review_status` | `VARCHAR(32)` | `NOT NULL, DEFAULT 'PENDING_REVIEW'`| `PENDING_REVIEW`, `CONFIRMED`, `DISMISSED`. |
| `reviewed_by_id`| `UUID` | `FK(accounts_user.id), NULL` | Operator who reviewed the link. |
| `reviewed_at` | `TIMESTAMPTZ` | `NULL` | Timestamp of human review. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Creation timestamp. |

*Unique Constraint:* `UNIQUE(incident_id, complaint_id)`

---

### 2.5 Transactions & Authoritative Evidence (`apps.transactions`, `apps.evidence`)

#### Table: `transactions_transactioninvestigation`
Represents core banking transactions under investigation for a specific complaint.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Investigation record ID. |
| `complaint_id` | `UUID` | `FK(complaints_complaint.id), NOT NULL` | Parent complaint. |
| `reference` | `VARCHAR(128)` | `NOT NULL, INDEX` | Core transaction ID (e.g. `TXN-TEST-90311`). |
| `source_system` | `VARCHAR(128)` | `NOT NULL` | System name ("Core banking", "NIBSS"). |
| `amount_value` | `NUMERIC(18,2)`| `NULL` | Monetary transaction amount. |
| `amount_currency`| `VARCHAR(8)` | `NOT NULL, DEFAULT 'NGN'` | ISO currency code. |
| `occurred_at` | `TIMESTAMPTZ` | `NULL` | Transaction posting timestamp. |
| `status_label` | `VARCHAR(64)` | `NULL` | System reported status (e.g., "Debited", "Pending"). |
| `status` | `VARCHAR(32)` | `NOT NULL, DEFAULT 'AVAILABLE'` | Source freshness: `AVAILABLE`, `STALE`, `UNAVAILABLE`. |
| `last_updated_at`| `TIMESTAMPTZ` | `NULL` | Last ledger sync timestamp. |
| `conflict` | `TEXT` | `NULL` | Conflict description (e.g., "core banking shows debited; switch shows pending"). |
| `match_evidence`| `TEXT` | `NULL` | Matching criteria explanation. |

#### Table: `evidence_evidencerecord`
Authoritative proof supporting transaction investigations and case resolutions.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Evidence identifier. |
| `complaint_id` | `UUID` | `FK(complaints_complaint.id), NOT NULL` | Associated complaint. |
| `kind` | `VARCHAR(64)` | `NOT NULL` | Type (`LEDGER_ENTRY`, `SWITCH_LOG`, `REVERSAL_SLIP`, `CUSTOMER_RECEIPT`). |
| `document_reference`| `VARCHAR(255)`| `NOT NULL` | Authoritative journal ID or switch session reference. |
| `is_verified` | `BOOLEAN` | `NOT NULL, DEFAULT FALSE` | Verified flag. |
| `verified_by_id`| `UUID` | `FK(accounts_user.id), NULL` | Verifying compliance/operator user. |
| `raw_payload` | `JSONB` | `NULL` | Raw JSON response from core banking adapter. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Record creation timestamp. |

---

### 2.6 Cross-Team Handoffs (`apps.handoffs`)

#### Table: `handoffs_receivingteam`
Teams eligible to receive forwarded complaints (e.g., "Settlements team", "Card operations").

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(64)` | `PRIMARY KEY` | Team code (`team-settle`, `team-cards`). |
| `tenant_id` | `UUID` | `FK(tenants_tenant.id), NOT NULL` | Scoped to tenant. |
| `name` | `VARCHAR(255)` | `NOT NULL` | Team display name. |
| `channel` | `VARCHAR(255)` | `NOT NULL` | Dispatch channel ("Bank case-management queue", "Secure email"). |
| `response_due_hours`| `INTEGER` | `NOT NULL, DEFAULT 24` | Expected SLA response hours. |

#### Table: `handoffs_teamrecipient`
Individual duty leads or desks on a receiving team.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Recipient identifier. |
| `team_id` | `VARCHAR(64)` | `FK(handoffs_receivingteam.id), NOT NULL`| Parent team. |
| `name` | `VARCHAR(255)` | `NOT NULL` | Recipient name (e.g. "Duty lead", "Reconciliation desk"). |

#### Table: `handoffs_forwardinghandoff`
Represents an inter-team delegation of case responsibility.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Handoff identifier (`h-SEND_FAILED-6`). |
| `complaint_id` | `UUID` | `FK(complaints_complaint.id), NOT NULL` | Parent complaint. |
| `team_id` | `VARCHAR(64)` | `FK(handoffs_receivingteam.id), NOT NULL`| Receiving team. |
| `recipient` | `VARCHAR(255)` | `NULL` | Named recipient if specified. |
| `channel` | `VARCHAR(255)` | `NOT NULL` | Specific channel used for dispatch. |
| `state` | `VARCHAR(32)` | `NOT NULL, DEFAULT 'PREPARED', INDEX` | 13 handoff states. |
| `created_by_id` | `UUID` | `FK(accounts_user.id), NOT NULL` | Operator who forwarded the case. |
| `response_due_at`| `TIMESTAMPTZ` | `NULL` | Calculated SLA response deadline. |
| `response_summary`| `TEXT` | `NULL` | Receiving team's resolution narrative. |
| `response_received_at`| `TIMESTAMPTZ`| `NULL` | When response was recorded. |
| `retry_allowed` | `BOOLEAN` | `NOT NULL, DEFAULT FALSE` | Flag enabling the `Retry send` UI button. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Record creation timestamp. |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Record last updated timestamp. |

#### Table: `handoffs_handoffattempt`
Individual dispatch and delivery attempts for a handoff.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Attempt ID. |
| `handoff_id` | `UUID` | `FK(handoffs_forwardinghandoff.id), NOT NULL` | Parent handoff. |
| `at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Timestamp of attempt. |
| `channel` | `VARCHAR(255)` | `NOT NULL` | Channel attempted. |
| `outcome` | `VARCHAR(255)` | `NOT NULL` | Result (e.g., "Submitted", "Rejected: queue unavailable"). |

---

### 2.7 Maker-Checker Resolution (`apps.resolutions`)

#### Table: `resolutions_resolutionoutcome`
Stores proposed and verified complaint resolution outcomes.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Resolution identifier. |
| `complaint_id` | `UUID` | `UNIQUE, FK(complaints_complaint.id), NOT NULL`| One-to-one with complaint. |
| `outcome` | `TEXT` | `NOT NULL` | Outcome narrative (max 2000 chars). |
| `evidence` | `TEXT` | `NULL` | Reference to supporting evidence/slips. |
| `reported_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Timestamp when reported. |
| `reported_by_id`| `UUID` | `FK(accounts_user.id), NOT NULL` | Operator who reported the outcome (Maker). |
| `verification` | `VARCHAR(32)` | `NOT NULL, DEFAULT 'AWAITING'` | `AWAITING`, `VERIFIED`, `REJECTED`. |
| `verified_at` | `TIMESTAMPTZ` | `NULL` | Verification timestamp. |
| `verified_by_id`| `UUID` | `FK(accounts_user.id), NULL` | Verifying operator/compliance lead (Checker). |
| `verification_note`| `TEXT` | `NULL` | Mandatory reason if rejected; optional if verified. |

*Security Constraint:* A database CHECK constraint or model-level validation ensures `reported_by_id != verified_by_id` when `verification = 'VERIFIED'`.

---

### 2.8 Customer Communication Engine (`apps.communications`)

#### Table: `communications_messagetemplate`
Pre-approved message templates for customer notifications.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(64)` | `PRIMARY KEY` | Template ID (e.g., `INTAKE_ACK`, `PROGRESS_UPDATE`, `RESOLUTION_FINAL`). |
| `tenant_id` | `UUID` | `FK(tenants_tenant.id), NOT NULL` | Tenant ownership. |
| `channel` | `VARCHAR(32)` | `NOT NULL` | `SMS`, `EMAIL`, `WHATSAPP`. |
| `subject` | `VARCHAR(255)` | `NULL` | Subject line (for Email). |
| `body_template` | `TEXT` | `NOT NULL` | Body template containing `{reference}`, `{summary}`, `{outcome}` tokens. |
| `is_active` | `BOOLEAN` | `NOT NULL, DEFAULT TRUE` | Active template flag. |

#### Table: `communications_customermessage`
Audit record of customer-facing notifications.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Message identifier. |
| `tenant_id` | `UUID` | `FK(tenants_tenant.id), NOT NULL` | Tenant scope. |
| `complaint_id` | `UUID` | `FK(complaints_complaint.id), NOT NULL` | Target complaint. |
| `template_id` | `VARCHAR(64)` | `FK(communications_messagetemplate.id), NOT NULL`| Template used. |
| `channel` | `VARCHAR(32)` | `NOT NULL` | Delivery channel (`SMS`, `EMAIL`, `WHATSAPP`). |
| `recipient` | `VARCHAR(255)` | `NOT NULL` | Masked customer address (`••••••@bank.com`, `••••1234`). |
| `rendered_body` | `TEXT` | `NOT NULL` | Exact dispatched text. |
| `status` | `VARCHAR(32)` | `NOT NULL, DEFAULT 'QUEUED'` | `QUEUED`, `DISPATCHED`, `DELIVERED`, `FAILED`. |
| `fingerprint` | `VARCHAR(64)` | `NOT NULL, INDEX` | `SHA-256` hash preventing duplicate messages within 15 mins. |
| `dispatched_at` | `TIMESTAMPTZ` | `NULL` | Dispatch timestamp. |
| `delivered_at` | `TIMESTAMPTZ` | `NULL` | External carrier delivery ACK timestamp. |
| `error_message` | `TEXT` | `NULL` | Failure reason from carrier/gateway. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Record creation timestamp. |

---

### 2.9 AI Intelligence & Embeddings (`apps.intelligence`)

#### Table: `intelligence_complaintfinding`
AI-generated root cause analysis, facts, hypotheses, and recommendations.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Finding identifier. |
| `complaint_id` | `UUID` | `UNIQUE, FK(complaints_complaint.id), NOT NULL`| One-to-one with complaint. |
| `availability` | `VARCHAR(32)` | `NOT NULL, DEFAULT 'UNAVAILABLE'` | `AVAILABLE`, `UNAVAILABLE`, `LOW_CONFIDENCE`. |
| `category` | `VARCHAR(128)` | `NULL` | AI-inferred category. |
| `possible_cause`| `VARCHAR(255)` | `NULL` | AI-inferred root cause. |
| `confidence` | `FLOAT` | `NULL` | Calibrated confidence score (0.0 to 1.0). |
| `recommended_next_step`| `TEXT` | `NULL` | Contextual action recommendation. |
| `facts` | `JSONB` | `NOT NULL, DEFAULT '[]'` | Confirmed facts derived from source banking records. |
| `hypotheses` | `JSONB` | `NOT NULL, DEFAULT '[]'` | Speculative inferences marked with sparkle icon. |
| `evidence` | `JSONB` | `NOT NULL, DEFAULT '[]'` | Supporting audit records and timestamps. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Finding generation timestamp. |

#### Table: `intelligence_embeddingstore`
Stores dense vectors with variable dimensions to prevent hardcoding embedding models.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Store ID. |
| `complaint_id` | `UUID` | `UNIQUE, FK(complaints_complaint.id), NOT NULL`| Parent complaint. |
| `model_name` | `VARCHAR(128)` | `NOT NULL` | Embedding model identifier (`all-MiniLM-L6-v2`, `text-embedding-3-small`). |
| `dimension` | `INTEGER` | `NOT NULL` | Vector length (e.g. 384 or 1536). |
| `vector_data` | `VECTOR(384)` | `NULL` | pgvector dense vector column (or fallback JSON array if pgvector disabled). |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Creation timestamp. |

---

### 2.10 In-App Notifications & Preferences (`apps.notifications`)

#### Table: `notifications_notification`
In-app alerts for operators.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Notification identifier (`nt1`). |
| `recipient_id` | `UUID` | `FK(accounts_user.id), NOT NULL, INDEX`| Operator recipient. |
| `kind` | `VARCHAR(64)` | `NOT NULL` | Alert kind (`ASSIGNED`, `RESPONSE`, `DEADLINE`, `REOPENED`). |
| `title` | `VARCHAR(255)` | `NOT NULL` | Alert headline text. |
| `occurred_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Event occurrence timestamp. |
| `read` | `BOOLEAN` | `NOT NULL, DEFAULT FALSE, INDEX` | Read status. |
| `complaint_id` | `UUID` | `FK(complaints_complaint.id), NULL` | Linked complaint for deep-link navigation. |

#### Table: `notifications_userpreference`
Operator-specific notification subscription preferences.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Preference ID. |
| `user_id` | `UUID` | `FK(accounts_user.id), NOT NULL` | Target operator. |
| `key` | `VARCHAR(64)` | `NOT NULL` | Preference key (`assigned`, `responses`, `deadlines`). |
| `label` | `VARCHAR(128)` | `NOT NULL` | UI display label. |
| `description` | `VARCHAR(255)` | `NOT NULL` | UI descriptive subtext. |
| `enabled` | `BOOLEAN` | `NOT NULL, DEFAULT TRUE` | Toggle state. |

*Unique Constraint:* `UNIQUE(user_id, key)`

---

### 2.11 Reliability, Idempotency & Transactional Outbox (`apps.common`)

#### Table: `common_idempotencyrecord`
Guarantees exactly-once mutation semantics across network retries.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `key` | `UUID` | `PRIMARY KEY` | Idempotency UUID passed in `Idempotency-Key` header. |
| `user_id` | `UUID` | `FK(accounts_user.id), NOT NULL` | Scoped to authenticated user. |
| `request_path` | `VARCHAR(255)` | `NOT NULL` | Target API path. |
| `request_hash` | `VARCHAR(64)` | `NOT NULL` | `SHA-256` hash of request body to detect payload tampering. |
| `status` | `VARCHAR(32)` | `NOT NULL, DEFAULT 'PENDING'` | `PENDING`, `COMPLETED`. |
| `response_status`| `INTEGER` | `NULL` | HTTP status code returned upon completion (e.g. 200, 204). |
| `response_body` | `JSONB` | `NULL` | Cached JSON response payload. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW(), INDEX` | Auto-purged after 24 hours. |

#### Table: `common_outboxmessage`
Implements the Transactional Outbox pattern to decouple atomic DB mutations from external network side-effects.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Message identifier. |
| `tenant_id` | `UUID` | `FK(tenants_tenant.id), NOT NULL` | Tenant ownership. |
| `topic` | `VARCHAR(128)` | `NOT NULL, INDEX` | Target queue/event topic (e.g., `communications.dispatch`, `ai.embedding`). |
| `payload` | `JSONB` | `NOT NULL` | Event payload containing entity IDs and mutation specifics. |
| `status` | `VARCHAR(32)` | `NOT NULL, DEFAULT 'PENDING', INDEX`| `PENDING`, `PROCESSING`, `PUBLISHED`, `FAILED`. |
| `retry_count` | `INTEGER` | `NOT NULL, DEFAULT 0` | Current retry attempt count. |
| `last_error` | `TEXT` | `NULL` | Exception stack trace on delivery failure. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Record creation timestamp. |
| `processed_at` | `TIMESTAMPTZ` | `NULL` | Timestamp of successful dispatch. |

---

## 3. Database Indexes & Performance Optimization

```sql
-- 1. Full-text search and filtering on Complaints
CREATE INDEX idx_complaints_tenant_status ON complaints_complaint(tenant_id, status);
CREATE INDEX idx_complaints_tenant_due ON complaints_complaint(tenant_id, due_at);
CREATE INDEX idx_complaints_operator ON complaints_complaint(assigned_operator_id, status);
CREATE INDEX idx_complaints_ref_trgm ON complaints_complaint USING gin (reference gin_trgm_ops);

-- 2. Handoffs lifecycle and SLA monitoring
CREATE INDEX idx_handoffs_state_due ON handoffs_forwardinghandoff(state, response_due_at);

-- 3. In-App Notifications unread feed
CREATE INDEX idx_notifications_user_unread ON notifications_notification(recipient_id, read, occurred_at DESC);

-- 4. Idempotency Key lookup
CREATE INDEX idx_idempotency_lookup ON common_idempotencyrecord(key, user_id);

-- 5. Outbox Message Polling index
CREATE INDEX idx_outbox_pending ON common_outboxmessage(status, created_at) WHERE status = 'PENDING';

-- 6. Vector Similarity Index (HNSW) for Semantic Clustering
CREATE INDEX idx_complaint_embedding_hnsw ON intelligence_embeddingstore 
USING hnsw (vector_data vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```
