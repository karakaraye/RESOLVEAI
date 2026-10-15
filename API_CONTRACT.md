# ResolveAI REST API Contract & Wire Specification

> **API Version:** `/api/v1`  
> **Protocol:** HTTPS / REST  
> **Data Format:** JSON (`application/json`)  
> **Source of Truth:** Client definitions in [`src/lib/api/types.ts`](file:///c:/Users/HIMSON/Desktop/Front%20End/src/lib/api/types.ts) and [`src/lib/api/endpoints.ts`](file:///c:/Users/HIMSON/Desktop/Front%20End/src/lib/api/endpoints.ts)  
> **Status:** APPROVED / IMPLEMENTATION-READY  

---

## 1. Global Wire Protocols & Header Specifications

All client requests must adhere to the following HTTP header standards:

```http
Accept: application/json
Content-Type: application/json
```

### 1.1 Authentication & Session
- Authentication is cookie-based via Django session (`sessionid`).
- Browser requests include credentials: `fetch(url, { credentials: "include" })`.

### 1.2 Anti-CSRF Defense
1. **Header `X-BIIRS-Request: 1`:** Mandatory on all state-changing HTTP methods (`POST`, `PUT`, `PATCH`, `DELETE`). Requests lacking this header are rejected with HTTP 403 Forbidden.
2. **Header `X-CSRFToken: <token>`:** Extracted from the `csrftoken` cookie or returned by `GET /api/v1/session`.

### 1.3 Idempotency Guarantee
- All mutating requests pass a client-generated UUIDv4 header:
  ```http
  Idempotency-Key: 123e4567-e89b-12d3-a456-426614174000
  ```
- Submitting the same key with the same body returns the cached response with the original status code.
- Submitting the same key while a prior request is processing returns `HTTP 409 Conflict`.

### 1.4 Standard Error Response Schema
All error responses adhere to the frontend's `ApiError` interface:

```json
{
  "message": "Human-readable explanation of why the request failed."
}
```

#### Status Code to `ApiErrorKind` Mapping
- `400 / 422` $\rightarrow$ `validation`
- `401` $\rightarrow$ `unauthorized`
- `403` $\rightarrow$ `forbidden`
- `404` $\rightarrow$ `not-found`
- `409` $\rightarrow$ `conflict`
- `500` $\rightarrow$ `server`

---

## 2. Authentication & Session Endpoints

### 2.1 Get Current Session
`GET /api/v1/session`

- **Description:** Returns the active operator profile, tenant context, and permissions.
- **Security:** Requires valid session cookie.
- **Response (200 OK):**
```json
{
  "user": {
    "id": "u-1",
    "displayName": "Test Operator",
    "email": "operator@bank.test",
    "department": "Customer Care",
    "roleLabel": "Operator"
  },
  "tenant": {
    "id": "t-1",
    "name": "Test Bank",
    "timeZone": "Africa/Lagos",
    "support": {
      "label": "Test Bank BIIRS desk",
      "contact": "biirs-support@bank.test",
      "hours": "Mon–Fri 08:00–18:00"
    }
  },
  "permissions": [
    "complaints.read",
    "complaints.assign",
    "complaints.forward",
    "complaints.notes",
    "complaints.follow_up",
    "complaints.record_outcome",
    "reports.read"
  ],
  "session": {
    "identityProvider": "Azure Active Directory",
    "signedInAt": "2026-10-14T08:00:00Z",
    "expiresAt": "2026-10-14T20:00:00Z",
    "signOutAffectsOtherSessions": false
  }
}
```
- **Error (401 Unauthorized):**
```json
{ "message": "Sign in to continue." }
```

### 2.2 Sign Out
`POST /api/v1/session/sign-out`

- **Headers:** `X-BIIRS-Request: 1`
- **Response (200 OK):**
```json
{
  "redirectUrl": "/signed-out"
}
```

### 2.3 Development-Only Persona Login
`POST /api/v1/auth/dev-login`

- **Guardrail:** Only active when `settings.DEBUG = True` and `settings.ALLOW_DEV_AUTH = True`.
- **Request Body:**
```json
{
  "persona": "operator"
}
```
*Valid personas:* `operator` (standard case worker), `verifier` (compliance officer with outcome verification rights), `lead` (supervisor).
- **Response (200 OK):** Sets `sessionid` and `csrftoken` cookies and returns the `Session` payload.

---

## 3. Reference Data & Workspace Aggregates

### 3.1 Get Reference Categories
`GET /api/v1/reference/categories`

- **Response (200 OK):**
```json
[
  { "code": "TRANSFER", "label": "Transfer" },
  { "code": "CARD", "label": "Card" },
  { "code": "CHARGES", "label": "Charges" },
  { "code": "MOBILE", "label": "Mobile banking" },
  { "code": "ACCOUNT", "label": "Account" },
  { "code": "ATM", "label": "ATM" }
]
```

### 3.2 Get Workspace Summary
`GET /api/v1/workspace/summary?scope=all|mine`

- **Query Parameters:**
  - `scope`: `"all"` (tenant-wide) or `"mine"` (scoped to `request.user`).
- **Response (200 OK):**
```json
{
  "counts": {
    "new": 6,
    "needsAttention": 5,
    "inProgress": 9,
    "awaitingVerification": 3,
    "overdue": 2,
    "resolvedVerified": 14,
    "totalAssigned": 18
  },
  "nextActions": [
    { "kind": "OVERDUE", "count": 2 },
    { "kind": "REVIEW_NEW", "count": 6 },
    { "kind": "FOLLOW_UP_RESPONSE", "count": 4 },
    { "kind": "VERIFY_RESOLUTION", "count": 1, "complaintId": "c-1004" },
    { "kind": "DEADLINE_APPROACHING", "count": 3 }
  ],
  "generatedAt": "2026-10-14T12:00:00Z"
}
```

---

## 4. Complaints Register & Operations

### 4.1 Query Complaints Register
`GET /api/v1/complaints`

- **Query Parameters:**
  - `q`: Search term (matches reference, summary, or customer reference).
  - `status`: `NEW`, `NEEDS_ACTION`, `IN_PROGRESS`, `FORWARDED`, `AWAITING_VERIFICATION`, `RESOLVED`, `REOPENED`.
  - `priority`: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.
  - `category`: Category code (e.g., `TRANSFER`).
  - `due`: Due filter on `/my-cases` (`overdue`, `today`, `soon`, `week`, `none`).
  - `received`: Received filter on `/complaints` (`today`, `7d`, `30d`, `90d`).
  - `scope`: `"all"` or `"mine"`.
  - `page`: Page integer (default `1`).
  - `pageSize`: Page size integer (`25` or `50`).
- **Response (200 OK):**
```json
{
  "items": [
    {
      "id": "c-1001",
      "reference": "TST-1044",
      "receivedAt": "2026-10-14T08:30:00Z",
      "customerReference": "•••• 1234",
      "summary": "Transfer not received after debit",
      "category": { "code": "TRANSFER", "label": "Transfer" },
      "priority": "HIGH",
      "status": "NEEDS_ACTION",
      "assignedOperator": { "id": "u-1", "displayName": "Test Operator" },
      "assignedAt": "2026-10-14T09:00:00Z",
      "dueAt": "2026-10-15T08:30:00Z",
      "overdue": false,
      "allowedActions": ["ASSIGN", "FORWARD", "ADD_NOTE", "SET_FOLLOW_UP", "RECORD_OUTCOME"]
    }
  ],
  "total": 32,
  "page": 1,
  "pageSize": 25
}
```

### 4.2 Get Complaint Detail
`GET /api/v1/complaints/{complaintId}`

- **Response (200 OK):**
```json
{
  "id": "c-1001",
  "reference": "TST-1044",
  "receivedAt": "2026-10-14T08:30:00Z",
  "customerReference": "•••• 1234",
  "summary": "Transfer not received after debit",
  "category": { "code": "TRANSFER", "label": "Transfer" },
  "priority": "HIGH",
  "status": "NEEDS_ACTION",
  "assignedOperator": { "id": "u-1", "displayName": "Test Operator" },
  "assignedAt": "2026-10-14T09:00:00Z",
  "dueAt": "2026-10-15T08:30:00Z",
  "overdue": false,
  "allowedActions": ["ASSIGN", "FORWARD", "ADD_NOTE", "SET_FOLLOW_UP", "RECORD_OUTCOME"],
  "narrative": "Customer reports a transfer sent on Monday morning has not reached the recipient. The amount left their account. They contacted the branch and were told to wait 24 hours, which has now passed.",
  "sourceChannel": "Contact centre",
  "sourceReference": "CC-TEST-55821",
  "source": { "name": "Contact centre feed", "status": "AVAILABLE", "lastUpdatedAt": "2026-10-14T11:30:00Z" },
  "transactions": [
    {
      "reference": "TXN-TEST-90311",
      "sourceSystem": "Core banking",
      "amount": { "value": "45,000.00", "currency": "NGN" },
      "occurredAt": "2026-10-13T09:00:00Z",
      "statusLabel": "Debited",
      "status": "STALE",
      "lastUpdatedAt": "2026-10-14T03:00:00Z",
      "conflict": "core banking shows debited; switch shows pending",
      "matchEvidence": "Same account, amount and time window as the complaint"
    }
  ],
  "related": [
    { "id": "c-1007", "kind": "COMPLAINT", "reference": "TST-1038", "title": "Transfer not received", "relation": "Possible duplicate" },
    { "id": "inc-1", "kind": "INCIDENT", "reference": "INC-TEST-7", "title": "Interbank transfers delayed", "relation": "Possibly part of" }
  ],
  "findings": {
    "availability": "AVAILABLE",
    "category": "Transfer",
    "possibleCause": "Interbank switch delay",
    "confidence": 0.62,
    "recommendedNextStep": "The settlements team handles switch delays; forwarding is suggested.",
    "facts": ["The debit is recorded in core banking."],
    "hypotheses": ["The transfer is held at the interbank switch.", "Related to INC-TEST-7, which has 14 linked complaints."],
    "evidence": ["Switch status: pending (updated 9 hours ago)"]
  },
  "notes": [
    { "id": "n1", "author": "Test Operator", "createdAt": "2026-10-14T09:15:00Z", "text": "Called the customer to confirm the recipient account number." }
  ],
  "handoffs": [
    {
      "id": "h-SEND_FAILED-6",
      "team": { "id": "team-settle", "name": "Settlements team" },
      "recipient": "Duty lead",
      "channel": "Bank case-management queue",
      "state": "SEND_FAILED",
      "createdAt": "2026-10-14T06:00:00Z",
      "createdBy": "Test Operator",
      "lastUpdatedAt": "2026-10-14T07:00:00Z",
      "responseDueAt": "2026-10-15T06:00:00Z",
      "attempts": [
        { "at": "2026-10-14T06:00:00Z", "channel": "Case-management queue", "outcome": "Rejected: queue unavailable" }
      ],
      "retryAllowed": true
    }
  ],
  "resolution": undefined,
  "reopenReason": undefined,
  "timeline": [
    { "id": "e1", "at": "2026-10-14T08:30:00Z", "kind": "RECEIVED", "title": "Complaint received", "detail": "Contact centre" },
    { "id": "e2", "at": "2026-10-14T09:00:00Z", "kind": "ASSIGNED", "title": "Assigned to Test Operator", "actor": "Routing rules" }
  ]
}
```

### 4.3 Get Eligible Assignees
`GET /api/v1/complaints/{complaintId}/eligible-assignees`

- **Response (200 OK):**
```json
[
  { "id": "u-1", "displayName": "Test Operator", "team": "Customer Care", "openCases": 18 },
  { "id": "u-2", "displayName": "Second Operator", "team": "Customer Care", "openCases": 9 }
]
```

### 4.4 Assign Complaint
`POST /api/v1/complaints/{complaintId}/assignment`

- **Headers:** `X-BIIRS-Request: 1`, `Idempotency-Key: <UUID>`
- **Request Body:**
```json
{
  "assigneeId": "u-1",
  "reason": "Escalated from tier-1 queue"
}
```
- **Response (204 No Content)**

### 4.5 Get Forwarding Options
`GET /api/v1/complaints/{complaintId}/forwarding-options`

- **Response (200 OK):**
```json
{
  "recommendedTeamId": "team-settle",
  "teams": [
    {
      "id": "team-settle",
      "name": "Settlements team",
      "recipients": ["Duty lead", "Reconciliation desk"],
      "channel": "Bank case-management queue",
      "responseDueHours": 24
    },
    {
      "id": "team-cards",
      "name": "Card operations",
      "recipients": [],
      "channel": "Secure email",
      "responseDueHours": 48
    }
  ],
  "shareableSummary": "TST-1044 · Transfer not received. Customer reports a debited transfer has not reached the recipient after 24 hours. Transaction TXN-TEST-90311.",
  "sharedFields": [
    "Complaint reference",
    "Issue summary",
    "Transaction reference",
    "Masked customer reference"
  ]
}
```

### 4.6 Forward Complaint (Create Handoff)
`POST /api/v1/complaints/{complaintId}/handoffs`

- **Headers:** `X-BIIRS-Request: 1`, `Idempotency-Key: <UUID>`
- **Request Body:**
```json
{
  "teamId": "team-settle",
  "recipient": "Duty lead",
  "message": "TST-1044 · Transfer not received. Please trace switch session."
}
```
- **Response (200 OK):** Returns created `Handoff` object with state (e.g., `SENT`).

### 4.7 Retry Failed Handoff
`POST /api/v1/handoffs/{handoffId}/retry`

- **Headers:** `X-BIIRS-Request: 1`, `Idempotency-Key: <UUID>`
- **Response (200 OK):** Returns updated `Handoff` with state `"RETRY_SCHEDULED"`.

### 4.8 Add Internal Note
`POST /api/v1/complaints/{complaintId}/notes`

- **Headers:** `X-BIIRS-Request: 1`, `Idempotency-Key: <UUID>`
- **Request Body:**
```json
{
  "text": "Confirmed switch reference with settlements lead."
}
```
- **Response (204 No Content)**

### 4.9 Set Follow-Up Deadline
`POST /api/v1/complaints/{complaintId}/follow-ups`

- **Headers:** `X-BIIRS-Request: 1`, `Idempotency-Key: <UUID>`
- **Request Body:**
```json
{
  "dueAt": "2026-10-16T14:00:00Z",
  "reason": "Check reconciliation file"
}
```
- **Response (204 No Content)**

### 4.10 Record Outcome (Propose Resolution)
`POST /api/v1/complaints/{complaintId}/resolution`

- **Headers:** `X-BIIRS-Request: 1`, `Idempotency-Key: <UUID>`
- **Request Body:**
```json
{
  "outcome": "Funds reversed back to customer account via manual journal entry.",
  "evidence": "Journal reference JRNL-2026-99120"
}
```
- **Response (204 No Content)**: Moves case to `AWAITING_VERIFICATION`.

### 4.11 Verify Outcome (Maker-Checker Gate)
`POST /api/v1/complaints/{complaintId}/resolution/verification`

- **Headers:** `X-BIIRS-Request: 1`, `Idempotency-Key: <UUID>`
- **Request Body:**
```json
{
  "decision": "VERIFY",
  "note": "Reversal confirmed on core banking ledger."
}
```
- **Security Check:** Backend verifies `request.user != resolution.reported_by`. Rejects self-verification with `403 Forbidden`.
- **Response (204 No Content)**: If verified, case status transitions to `RESOLVED`, and customer final resolution message is dispatched via the Communications Engine.

### 4.12 Reopen Case
`POST /api/v1/complaints/{complaintId}/reopen`

- **Headers:** `X-BIIRS-Request: 1`, `Idempotency-Key: <UUID>`
- **Request Body:**
```json
{
  "reason": "Customer states funds still not reflecting in destination bank."
}
```
- **Response (204 No Content)**

---

## 5. Handoffs, Reports & Notifications

### 5.1 Query Handoffs Register
`GET /api/v1/handoffs`

- **Query Parameters:** `q`, `state`, `page`, `pageSize`.
- **Response (200 OK):** `Page<HandoffSummary>`.

### 5.2 Get Handoff Summary Counts
`GET /api/v1/handoffs/summary`

- **Response (200 OK):**
```json
{
  "total": 41,
  "awaitingResponse": 9,
  "responded": 27,
  "overdue": 3,
  "failed": 2
}
```

### 5.3 Get Analytical Report
`GET /api/v1/reports/{reportType}?range=&from=&to=`

- **Types:** `overview`, `complaint-volumes`, `recurring-issues`, `resolution-performance`, `team-response-times`, `overdue-cases`, `incident-trends`.
- **Response (200 OK):** Returns `ReportResult` with coverage note, metrics, series data, and definitions.

### 5.4 Notifications Endpoints
- `GET /api/v1/notifications?unread=true&page=&pageSize=`: Returns `NotificationPage`.
- `POST /api/v1/notifications/{id}/read`: Marks notification read. Returns 204.
- `POST /api/v1/notifications/read-all`: Marks all read. Returns 204.
- `GET /api/v1/me/notification-preferences`: Returns `NotificationPreference[]`.
- `PUT /api/v1/me/notification-preferences`: Body: `[{ "key": "deadlines", "enabled": true }]`. Returns updated array.
- `GET /api/v1/data-sources`: Returns `DataSource[]`.
