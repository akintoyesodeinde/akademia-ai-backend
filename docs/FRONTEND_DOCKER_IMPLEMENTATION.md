# Akademia AI — Frontend Docker Implementation Report

## 1. Overview

The `akademia-ai-frontend` repository (`c:\Users\LENOVO\AkademiaAI\akademia-ai-frontend`) is packaged as a multi-stage production container image (`akademia-ai-frontend:local` / `akintoyesodeinde/akademia-ai-frontend`) built on `node:22-alpine` and served by `nginx:1.27-alpine`.

## 2. Implemented Files

| File | Responsibility |
|---|---|
| `Dockerfile` | Multi-stage build (`node:22-alpine` -> `nginx:1.27-alpine`), deterministic `npm ci`, Vite production bundle, CRLF-safe entrypoint setup, and container `HEALTHCHECK`. |
| `.dockerignore` | Excludes `node_modules`, `dist`, `.git`, `.github`, `.env*`, `playwright-report`, `test-results`, `coverage`, `*.tsbuildinfo`, `docs`, and `e2e`. |
| `docker/40-akademia-runtime-config.sh` | Generates `/usr/share/nginx/html/config.js` (`window.__AKADEMIA_CONFIG__`) from non-secret runtime environment variables (`VITE_API_BASE_URL`) and writes `/etc/nginx/conf.d/default.conf` with SPA fallback routing, static asset caching, security headers (`/etc/nginx/conf.d/security-headers.inc`), `/healthz` endpoint, and optional `/api/` reverse proxy when `API_UPSTREAM` is set. |
| `public/config.js` | Default empty `window.__AKADEMIA_CONFIG__` object for local Vite development and test runs. |
| `index.html` | Loads `/config.js` prior to the Vite module entry (`/src/main.tsx`). |
| `src/api/client.ts` | Reads `globalThis.__AKADEMIA_CONFIG__?.VITE_API_BASE_URL` first, then `import.meta.env.VITE_API_BASE_URL`, then falls back to `DEFAULT_API_BASE`. |

## 3. Build & Runtime Verification Results

### 3.1 Build Command & Immutable Image Digest

```powershell
cd C:\Users\LENOVO\AkademiaAI\akademia-ai-frontend
docker build -t akademia-ai-frontend:local .
```

- **Built Image Tag**: `akademia-ai-frontend:local`
- **Image Size**: `74.6 MB`
- **Manifest List Digest**: `sha256:f2c22e72cc2941d08f7f76dbae65ee4b1617a7ab009a86511de5fcf853e20642`
- **Image Config Digest**: `sha256:564d864744d7be7ab5a70e48842114243184936ef734676c553090ea7a9142e9`

### 3.2 Standalone Runtime Verification

Because host port `127.0.0.1:8080` was occupied by an existing container (`ajohq-preview-api`), standalone verification bound host port `127.0.0.1:8088` to container port `80`:

```powershell
docker run --rm -d `
  --name akademia-frontend-test `
  -p 127.0.0.1:8088:80 `
  -e VITE_API_BASE_URL="http://localhost:8000/api/v1" `
  akademia-ai-frontend:local
```

Verified container status and HTTP responses:
- `docker ps --filter "name=akademia-frontend-test"`:
  - `akademia-frontend-test   akademia-ai-frontend:local   Up (healthy)   127.0.0.1:8088->80/tcp`
- Root SPA entry (`GET http://127.0.0.1:8088/`):
  - `ROOT_STATUS=200`
  - `X-Frame-Options: DENY`
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: strict-origin-when-cross-origin`
- Deep client-side route refresh (`GET http://127.0.0.1:8088/instructor/courses`):
  - `SPA_FALLBACK_STATUS=200` (serves `index.html` via `try_files $uri $uri/ /index.html;`)
- Health endpoint (`GET http://127.0.0.1:8088/healthz`):
  - `HEALTH_STATUS=200 BODY={"status":"healthy","service":"akademia-ai-frontend"}`
- Runtime configuration (`GET http://127.0.0.1:8088/config.js`):
  - Returns `window.__AKADEMIA_CONFIG__ = { VITE_API_BASE_URL: "http://localhost:8000/api/v1" };` without baking environment URLs or secrets into the build layer.
