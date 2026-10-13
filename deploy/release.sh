#!/bin/bash
# Rolls the demo instance to an image tag: records the tag, pushes the deploy files over
# SSM, restarts the stack, and waits until the site answers. Usage: release.sh <tag>
set -euo pipefail
cd "$(dirname "$0")/.."
region=${AWS_REGION:-ap-south-1}
tag=${1:?usage: release.sh <image tag>}

for image in app web; do
  aws ecr describe-images --region "$region" --repository-name "voice-order-agent/$image" \
    --image-ids imageTag="$tag" >/dev/null \
    || { echo "voice-order-agent/$image:$tag isn't in ECR; run make deploy-images first" >&2; exit 1; }
done

instance=$(terraform -chdir=deploy/terraform output -raw instance_id)
host=$(terraform -chdir=deploy/terraform output -raw site_host)

aws ssm put-parameter --region "$region" --name /voice-order-agent/image_tag --type String \
  --overwrite --value "$tag" >/dev/null

write() {  # local file, remote path
  printf 'echo %s | base64 -d > /opt/voice-order-agent/%s' "$(base64 < "deploy/$1" | tr -d '\n')" "$1"
}
commands=$(python3 - "$(write compose.yaml)" "$(write livekit.yaml)" "$(write run.sh)" <<'EOF'
import json, sys
print(json.dumps(sys.argv[1:] + ["chmod 755 /opt/voice-order-agent/run.sh", "systemctl restart voice-order-agent"]))
EOF
)
command_id=$(aws ssm send-command --region "$region" --instance-ids "$instance" \
  --document-name AWS-RunShellScript --comment "voice-order-agent release $tag" \
  --parameters "{\"commands\": $commands, \"executionTimeout\": [\"1200\"]}" \
  --query Command.CommandId --output text)
echo "release $tag: SSM command $command_id"
aws ssm wait command-executed --region "$region" --command-id "$command_id" --instance-id "$instance" \
  || true
aws ssm get-command-invocation --region "$region" --command-id "$command_id" \
  --instance-id "$instance" --query '[Status, StandardOutputContent, StandardErrorContent]' \
  --output text | tail -20

for _ in $(seq 1 60); do
  if curl -fsS -o /dev/null "https://$host/api/menu"; then
    echo "up: https://$host"
    exit 0
  fi
  sleep 5
done
echo "https://$host didn't answer within 5 minutes" >&2
exit 1
