#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--apply" ]]; then
  printf 'Dry by default. Re-run with --apply after reviewing the runbook.\n'
  exit 2
fi

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
"$repo_root/scripts/aws_preflight.sh"

stack_name="${CONTINUUM_AWS_STACK_NAME:-continuum-hackathon}"
deployment_key="${CONTINUUM_DEPLOYMENT_KEY:-lambda/continuum-managed-mcp-worker.zip}"
package_path="$repo_root/build/aws/continuum-managed-mcp-worker.zip"

"$repo_root/scripts/build_lambda_package.sh" "$package_path"
aws s3 cp "$package_path" \
  "s3://$CONTINUUM_DEPLOY_BUCKET/$deployment_key" \
  --only-show-errors
aws cloudformation deploy \
  --stack-name "$stack_name" \
  --template-file "$repo_root/infra/aws/template.json" \
  --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    "DeploymentBucket=$CONTINUUM_DEPLOY_BUCKET" \
    "DeploymentKey=$deployment_key" \
    "CockroachMcpSecretArn=$CONTINUUM_COCKROACH_MCP_SECRET_ARN" \
    "CockroachClusterId=$CONTINUUM_COCKROACH_CLUSTER_ID"

aws cloudformation describe-stacks \
  --stack-name "$stack_name" \
  --query 'Stacks[0].Outputs' \
  --output table
