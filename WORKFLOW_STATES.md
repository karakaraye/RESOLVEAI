# ResolveAI Workflow States & Lifecycle State Machine Specification

> **Document Version:** 2.0.0  
> **System:** Banking Incident Intelligence & Resolution System (BIIRS)  
> **Author:** Senior Software Architect, ResolveAI  
> **Status:** APPROVED / IMPLEMENTATION-READY  

---

## 1. Complaint Lifecycle State Machine

The complaint status governs operator actions and regulatory SLA timers. The browser does not calculate transitions; the server calculates `allowedActions` based on the current state.

```
                  +-------------------+
                  |        NEW        |
                  +-------------------+
                            |
           [Intake / Assign / Initial Review]
                            v
                  +-------------------+
                  |   NEEDS_ACTION    | <---------------+
                  +-------------------+                 |
                     |             |                    |
        [Investigate]|             |[Forward to Team]   |
                     v             v                    |
       +---------------+   +---------------+            |
       |  IN_PROGRESS  |   |   FORWARDED   |            |
       +---------------+   +---------------+            |
              |                    |                    |
              +---------+----------+                    |
                        |                               |
                 [Record Outcome]                       |
                        v                               |
           +-------------------------+                  |
           |  AWAITING_VERIFICATION  |                  |
           +-------------------------+                  |
                 |             |                        |
         [Verify]|             |[Reject Outcome]        |
                 v             +------------------------+
           +---------------+                            |
           |   RESOLVED    |                            |
           +---------------+                            |
                   |                                    |
             [Reopen Case]                              |
                   +------------------------------------+
```

### 1.1 Complaint State Definitions

| State | Semantic Meaning | Allowed Actions |
| :--- | :--- | :--- |
| `NEW` | Complaint has just arrived from an intake channel and awaits initial operator review. | `ASSIGN`, `FORWARD`, `ADD_NOTE`, `SET_FOLLOW_UP`, `RECORD_OUTCOME` |
| `NEEDS_ACTION` | Complaint is unassigned, information is incomplete, or an external handoff failed. | `ASSIGN`, `FORWARD`, `ADD_NOTE`, `SET_FOLLOW_UP`, `RECORD_OUTCOME` |
| `IN_PROGRESS` | An operator is actively investigating ledger records, switch logs, or customer evidence. | `ASSIGN`, `FORWARD`, `ADD_NOTE`, `SET_FOLLOW_UP`, `RECORD_OUTCOME` |
| `FORWARDED` | Responsibility or technical investigation has been dispatched to a specialized bank team. | `SET_FOLLOW_UP`, `RECORD_OUTCOME`, `ADD_NOTE`, `ASSIGN` |
| `AWAITING_VERIFICATION` | An outcome has been reported (Maker). Awaiting independent verification (Checker). | `VERIFY_OUTCOME`, `ADD_NOTE` |
| `RESOLVED` | Outcome has been verified by an authorized verifier. SLA timer stops. | `ADD_NOTE`, `REOPEN` |
| `REOPENED` | Customer disputed the resolution or new evidence emerged. SLA timer restarts. | `ASSIGN`, `FORWARD`, `ADD_NOTE`, `SET_FOLLOW_UP`, `RECORD_OUTCOME` |

---

## 2. Handoff Lifecycle State Machine (13 States)

Cross-team handoffs represent asynchronous delegation to internal bank departments (Settlements, Cards, Fraud, Core Banking Operations).

```
[ PREPARED ] ---> [ SENT ] ---> [ DELIVERY_UNCONFIRMED ] ---> [ DELIVERED ]
      |              |
      |              +---> [ SEND_FAILED ] <---> [ RETRY_SCHEDULED ]
      |                                              |
      +---> [ FALLBACK_IN_PROGRESS ] <---------------+

[ DELIVERED ] ---> [ ACKNOWLEDGED ] ---> [ ACCEPTED ] ---> [ AWAITING_RESPONSE ]
                                                                   |
                                  +--------------------------------+
                                  |                                |
                           [ RESPONDED ]                      [ OVERDUE ]
                                  |                                |
                                  +---------------+----------------+
                                                  |
                                                  v
                                              [ CLOSED ]
```

### 2.1 Handoff State Matrix

| State | Tone | Semantic Definition | Next Allowed Progression |
| :--- | :--- | :--- | :--- |
| `PREPARED` | Neutral | Handoff is being packaged; nothing has left ResolveAI. | `SENT`, `FALLBACK_IN_PROGRESS` |
| `SENT` | Info | Submitted to the team's channel; receipt unconfirmed. | `DELIVERED`, `DELIVERY_UNCONFIRMED`, `SEND_FAILED` |
| `DELIVERY_UNCONFIRMED` | Warning | Channel accepted message without delivery ACK. | `DELIVERED`, `SEND_FAILED` |
| `DELIVERED` | Info | Receiving system/channel confirmed delivery. | `ACKNOWLEDGED`, `ACCEPTED` |
| `ACKNOWLEDGED` | Accent | Receiving team opened or registered receipt. | `ACCEPTED`, `AWAITING_RESPONSE` |
| `ACCEPTED` | Accent | Receiving team formally assumed responsibility. | `AWAITING_RESPONSE` |
| `AWAITING_RESPONSE` | Neutral | Team is working; response deadline active. | `RESPONDED`, `OVERDUE` |
| `RESPONDED` | Success | Team provided final investigation response. | `CLOSED` |
| `OVERDUE` | Danger | Response deadline passed without reply. | `RESPONDED`, `CLOSED` |
| `SEND_FAILED` | Danger | All approved channels failed. `retryAllowed = True`. | `RETRY_SCHEDULED`, `FALLBACK_IN_PROGRESS` |
| `RETRY_SCHEDULED` | Warning | System or operator scheduled a retry attempt. | `SENT`, `SEND_FAILED` |
| `FALLBACK_IN_PROGRESS`| Warning | Primary channel failed; secondary channel active. | `SENT`, `SEND_FAILED` |
| `CLOSED` | Success | Handoff objective complete. | End state |

