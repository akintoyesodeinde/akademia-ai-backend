# Akademia AI — Local Development Guide (`LOCAL_DEVELOPMENT.md`)

## 1. Prerequisites

- **Docker Desktop** with Docker Compose v2+
- **Python 3.13+** and **`uv`** (`pip install uv`) for local host execution
- **Node.js 20+** and **npm 10+** for `akademia-ai-frontend`

---

## 2. Service Port Allocation

To prevent collisions with common local services, `akademia-ai-backend/compose.yaml` binds the following host ports by default (all configurable via environment variables):

| Service | Container Name | Host Port | Container Port | Purpose |
|---|---|---|---|---|
| PostgreSQL 16 + `pgvector` | `akademia-postgres` | `5436` | `5432` | Primary relational + vector store with RLS |
| Redis 7.4 | `akademia-redis` | `6386` | `6379` | Rate limiting & ephemeral coordination |
| FastAPI Backend API | `akademia-api` | `8005` | `8000` | REST API (`/api/v1`) & OpenAPI docs (`/docs`) |
| Background Worker | `akademia-worker` | — | — | Async document chunking, embedding, & AI jobs |
| React/Vite Frontend | `akademia-ai-frontend` | `5175` | `5173` | Single-Page Application |

---

## 3. Step-by-Step Local Startup

### Step 1: Start PostgreSQL (`pgvector`) & Redis
From `akademia-ai-backend/`:
```bash
docker compose up -d postgres redis
```
On first startup, `scripts/init-db-roles.sql` automatically provisions:
- Databases: `akademia_ai` and `akademia_ai_test`
- Extensions: `pgcrypto` and `vector`
- Roles: `akademia_migrator`, `akademia_app` (`NOSUPERUSER NOBYPASSRLS`), `akademia_worker` (`NOSUPERUSER NOBYPASSRLS`), and `akademia_readonly`

### Step 2: Install Backend Dependencies & Run Migrations
```bash
cd akademia-ai-backend
uv sync --dev
uv run alembic upgrade head
```

### Step 3: Run Backend Linters, Type Checks & Test Suite
```bash
uv run ruff check .
uv run mypy app
uv run python scripts/export_openapi.py
uv run pytest -v
```

### Step 4: Start the Backend API & Worker
Either via Docker Compose:
```bash
docker compose up --build -d api worker
```
Or directly on the host for hot-reload debugging:
```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8005 --reload
```

### Step 5: Start the Frontend Application
```bash
cd ../akademia-ai-frontend
npm install
npm run generate:api
npm run typecheck
npm test
npm run dev -- --port 5175
```
