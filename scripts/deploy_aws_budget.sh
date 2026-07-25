#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--apply" ]]; then
  printf 'Dry by default. Re-run with --apply before creating project resources.\n'
  exit 2
fi

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
required=(
  AWS_REGION
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
if ! [[ "$CONTINUUM_AWS_BUDGET_NAME" =~ ^[A-Za-z0-9_-]{1,100}$ ]]; then
  printf 'CONTINUUM_AWS_BUDGET_NAME is invalid.\n' >&2
  exit 2
fi
command -v aws >/dev/null || {
  printf 'AWS CLI v2 is required.\n' >&2
  exit 3
}

aws sts get-caller-identity >/dev/null
aws cloudformation validate-template \
  --template-body "file://$repo_root/infra/aws/budget-template.json" >/dev/null
aws cloudformation deploy \
  --stack-name continuum-hackathon-budget \
  --template-file "$repo_root/infra/aws/budget-template.json" \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    "BudgetName=$CONTINUUM_AWS_BUDGET_NAME" \
    "BudgetEmail=$CONTINUUM_BUDGET_EMAIL" \
    "MonthlyBudgetUsd=$CONTINUUM_MONTHLY_BUDGET_USD"

account_id="$(aws sts get-caller-identity --query Account --output text)"
aws budgets describe-budget \
  --account-id "$account_id" \
  --budget-name "$CONTINUUM_AWS_BUDGET_NAME" \
  --query 'Budget.{Name:BudgetName,Limit:BudgetLimit}' \
  --output table
