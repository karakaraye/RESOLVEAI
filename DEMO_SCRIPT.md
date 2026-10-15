# ResolveAI (BIIRS) — Live Hackathon Demonstration Script

## Presentation Overview

**Time Allotment**: 5–7 Minutes  
**Presenters**: Full-Stack Developer & Technical Lead  
**Narrative Arc**:  
Customer complains $\rightarrow$ ResolveAI acknowledges $\rightarrow$ AI detects wider incident cluster $\rightarrow$ Evidence is investigated $\rightarrow$ Operations team receives the case $\rightarrow$ SLA is monitored $\rightarrow$ Resolution is proposed $\rightarrow$ Independent verifier approves $\rightarrow$ Customer receives verified notice $\rightarrow$ Management views real-time operational reports.

---

## Act 1: Intake & Automated Customer Acknowledgement (1 Minute)

### Action:
1. Open the ResolveAI Operator Dashboard at `http://localhost:3000/complaints`.
2. Select Persona **"Operator"** in the top navigation switcher.
3. Show incoming complaint `CMP-2026-0001` from **Adaeze Okonkwo**:
   - *Summary*: "Dispenser timeout at ATM terminal 04. Account debited 50,000 NGN without cash dispense."
   - *Category*: `CARDS_ATM` | *Priority*: `HIGH` | *Channel*: `Mobile Banking App`
4. Click into the complaint to view the **Audit Timeline**.

### Speaker Notes:
> *"In a standard retail bank, a customer complaining about a failed ATM withdrawal waits days for manual logging. With ResolveAI, within milliseconds of ingestion, the transactional outbox enqueues an approved regulatory acknowledgement. Look at the audit stream: an SMS was immediately queued and delivered to the customer with an immutable audit hash. No manual operator effort required."*

---

## Act 2: AI Incident Intelligence & Semantic Correlation (1.5 Minutes)

### Action:
1. Scroll to the **AI Intelligence & Semantic Analysis** panel in Complaint Detail.
2. Highlight:
   - **Grounded Root-Cause Assessment**: *Possible switch timeout on terminal hardware.*
   - **Related Complaint Cluster**: Shows 4 similar complaints at Victoria Island Branch Terminal 04 within the last 3 hours.
   - **Incident Association**: Correlated to Active Banking Incident `INC-ATM-TIMEOUT`.
   - **Engine Mode Indicator**: *Deterministic Offline AI Fallback* (384-dimensional vector similarity).

### Speaker Notes:
> *"Here is where ResolveAI transforms customer care into proactive incident management. Notice the engine attribution: we are demonstrating our deterministic offline AI fallback. It operates with zero external cloud dependencies and executes in 0.022 milliseconds. In benchmark testing on our synthetic dataset, it achieved 80% classification accuracy and 100% evidence grounding because facts are extracted directly from structured switch journals, eliminating speculative hallucination.*
>
> *For similar-complaint retrieval, our offline token-hashing baseline achieves a 38.89% Precision@3—a solid lexical baseline that proves why our production design incorporates trained neural embeddings (Sentence Transformers all-MiniLM-L6-v2) for deeper semantic synonym matching. Most critically: AI findings here are strictly advisory. No AI can autonomously disburse refunds or alter customer ledger balances without human verification."*

---

## Act 3: Evidence Investigation & Operational Handoff (1.5 Minutes)

### Action:
1. Scroll to **Transaction Evidence & Audit Logs**.
   - Show the simulated Switch Ledger evidence record: `TXN-REF-894021` (`50,000 NGN`, status: `FAILED_DISPENSE`).
   - Highlight the **SHA-256 Payload Integrity Hash**.
2. Click **"Forward to Operations"** action button.
   - Select Receiving Team: **"ATM Operations & Field Engineering"**.
   - Note: *"Priority hardware investigation for Terminal 04 dispenser jam."*
   - Submit handoff.
3. Show the handoff status transition to **`DELIVERED`** with external tracking reference.

### Speaker Notes:
> *"ResolveAI retrieves evidence directly from authoritative banking core journals. Notice the SHA-256 cryptographic hash guaranteeing tamper-proof audit trails. The operator forwards the case to ATM Engineering with one click. The operational SLA timer starts immediately, and Celery Beat monitors the response window."*

---

## Act 4: Maker-Checker Resolution & Customer Protection Barrier (1.5 Minutes)

### Action:
1. In Complaint Detail, click **"Record Outcome"**:
   - Outcome: *"Upheld in Full — 50,000 NGN reversed to customer account. Hardware log confirms cassette jam."*
   - Evidence: *"Core banking journal entry JRNL-84920 confirmed reversal."*
   - Submit outcome.
2. Note that the Complaint status is now **`AWAITING_VERIFICATION`**.
3. **Crucial Demonstration Point**:
   - Scroll to Customer Communications: **No customer resolution message is sent!**
   - Attempt to verify as the Operator: System rejects self-approval with **`403 Segregation of Duties Violation`**.
4. Switch Persona in header to **"Supervisor / Verifier"**.
5. Click **"Verify Outcome"**:
   - Decision: **`VERIFY`**
   - Note: *"Confirmed against settlement journal. Approved for customer notification."*
   - Submit verification.
6. The complaint status becomes **`RESOLVED`**, and the approved customer resolution message is released and delivered!

### Speaker Notes:
> *"Here is ResolveAI's strict financial governance: Maker-Checker segregation of duties. An operator who records an outcome CANNOT self-verify. Most importantly, customer resolution messaging is hard-blocked at the database level until an independent supervisor approves. Once the supervisor approves, ResolveAI automatically renders the approved regulatory template, scrubs any sensitive credentials, and delivers the resolution notice."*

---

## Act 5: Real-Time Operational Intelligence & Management Reports (1 Minute)

### Action:
1. Navigate to **Reports** in the main navigation (`/reports`).
2. Demonstrate the 7 real-time report tabs:
   - **Overview**: Resolution rates, total volumes, active breaches.
   - **Resolution Performance**: Distinguishes *Reported Outcomes* from *Independently Verified Resolutions*.
   - **Incident Trends**: Visualizes the spike in CARDS_ATM disputes linked to `INC-ATM-TIMEOUT`.
   - **Data Source Freshness**: Shows Core Banking feed freshness (Current vs Stale).

### Speaker Notes:
> *"Finally, management receives 100% ground-truth operational intelligence. In the resolution performance report, ResolveAI explicitly separates reported outcomes from independently verified resolutions. Denominators are exact, data freshness is transparent, and every metric is backed by PostgreSQL row-level audit trails. That is ResolveAI: from complaint intake to executive oversight, completely auditable, secure, and intelligent."*
