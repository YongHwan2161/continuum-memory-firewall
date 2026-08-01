#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--apply" || $# -lt 2 ]]; then
  printf 'usage: with_ephemeral_deployer.sh --apply COMMAND [ARG ...]\n' >&2
  exit 2
fi
shift
repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
caller_arn="$(aws sts get-caller-identity --query Arn --output text)"
case "$caller_arn" in
  arn:aws:iam::*:root) ;;
  *)
    printf 'The ephemeral bridge may only be created by the root bootstrap session.\n' >&2
    exit 4
    ;;
esac

broker_user="continuum-deployer-session-broker"
broker_policy="AssumeContinuumDeployerOnly"
account_id="$(aws sts get-caller-identity --query Account --output text)"
role_arn="arn:aws:iam::${account_id}:role/continuum-hackathon-deployer"
key_file="$(mktemp)"
chmod 0600 "$key_file"
access_key_id=""

cleanup() {
  status=$?
  trap - EXIT INT TERM
  set +e
  if [[ -n "$access_key_id" ]]; then
    aws iam delete-access-key \
      --user-name "$broker_user" \
      --access-key-id "$access_key_id" >/dev/null 2>&1
  fi
  aws iam delete-user-policy \
    --user-name "$broker_user" \
    --policy-name "$broker_policy" >/dev/null 2>&1
  aws iam delete-user --user-name "$broker_user" >/dev/null 2>&1
  rm -f -- "$key_file"
  exit "$status"
}
trap cleanup EXIT INT TERM

if aws iam get-user --user-name "$broker_user" >/dev/null 2>&1; then
  printf 'Ephemeral broker already exists; refusing to reuse or replace it.\n' >&2
  exit 6
fi
aws iam create-user \
  --user-name "$broker_user" \
  --tags Key=Project,Value=continuum-memory-firewall Key=Lifecycle,Value=ephemeral >/dev/null
policy_document="$(printf '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"sts:AssumeRole","Resource":"%s"}]}' "$role_arn")"
aws iam put-user-policy \
  --user-name "$broker_user" \
  --policy-name "$broker_policy" \
  --policy-document "$policy_document"
aws iam create-access-key \
  --user-name "$broker_user" \
  --query 'AccessKey.[AccessKeyId,SecretAccessKey]' \
  --output text >"$key_file"
read -r access_key_id secret_access_key <"$key_file"
if [[ -z "$access_key_id" || -z "$secret_access_key" ]]; then
  printf 'Ephemeral key creation returned incomplete credentials.\n' >&2
  exit 7
fi

env -u AWS_PROFILE \
  AWS_ACCESS_KEY_ID="$access_key_id" \
  AWS_SECRET_ACCESS_KEY="$secret_access_key" \
  AWS_SESSION_TOKEN="" \
  bash "$repo_root/scripts/run_as_deployer.sh" "$@"
