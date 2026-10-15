# ResolveAI (BIIRS) — Staging & Production Deployment Guide

## 1. Executive Deployment Architecture

ResolveAI (Banking Incident & Inquiry Resolution System) is architected as a secure, multi-tenant, asynchronous distributed financial operations platform.

```
+-----------------------------------------------------------------------------------+
|                                 Public Internet                                   |
+-----------------------------------------------------------------------------------+
                                          | HTTPS (TLS 1.3)
                                          v
+-----------------------------------------------------------------------------------+
|                        Next.js Frontend (Vercel / Node.js)                        |
|  - Edge-cached static assets                                                      |
|  - Strict CORS / CSP Headers                                                      |
|  - Operator Persona Context & Role-based Navigation Drawer                        |
+-----------------------------------------------------------------------------------+
                                          | Reverse Proxy / Internal HTTPS
                                          v
+-----------------------------------------------------------------------------------+
|                        Django REST Framework Application                          |
|  - Gunicorn / Uvicorn ASGI Application Cluster                                    |
|  - X-BIIRS-Request CSRF Header Enforcement                                        |
|  - Multi-Tenant Row-Level Security Middleware                                     |
|  - Maker-Checker Segregation Enforcement                                          |
+-----------------------------------------------------------------------------------+
        |                                   |                              |
        v                                   v                              v
+-----------------------+       +-----------------------+      +-----------------------+
|  Supabase PostgreSQL  |       |   Managed Redis 7.x   |      | Asynchronous Cluster  |
|  - PostgreSQL 17.11   |       |  - Broker & Results   |      |  - Dedicated Celery   |
|  - pgvector 0.8.0     |       |  - Idempotency Locks  |      |    Solo/Prefork Worker|
|  - Append-only Audit  |       |  - Backpressure Queue |      |  - Celery Beat        |
|  - Transaction Outbox |       |                       |      |    Periodic Scheduler |
+-----------------------+       +-----------------------+      +-----------------------+
```

---

## 2. Infrastructure Prerequisites

| Component | Minimum Staging Spec | Recommended Production Spec | Purpose |
| :--- | :--- | :--- | :--- |
| **Frontend** | 1 vCPU, 1 GB RAM (Vercel Pro / Node 20 LTS) | 2+ Instances, Auto-scaling | Next.js 16 SSR & App Router |
| **Backend API** | 2 vCPU, 2 GB RAM (AWS ECS / Render) | 4 vCPU, 8 GB RAM, 3 Replicas | Django REST Framework API |
| **PostgreSQL** | Supabase Pro (Postgres 17.x, 2 vCPU, 4GB RAM) | Dedicated Supabase / AWS RDS Postgres 17 with `pgvector` | Multi-tenant core DB & vector store |
| **Redis Broker** | Managed Redis (Upstash / Redis Cloud 1GB) | AWS ElastiCache Redis 7.x Cluster with Multi-AZ | Celery Task Broker & Task Results |
| **Celery Worker** | 1 vCPU, 2 GB RAM (Dedicated worker instance) | 2+ Dedicated Worker Nodes (`celery -A config worker`) | Outbox dispatch & simulated providers |
| **Celery Beat** | 0.5 vCPU, 512 MB RAM (Single instance) | Dedicated Beat Daemon with failover leader | SLA heartbeat & scheduled escalations |

---

## 3. Environment Variables & Secret Configuration

Create `.env` in the backend root directory (do not commit to Git):

