#!/usr/bin/env bash
set -euo pipefail

required=(
  CONTINUUM_RUNTIME_SECRET_ARN
  CONTINUUM_DEPLOY_BUCKET
  CONTINUUM_CA_CERT_PATH
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
agent_bedrock_region="${CONTINUUM_AGENT_BEDROCK_REGION:-ap-southeast-2}"
stack_name="${CONTINUUM_MCP_STACK_NAME:-continuum-authenticated-mcp}"
deployment_key="${CONTINUUM_MCP_DEPLOYMENT_KEY:-mcp-host/continuum-mcp-host.zip}"
package_path="$repo_root/build/aws/continuum-mcp-host.zip"

"$repo_root/scripts/build_mcp_host_package.sh" "$package_path"
aws s3 cp "$package_path" "s3://$CONTINUUM_DEPLOY_BUCKET/$deployment_key" \
  --region "$region" --only-show-errors
package_sha256="$(sha256sum "$package_path" | awk '{print $1}')"

vpc_id="$(aws ec2 describe-vpcs --region "$region" \
  --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text)"
subnet_id="$(aws ec2 describe-subnets --region "$region" \
  --filters Name=vpc-id,Values="$vpc_id" Name=default-for-az,Values=true \
  --query 'sort_by(Subnets,&AvailabilityZone)[0].SubnetId' --output text)"
ami_id="$(MSYS_NO_PATHCONV=1 aws ssm get-parameter --region "$region" \
  --name /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id \
  --query 'Parameter.Value' --output text)"

if ! aws cloudformation deploy \
  --region "$region" \
  --stack-name "$stack_name" \
  --template-file "$repo_root/infra/aws/mcp-host-template.json" \
  --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    "VpcId=$vpc_id" \
    "SubnetId=$subnet_id" \
    "AmiId=$ami_id" \
    "PackageBucket=$CONTINUUM_DEPLOY_BUCKET" \
    "PackageKey=$deployment_key" \
    "ArtifactSha256=$package_sha256" \
    "BedrockRegion=$bedrock_region" \
    "AgentBedrockRegion=$agent_bedrock_region" \
    "RuntimeSecretArn=$CONTINUUM_RUNTIME_SECRET_ARN"; then
  # Emit bounded metadata only. Do not request template properties, parameters,
  # or secret values when a live stack update fails.
  aws cloudformation describe-stack-events \
    --region "$region" \
    --stack-name "$stack_name" \
    --query 'StackEvents[:12].{Time:Timestamp,LogicalId:LogicalResourceId,Type:ResourceType,Status:ResourceStatus,Reason:ResourceStatusReason}' \
    --output table || true
  exit 1
fi

instance_id="$(aws cloudformation describe-stacks --region "$region" \
  --stack-name "$stack_name" \
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue | [0]" \
  --output text)"
static_ip="$(aws cloudformation describe-stacks --region "$region" \
  --stack-name "$stack_name" \
  --query "Stacks[0].Outputs[?OutputKey=='StaticIp'].OutputValue | [0]" \
  --output text)"

aws ec2 wait instance-status-ok --region "$region" --instance-ids "$instance_id"

update_command="set -eu
stage_dir=\$(mktemp -d)
trap 'rm -rf -- \"\$stage_dir\"' EXIT
aws s3 cp 's3://$CONTINUUM_DEPLOY_BUCKET/$deployment_key' \"\$stage_dir/continuum-mcp-host.zip\" --region '$region' --only-show-errors
echo '$package_sha256  '\"\$stage_dir/continuum-mcp-host.zip\" | sha256sum --check --strict
rm -rf -- /opt/continuum/build
unzip -oq \"\$stage_dir/continuum-mcp-host.zip\" -d /opt/continuum
chmod 0755 /opt/continuum/scripts/bootstrap_mcp_host.sh
/opt/continuum/scripts/bootstrap_mcp_host.sh '$region' '$CONTINUUM_RUNTIME_SECRET_ARN' '$static_ip' >/var/log/continuum-bootstrap-update.log 2>&1
systemctl is-active continuum-mcp"
ssm_parameters="$(UPDATE_COMMAND="$update_command" python -c \
  'import json, os; print(json.dumps({"commands": [os.environ["UPDATE_COMMAND"]]}))')"
command_id="$(aws ssm send-command \
  --region "$region" \
  --instance-ids "$instance_id" \
  --document-name AWS-RunShellScript \
  --comment "Deploy MCP artifact ${package_sha256:0:12}" \
  --parameters "$ssm_parameters" \
  --query 'Command.CommandId' \
  --output text)"
command_succeeded=1
if ! aws ssm wait command-executed \
    --region "$region" \
    --command-id "$command_id" \
    --instance-id "$instance_id"; then
  command_succeeded=0
fi
aws ssm get-command-invocation \
  --region "$region" \
  --command-id "$command_id" \
  --instance-id "$instance_id" \
  --query '{Status:Status,ResponseCode:ResponseCode,Output:StandardOutputContent,Error:StandardErrorContent}' \
  --output table
if [[ "$command_succeeded" -ne 1 ]]; then
  exit 1
fi

aws cloudformation describe-stacks --region "$region" --stack-name "$stack_name" \
  --query 'Stacks[0].Outputs' --output table
