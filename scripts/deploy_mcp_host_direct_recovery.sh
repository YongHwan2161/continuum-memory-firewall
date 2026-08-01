#!/usr/bin/env bash
set -euo pipefail

required=(
  CONTINUUM_RUNTIME_SECRET_ARN
  CONTINUUM_DEPLOY_BUCKET
  CONTINUUM_CA_CERT_PATH
  CONTINUUM_INSTANCE_ROLE_NAME
)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    printf '%s is required.\n' "$name" >&2
    exit 2
  fi
done

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
"$repo_root/scripts/assert_deployer_identity.sh"
region="${AWS_REGION:-${AWS_DEFAULT_REGION:-ap-southeast-1}}"
bedrock_region="${CONTINUUM_BEDROCK_REGION:-ap-northeast-2}"
stack_name="${CONTINUUM_MCP_STACK_NAME:-continuum-authenticated-mcp}"
deployment_key="${CONTINUUM_MCP_DEPLOYMENT_KEY:-mcp-host/continuum-mcp-host.zip}"
package_path="$repo_root/build/aws/continuum-mcp-host.zip"

stack_status="$(aws cloudformation describe-stacks --region "$region" \
  --stack-name "$stack_name" --query 'Stacks[0].StackStatus' --output text)"
if [[ "$stack_status" == "UPDATE_ROLLBACK_FAILED" ]]; then
  aws cloudformation continue-update-rollback \
    --region "$region" \
    --stack-name "$stack_name" \
    --resources-to-skip McpInstance
  rollback_ready=0
  for _attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18; do
    stack_status="$(aws cloudformation describe-stacks --region "$region" \
      --stack-name "$stack_name" --query 'Stacks[0].StackStatus' --output text)"
    if [[ "$stack_status" == "UPDATE_ROLLBACK_COMPLETE" ]]; then
      rollback_ready=1
      break
    fi
    case "$stack_status" in
      UPDATE_ROLLBACK_IN_PROGRESS) ;;
      *) printf 'Unexpected rollback status: %s\n' "$stack_status" >&2; exit 5 ;;
    esac
    sleep 5
  done
  if [[ "$rollback_ready" -ne 1 ]]; then
    printf 'CloudFormation rollback recovery did not finish.\n' >&2
    exit 5
  fi
elif [[ "$stack_status" != "UPDATE_ROLLBACK_COMPLETE" ]]; then
  printf 'Direct recovery is limited to a rolled-back stack; current status: %s\n' \
    "$stack_status" >&2
  exit 5
fi

"$repo_root/scripts/build_mcp_host_package.sh" "$package_path"
aws s3 cp "$package_path" "s3://$CONTINUUM_DEPLOY_BUCKET/$deployment_key" \
  --region "$region" --only-show-errors
package_sha256="$(sha256sum "$package_path" | awk '{print $1}')"
instance_id="$(aws cloudformation describe-stacks --region "$region" \
  --stack-name "$stack_name" \
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue | [0]" \
  --output text)"
static_ip="$(aws cloudformation describe-stacks --region "$region" \
  --stack-name "$stack_name" \
  --query "Stacks[0].Outputs[?OutputKey=='StaticIp'].OutputValue | [0]" \
  --output text)"

model_arn="arn:aws:bedrock:${bedrock_region}::foundation-model/amazon.titan-embed-text-v2:0"
model_policy="$(jq -cn --arg model "$model_arn" \
  '{Version:"2012-10-17",Statement:[{Effect:"Allow",Action:"bedrock:InvokeModel",Resource:$model}]}')"
aws iam put-role-policy \
  --role-name "$CONTINUUM_INSTANCE_ROLE_NAME" \
  --policy-name InvokeOneSemanticEmbeddingModel \
  --policy-document "$model_policy"
aws ec2 create-tags --region "$region" --resources "$instance_id" \
  --tags "Key=continuum:artifact-sha256,Value=$package_sha256"
aws ec2 wait instance-status-ok --region "$region" --instance-ids "$instance_id"

update_command="set -eu
stage_dir=\$(mktemp -d)
trap 'rm -rf -- \"\$stage_dir\"' EXIT
aws s3 cp 's3://$CONTINUUM_DEPLOY_BUCKET/$deployment_key' \"\$stage_dir/continuum-mcp-host.zip\" --region '$region' --only-show-errors
echo '$package_sha256  '"\$stage_dir/continuum-mcp-host.zip" | sha256sum --check --strict
rm -rf -- /opt/continuum/build
unzip -oq \"\$stage_dir/continuum-mcp-host.zip\" -d /opt/continuum
chmod 0755 /opt/continuum/scripts/bootstrap_mcp_host.sh
/opt/continuum/scripts/bootstrap_mcp_host.sh '$region' '$CONTINUUM_RUNTIME_SECRET_ARN' '$static_ip' >/var/log/continuum-bootstrap-update.log 2>&1
systemctl is-active continuum-mcp"
ssm_parameters="$(jq -cn --arg command "$update_command" '{commands:[$command]}')"
command_id="$(aws ssm send-command \
  --region "$region" \
  --instance-ids "$instance_id" \
  --document-name AWS-RunShellScript \
  --comment "Direct recovery artifact ${package_sha256:0:12}" \
  --parameters "$ssm_parameters" \
  --query 'Command.CommandId' --output text)"
command_succeeded=1
if ! aws ssm wait command-executed --region "$region" \
    --command-id "$command_id" --instance-id "$instance_id"; then
  command_succeeded=0
fi
aws ssm get-command-invocation --region "$region" \
  --command-id "$command_id" --instance-id "$instance_id" \
  --query '{Status:Status,ResponseCode:ResponseCode,Output:StandardOutputContent,Error:StandardErrorContent}' \
  --output table
if [[ "$command_succeeded" -ne 1 ]]; then
  exit 1
fi
printf 'direct_recovery=true\nartifact_sha256=%s\n' "$package_sha256"
