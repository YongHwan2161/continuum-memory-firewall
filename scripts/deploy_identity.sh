#!/usr/bin/env bash
set -euo pipefail

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
region="${AWS_REGION:-${AWS_DEFAULT_REGION:-ap-southeast-1}}"
required=(CONTINUUM_COGNITO_DOMAIN_PREFIX CONTINUUM_RUNTIME_SECRET_ARN)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    printf '%s is required.\n' "$name" >&2
    exit 2
  fi
done
"$repo_root/scripts/assert_deployer_identity.sh"

stack_name="${CONTINUUM_IDENTITY_STACK_NAME:-continuum-caller-identity}"
client_secret_name="${CONTINUUM_DEMO_CLIENT_SECRET_NAME:-continuum/cognito/demo-client}"
aws cloudformation deploy \
  --region "$region" \
  --stack-name "$stack_name" \
  --template-file "$repo_root/infra/aws/identity-template.json" \
  --no-fail-on-empty-changeset \
  --parameter-overrides "DomainPrefix=$CONTINUUM_COGNITO_DOMAIN_PREFIX"

output() {
  aws cloudformation describe-stacks --region "$region" --stack-name "$stack_name" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue | [0]" --output text
}
pool_id="$(output UserPoolId)"
client_id="$(output ClientId)"
issuer="$(output Issuer)"
token_endpoint="$(output TokenEndpoint)"
required_scope="$(output RequiredScope)"
client_secret="$(aws cognito-idp describe-user-pool-client \
  --region "$region" --user-pool-id "$pool_id" --client-id "$client_id" \
  --query 'UserPoolClient.ClientSecret' --output text)"

secret_payload="$(CLIENT_ID="$client_id" CLIENT_SECRET="$client_secret" \
  TOKEN_ENDPOINT="$token_endpoint" REQUIRED_SCOPE="$required_scope" python -c \
  'import json,os; print(json.dumps({"client_id":os.environ["CLIENT_ID"],"client_secret":os.environ["CLIENT_SECRET"],"token_endpoint":os.environ["TOKEN_ENDPOINT"],"scope":os.environ["REQUIRED_SCOPE"]},separators=(",",":")))')"
if aws secretsmanager describe-secret --region "$region" \
    --secret-id "$client_secret_name" >/dev/null 2>&1; then
  printf '%s' "$secret_payload" | aws secretsmanager put-secret-value \
    --region "$region" --secret-id "$client_secret_name" \
    --secret-string file:///dev/stdin >/dev/null
else
  printf '%s' "$secret_payload" | aws secretsmanager create-secret \
    --region "$region" --name "$client_secret_name" \
    --description 'Cognito M2M client for the Continuum hackathon smoke' \
    --tags Key=Project,Value=continuum-memory-firewall \
    --secret-string file:///dev/stdin >/dev/null
fi
unset client_secret secret_payload

aws secretsmanager get-secret-value \
  --region "$region" --secret-id "$CONTINUUM_RUNTIME_SECRET_ARN" \
  --query SecretString --output text |
  python "$repo_root/scripts/upgrade_runtime_secret.py" \
    --client-id "$client_id" \
    --issuer "$issuer" \
    --required-scope "$required_scope" \
    --region "$region" |
  aws secretsmanager put-secret-value \
    --region "$region" --secret-id "$CONTINUUM_RUNTIME_SECRET_ARN" \
    --secret-string file:///dev/stdin >/dev/null

printf 'identity_stack=%s\n' "$stack_name"
printf 'access_token_minutes=5\n'
printf 'runtime_secret_upgraded=true\n'
printf 'demo_client_secret_stored=true\n'
