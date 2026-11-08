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

## 2. AWS CLI & Account Verification Status

Executed on host Windows PowerShell:
- `aws --version`: `aws-cli/2.36.17 Python/3.14.6 Windows/10 script-exe/AMD64`
- `aws sts get-caller-identity --profile akademia-deploy`: `The config profile (akademia-deploy) could not be found`
- `aws sts get-caller-identity` (default profile):
  - `Account`: `415805875879`
  - `Arn`: `arn:aws:iam::415805875879:user/drinks-deployer`
  - `UserId`: `AIDAWBT7WE2T3FK2VKDGQ`

### Approval Gate Before Provisioning AWS Resources (Step 10 / Step 11)

Per Section 7 and Section 14 ("Do not create resources until the account, AWS region, deployment scope and expected costs have been confirmed. Stop at any step that requires unavailable credentials, explicit approval, or external account access"):
1. **Account Confirmation Required**: Please confirm whether AWS Account `415805875879` (`arn:aws:iam::415805875879:user/drinks-deployer`) is the intended target account for `toyesode123@gmail.com` or if you wish to authenticate a separate `akademia-deploy` profile first.
2. **Region & Cost Confirmation Required**:
   - Target Region: `us-east-1` (default in `infra/aws/provision-sandbox.ps1`).
   - Planned Resources: **1x `db.t3.micro` RDS PostgreSQL 16** (`BackupRetentionPeriod=0` / no backups, Single-AZ, 20 GiB `gp3`) + **1x `t3.micro` EC2 instance** (Amazon Linux 2023, 20 GiB `gp3`, no snapshots/backups).
   - Estimated Sandbox Cost: `$0/month` if within active 12-month AWS Free Tier (`750 hrs/mo` `t3.micro` EC2 + `750 hrs/mo` `db.t3.micro` RDS + `20 GiB` RDS storage, `$0` backup storage since backups are disabled), or `~$21–$24/month` (`~$0.017/hr` `db.t3.micro` + `~$0.0104/hr` `t3.micro` + EBS/RDS `gp3` storage) outside Free Tier.
