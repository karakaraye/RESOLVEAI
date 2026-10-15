# RESOLVEIQ — Banking Incident & Inquiry Resolution Desk

RESOLVEIQ (BIIRS) is an intelligent, multi-tenant incident resolution and complaint intake platform designed for banking and financial operations.

---

## Architecture Overview

```
[ Next.js 16 Web Desk (Port 3000) ]
               │
               ▼ (Proxy /api/v1/*)
[ Django REST Framework Core API (Port 8000) ]
               │
               ▼
[ Supabase PostgreSQL 17 + pgvector ]
```

- **Frontend**: Next.js 16 (App Router, Turbopack, IBM Plex typography, Vanilla CSS design system).
- **Backend**: Django REST Framework, Gunicorn, WhiteNoise, Celery event outbox.
- **Database & AI Vector Store**: Supabase PostgreSQL 17 with `pgvector` for semantic clustering and incident embeddings.

---

## Live Deployment Setup

### 1. Backend API (Render / Railway)
- **Repository Root**: `backend`
- **Build Command**: `./build.sh` (or `pip install -r requirements.txt && python manage.py collectstatic --no-input && python manage.py migrate`)
- **Start Command**: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`
- **Environment Variables**:
  - `DATABASE_URL`: Supabase PostgreSQL connection string
  - `DJANGO_SECRET_KEY`: Random 50+ character string
  - `DJANGO_DEBUG`: `True` *(enables rapid evaluator/demo persona sign-in)*
  - `ALLOW_DEV_AUTH`: `True`
  - `CELERY_TASK_ALWAYS_EAGER`: `True`
  - `DJANGO_ALLOWED_HOSTS`: `*`
  - `CSRF_TRUSTED_ORIGINS`: `https://your-frontend.vercel.app`
  - `CORS_ALLOWED_ORIGINS`: `https://your-frontend.vercel.app`

### 2. Frontend UI (Vercel)
- **Framework**: Next.js
- **Root Directory**: `./`
- **Environment Variable**:
  - `DJANGO_API_URL`: URL of the deployed backend (e.g. `https://resolveai-backend.onrender.com`)

---

## Local Development Setup

### Prerequisites
- Node.js 20+ & npm / pnpm
- Python 3.12+

### 1. Start the Backend API
```bash
cd backend
pip install -r requirements.txt
python django_manage.py migrate
python django_manage.py run_stage7_e2e_journey  # Seeds synthetic bank & demo complaints
python django_manage.py runserver 8000
```

### 2. Start the Frontend Desk
```bash
# In project root
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.
Click **Sign in** (or open [http://localhost:3000/api/v1/session/sign-in](http://localhost:3000/api/v1/session/sign-in)) to authenticate as the demo operator persona.
