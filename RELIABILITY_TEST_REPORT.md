# ResolveAI (BIIRS) — Reliability & Recovery Test Report

## Executive Summary

This report documents the fault-tolerance, asynchronous resilience, and disaster recovery validation performed under **Task 6 (Reliability and Recovery)** for ResolveAI.

Testing verified that the asynchronous architecture—combining a transactional outbox, a Celery worker pool, a Celery Beat periodic scheduler, and a PostgreSQL persistence store—maintains ACID guarantees and state consistency across system interruptions, network partitions, and third-party delivery provider degradation.

---

## 1. Asynchronous Architecture & Verification Scope

```
+-----------------------------------------------------------------------------------+
|                        PostgreSQL 17 Transaction Boundary                         |
|  [ Business Entity Update ]  +  [ common_outboxmessage (Status: PENDING) ]        |
+-----------------------------------------------------------------------------------+
                                          | Atomic Commit (No Message Loss)
                                          v
+-----------------------------------------------------------------------------------+
|                     Message Broker (Redis 6379 / fakeredis)                       |
|  - Queues: celery, handoffs, communications, incidents                            |
|  - Exponential Backoff & Retry Dead-Letter Tracking                               |
+-----------------------------------------------------------------------------------+
                                          | Pull & Acknowledge
                                          v
+-----------------------------------------------------------------------------------+
|                 Celery Worker Pool (Solo / Prefork Processors)                    |
|  - Outbox Poller / Dispatcher Task                                                |
|  - Canonical Lock Hierarchy: Complaint -> CustomerCommunication                   |
|  - Delivery Provider Adapters (Simulated / Live)                                  |
+-----------------------------------------------------------------------------------+
```

---

## 2. Controlled Failure Scenarios & Empirical Outcomes

| Failure Scenario | Injected Condition | Expected System Behavior | Empirical Test Result | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Outbox Durability Across Commits** | Application enqueues escalation event within DB transaction | Message persists durably in PostgreSQL even if broker is offline | `OutboxMessage` `17887cb4` persisted with status `PENDING` in `common_outboxmessage`. | **PASSED** |
| **Worker Interruption During Handoff** | Worker terminated while dispatching forward to external team | Handoff state remains `DELIVERY_UNCONFIRMED` or `PENDING`; task re-queued on restart | Task redelivered upon worker restart; handoff completed without duplicate message generation. | **PASSED** |
| **Broker Unavailability** | Simulated broker connection timeout | Application writes outbox records locally; buffers without dropping requests | HTTP requests succeeded; outbox records queued in DB until broker reconnection. | **PASSED** |
| **Duplicate External Ingest Events** | Same external event ID submitted multiple times | Idempotency engine prevents duplicate complaint creation | `SourceEvent` table matched unique hash; returned cached reference without duplication. | **PASSED** |
| **Delayed Provider Acknowledgement** | Simulated SMS provider delays callback by 10 seconds | Communication enters `SENDING`; does not lock worker thread | Worker processed next queue message; callback updated state to `DELIVERED` asynchronously. | **PASSED** |
| **Uncertain Delivery Outcomes** | Provider returns HTTP 504 Gateway Timeout | Message state marked `DELIVERY_UNCONFIRMED`; avoids blind retry | State set to `DELIVERY_UNCONFIRMED`; manual verification and status query scheduled. | **PASSED** |
| **Retry Exhaustion** | 3 consecutive HTTP 503 Provider Unavailable errors | Exponential backoff retry increments; caps at `max_retries=3` | Final status marked `FAILED`; `is_terminal_failure=True`; escalation logged to audit trail. | **PASSED** |
| **Stale Data Source Handling** | Data feed timestamp older than threshold | Dashboard and reports flag source as `STALE` or `UNAVAILABLE` | Reports display freshness badge: `STALE` (Core Banking Ledger last updated >24h). | **PASSED** |
| **AI Provider Outage / Missing Weights** | `sentence_transformers` PyTorch model unavailable | Coordinator activates 384-d deterministic feature hashing | Seamless zero-downtime fallback to 384-d hashing; cosine search remained functional. | **PASSED** |
| **Concurrent Reopening Race Condition** | Operator reopens case while resolution SMS is queued | Pending resolution notice cancelled before provider submission | Pending SMS cancelled with reason `Customer called stating ATM issue was not resolved`. | **PASSED** |

---

## 3. Deep-Dive Reliability Findings

### 1. Canonical Lock Hierarchy & Concurrency Protection
In Stage 6, concurrent execution of case reopening and resolution communication dispatch risked database deadlocks or race conditions where a customer could receive a resolution notification for a case that had just been reopened.
- **Resolution Implemented in Stage 7**:
  Enforced a canonical lock hierarchy in `apps/complaints/services.py` and `apps/communications/services/communication_service.py`:
  1. `Complaint` is ALWAYS locked first via `select_for_update()`.
  2. `CustomerCommunication` records are locked second.
  3. Pre-submission cancellation immediately transitions `PENDING` and `QUEUED` communications to `CANCELLED` with explicit audit reasons.
- **Empirical Validation**:
  Audit test `concurrency_reopen_cancel` confirmed that when complaint `CMP-AUDIT-438707` was reopened, 2 pending resolution communications were suppressed with reason: `"Customer called stating ATM issue was not resolved"`.

### 2. Transactional Outbox Durability
- **Test**: Simulated crash between database commit and broker publication.
- **Outcome**: Because state transitions and outbox records reside in the same atomic database transaction, the outbox record is guaranteed to exist on disk in PostgreSQL (`common_outboxmessage`). When the outbox poller executes, it processes pending records in FIFO order.

### 3. Retry Exhaustion & Dead-Letter Safety
- **Test**: Dispatch of SMS communication with simulated provider outage.
- **Outcome**: The message retry counter incremented sequentially:
  - Attempt 1: HTTP 503 $\rightarrow$ `retry_count=1`
  - Attempt 2: HTTP 503 $\rightarrow$ `retry_count=2`
  - Attempt 3: HTTP 503 $\rightarrow$ `retry_count=3` $\rightarrow$ Transition to `FAILED`.
- Consequential financial operations cannot be duplicated because message generation is tied to an immutable `outbox_message_id`.

---

## 4. Development Broker vs. Production Managed Redis

> [!CAUTION]
> **DEVELOPMENT BROKER LIMITATION NOTICE**:  
> For local Windows development and hackathon testing, ResolveAI utilizes a simulated TCP Redis-compatible broker (`manage.py run_redis_broker` via `fakeredis`).
> 
> **Production Gaps**:
> 1. `fakeredis` stores broker state in memory within a single Python process. If the broker process is terminated abruptly (SIGKILL), in-flight Celery queue tasks that have not been acknowledged to PostgreSQL are lost from memory (though preserved in PostgreSQL outbox).
> 2. For production staging and multi-instance deployment, a managed Redis instance (such as AWS ElastiCache, Upstash, or Redis Cloud) with Append-Only File (AOF) persistence and Multi-AZ replication is required.
> 3. Production fault tolerance claims must be based on testing against an external managed Redis cluster, not development-only `fakeredis`.

---

## 5. Conclusion

The ResolveAI asynchronous architecture successfully ensures message durability, idempotency under retry, and concurrency safety. All 10 injected failure modes were handled predictably with zero database corruption and zero duplicate customer notices.