---

## 3. Incident Lifecycle & Incident-Complaint Separation

### 3.1 Incident State Machine

```
[ DETECTED ] ---> [ INVESTIGATING ] ---> [ MITIGATED ] ---> [ RESOLVED ] ---> [ POSTMORTEM ]
```

- **`DETECTED`**: AI clustering or operational alerts flagged a shared anomaly (e.g. 15 complaints with debit failures on switch X).
- **`INVESTIGATING`**: Infrastructure/Operations lead is diagnosing switch/core banking telemetry.
- **`MITIGATED`**: Workaround applied (e.g. network switch rebooted, failover active).
- **`RESOLVED`**: System restored to 100% operational capacity.
- **`POSTMORTEM`**: Root cause analysis archived for risk auditors.

### 3.2 The Incident-Complaint Resolution Invariant

> **CRITICAL ARCHITECTURAL PRINCIPLE:**  
> **An Incident Resolution does NOT equal a Complaint Resolution.**

```
+---------------------------------------------------------------------------------------------------------+
|                                    INCIDENT RESOLUTION GATEWAY                                          |
+---------------------------------------------------------------------------------------------------------+

                 [ INCIDENT: "NIBSS Interbank Transfer Timeout" Marked RESOLVED ]
                                                |
                                                v
               +----------------------------------------------------------------+
               |  ResolveAI Event Engine: Scans all linked IncidentComplaint   |
               |  associations for INC-2026-007                                 |
               +----------------------------------------------------------------+
                                                |
                   +----------------------------+----------------------------+
                   |                                                         |
                   v                                                         v
        [ Linked Complaint A ]                                    [ Linked Complaint B ]
        - Customer debited: YES                                   - Customer debited: YES
        - Destination credited: YES (delayed)                     - Destination credited: NO
                   |                                                         |
                   v                                                         v
        Outcome: Auto-reconciled                                  Outcome: Requires Manual Reversal
        Status: Moves to AWAITING_VERIFICATION                    Status: Moves to NEEDS_ACTION
                   |                                                         |
                   v                                                         v
        Verification by Checker: PASS                             Operator processes Reversal
        Status: RESOLVED                                          Verification by Checker: PASS
                   |                                              Status: RESOLVED
                   v                                                         |
        [ Customer Resolution SMS Sent ]                                     v
                                                                  [ Customer Resolution SMS Sent ]
```

#### Verification Gate Rules
1. **No Automatic Customer Notifications:** When an incident transitions to `RESOLVED`, the system **never** sends mass resolution messages to complainants.
2. **Individual State Transition:** Linked complaints transition to `AWAITING_VERIFICATION` (if transaction logs prove debit reversed or value delivered) or `NEEDS_ACTION` (if manual journal posting is required).
3. **Mandatory Checker Sign-Off:** Each individual complaint must have its `ResolutionOutcome` approved by an independent verifier. Only upon that individual verification does the Communications Engine release the final customer notification.

---

## 4. Two-Person Maker-Checker Verification Workflow

```
[ Operator A (Maker) ]
         |
         v
  Submits POST /complaints/{id}/resolution
  - Outcome narrative: "Reversal posted"
  - Evidence: "JRNL-2026-99120"
         |
         v
  Complaint.status = "AWAITING_VERIFICATION"
  ResolutionOutcome.verification = "AWAITING"
         |
         v
+---------------------------------------------------------------------------------------+
| SERVER-SIDE MAKER-CHECKER SECURITY INVARIANT                                          |
|                                                                                       |
| If request.user.id == complaint.resolution.reported_by.id:                            |
|     - allowedActions does NOT contain "VERIFY_OUTCOME"                                |
|     - Submitting POST .../verification returns HTTP 403 Forbidden ("Self-verification |
|       is strictly prohibited under banking compliance rules.")                        |
+---------------------------------------------------------------------------------------+
         |
         +----------------------------------+
         |                                  |
         v                                  v
[ Operator B (Checker - VERIFY) ]    [ Operator B (Checker - REJECT) ]
- Verifies ledger & evidence         - Discovers funds still trapped
- Complaint.status = "RESOLVED"      - Complaint.status = "IN_PROGRESS"
- Resolution.verification =          - Resolution.verification =
  "VERIFIED"                           "REJECTED"
- Audit timeline logged              - Mandatory rejection note saved
- Triggers Outbound Customer         - Case returns to operator queue
  Resolution Notification
```

---

## 5. Customer Communication State Machine

```
[ Intake Received ] ---> [ QUEUED ] ---> [ DISPATCHED ] ---> [ DELIVERED ]
                              |                |
                              |                +---> [ FAILED ] ---> [ RETRY_SCHEDULED ]
                              |                                             |
                              +---------------------------------------------+
```

### De-duplication Invariant
Before transitioning any message to `QUEUED`:
1. Calculate fingerprint: `SHA256(tenant_id + complaint_id + template_id + recipient)`.
2. Check if a message with this fingerprint was created within the last 15 minutes.
3. If duplicate detected: abort dispatch, log duplicate warning to audit log, return existing message ID.
