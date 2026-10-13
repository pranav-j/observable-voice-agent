#!/bin/bash
# Builds the app and web images for the demo instance (linux/arm64) and pushes them to ECR,
# tagged with the commit. Refuses a dirty tree: a tag has to mean exactly one commit.
set -euo pipefail
cd "$(dirname "$0")/.."
region=${AWS_REGION:-ap-south-1}

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "Commit or stash your changes first: the image tag is the commit." >&2
  exit 1
fi
tag=$(git rev-parse --short=12 HEAD)
registry=$(terraform -chdir=deploy/terraform output -raw registry)

aws ecr get-login-password --region "$region" \
  | docker login --username AWS --password-stdin "$registry" >/dev/null

for image in app web; do
  ref="$registry/voice-order-agent/$image:$tag"
  if aws ecr describe-images --region "$region" --repository-name "voice-order-agent/$image" \
      --image-ids imageTag="$tag" >/dev/null 2>&1; then
    echo "$ref already pushed"
    continue
  fi
  docker buildx build --platform linux/arm64 -f "deploy/Dockerfile.$image" -t "$ref" --push .
done
echo "$tag"