```bash
# ==============================================================================
# RESOLVEAI PRODUCTION & STAGING ENVIRONMENT CONFIGURATION
# ==============================================================================

# Core Django Settings
DEBUG=False
SECRET_KEY="<GENERATE_CRYPTOGRAPHICALLY_SECURE_50_CHAR_STRING>"
ALLOWED_HOSTS="app.resolveai.bank.ng,api.resolveai.bank.ng,localhost,127.0.0.1"

# Database Configuration (Supabase PostgreSQL with pgvector)
DATABASE_URL="postgres://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres?sslmode=require"
DB_CONN_MAX_AGE=600

# Redis & Broker Configuration (Managed Redis)
REDIS_URL="rediss://default:[REDIS_PASSWORD]@[HOST].upstash.io:6379"
CELERY_BROKER_URL="rediss://default:[REDIS_PASSWORD]@[HOST].upstash.io:6379/0"
CELERY_RESULT_BACKEND="rediss://default:[REDIS_PASSWORD]@[HOST].upstash.io:6379/1"

# Security & Cookie Directives
CSRF_TRUSTED_ORIGINS="https://app.resolveai.bank.ng,https://api.resolveai.bank.ng"
CORS_ALLOWED_ORIGINS="https://app.resolveai.bank.ng"
SESSION_COOKIE_SECURE=True
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SAMESITE="Lax"
CSRF_COOKIE_SECURE=True
CSRF_COOKIE_HTTPONLY=False
X_BIIRS_ENFORCE_HEADER=True

# AI Pipeline Engine Configuration
AI_EMBEDDING_PROVIDER="SENTENCE_TRANSFORMER"  # Options: SENTENCE_TRANSFORMER, FEATURE_HASHING
AI_SENTENCE_MODEL_NAME="all-MiniLM-L6-v2"
AI_CLASSIFIER_MODE="HYBRID"                   # Options: DETERMINISTIC, HYBRID

# External Delivery Adapters (Simulated for Hackathon/Staging)
COMMUNICATION_DELIVERY_ADAPTER="SIMULATED"    # Options: SIMULATED, INFOBIP, TWILIO
SIMULATED_PROVIDER_LATENCY_MS=250
SIMULATED_PROVIDER_FAILURE_RATE=0.00
```

Frontend Environment Configuration (`.env.production`):

```bash
NEXT_PUBLIC_API_URL="https://api.resolveai.bank.ng"
NEXT_PUBLIC_APP_ENV="staging"
NEXT_PUBLIC_ENABLE_ANALYTICS=true
```

---

## 4. Staging Step-by-Step Deployment Procedure

### Step 1: Database Migration & Extensions (Supabase PostgreSQL)
1. In Supabase SQL Editor, verify that the vector extension is enabled:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
2. Run database migrations:
   ```bash
   python manage.py migrate --noinput
   ```
3. Verify all 10 apps are migrated cleanly:
   - `tenants`, `accounts`, `complaints`, `transactions`, `incidents`, `intelligence`, `handoffs`, `communications`, `reports`, `common`.

### Step 2: Seed Initial Synthetic Staging Data
1. Seed the default demonstration tenant and sample operational teams:
   ```bash
   python manage.py seed_stage6_demo
   ```
2. Verify seeded records:
   - Tenant: `Apex Commercial Bank (apex-bank)`
   - Categories: `CARDS_ATM`, `TRANSFERS`, `FRAUD_SECURITY`, `BILL_PAYMENTS`, `ACCOUNT_SERVICES`
   - Receiving Teams: Core Banking, Switch Operations, Fraud Investigations, Card Services

### Step 3: Launch Asynchronous Worker & Beat Services
1. Start the Celery Worker:
   ```bash
   celery -A config worker --loglevel=info --concurrency=4 -n worker1@%h
   ```
2. Start the Celery Beat Scheduler:
   ```bash
   celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
   ```

### Step 4: Launch Backend API Cluster
1. Run with Gunicorn WSGI:
   ```bash
   gunicorn config.wsgi:application \
       --bind 0.0.0.0:8000 \
       --workers 4 \
       --threads 2 \
       --timeout 60 \
       --access-logfile - \
       --error-logfile -
   ```

### Step 5: Build & Deploy Frontend (Next.js)
1. Test production build locally:
   ```bash
   npm run build
   ```
2. Start production Next.js server:
   ```bash
   npm run start
   ```

---

## 5. Reliability, Backup & Disaster Recovery

1. **Transactional Outbox Guarantee**:
   All inter-service messages, provider dispatches, and handoffs are staged in `common_outboxmessage` in the same database transaction as the business entity update. Worker crashes cannot cause message loss.
2. **Automated Database Backups**:
   Supabase PostgreSQL executes continuous Write-Ahead Log (WAL) archiving with point-in-time recovery (PITR) up to 7 days on Pro tiers.
3. **Queue Health Check Endpoint**:
   - `GET /api/v1/health/` returns database connectivity, outbox backlog, and data-source freshness status.

---

## 6. Pre-Production Sign-off & Human Approval Gate

> [!IMPORTANT]
> **MANDATORY APPROVAL GATE**:
> Under no circumstances should automated continuous deployment pipelines push migrations to production without written sign-off from the Technical Lead.
> Real bank customer PII and live external SMS/Email gateways MUST remain disconnected in staging and hackathon readiness modes.
