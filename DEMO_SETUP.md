# ResolveAI (BIIRS) — Hackathon Demonstration Setup Guide

## Overview

This guide provides step-by-step instructions for initializing, verifying, and resetting the ResolveAI (Banking Incident & Inquiry Resolution System) environment for a live hackathon demonstration or technical presentation.

---

## 1. Environment Topology & Prerequisites

ResolveAI operates as a paired Next.js frontend and Django REST Framework backend with Supabase PostgreSQL (pgvector) and an asynchronous background task broker:

```
[ Next.js UI: Port 3000 ] <---> [ Django API: Port 8000 ] <---> [ Supabase PostgreSQL 17 + pgvector ]
                                        ^
                                        v
                            [ Redis Broker: Port 6379 ]
                                        ^
                                        v
                            [ Celery Solo Worker & Beat ]
```

### Prerequisites
- Node.js 18.x or 20.x LTS & npm
- Python 3.12+ with virtual environment
- Supabase PostgreSQL with `vector` extension enabled
- Redis-compatible message broker (or built-in `run_redis_broker`)

---

## 2. Quick-Start Demonstration Launch (Under 2 Minutes)

Open three terminal windows to launch the system daemons:

### Terminal 1: Backend API & Celery Broker
```bash
cd backend
python manage.py run_redis_broker
```

### Terminal 2: Celery Background Worker & Django Server
```bash
cd backend
# Start background worker
python -m celery -A config worker -l info -P solo

# In parallel or secondary window:
python manage.py runserver 8000
```

### Terminal 3: Next.js Frontend Operator UI
```bash
# In workspace root
npm run dev
```

Visit `http://localhost:3000` in your browser.

---

## 3. Seed Synthetic Demonstration Dataset

To populate realistic synthetic banking data without manual form entry, execute the automated seeding command:

```bash
cd backend
python manage.py run_stage7_e2e_journey
```

This seeds:
- **Demonstration Bank**: Apex Commercial Bank PLC (code: `apex-bank`)
- **Operator Personas**:
  - `operator`: Case Manager / Intake Operator
  - `supervisor`: Supervisor / Maker-Checker Verifier
  - `auditor`: Compliance Auditor / Quality Assurance
- **Synthetic Customer**: Adaeze Okonkwo (`CUST-NGN-084920`)
- **Synthetic Complaint**: ATM Dispense Failure at Victoria Island Terminal 04 (`CMP-2026-0001`)
- **Simulated Evidence**: Core Banking Journal Switch Log with SHA-256 payload integrity
- **Simulated Incident**: `INC-ATM-TIMEOUT` (Hardware Dispenser Micro-switch Stoppage)

---

## 4. Resetting Demonstration State

If you need to reset the demonstration state to a clean slate before presenting:

```bash
cd backend
python manage.py shell -c "
from apps.complaints.models import Complaint, Customer
from apps.handoffs.models import ForwardingHandoff
from apps.communications.models import CustomerCommunication
from apps.common.models import OutboxMessage, AuditEvent

print('Purging demo complaints and outbox...')
Complaint.objects.filter(reference__startswith='CMP-DEMO').delete()
OutboxMessage.objects.filter(topic__startswith='complaints').delete()
print('Reset complete.')
"
```

---

## 5. Offline & Fallback Procedures

ResolveAI is designed with **zero hard external runtime dependencies** for demonstration safety:

| System Component | Primary Service | Offline Fallback Mechanism |
| :--- | :--- | :--- |
| **Embeddings** | SentenceTransformers (`all-MiniLM-L6-v2`) | Deterministic 384-dimensional token feature-hashing (`apps.intelligence.services.embeddings`) |
| **Broker** | Production Redis 7.x Cluster | Local TCP Redis-compatible broker (`manage.py run_redis_broker`) |
| **SMS Gateway** | Live SMS Provider | `SimulatedDeliveryProvider` with realistic latency and masked phone logging |
| **Email Gateway**| Live SMTP / SendGrid | `SimulatedDeliveryProvider` with inbox audit record generation |
| **Banking Core** | ISO 8583 Live Switch | Simulated Core Banking Ledger Adapter with cryptographic SHA-256 evidence hashing |

If internet connectivity drops during the hackathon, the system continues running 100% locally with zero downtime.
