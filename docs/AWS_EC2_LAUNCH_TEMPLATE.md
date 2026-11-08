# Akademia AI — AWS EC2 Launch Template & Cost-Economized Sandbox Architecture

## 1. Sandbox Budget & Cost-Economy Design

Per the explicit sandbox budget requirement (**1x `db.t3.micro` RDS PostgreSQL instance + 1x EC2 instance with NO backups**):

| Component | AWS Resource / Class | Configuration | Cost Optimization & Availability Note |
|---|---|---|---|
| **Application Host** | **1x EC2 `t3.micro`** (or `t3.small`) | Amazon Linux 2023 (`x86_64`), 20 GiB `gp3` encrypted EBS (`DeleteOnTermination=true`, **0 EBS snapshots/backups**) | Single-instance sandbox deployment; **not high-availability (HA)**. If the single EC2 instance is replaced, stateless containers restart automatically from SSM Parameter Store + RDS. |
| **PostgreSQL Database** | **1x RDS PostgreSQL 16 `db.t3.micro`** | Single-AZ (`--no-multi-az`), 20 GiB `gp3` encrypted, **`--backup-retention-period 0` (no automated backups)**, private SG | Zero backup storage fees and zero Multi-AZ standby cost while keeping authoritative database storage independent of EC2 replacement. |
| **Redis & Worker** | Containers on the EC2 host (`compose.prod.yaml`) | `redis:7.4-alpine` + `akademia-worker` running alongside `akademia-api` and `akademia-frontend` | Eliminates separate ElastiCache hourly charges in the sandbox environment. |
| **Administrative Access** | AWS Systems Manager Session Manager | Outbound HTTPS (443) via `AmazonSSMManagedInstanceCore` | Zero bastion host cost; SSH port `22` is not exposed. |

## 2. Security Groups

1. **`akademia-ec2-sg` (EC2 Application Host)**:
   - **Inbound**: TCP `80` (HTTP) and TCP `443` (HTTPS) from `0.0.0.0/0`.
   - **Blocked (Not Exposed)**: TCP `22` (SSH), TCP `5432` (PostgreSQL), TCP `6379` (Redis), TCP `8000` (internal Uvicorn port).
2. **`akademia-rds-sg` (RDS PostgreSQL `db.t3.micro`)**:
   - **Inbound**: TCP `5432` strictly from source security group `akademia-ec2-sg`.
   - **Public Access**: Disabled (`--no-publicly-accessible`).

## 3. Launch Template Specification (`akademia-ai-ec2-lt`)

Implemented in `infra/aws/provision-sandbox.ps1` and `infra/aws/user-data.sh`:
- **AMI**: Latest Amazon Linux 2023 (`x86_64`) resolved dynamically from `/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64`.
- **Instance Type**: `t3.micro` (1 instance).
- **IAM Instance Profile**: `akademia-ec2-instance-profile`.
- **IMDSv2 Enforcement**: `HttpTokens=required`, `HttpPutResponseHopLimit=2`.
- **Storage**: 20 GiB encrypted `gp3` root volume (`/dev/xvda`), no automated backup policy.
- **User Data (`infra/aws/user-data.sh`)**:
  1. Installs Docker Engine, Docker Compose v2 plugin, `jq`, and AWS CLI.
  2. Creates `/opt/akademia-ai/compose.prod.yaml` and `/opt/akademia-ai/deploy-release.sh`.
  3. Queries IMDSv2 for the region and fetches runtime configuration (`database_url`, `migration_database_url`, `worker_database_url`, `jwt_secret_key`, `backend_image`, `frontend_image`) from AWS SSM Parameter Store (`/akademia-ai/prod/*`) with `--with-decryption`.
  4. Pulls the immutable `@sha256:...` image digests for `akademia-ai-backend` and `akademia-ai-frontend`.
  5. Runs `alembic upgrade head` via the one-shot `migrator` service using `akademia_migrator`.
  6. Starts `akademia-api` (`akademia_app`), `akademia-worker` (`akademia_worker`), `akademia-redis`, and `akademia-frontend` (Nginx reverse proxy on port 80).
  7. Verifies `/healthz` and `/api/v1/platform/health`, rolling back automatically to `.env.images.prev` if health checks fail.
