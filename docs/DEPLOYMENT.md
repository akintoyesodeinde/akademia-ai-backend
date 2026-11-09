# Akademia AI — Staging & Production Deployment Guide (`DEPLOYMENT.md`)

## 1. Deployment Topology

Akademia AI is designed so that local Docker Compose, staging, and production share the exact same container topology without architectural redesign:

1. **`akademia-ai-backend` Container Image (`Dockerfile`)**:
   - Built on `python:3.13-slim` running as non-root user `akademia` (`UID 10001`).
   - Deployed as two workload types from the same immutable image:
     - **API Deployment**: Runs `uvicorn app.main:app --host 0.0.0.0 --port 8000` behind a TLS-terminating reverse proxy / ingress.
     - **Worker Deployment**: Runs `python -m app.workers.runner` to process document ingestion and AI generation jobs.
2. **`akademia-ai-frontend` Container Image (`Dockerfile`)**:
   - Multi-stage build compiling the static TypeScript/Vite bundle (`npm run build`) and serving it with SPA route fallback.
3. **Managed PostgreSQL 16+ (`pgvector` + RLS)**:
   - Provisioned with the four least-privilege roles defined in `scripts/init-db-roles.sql`.
   - `MIGRATION_DATABASE_URL` (`akademia_migrator`) is injected **only** into the pre-deploy migration job (`alembic upgrade head`).
   - `DATABASE_URL` (`akademia_app`) is injected into the API service (`NOSUPERUSER NOBYPASSRLS`).
   - `WORKER_DATABASE_URL` (`akademia_worker`) is injected into the worker service (`NOSUPERUSER NOBYPASSRLS`).

---

## 2. Production Environment Variables Checklist

| Variable | Required in Prod | Description |
|---|---|---|
| `APP_ENV` | Yes (`production`) | Disables debug stack traces and enforces strict security settings |
| `DATABASE_URL` | Yes | Async PostgreSQL URL using `akademia_app` role |
| `MIGRATION_DATABASE_URL` | Migration job only | PostgreSQL URL using `akademia_migrator` role |
| `WORKER_DATABASE_URL` | Worker service | Async PostgreSQL URL using `akademia_worker` role |
| `JWT_SECRET_KEY` | Yes | Cryptographically random secret (`>= 32` bytes) from secret manager |
| `COOKIE_SECURE` | Yes (`true`) | Enforces HTTPS-only transmission of session cookies |
| `CORS_ORIGINS` | Yes | Explicit JSON list of authorized frontend origins |
| `AI_PROVIDER` | Yes | `openai_compatible` (or `deterministic` for air-gapped testing) |
| `AI_API_KEY` | Yes (when external) | Provider API key injected from secret manager |

---

## 3. Release & Rollback Procedure

1. **CI Verification**: Both `akademia-ai-backend/.github/workflows/ci.yml` and `akademia-ai-frontend/.github/workflows/ci.yml` must pass Ruff, mypy, Alembic migration verification, RLS isolation tests, AI quality gates, Vitest, and production builds.
2. **Database Migration**: Run `alembic upgrade head` using `MIGRATION_DATABASE_URL`. All 12 migrations are additive and preserve RLS policies.
3. **Rolling Update**: Roll out new `api` and `worker` containers; verify `/health/live` and `/health/ready` return HTTP `200`.
