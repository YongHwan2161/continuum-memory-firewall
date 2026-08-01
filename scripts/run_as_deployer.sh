#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  printf 'usage: run_as_deployer.sh COMMAND [ARG ...]\n' >&2
  exit 2
fi
region="${AWS_REGION:-${AWS_DEFAULT_REGION:-ap-southeast-1}}"
account_id="$(aws sts get-caller-identity --query Account --output text)"
role_arn="arn:aws:iam::${account_id}:role/continuum-hackathon-deployer"
read -r AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN <<EOF
$(aws sts assume-role \
  --region "$region" \
  --role-arn "$role_arn" \
  --role-session-name continuum-release \
  --duration-seconds 3600 \
  --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' \
  --output text)
EOF
export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
export AWS_REGION="$region" AWS_DEFAULT_REGION="$region"
exec "$@"
