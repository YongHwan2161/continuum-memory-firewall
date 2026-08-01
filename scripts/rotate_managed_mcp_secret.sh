#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${ROTATED_API_KEY:-}" ]]; then
  if [[ "${CONTINUUM_ROTATION_REQUIRED:-0}" == 1 ]]; then
    printf 'HOLD: CONTINUUM_ROTATED_MCP_API_KEY is unavailable.\n' >&2
    exit 2
  fi
  printf 'managed_mcp_rotation_skipped=true\n'
  exit 0
fi

umask 077
region=ap-southeast-1
secret_id=continuum/cockroach/managed-mcp-api-key
function_name=continuum-hackathon-managed-mcp-worker
old_secret=/tmp/continuum-managed-mcp-old
list_databases_response=/tmp/continuum-list-databases.json
list_tables_response=/tmp/continuum-list-tables.json
denied_response=/tmp/continuum-managed-mcp-denied.json
rotated=0

cleanup() {
  status=$?
  if [[ "$status" -ne 0 && "$rotated" -eq 1 && -s "$old_secret" ]]; then
    aws secretsmanager put-secret-value \
      --region "$region" \
      --secret-id "$secret_id" \
      --secret-string file://"$old_secret" >/dev/null
    printf 'managed_mcp_secret_rollback=true\n'
  fi
  rm -f -- "$old_secret" "$list_databases_response" \
    "$list_tables_response" "$denied_response"
  exit "$status"
}
trap cleanup EXIT

if [[ "$ROTATED_API_KEY" =~ [[:space:]] ]]; then
  printf 'rotated API key has invalid whitespace\n' >&2
  exit 2
fi
aws secretsmanager get-secret-value \
  --region "$region" \
  --secret-id "$secret_id" \
  --query SecretString --output text >"$old_secret"
test -s "$old_secret"
printf '%s' "$ROTATED_API_KEY" | aws secretsmanager put-secret-value \
  --region "$region" \
  --secret-id "$secret_id" \
  --secret-string file:///dev/stdin >/dev/null
rotated=1
unset ROTATED_API_KEY

# Warm Lambda containers cache this one secret for at most five minutes. Wait
# for that bound rather than broadening Lambda IAM to force a configuration edit.
sleep 310

aws lambda invoke \
  --region "$region" \
  --function-name "$function_name" \
  --cli-binary-format raw-in-base64-out \
  --payload '{"tool":"list_databases","arguments":{}}' \
  "$list_databases_response" >/dev/null
jq -e '.ok == true and .tool == "list_databases"' \
  "$list_databases_response" >/dev/null

aws lambda invoke \
  --region "$region" \
  --function-name "$function_name" \
  --cli-binary-format raw-in-base64-out \
  --payload '{"tool":"list_tables","arguments":{"database":"continuum"}}' \
  "$list_tables_response" >/dev/null
jq -e '.ok == true and .tool == "list_tables"' \
  "$list_tables_response" >/dev/null

aws lambda invoke \
  --region "$region" \
  --function-name "$function_name" \
  --cli-binary-format raw-in-base64-out \
  --payload '{"tool":"insert_rows","arguments":{}}' \
  "$denied_response" >/dev/null
jq -e '.ok == false and .error.code == "INVALID_REQUEST"' \
  "$denied_response" >/dev/null

rotated=0
printf 'managed_mcp_secret_rotated=true\n'
printf 'managed_mcp_tools=list_databases,list_tables\n'
printf 'managed_mcp_write_denied_pre_secret=true\n'
