#!/usr/bin/env bash
set -euo pipefail

SERVICE_TYPE="${1:?Usage: ssm-deploy-service.sh <backend|frontend> <image-with-digest>}"
IMAGE_REF="${2:?Usage: ssm-deploy-service.sh <backend|frontend> <image-with-digest>}"
AWS_REGION="${AWS_REGION:-us-east-1}"
APP_TAG="${APP_TAG:-akademia-ai}"

case "$IMAGE_REF" in
  *@sha256:*) ;;
  *)
    echo "ERROR: Deployment requires an immutable @sha256:... image digest, got: $IMAGE_REF" >&2
    exit 1
    ;;
esac

PARAM_NAME="/akademia-ai/prod/${SERVICE_TYPE}_image"
echo "Recording approved immutable digest in SSM Parameter Store: ${PARAM_NAME} -> ${IMAGE_REF}"
aws ssm put-parameter \
  --region "$AWS_REGION" \
  --name "$PARAM_NAME" \
  --type "String" \
  --value "$IMAGE_REF" \
  --overwrite

INSTANCE_ID=$(aws ec2 describe-instances \
  --region "$AWS_REGION" \
  --filters "Name=tag:Application,Values=${APP_TAG}" "Name=instance-state-name,Values=running" \
  --query "Reservations[0].Instances[0].InstanceId" \
  --output text)

if [ -z "$INSTANCE_ID" ] || [ "$INSTANCE_ID" = "None" ]; then
  echo "ERROR: No running EC2 instance found with tag Application=${APP_TAG}" >&2
  exit 1
fi

echo "Triggering SSM Run Command deployment on instance ${INSTANCE_ID}..."
COMMAND_ID=$(aws ssm send-command \
  --region "$AWS_REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --comment "Deploy ${SERVICE_TYPE} image ${IMAGE_REF}" \
  --parameters "commands=[\"/opt/akademia-ai/deploy-release.sh ${SERVICE_TYPE} ${IMAGE_REF}\"]" \
  --query "Command.CommandId" \
  --output text)

echo "Waiting for SSM Command ${COMMAND_ID} to complete..."
aws ssm wait command-executed \
  --region "$AWS_REGION" \
  --command-id "$COMMAND_ID" \
  --instance-id "$INSTANCE_ID"

STATUS=$(aws ssm get-command-invocation \
  --region "$AWS_REGION" \
  --command-id "$COMMAND_ID" \
  --instance-id "$INSTANCE_ID" \
  --query "Status" \
  --output text)

aws ssm get-command-invocation \
  --region "$AWS_REGION" \
  --command-id "$COMMAND_ID" \
  --instance-id "$INSTANCE_ID" \
  --query "StandardOutputContent" \
  --output text

if [ "$STATUS" != "Success" ]; then
  echo "ERROR: SSM deployment failed with status ${STATUS}" >&2
  aws ssm get-command-invocation \
    --region "$AWS_REGION" \
    --command-id "$COMMAND_ID" \
    --instance-id "$INSTANCE_ID" \
    --query "StandardErrorContent" \
    --output text >&2
  exit 1
fi

echo "Deployment of ${SERVICE_TYPE} (${IMAGE_REF}) succeeded on ${INSTANCE_ID}."
