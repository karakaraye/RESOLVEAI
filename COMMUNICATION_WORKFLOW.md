# ResolveAI Customer Communication Engine Specification

> **Document Version:** 2.0.0  
> **Subsystem:** `apps.communications`  
> **Channels:** SMS, Email, WhatsApp Push  
> **Delivery Model:** Transactional Outbox & Celery Worker Dispatch  
> **Status:** APPROVED / IMPLEMENTATION-READY  

---

## 1. Engine Objectives & Architectural Mandates

The ResolveAI Customer Communication Engine delivers timely, regulatory-compliant communications to customers while strictly upholding banking integrity invariants:

1. **Deterministic Reference Generation:** Every customer complaint receives a human-readable tracking reference (e.g. `TST-1044` / `FID-2026-09811`) in the initial acknowledgement.
2. **Strict Verification Gate (Anti-Premature Notification):** No resolution message can be dispatched merely because an underlying IT or payment switch incident was marked resolved. Every individual complaint requires independent verification of its specific outcome.
3. **Guaranteed Delivery with De-duplication:** All outbound communications use the Transactional Outbox pattern with payload fingerprinting to prevent duplicate SMS/email blasts during network retries.
4. **Complete Audit Trail:** Every dispatched message, delivery receipt, and carrier error code is immutably archived.

```
+---------------------------------------------------------------------------------------------------------+
|                                  COMMUNICATION ENGINE ARCHITECTURE                                      |
+---------------------------------------------------------------------------------------------------------+

  Trigger Event (Intake / Status Change / Maker-Checker Verified)
       |
       v
  [ Communication Policy & Verification Gate ]
       |
       |-- Is this a Resolution Message?
       |      |
       |      +---> NO  ===> Proceed
       |      |
       |      +---> YES ===> Check: Is individual Complaint status == "RESOLVED"
       |                     AND ResolutionOutcome.verification == "VERIFIED"?
       |                        |
       |                        +--- NO  ===> [ DISPATCH BLOCKED ] (Halt - No Premature Notice)
       |                        +--- YES ===> Proceed
       v
  [ Message Template Renderer ]
       - Template: INTAKE_ACK, PROGRESS_UPDATE, RESOLUTION_FINAL
       - Substitutes: {reference}, {summary}, {outcome}, {portal_url}
       v
  [ Fingerprint Hash Generator & Duplicate Guard ]
       - SHA-256(tenant_id + complaint_id + template_id + recipient)
       - Exists within 15 mins? ===> ABORT DISPATCH
       v
  [ Insert into communications_customermessage (status='QUEUED') ]
  [ Insert into common_outboxmessage (topic='communications.dispatch') ]
       v (PostgreSQL Transaction Commit)
       |
       +---> [ Celery Communication Worker ]
                   |
                   v
        [ Channel Adapter Engine ]
        - SMSAdapter (Twilio / Africa's Talking / Bank SMS Gateway)
        - EmailAdapter (SendGrid / AWS SES / Bank SMTP)
        - WhatsAppAdapter (Meta Cloud API / Infobip)
                   |
                   v
        [ Carrier Webhook Listener: Updates Delivery Status to 'DELIVERED' or 'FAILED' ]
```

---

## 2. Event Triggers & Communication Rules

| Event Trigger | Recipient Channel | Template ID | Timing | Mandatory Verification Gate |
| :--- | :--- | :--- | :--- | :--- |
| **Complaint Received (Intake)** | SMS / Email | `INTAKE_ACK` | Immediate (< 30s) | None (Automatic acknowledgment). |
| **Team Handoff Dispatched** | SMS / Email | `PROGRESS_FORWARDED` | Operator Option | Operator approval required. |
| **Underlying Incident Resolved** | System Internal | None | Immediate | **NO CUSTOMER NOTIFICATION.** Triggers complaint ledger check. |
| **Maker Reports Outcome** | System Internal | None | Immediate | **NO CUSTOMER NOTIFICATION.** Case is `AWAITING_VERIFICATION`. |
| **Checker Approves Outcome** | SMS & Email | `RESOLUTION_FINAL` | Immediate upon approval | **GATED:** Requires `verification == 'VERIFIED'` and `verified_by != reported_by`. |
| **Complaint Reopened** | SMS / Email | `REOPEN_ACK` | Immediate | Reopening reason must be recorded. |

---

## 3. Approved Message Templates

Templates support token substitution and multi-language bank localization.

