#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--after-judging" || "${2:-}" != "--apply" ]]; then
  printf 'HOLD: requires both --after-judging and --apply. No resources changed.\n' >&2
  exit 2
fi

region=ap-southeast-1
stack_name=continuum-authenticated-mcp

caller_arn="$(aws sts get-caller-identity --query Arn --output text)"
if [[ "$caller_arn" != *":assumed-role/continuum-hackathon-deployer/"* ]]; then
  printf 'HOLD: teardown requires the dedicated continuum deployer role.\n' >&2
  exit 2
fi

stack_id="$(aws cloudformation describe-stacks \
  --region "$region" \
  --stack-name "$stack_name" \
  --query 'Stacks[0].StackId' --output text)"
instance_id="$(aws cloudformation describe-stacks \
  --region "$region" \
  --stack-name "$stack_name" \
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue | [0]" \
  --output text)"
static_ip="$(aws cloudformation describe-stacks \
  --region "$region" \
  --stack-name "$stack_name" \
  --query "Stacks[0].Outputs[?OutputKey=='StaticIp'].OutputValue | [0]" \
  --output text)"

[[ "$stack_id" == arn:aws:cloudformation:${region}:*:stack/${stack_name}/* ]]
[[ "$instance_id" =~ ^i-[0-9a-f]+$ ]]
[[ "$static_ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]

project_tag="$(aws ec2 describe-tags \
  --region "$region" \
  --filters "Name=resource-id,Values=$instance_id" "Name=key,Values=Project" \
  --query 'Tags[0].Value' --output text)"
environment_tag="$(aws ec2 describe-tags \
  --region "$region" \
  --filters "Name=resource-id,Values=$instance_id" "Name=key,Values=Environment" \
  --query 'Tags[0].Value' --output text)"
associated_instance="$(aws ec2 describe-addresses \
  --region "$region" --public-ips "$static_ip" \
  --query 'Addresses[0].InstanceId' --output text)"

[[ "$project_tag" == continuum-memory-firewall ]]
[[ "$environment_tag" == hackathon ]]
[[ "$associated_instance" == "$instance_id" ]]

aws cloudformation delete-stack \
  --region "$region" \
  --stack-name "$stack_name"
aws cloudformation wait stack-delete-complete \
  --region "$region" \
  --stack-name "$stack_name"

if aws ec2 describe-addresses \
  --region "$region" --public-ips "$static_ip" \
  --query 'Addresses[0].PublicIp' --output text 2>/dev/null | grep -Fqx "$static_ip"; then
  printf 'HOLD: stack deleted but the Elastic IP is still allocated.\n' >&2
  exit 1
fi

printf 'authenticated_mcp_stack_deleted=true\n'
printf 'elastic_ip_released=true\n'
