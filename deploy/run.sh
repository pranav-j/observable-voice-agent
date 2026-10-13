#!/bin/bash
# Starts the demo stack on the instance. Run by voice-order-agent.service at boot and on every
# release: secrets from SSM Parameter Store into a root-only .env, images from ECR at the
# tag recorded in /voice-order-agent/image_tag, then docker compose.
set -euo pipefail
cd /opt/voice-order-agent
source ./host.env  # REGISTRY, SITE_HOST, AWS_REGION, written at first boot

param() {
  aws ssm get-parameter --region "$AWS_REGION" --name "/voice-order-agent/$1" \
    --with-decryption --query Parameter.Value --output text
}

tag=$(param image_tag)
if [ "$tag" = "none" ]; then
  echo "No release yet (/voice-order-agent/image_tag is 'none'); nothing to start."
  exit 0
fi

umask 077
{
  echo "OPENAI_API_KEY=$(param openai_api_key)"
  echo "LIVEKIT_API_KEY=$(param livekit_api_key)"
  echo "LIVEKIT_API_SECRET=$(param livekit_api_secret)"
  echo "POSTGRES_PASSWORD=$(param postgres_password)"
  echo "IMAGE_TAG=$tag"
  echo "REGISTRY=$REGISTRY"
  echo "SITE_HOST=$SITE_HOST"
} > .env.new
mv .env.new .env

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$REGISTRY" >/dev/null
docker compose pull --quiet
docker compose up -d --remove-orphans
echo "voice-order-agent $tag is up at https://$SITE_HOST"
