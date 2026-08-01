#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--apply" ]]; then
  printf 'Dry by default. Re-run with --apply for the one-time root bootstrap.\n' >&2
  exit 2
fi
repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
region="${AWS_REGION:-${AWS_DEFAULT_REGION:-ap-southeast-1}}"
caller_arn="$(aws sts get-caller-identity --query Arn --output text)"
case "$caller_arn" in
  arn:aws:iam::*:root) ;;
  *)
    printf 'The bootstrap must be the only root CLI operation; current caller is not root.\n' >&2
    exit 4
    ;;
esac

aws cloudformation validate-template \
  --region "$region" \
  --template-body "file://$repo_root/infra/aws/deployer-role-template.json" >/dev/null
aws cloudformation deploy \
  --region "$region" \
  --stack-name continuum-deployer-bootstrap \
  --template-file "$repo_root/infra/aws/deployer-role-template.json" \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset
aws cloudformation describe-stacks \
  --region "$region" \
  --stack-name continuum-deployer-bootstrap \
  --query "Stacks[0].Outputs[?OutputKey=='RoleArn'].OutputValue | [0]" \
  --output text
