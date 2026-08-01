#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  printf 'usage: run_as_deployer.sh COMMAND [ARG ...]\n' >&2
  exit 2
fi
region="${AWS_REGION:-${AWS_DEFAULT_REGION:-ap-southeast-1}}"
source_arn="$(aws sts get-caller-identity --query Arn --output text)"
case "$source_arn" in
  arn:aws:iam::*:root)
    printf 'AWS root cannot assume roles. Use with_ephemeral_deployer.sh for the one-time bridge.\n' >&2
    exit 4
    ;;
esac
account_id="$(aws sts get-caller-identity --query Account --output text)"
role_arn="arn:aws:iam::${account_id}:role/continuum-hackathon-deployer"
credentials="$(aws sts assume-role \
  --region "$region" \
  --role-arn "$role_arn" \
  --role-session-name continuum-release \
  --duration-seconds 3600 \
  --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' \
  --output text)"
read -r AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN <<EOF
$credentials
EOF
if [[ -z "$AWS_ACCESS_KEY_ID" || -z "$AWS_SECRET_ACCESS_KEY" || -z "$AWS_SESSION_TOKEN" ]]; then
  printf 'AssumeRole returned incomplete credentials; refusing to run the command.\n' >&2
  exit 5
fi
export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
export AWS_REGION="$region" AWS_DEFAULT_REGION="$region"
exec "$@"
