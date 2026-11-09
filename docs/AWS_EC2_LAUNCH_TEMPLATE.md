# Akademia AI — AWS EC2 Launch Template & Cost-Economized Sandbox Architecture

## 1. Sandbox Budget & Cost-Economy Design (Account `973429899833` — `eu-north-1`)

Per the explicit sandbox budget requirement (**1x Free-Tier `db.t3.micro` RDS PostgreSQL 18 instance + 1x Free-Tier `t3.micro` EC2 instance with NO backups**):

| Component | Provisioned AWS Resource | Configuration | Cost Optimization & Availability Note |
|---|---|---|---|
| **Application Host** | **1x EC2 `t3.micro`** (`i-0466cd9dca457d16b`, Public IP `13.60.186.44`) | Amazon Linux 2023 (`ami-09003c75a6f592e41`, `x86_64`), 20 GiB `gp3` encrypted EBS (`DeleteOnTermination=true`, **0 EBS snapshots/backups**) | Single-instance Free-Tier sandbox deployment; **not high-availability (HA)**. If the single EC2 instance is replaced, stateless containers restart automatically from SSM Parameter Store + RDS. |
| **PostgreSQL Database** | **1x RDS PostgreSQL 18.6 `db.t3.micro`** (`akademia-ai-db`) | Endpoint `akademia-ai-db.cte8a4cygk0a.eu-north-1.rds.amazonaws.com:5432`, Single-AZ (`MultiAZ=false`), 20 GiB `gp2` encrypted, **`BackupRetentionPeriod=0` (no automated backups)**, private SG | Zero backup storage fees and zero Multi-AZ standby cost while keeping authoritative database storage independent of EC2 replacement. |
| **Redis & Worker** | Containers on the EC2 host (`compose.prod.yaml`) | `redis:7.4-alpine` + `akademia-worker` running alongside `akademia-api` and `akademia-frontend` | Eliminates separate ElastiCache hourly charges in the sandbox environment. |
| **Administrative Access** | AWS Systems Manager Session Manager | Outbound HTTPS (443) via `AmazonSSMManagedInstanceCore` | Zero bastion host cost; SSH port `22` is not exposed. |

## 2. Security Groups (`vpc-010c9378937e51230` in `eu-north-1`)

1. **`akademia-ec2-sg` (`sg-068d80172b5e00cb9`)**:
   - **Inbound**: TCP `80` (HTTP) and TCP `443` (HTTPS) from `0.0.0.0/0`.
   - **Blocked (Not Exposed)**: TCP `22` (SSH), TCP `5432` (PostgreSQL), TCP `6379` (Redis), TCP `8000` (internal Uvicorn port).
2. **`akademia-rds-sg` (`sg-05b6d8816c6137f57`)**:
   - **Inbound**: TCP `5432` strictly from source security group `akademia-ec2-sg` (`sg-068d80172b5e00cb9`).
   - **Public Access**: Disabled (`PubliclyAccessible=false`).

## 3. Launch Template Specification (`akademia-ai-ec2-lt` / `lt-08d808b49818f4040`)

Implemented in `infra/aws/provision-sandbox.ps1` and `infra/aws/user-data.sh`:
- **AMI**: Amazon Linux 2023 (`ami-09003c75a6f592e41`, `x86_64`) resolved dynamically from `/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64` in `eu-north-1`.
- **Instance Type**: `t3.micro` (1 instance: `i-0466cd9dca457d16b`).
- **IAM Instance Profile**: `akademia-ec2-instance-profile` (`arn:aws:iam::973429899833:instance-profile/akademia-ec2-instance-profile`).
- **IMDSv2 Enforcement**: `HttpTokens=required`, `HttpPutResponseHopLimit=2`.
- **Storage**: 20 GiB encrypted `gp3` root volume (`/dev/xvda`), no automated backup policy.
- **User Data (`infra/aws/user-data.sh`)**:
  1. Installs Docker Engine, Docker Compose v2 plugin, `jq`, `postgresql16` client tools, and AWS CLI.
  2. Downloads the AWS RDS Global CA Bundle (`https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem`) to `/opt/akademia-ai/certs/rds-global-bundle.pem` for `sslmode=verify-full` TLS connections to RDS PostgreSQL 18.6.
  3. Creates `/opt/akademia-ai/compose.prod.yaml` and `/opt/akademia-ai/deploy-release.sh`.
  4. Queries IMDSv2 for the region (`eu-north-1`), fetches RDS credentials and runtime configuration (`database_url`, `migration_database_url`, `worker_database_url`, `jwt_secret_key`, `backend_image`, `frontend_image`) from AWS SSM Parameter Store (`/akademia-ai/prod/*`) with `--with-decryption`, and idempotently initializes the least-privilege PostgreSQL roles (`akademia_migrator`, `akademia_app`, `akademia_worker`, `akademia_readonly`) and `vector` extension on RDS.
  5. Pulls the immutable `@sha256:...` image digests for `akademia-ai-backend` and `akademia-ai-frontend`.
  6. Runs `alembic upgrade head` via the one-shot `migrator` service using `akademia_migrator`.
  7. Starts `akademia-api` (`akademia_app`), `akademia-worker` (`akademia_worker`), `akademia-redis`, and `akademia-frontend` (Nginx reverse proxy on port 80).
  8. Verifies `/healthz` and `/api/v1/platform/health`, rolling back automatically to `.env.images.prev` if health checks fail.
