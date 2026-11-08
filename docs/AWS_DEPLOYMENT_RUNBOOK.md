# Akademia AI — AWS Sandbox Deployment & Rollback Runbook

## 1. Pre-Deployment Checklist

1. Authenticate to the AWS account associated with `toyesode123@gmail.com` (**AWS Account ID `973429899833`**, region `eu-north-1`) from Windows PowerShell:
   ```powershell
   aws sts get-caller-identity --profile akademia-deploy
   ```
2. Confirm the AWS account ID (`973429899833`), target region (`eu-north-1`), and sandbox resource scope:
   - **1x `db.t3.micro` RDS PostgreSQL 18 (`18.6`) instance** (`--backup-retention-period 0` / no backups, Single-AZ, encrypted `20 GiB gp2` Free Tier).
   - **1x `t3.micro` EC2 instance** (`i-0466cd9dca457d16b`, Public IP `13.60.186.44`) launched from `akademia-ai-ec2-lt` (no EBS backup snapshots).

## 2. Step-by-Step Provisioning Procedure

### Step 1: Provision IAM Roles, Security Groups, RDS (`db.t3.micro`, No Backups), SSM Parameters & EC2 Launch Template

From `c:\Users\LENOVO\AkademiaAI\akademia-ai-backend`:

```powershell
.\infra\aws\provision-sandbox.ps1 `
  -Profile "akademia-deploy" `
  -Region "eu-north-1" `
  -GitHubOwner "akintoyesodeinde" `
  -Ec2InstanceType "t3.micro" `
  -RdsInstanceClass "db.t3.micro" `
  -RdsEngineVersion "18.6"
```

### Step 2: Automated RDS Role Initialization & SSM Parameter Store Bootstrap

`infra/aws/provision-sandbox.ps1` and `infra/aws/user-data.sh` automatically:
1. Wait for `akademia-ai-db` (`akademia-ai-db.cte8a4cygk0a.eu-north-1.rds.amazonaws.com`) to reach `available`.
2. Store all runtime parameters as `SecureString` / `String` under `/akademia-ai/prod/*` in AWS SSM Parameter Store (`eu-north-1`):
   - `/akademia-ai/prod/database_url` (`SecureString`, `sslmode=verify-full`)
   - `/akademia-ai/prod/migration_database_url` (`SecureString`, `sslmode=verify-full`)
   - `/akademia-ai/prod/worker_database_url` (`SecureString`, `sslmode=verify-full`)
   - `/akademia-ai/prod/jwt_secret_key` (`SecureString`)
   - `/akademia-ai/prod/rds_endpoint` (`String`)
   - `/akademia-ai/prod/rds_master_password`, `/akademia-ai/prod/migrator_password`, `/akademia-ai/prod/app_password`, `/akademia-ai/prod/worker_password`, `/akademia-ai/prod/readonly_password` (`SecureString`)
   - `/akademia-ai/prod/backend_image` (`String`: `akintoyesodeinde/akademia-ai-backend@sha256:e3dfc9f8ea5cd1393276b178a75ed5d1137c3a5d32d7887bea72e048d4b7a8d4`)
   - `/akademia-ai/prod/frontend_image` (`String`: `akintoyesodeinde/akademia-ai-frontend@sha256:3aff557118edcfe407a284005bce099c1ade960f84b16902d04a194095bbebf3`)
3. On EC2 first boot (`user-data.sh`), download the AWS RDS Global CA Bundle (`/opt/akademia-ai/certs/rds-global-bundle.pem`), initialize the least-privilege PostgreSQL roles (`akademia_migrator`, `akademia_app`, `akademia_worker`, `akademia_readonly`) and `vector` extension on RDS, run `alembic upgrade head`, and start the Docker Compose stack.

## 3. Continuous Deployment & Controlled Database Migration Execution

On every merge to `main`:
1. GitHub Actions runs full lint, typecheck, database migration, RLS, and AI quality gate tests.
2. Trivy scans the built Docker image for `HIGH` and `CRITICAL` vulnerabilities.
3. The image is pushed to Docker Hub (`akintoyesodeinde/akademia-ai-backend` or `akintoyesodeinde/akademia-ai-frontend`) and its `@sha256:...` digest is recorded.
4. GitHub Actions assumes `arn:aws:iam::973429899833:role/akademia-github-deploy-role` via OIDC and invokes `ssm-deploy-service.sh` / `ssm-deploy-frontend.sh`.
5. On the EC2 host (`i-0466cd9dca457d16b`), `/opt/akademia-ai/deploy-release.sh`:
   - Saves the current working image digests to `/opt/akademia-ai/.env.images.prev`.
   - Pulls the new `@sha256:...` digest.
   - Runs `akademia-migrator` (`alembic upgrade head`) as a single-execution step before starting `akademia-api` and `akademia-worker`.
   - Verifies `/healthz` and `/api/v1/platform/health`.

## 4. Automated & Manual Rollback Procedure

- **Automated Rollback (Verified Live via SSM Run Command)**: If `docker pull`, `alembic upgrade head`, or the 60-second HTTP health check fails during `/opt/akademia-ai/deploy-release.sh`, the `ERR` trap automatically restores `/opt/akademia-ai/.env.images.prev` and restarts the previous healthy containers.
- **Manual Rollback via SSM Run Command**:
  ```powershell
  aws ssm send-command `
    --profile akademia-deploy --region eu-north-1 `
    --instance-ids "i-0466cd9dca457d16b" `
    --document-name "AWS-RunShellScript" `
    --parameters 'commands=["cp /opt/akademia-ai/.env.images.prev /opt/akademia-ai/.env.images && docker compose --env-file /opt/akademia-ai/.env.images -f /opt/akademia-ai/compose.prod.yaml up -d"]'
  ```