### 3.1 Initial Complaint Acknowledgement (`INTAKE_ACK`)
- **Channel:** SMS
```text
Dear Customer, we have received your complaint regarding "{summary}". Your reference number is {reference}. Our resolution desk is investigating. Track status: {portal_link}
```
- **Channel:** Email
```text
Subject: Complaint Acknowledged — Reference {reference}

Dear Customer,

We have logged your complaint concerning:
Summary: {summary}
Reference Number: {reference}
Received: {received_at}

Our customer resolution team is actively investigating this matter with our transaction settlement desk. You will receive updates as progress is made.

ResolveAI Operations Desk
{tenant_name}
```

### 3.2 Individual Verified Resolution Notice (`RESOLUTION_FINAL`)
- **Channel:** SMS
```text
Dear Customer, your complaint {reference} has been resolved and verified: {outcome_summary}. Thank you for banking with {tenant_name}.
```
- **Channel:** Email
```text
Subject: Resolution Confirmation — Reference {reference}

Dear Customer,

We are pleased to inform you that your complaint regarding "{summary}" (Reference: {reference}) has been fully investigated, resolved, and verified by our compliance team.

Resolution Outcome:
{outcome}

Verification Reference:
Verified on: {verified_at}
Evidence Reference: {evidence_reference}

If you have any further questions or if your account does not reflect this outcome, please reply directly or visit any branch with reference {reference}.

Warm regards,
Customer Resolution Desk
{tenant_name}
```

---

## 4. Duplicate Message Prevention & Fingerprint Algorithm

To eliminate duplicate SMS/email sends caused by browser reloads, operator double-clicks, or Celery retry attempts:

```python
# apps/communications/services.py
import hashlib
from datetime import timedelta
from django.utils import timezone
from .models import CustomerMessage

class DuplicateMessageError(Exception):
    pass

def calculate_message_fingerprint(tenant_id: str, complaint_id: str, template_id: str, recipient: str) -> str:
    seed = f"{tenant_id}:{complaint_id}:{template_id}:{recipient.strip().lower()}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()

def guard_duplicate_dispatch(tenant_id: str, complaint_id: str, template_id: str, recipient: str, window_minutes: int = 15):
    fingerprint = calculate_message_fingerprint(tenant_id, complaint_id, template_id, recipient)
    recent_cutoff = timezone.now() - timedelta(minutes=window_minutes)
    
    if CustomerMessage.objects.filter(
        tenant_id=tenant_id,
        fingerprint=fingerprint,
        created_at__gte=recent_cutoff
    ).exists():
        raise DuplicateMessageError(f"Duplicate message suppressed for complaint {complaint_id} (Fingerprint: {fingerprint})")
    
    return fingerprint
```

---

## 5. Delivery Status Lifecycle & Retry Policy

### 5.1 Status Lifecycle
- **`QUEUED`**: Written to database inside transaction; awaiting Celery worker pickup.
- **`DISPATCHED`**: Sent to carrier/gateway API (e.g. Twilio / SendGrid); carrier message ID recorded.
- **`DELIVERED`**: Inbound carrier webhook confirmed delivery to customer's handset/inbox.
- **`FAILED`**: Gateway rejected message (e.g. invalid phone number, carrier network unreachable).

### 5.2 Retry & Exponential Backoff Policy
- **Transient Failures (HTTP 500, Rate-Limit 429, Network Timeout):**
  - Celery retries with exponential backoff:
    $$T_{\text{delay}} = \min(60 \cdot 2^{\text{attempt}}, 3600) \text{ seconds}$$
  - Maximum retry attempts: **5**.
- **Permanent Failures (Invalid phone number, blacklisted email):**
  - State marked `FAILED`.
  - Alert logged to the operator's complaint timeline (`Customer notification failed: Invalid contact number`).
  - No further automated retries.

---

## 6. Simulated Communication Adapter for Testing

For local development and hackathons without external SMS/Email gateway costs:

```python
# apps/communications/adapters/simulated.py
import logging
from .base import CommunicationAdapterBase

logger = logging.getLogger("communications.simulated")

class SimulatedCommunicationAdapter(CommunicationAdapterBase):
    def send_sms(self, recipient: str, body: str) -> dict:
        logger.info(f"[SIMULATED SMS DISPATCH] To: {recipient} | Body: {body}")
        return {"status": "DELIVERED", "external_id": f"sim-sms-{uuid.uuid4().hex[:8]}"}

    def send_email(self, recipient: str, subject: str, body: str) -> dict:
        logger.info(f"[SIMULATED EMAIL DISPATCH] To: {recipient} | Subject: {subject}")
        return {"status": "DELIVERED", "external_id": f"sim-email-{uuid.uuid4().hex[:8]}"}
```
