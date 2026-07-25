#!/usr/bin/env bash
set -euo pipefail

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
required=(
  AWS_REGION
  CONTINUUM_DEPLOY_BUCKET
  CONTINUUM_COCKROACH_CLUSTER_ID
  CONTINUUM_COCKROACH_MCP_SECRET_ARN
  CONTINUUM_BUDGET_EMAIL
  CONTINUUM_MONTHLY_BUDGET_USD
  CONTINUUM_AWS_BUDGET_NAME
)

for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    printf 'Missing required variable: %s\n' "$name" >&2
    exit 2
  fi
done
if ! [[ "$CONTINUUM_MONTHLY_BUDGET_USD" =~ ^([1-9]|[12][0-9]|30)$ ]]; then
  printf 'CONTINUUM_MONTHLY_BUDGET_USD must be an integer from 1 to 30.\n' >&2
  exit 2
fi
if ! [[ "$CONTINUUM_BUDGET_EMAIL" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]]; then
  printf 'CONTINUUM_BUDGET_EMAIL is not a valid email address.\n' >&2
  exit 2
fi
command -v aws >/dev/null || {
  printf 'AWS CLI v2 is required.\n' >&2
  exit 3
}

account_id="$(aws sts get-caller-identity --query Account --output text)"
aws s3api head-bucket --bucket "$CONTINUUM_DEPLOY_BUCKET"
aws secretsmanager describe-secret \
  --secret-id "$CONTINUUM_COCKROACH_MCP_SECRET_ARN" \
  --query ARN \
  --output text >/dev/null
aws budgets describe-budget \
  --account-id "$account_id" \
  --budget-name "$CONTINUUM_AWS_BUDGET_NAME" >/dev/null
aws cloudformation validate-template \
  --template-body "file://$repo_root/infra/aws/template.json" >/dev/null

printf 'AWS preflight passed for account %s in %s.\n' \
  "$account_id" "$AWS_REGION"
