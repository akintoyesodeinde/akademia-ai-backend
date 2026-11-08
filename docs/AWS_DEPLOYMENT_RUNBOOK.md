# Akademia AI — AWS Sandbox Deployment & Rollback Runbook

## 1. Pre-Deployment Checklist

1. Authenticate to the AWS account associated with `toyesode123@gmail.com` from Windows PowerShell:
   ```powershell
   aws sso login --profile akademia-deploy
   aws sts get-caller-identity --profile akademia-deploy
   ```
2. Confirm the AWS account ID, target region (default `us-east-1`), and sandbox resource scope:
   - **1x `db.t3.micro` RDS PostgreSQL 16 instance** (`--backup-retention-period 0` / no backups, Single-AZ, encrypted `gp3`).
   - **1x `t3.micro` EC2 instance** launched from `akademia-ai-ec2-lt` (no EBS backup snapshots).

## 2. Step-by-Step Provisioning Procedure

### Step 1: Provision IAM Roles, Security Groups, RDS (`db.t3.micro`, No Backups) & EC2 Launch Template

From `c:\Users\LENOVO\AkademiaAI\akademia-ai-backend`:

```powershell
.\infra\aws\provision-sandbox.ps1 `
  -Profile "akademia-deploy" `
  -Region "us-east-1" `
  -GitHubOwner "akintoyesodeinde" `
  -Ec2InstanceType "t3.micro" `
  -RdsInstanceClass "db.t3.micro" `
  -RdsMasterPassword "<STRONG_RDS_MASTER_PASSWORD>"
```

### Step 2: Initialize PostgreSQL Least-Privilege Roles on RDS & Populate SSM Parameter Store

Once `akademia-ai-db` reaches `available`:
1. Retrieve the RDS endpoint:
   ```powershell
   $RdsEndpoint = aws rds describe-db-instances `
     --profile akademia-deploy --region us-east-1 `
     --db-instance-identifier akademia-ai-db `
     --query "DBInstances[0].Endpoint.Address" --output text
   ```
2. Connect from an SSM Session on the EC2 instance (`aws ssm start-session --target <INSTANCE_ID>`) and run `scripts/init-db-roles.sql` with strong passwords for `akademia_migrator`, `akademia_app`, `akademia_worker`, and `akademia_readonly`.
3. Store the runtime parameters as `SecureString` / `String` in AWS SSM Parameter Store:
   ```powershell
   aws ssm put-parameter --profile akademia-deploy --region us-east-1 --name "/akademia-ai/prod/database_url" --type "SecureString" --value "postgresql+asyncpg://akademia_app:<APP_PW>@${RdsEndpoint}:5432/akademia_ai" --overwrite
   aws ssm put-parameter --profile akademia-deploy --region us-east-1 --name "/akademia-ai/prod/migration_database_url" --type "SecureString" --value "postgresql+asyncpg://akademia_migrator:<MIGRATOR_PW>@${RdsEndpoint}:5432/akademia_ai" --overwrite
   aws ssm put-parameter --profile akademia-deploy --region us-east-1 --name "/akademia-ai/prod/worker_database_url" --type "SecureString" --value "postgresql+asyncpg://akademia_worker:<WORKER_PW>@${RdsEndpoint}:5432/akademia_ai" --overwrite
   aws ssm put-parameter --profile akademia-deploy --region us-east-1 --name "/akademia-ai/prod/jwt_secret_key" --type "SecureString" --value "<RANDOM_64_CHAR_JWT_SECRET>" --overwrite
   aws ssm put-parameter --profile akademia-deploy --region us-east-1 --name "/akademia-ai/prod/backend_image" --type "String" --value "akintoyesodeinde/akademia-ai-backend@sha256:<BACKEND_DIGEST>" --overwrite
   aws ssm put-parameter --profile akademia-deploy --region us-east-1 --name "/akademia-ai/prod/frontend_image" --type "String" --value "akintoyesodeinde/akademia-ai-frontend@sha256:<FRONTEND_DIGEST>" --overwrite
   ```

## 3. Continuous Deployment & Controlled Database Migration Execution

On every merge to `main`:
1. GitHub Actions runs full lint, typecheck, database migration, RLS, and AI quality gate tests.
2. Trivy scans the built Docker image for `HIGH` and `CRITICAL` vulnerabilities.
3. The image is pushed to Docker Hub (`akintoyesodeinde/akademia-ai-backend` or `akintoyesodeinde/akademia-ai-frontend`) and its `@sha256:...` digest is recorded.
4. GitHub Actions assumes `arn:aws:iam::<ACCOUNT_ID>:role/akademia-github-deploy-role` via OIDC and invokes `ssm-deploy-service.sh` / `ssm-deploy-frontend.sh`.
5. On the EC2 host, `/opt/akademia-ai/deploy-release.sh`:
   - Saves the current working image digests to `/opt/akademia-ai/.env.images.prev`.
   - Pulls the new `@sha256:...` digest.
   - Runs `akademia-migrator` (`alembic upgrade head`) as a single-execution step before starting `akademia-api` and `akademia-worker`.
   - Verifies `/healthz` and `/api/v1/platform/health`.

## 4. Automated & Manual Rollback Procedure

- **Automated Rollback**: If `docker pull`, `alembic upgrade head`, or the 60-second HTTP health check fails during `/opt/akademia-ai/deploy-release.sh`, the `ERR` trap automatically restores `/opt/akademia-ai/.env.images.prev` and restarts the previous healthy containers.
- **Manual Rollback via SSM Run Command**:
  ```powershell
  aws ssm send-command `
    --profile akademia-deploy --region us-east-1 `
    --instance-ids "<INSTANCE_ID>" `
    --document-name "AWS-RunShellScript" `
    --parameters 'commands=["cp /opt/akademia-ai/.env.images.prev /opt/akademia-ai/.env.images && docker compose --env-file /opt/akademia-ai/.env.images -f /opt/akademia-ai/compose.prod.yaml up -d"]'
  ```
