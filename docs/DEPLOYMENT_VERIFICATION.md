# Akademia AI — End-to-End Deployment Verification & Status Report

## 1. Local Docker Image & Compose Verification Summary

| Check | Target | Result | Evidence / Identifier |
|---|---|---|---|
| Frontend Docker Image Build | `akademia-ai-frontend:local` | **PASSED** | Digest `sha256:f2c22e72cc2941d08f7f76dbae65ee4b1617a7ab009a86511de5fcf853e20642` (`74.6 MB`) |
| Standalone Frontend Container | `akademia-frontend-test` (`127.0.0.1:8088->80`) | **PASSED** | `ROOT_STATUS=200`, `SPA_FALLBACK_STATUS=200` (`/instructor/courses`), `HEALTH_STATUS=200`, `X-Frame-Options=DENY`, `X-Content-Type-Options=nosniff` |
| Backend Docker Image Build | `akademia-ai-backend:local` | **PASSED** | Digest `sha256:e3dfc9f8ea5cd1393276b178a75ed5d1137c3a5d32d7887bea72e048d4b7a8d4` |
| Docker Compose Stack Startup | `compose.yaml` (`akademia-postgres`, `akademia-redis`, `akademia-migrator`, `akademia-api`, `akademia-worker`, `akademia-frontend`) | **PASSED** | All 5 long-running services `Up (healthy)`; `akademia-migrator` `Exited (0)` |
| Alembic Migrations (`akademia_migrator`) | Revisions `001`–`012` | **PASSED** | `012_audit_notifications_outbox (head)` |
| Least-Privilege Runtime Roles & RLS | `akademia_app`, `akademia_worker` (`NOSUPERUSER NOBYPASSRLS`) across 52 tenant tables | **PASSED** | Verified in `test_migrations_and_schema.py` & `test_rls_and_tenant_isolation.py` |
| Live Frontend-to-Backend Proxy Flow | `http://127.0.0.1:5175/api/v1/*` -> `http://api:8000` | **PASSED** | Registered user, authenticated JWT (`len=304`), created tenant `1bde05cb-32bc-4bb2-896c-cc1e1bd287a8`, verified `/tenants/current`, created course `1e7ec52a-2a09-4c19-9b6f-8f1b3b7c0659` (`CS-1794153126`) |
| Missing External AI Provider Guardrail | `AI_PROVIDER=openai_compatible` without `AI_API_KEY` | **PASSED** | Raises `ExternalProviderError("AI_API_KEY is required when AI_PROVIDER=openai_compatible.")` rather than returning fake data |
| GitHub Feature Branch & PR Publishing | `akintoyesodeinde/akademia-ai-backend` & `akintoyesodeinde/akademia-ai-frontend` | **PASSED** | Backend PR #1 (`https://github.com/akintoyesodeinde/akademia-ai-backend/pull/1`) & Frontend PR #1 (`https://github.com/akintoyesodeinde/akademia-ai-frontend/pull/1`) |
| Docker Hub Immutable Image Push | `akintoyesodeinde/akademia-ai-backend` & `akintoyesodeinde/akademia-ai-frontend` | **PASSED** | Backend: `sha256:e3dfc9f8ea5cd1393276b178a75ed5d1137c3a5d32d7887bea72e048d4b7a8d4`; Frontend: `sha256:3aff557118edcfe407a284005bce099c1ade960f84b16902d04a194095bbebf3` |

## 2. Live AWS Sandbox Deployment & Verification Summary (Account `973429899833` — `eu-north-1`)

| Check | AWS Resource / Endpoint | Result | Evidence / Identifier |
|---|---|---|---|
| AWS STS Identity Verification | `aws sts get-caller-identity --profile akademia-deploy` | **PASSED** | Account `973429899833`, ARN `arn:aws:iam::973429899833:user/akademia-deploy` (`toyesode123@gmail.com`) |
| IAM Roles & Instance Profile | `akademia-github-deploy-role` & `akademia-ec2-instance-role` | **PASSED** | `arn:aws:iam::973429899833:role/akademia-github-deploy-role`, `arn:aws:iam::973429899833:instance-profile/akademia-ec2-instance-profile` |
| VPC & Security Groups | `vpc-010c9378937e51230` (`eu-north-1`) | **PASSED** | `akademia-ec2-sg` (`sg-068d80172b5e00cb9`, ports `80`/`443` only; no SSH `22`) & `akademia-rds-sg` (`sg-05b6d8816c6137f57`, port `5432` strictly from `akademia-ec2-sg`) |
| RDS PostgreSQL 18.6 (`db.t3.micro`) | `akademia-ai-db` | **PASSED** | Endpoint `akademia-ai-db.cte8a4cygk0a.eu-north-1.rds.amazonaws.com:5432`, `EngineVersion=18.6`, `MultiAZ=false` (Single-AZ), `BackupRetentionPeriod=0` (no backups), `PubliclyAccessible=false`, `20 GiB gp2` Free Tier |
| EC2 Launch Template & Single Host | `akademia-ai-ec2-lt` -> `i-0466cd9dca457d16b` | **PASSED** | **1x `t3.micro`** (`PublicIp: 13.60.186.44`, `PrivateIp: 172.31.46.69`), Amazon Linux 2023, `IMDSv2=required`, 20 GiB encrypted `gp3`, no EBS backups |
| RDS Role Provisioning & Alembic Migrations | `akademia_migrator`, `akademia_app`, `akademia_worker`, `akademia_readonly` | **PASSED** | `vector` extension (`0.8.1`), all 12 Alembic migrations (`001`–`012`) applied over TLS (`sslmode=verify-full` with AWS RDS global bundle) |
| Live AWS Frontend & SPA Routing | `http://13.60.186.44/` & `http://13.60.186.44/instructor/courses` | **PASSED** | `HTTP 200 OK`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` |
| Live AWS Health Checks | `http://13.60.186.44/healthz` & `http://13.60.186.44/api/v1/platform/health` | **PASSED** | `{"status":"healthy","service":"akademia-ai-frontend"}` & `{"status":"healthy","service":"akademia-ai-backend","database":"connected"}` |
| Live Multi-Tenant E2E Workflow on AWS | `http://13.60.186.44/api/v1/*` | **PASSED** | Registered user, authenticated JWT (`len=304`), created tenant `7934cca2-56b2-4047-9027-d663ee0051dc`, created course `0eb6b856-71e3-4d37-a1e3-3974ae0bf947` in RDS PostgreSQL 18.6 |
| Automated Rollback Verification | `/opt/akademia-ai/deploy-release.sh` via SSM Run Command | **PASSED** | Simulated invalid digest automatically triggered `ERR` trap, restored `/opt/akademia-ai/.env.images.prev`, and kept `/api/v1/platform/health` returning `200 OK` |
