# Akademia AI — Local Docker Compose Startup & Verification Report

## 1. Local Docker Compose Architecture (`compose.yaml`)

File: `c:\Users\LENOVO\AkademiaAI\akademia-ai-backend\compose.yaml`

| Container Name | Service | Image | Database Role / Identity | Host -> Container Port | Status |
|---|---|---|---|---|---|
| `akademia-postgres` | `postgres` | `pgvector/pgvector:pg16` | `postgres` (provisions `akademia_migrator`, `akademia_app`, `akademia_worker`, `akademia_readonly`) | `5436 -> 5432` | `Up (healthy)` |
| `akademia-redis` | `redis` | `redis:7.4-alpine` | N/A | `6386 -> 6379` | `Up (healthy)` |
| `akademia-migrator` | `migrator` | `akademia-ai-backend:local` | `akademia_migrator` (`CREATEDB BYPASSRLS` — migration role only) | Internal | `Exited (0)` (`alembic upgrade head`) |
| `akademia-api` | `api` | `akademia-ai-backend:local` | `akademia_app` (`NOSUPERUSER NOBYPASSRLS`), Linux UID `10001` (`akademia`) | `8000 -> 8000`, `8005 -> 8000` | `Up (healthy)` |
| `akademia-worker` | `worker` | `akademia-ai-backend:local` | `akademia_worker` (`NOSUPERUSER NOBYPASSRLS`), Linux UID `10001` (`akademia`) | Internal | `Up (healthy)` |
| `akademia-frontend` | `frontend` | `akademia-ai-frontend:local` | Nginx runtime + `/api/` reverse proxy to `http://api:8000` | `5175 -> 80` (port `3000` occupied on host by `ajohq-web`) | `Up (healthy)` |

## 2. Built Local Image Digests

- **Backend (`akademia-ai-backend:local`)**:
  - Manifest List Digest: `sha256:e3dfc9f8ea5cd1393276b178a75ed5d1137c3a5d32d7887bea72e048d4b7a8d4`
  - Image Config Digest: `sha256:81720a9fbdd4521bf68bc49bf014604810ef6b35fe78b699b51ac915eaaa6e9a`
- **Frontend (`akademia-ai-frontend:local`)**:
  - Manifest List Digest: `sha256:f2c22e72cc2941d08f7f76dbae65ee4b1617a7ab009a86511de5fcf853e20642`
  - Image Config Digest: `sha256:564d864744d7be7ab5a70e48842114243184936ef734676c553090ea7a9142e9`

## 3. Local Startup Commands

```powershell
cd C:\Users\LENOVO\AkademiaAI\akademia-ai-backend
docker compose up --build -d
docker compose ps
docker compose logs --tail=100
```

## 4. Verified Local URLs & Live End-to-End Integration Checks

- **Frontend Application**: `http://localhost:5175` -> `200 OK`
- **Frontend SPA Deep Route (`/learner/dashboard`)**: `http://localhost:5175/learner/dashboard` -> `200 OK`
- **Frontend Health Check**: `http://localhost:5175/healthz` -> `200 OK` (`{"status":"healthy","service":"akademia-ai-frontend"}`)
- **Frontend-to-Backend Reverse Proxy Health Check**: `http://localhost:5175/api/v1/platform/health` -> `200 OK`
- **Backend API Direct Health Check**: `http://localhost:8000/api/v1/platform/health` -> `200 OK` (`{"status":"healthy","service":"akademia-ai-backend","database":"connected",...}`)
- **OpenAPI Interactive Documentation**: `http://localhost:8000/api/v1/docs` (and `http://localhost:8000/docs` redirect) -> `200 OK`
- **OpenAPI Specification**: `http://localhost:8000/api/v1/openapi.json` -> `61` paths verified

### Verified Live Multi-Tenant Workflow Through Frontend Reverse Proxy (`http://127.0.0.1:5175/api/v1`)

1. **User Registration & Authentication (`POST /api/v1/auth/register` -> `POST /api/v1/auth/login`)**:
   - Issued signed JWT access token (`2_LOGIN_ACCESS_TOKEN_LEN=304`).
2. **Tenant Provisioning (`POST /api/v1/tenants`)**:
   - Created tenant `1bde05cb-32bc-4bb2-896c-cc1e1bd287a8` (`SLUG=horizon-sandbox-1794153126`).
3. **RLS-Scoped Tenant Context Verification (`GET /api/v1/tenants/current`)**:
   - Returned `4_CURRENT_TENANT_VERIFIED=1bde05cb-32bc-4bb2-896c-cc1e1bd287a8 STATUS=active`.
4. **Course Creation Under Tenant RLS (`POST /api/v1/courses`)**:
   - Created course `1e7ec52a-2a09-4c19-9b6f-8f1b3b7c0659` (`CODE=CS-1794153126`).
