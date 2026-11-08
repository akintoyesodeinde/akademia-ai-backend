# Akademia AI — Docker Hub Publishing & CI/CD Pipeline Report

## 1. Docker Hub Image Repositories

Each independent repository publishes its own immutable container image to Docker Hub under the discovered namespace `akintoyesodeinde` (configurable via the `DOCKERHUB_NAMESPACE` repository variable):

| Repository | Docker Hub Image Name | Runtime Base | Exposed Port |
|---|---|---|---|
| `akademia-ai-backend` | `akintoyesodeinde/akademia-ai-backend` | `python:3.13-slim` (non-root `akademia`, UID `10001`) | `8000` |
| `akademia-ai-frontend` | `akintoyesodeinde/akademia-ai-frontend` | `nginx:1.27-alpine` | `80` |

## 2. GitHub Actions CI/CD Workflows

- **Backend Workflow**: `c:\Users\LENOVO\AkademiaAI\akademia-ai-backend\.github\workflows\ci.yml`
- **Frontend Workflow**: `c:\Users\LENOVO\AkademiaAI\akademia-ai-frontend\.github\workflows\ci.yml`

### Pipeline Stages

1. **Stage 1 — Quality Gates & Automated Tests**:
   - **Backend (`lint-typecheck-and-test`)**:
     - Provisions `pgvector/pgvector:pg16` and `redis:7.4-alpine` service containers.
     - Executes `scripts/init-db-roles.sql` to create `akademia_migrator`, `akademia_app` (`NOBYPASSRLS`), `akademia_worker` (`NOBYPASSRLS`), and `akademia_readonly`.
     - Runs `uv run ruff check .` and `uv run mypy app`.
     - Applies Alembic migrations (`001`–`012`) using `akademia_migrator`.
     - Runs `uv run pytest` (unit, integration, RLS isolation, API contract, AI evaluation quality gates, and end-to-end multi-tenant journeys).
     - Exports `openapi.json` (`61` paths).
   - **Frontend (`build-and-test`)**:
     - Runs `npm ci` against committed `package-lock.json`.
     - Verifies OpenAPI contract synchronization (`npm run generate:api`).
     - Runs `npm run typecheck` (`tsc --noEmit`), `npm test` (`vitest run`), and `npm run build` (`tsc -b && vite build`).

2. **Stage 2 — Build, Vulnerability Scan & Immutable Docker Hub Publish (`build-scan-and-publish`)**:
   - Builds the Docker image via `docker/build-push-action@v6` with GitHub Actions layer caching (`type=gha`).
   - Scans the built image using **Aqua Trivy (`aquasecurity/trivy-action@0.28.0`)** for `CRITICAL` and `HIGH` OS and library vulnerabilities (`exit-code: "1"`, `ignore-unfixed: true`).
   - Authenticates to Docker Hub via `docker/login-action@v3` using repository variable `DOCKERHUB_USERNAME` and secret `DOCKERHUB_TOKEN` (scoped Read/Write/Delete Personal Access Token).
   - Tags images with the immutable Git commit SHA (`sha-<40-char-commit-sha>`) and semantic version tag (`v*.*.*` on release tags).
   - **Never deploys production using a mutable `latest` tag.**
   - Records the immutable `@sha256:...` digest into job outputs (`image_digest`) and `$GITHUB_STEP_SUMMARY`.

3. **Stage 3 — AWS EC2 Deployment via OIDC & SSM Run Command (`deploy-aws-ec2`)**:
   - Protected by the `production` GitHub Environment.
   - Assumes `vars.AWS_DEPLOY_ROLE_ARN` via `aws-actions/configure-aws-credentials@v4` using GitHub OIDC (`id-token: write`).
   - Invokes `infra/aws/scripts/ssm-deploy-service.sh` (backend) or `scripts/ssm-deploy-frontend.sh` (frontend), which validates the `@sha256:...` digest, updates `/akademia-ai/prod/<service>_image` in AWS SSM Parameter Store, and triggers `/opt/akademia-ai/deploy-release.sh` on the EC2 host via AWS Systems Manager Run Command (`AWS-RunShellScript`).

## 3. Required GitHub Repository Secrets & Variables

| Setting Type | Name | Description |
|---|---|---|
| **Variable** | `DOCKERHUB_NAMESPACE` | `akintoyesodeinde` |
| **Variable** | `DOCKERHUB_USERNAME` | `akintoyesodeinde` |
| **Secret** | `DOCKERHUB_TOKEN` | Scoped Docker Hub Access Token (Read & Write) |
| **Variable** | `AWS_REGION` | Target AWS Region (e.g., `us-east-1`) |
| **Variable** | `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::<ACCOUNT_ID>:role/akademia-github-deploy-role` |
