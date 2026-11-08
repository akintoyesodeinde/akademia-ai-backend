# Akademia AI — GitHub Repository Integration & Publishing Report

## 1. Independent Repository Architecture

Akademia AI strictly maintains two separate Git repositories (never a monorepo):

| Repository | Local Directory | GitHub Remote (`origin`) | Default Branch | Feature Branch |
|---|---|---|---|---|
| **Backend** | `c:\Users\LENOVO\AkademiaAI\akademia-ai-backend` | `https://github.com/akintoyesodeinde/akademia-ai-backend.git` | `main` | `feat/docker-aws-cicd-deployment` |
| **Frontend** | `c:\Users\LENOVO\AkademiaAI\akademia-ai-frontend` | `https://github.com/akintoyesodeinde/akademia-ai-frontend.git` | `main` | `feat/docker-aws-cicd-deployment` |

## 2. Secret & Credential Hygiene Verification

Before staging or committing any files in either repository:
- `.gitignore` in `akademia-ai-backend` excludes `.env`, `.env.local`, `.venv/`, `venv/`, `storage_data/`, `storage_data_test/`, `*.db`, `*.sqlite3`, and cache directories.
- `.gitignore` in `akademia-ai-frontend` excludes `node_modules/`, `dist/`, `.env`, `.env.local`, `playwright-report/`, `test-results/`, `coverage/`, and `*.tsbuildinfo`.
- Verified zero `.env` files, AWS access keys, Docker Hub tokens, private certificates, database passwords, or model API keys are tracked in Git.

## 3. Pre-Push Quality Gate Verification

### Backend (`akademia-ai-backend`)
- `python -m uv run ruff check .` -> `All checks passed!`
- `python -m uv run mypy app` -> `Success: no issues found in 92 source files`
- `python -m uv run pytest -q -p no:cacheprovider` -> `14 passed` (7 unit, 1 AI evaluation harness, 2 schema/role integration, 1 RLS fail-closed isolation, 2 API contract/security, 1 end-to-end Journeys A–G)

### Frontend (`akademia-ai-frontend`)
- `npm run generate:api` -> `Verified OpenAPI contract synchronization: 61 API paths in openapi.json`
- `npm run typecheck` -> `0 errors`
- `npm test` -> `3 passed (3)`
- `npm run build` -> Production Vite bundle built cleanly
