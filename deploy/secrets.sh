#!/bin/bash
# Puts the demo's secrets in SSM Parameter Store (SecureString), where the instance reads
# them at start. The OpenAI key comes from .env; the LiveKit keys and the database password
# are generated once and kept. Nothing is printed. --rotate regenerates the generated ones.
set -euo pipefail
cd "$(dirname "$0")/.."
region=${AWS_REGION:-ap-south-1}
rotate=${1:-}

exists() {
  aws ssm get-parameter --region "$region" --name "/voice-order-agent/$1" >/dev/null 2>&1
}
put() {  # name; the value comes on stdin and reaches the CLI in a private file, never argv
  local request
  request=$(mktemp)  # mode 600
  python3 -c 'import json, sys; print(json.dumps({"Name": sys.argv[1], "Value": sys.stdin.read(),
    "Type": "SecureString", "Overwrite": True}))' "/voice-order-agent/$1" > "$request"
  aws ssm put-parameter --region "$region" --cli-input-json "file://$request" >/dev/null
  rm -f "$request"
  tag "$1"
  echo "set /voice-order-agent/$1"
}
tag() {  # so the parameter shows up as this project's, like the Terraform resources
  aws ssm add-tags-to-resource --region "$region" --resource-type Parameter \
    --resource-id "/voice-order-agent/$1" \
    --tags Key=project,Value=voice-order-agent Key=repo,Value=observable-voice-agent >/dev/null
}
generated() {  # name, shell command that prints a new value
  if [ "$rotate" = "--rotate" ] || ! exists "$1"; then
    bash -c "$2" | put "$1"
  else
    echo "kept /voice-order-agent/$1"
  fi
}

key=$(grep -E '^OPENAI_API_KEY=' .env | cut -d= -f2- || true)
[ -n "$key" ] || { echo "OPENAI_API_KEY is empty in .env" >&2; exit 1; }
printf '%s' "$key" | put openai_api_key

generated livekit_api_key 'printf "API%s" "$(openssl rand -hex 6)"'
generated livekit_api_secret 'openssl rand -base64 36 | tr -d "\n"'
generated postgres_password 'openssl rand -hex 24'

if ! exists image_tag; then
  aws ssm put-parameter --region "$region" --name /voice-order-agent/image_tag --type String \
    --value none >/dev/null
  tag image_tag
  echo "set /voice-order-agent/image_tag to none (no release yet)"
fi
