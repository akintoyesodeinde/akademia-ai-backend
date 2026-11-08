#!/bin/bash
set -euo pipefail
exec > >(tee /var/log/akademia-userdata.log | logger -t akademia-userdata -s 2>/dev/console) 2>&1

echo "[1/8] Installing Docker Engine, Docker Compose plugin, and jq on Amazon Linux 2023..."
dnf update -y
dnf install -y docker jq awscli
mkdir -p /usr/local/lib/docker/cli-plugins
ARCH=$(uname -m)
curl -fsSL "https://github.com/docker/compose/releases/download/v2.32.4/docker-compose-linux-${ARCH}" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

systemctl enable --now docker

echo "[2/8] Creating application deployment directory /opt/akademia-ai..."
mkdir -p /opt/akademia-ai/storage_data
chmod 750 /opt/akademia-ai

echo "[3/8] Discovering AWS Region via IMDSv2..."
TOKEN=$(curl -sS -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
AWS_REGION=$(curl -sS -H "X-aws-ec2-metadata-token: ${TOKEN}" "http://169.254.169.254/latest/meta-data/placement/region")

echo "[4/8] Writing production Docker Compose specification (/opt/akademia-ai/compose.prod.yaml)..."
cat > /opt/akademia-ai/compose.prod.yaml <<'EOF'
services:
  redis:
    image: redis:7.4-alpine
    container_name: akademia-redis
    restart: unless-stopped
    volumes:
      - akademia_redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  migrator:
    image: ${BACKEND_IMAGE}
    container_name: akademia-migrator
    restart: "no"
    command: ["alembic", "upgrade", "head"]
    env_file:
      - /opt/akademia-ai/.env.runtime
    environment:
      DATABASE_URL: ${MIGRATION_DATABASE_URL}

  api:
    image: ${BACKEND_IMAGE}
    container_name: akademia-api
    restart: unless-stopped
    env_file:
      - /opt/akademia-ai/.env.runtime
    volumes:
      - /opt/akademia-ai/storage_data:/app/storage_data
    depends_on:
      redis:
        condition: service_healthy
      migrator:
        condition: service_completed_successfully
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/platform/health', timeout=8)"]
      interval: 15s
      timeout: 10s
      start_period: 60s
      retries: 5

  worker:
    image: ${BACKEND_IMAGE}
    container_name: akademia-worker
    restart: unless-stopped
    command: ["python", "-m", "app.workers.runner"]
    env_file:
      - /opt/akademia-ai/.env.runtime
    environment:
      DATABASE_URL: ${WORKER_DATABASE_URL}
    volumes:
      - /opt/akademia-ai/storage_data:/app/storage_data
    depends_on:
      redis:
        condition: service_healthy
      migrator:
        condition: service_completed_successfully
    healthcheck:
      test: ["CMD-SHELL", "kill -0 1"]
      interval: 15s
      timeout: 5s
      start_period: 10s
      retries: 3

  frontend:
    image: ${FRONTEND_IMAGE}
    container_name: akademia-frontend
    restart: unless-stopped
    environment:
      VITE_API_BASE_URL: "/api/v1"
      API_UPSTREAM: "http://api:8000"
    ports:
      - "80:80"
    depends_on:
      api:
        condition: service_healthy

volumes:
  akademia_redisdata:
EOF

echo "[5/8] Creating atomic release & rollback helper (/opt/akademia-ai/deploy-release.sh)..."
cat > /opt/akademia-ai/deploy-release.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

SERVICE_TYPE="${1:-all}"
OVERRIDE_IMAGE="${2:-}"

TOKEN=$(curl -sS -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
AWS_REGION=$(curl -sS -H "X-aws-ec2-metadata-token: ${TOKEN}" "http://169.254.169.254/latest/meta-data/placement/region")

get_param() {
  aws ssm get-parameter --region "$AWS_REGION" --name "$1" --with-decryption --query "Parameter.Value" --output text
}

BACKEND_IMAGE=$(get_param "/akademia-ai/prod/backend_image")
FRONTEND_IMAGE=$(get_param "/akademia-ai/prod/frontend_image")
DATABASE_URL=$(get_param "/akademia-ai/prod/database_url")
MIGRATION_DATABASE_URL=$(get_param "/akademia-ai/prod/migration_database_url")
WORKER_DATABASE_URL=$(get_param "/akademia-ai/prod/worker_database_url")
JWT_SECRET_KEY=$(get_param "/akademia-ai/prod/jwt_secret_key")
AI_PROVIDER=$(aws ssm get-parameter --region "$AWS_REGION" --name "/akademia-ai/prod/ai_provider" --query "Parameter.Value" --output text 2>/dev/null || echo "deterministic")

if [ "$SERVICE_TYPE" = "backend" ] && [ -n "$OVERRIDE_IMAGE" ]; then
  BACKEND_IMAGE="$OVERRIDE_IMAGE"
elif [ "$SERVICE_TYPE" = "frontend" ] && [ -n "$OVERRIDE_IMAGE" ]; then
  FRONTEND_IMAGE="$OVERRIDE_IMAGE"
fi

# Optional Docker Hub login if private images are configured
DOCKERHUB_TOKEN=$(aws ssm get-parameter --region "$AWS_REGION" --name "/akademia-ai/prod/dockerhub_token" --with-decryption --query "Parameter.Value" --output text 2>/dev/null || true)
DOCKERHUB_USER=$(aws ssm get-parameter --region "$AWS_REGION" --name "/akademia-ai/prod/dockerhub_username" --query "Parameter.Value" --output text 2>/dev/null || true)
if [ -n "$DOCKERHUB_TOKEN" ] && [ -n "$DOCKERHUB_USER" ]; then
  echo "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USER" --password-stdin
fi

# Record previous state for automatic rollback
if [ -f /opt/akademia-ai/.env.images ]; then
  cp /opt/akademia-ai/.env.images /opt/akademia-ai/.env.images.prev
fi

umask 077
cat > /opt/akademia-ai/.env.runtime <<ENVEOF
APP_ENV=production
DATABASE_URL=${DATABASE_URL}
MIGRATION_DATABASE_URL=${MIGRATION_DATABASE_URL}
WORKER_DATABASE_URL=${WORKER_DATABASE_URL}
REDIS_URL=redis://redis:6379/0
JWT_SECRET_KEY=${JWT_SECRET_KEY}
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=/app/storage_data
AI_PROVIDER=${AI_PROVIDER}
ENVEOF

cat > /opt/akademia-ai/.env.images <<IMGEOF
BACKEND_IMAGE=${BACKEND_IMAGE}
FRONTEND_IMAGE=${FRONTEND_IMAGE}
MIGRATION_DATABASE_URL=${MIGRATION_DATABASE_URL}
WORKER_DATABASE_URL=${WORKER_DATABASE_URL}
IMGEOF

chown -R 10001:10001 /opt/akademia-ai/storage_data

rollback() {
  echo "ERROR: Release verification failed. Rolling back to previous image digests..." >&2
  if [ -f /opt/akademia-ai/.env.images.prev ]; then
    cp /opt/akademia-ai/.env.images.prev /opt/akademia-ai/.env.images
    docker compose --env-file /opt/akademia-ai/.env.images -f /opt/akademia-ai/compose.prod.yaml up -d
  fi
  exit 1
}

trap rollback ERR

docker pull "$BACKEND_IMAGE"
docker pull "$FRONTEND_IMAGE"

docker compose --env-file /opt/akademia-ai/.env.images -f /opt/akademia-ai/compose.prod.yaml up -d

for i in $(seq 1 20); do
  if curl -fsS http://127.0.0.1/healthz >/dev/null && curl -fsS http://127.0.0.1/api/v1/platform/health >/dev/null; then
    echo "Release verified healthy: BACKEND=${BACKEND_IMAGE} FRONTEND=${FRONTEND_IMAGE}"
    exit 0
  fi
  sleep 3
done

echo "Health check timed out after 60 seconds." >&2
false
EOF

chmod +x /opt/akademia-ai/deploy-release.sh

echo "[6/8] Executing initial deployment from SSM Parameter Store..."
/opt/akademia-ai/deploy-release.sh all || echo "Initial boot awaiting SSM parameters."
