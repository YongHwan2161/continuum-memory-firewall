#!/usr/bin/env bash
set -euo pipefail

cluster_name="${CONTINUUM_COCKROACH_CLUSTER_NAME:-continuum-ai}"
region="${CONTINUUM_COCKROACH_REGION:-ap-southeast-1}"
spend_limit="${CONTINUUM_COCKROACH_SPEND_LIMIT:-0}"

if ! [[ "$cluster_name" =~ ^[a-z][a-z0-9-]{1,38}[a-z0-9]$ ]]; then
  printf 'CONTINUUM_COCKROACH_CLUSTER_NAME is invalid.\n' >&2
  exit 2
fi
if [[ "$region" != "ap-southeast-1" ]]; then
  printf 'This project pins CockroachDB Basic to AWS ap-southeast-1.\n' >&2
  exit 2
fi
if [[ "$spend_limit" != "0" ]]; then
  printf 'Initial CockroachDB spend limit must remain 0.\n' >&2
  exit 2
fi

printf 'Planned cluster: Basic / AWS / %s / %s / spend limit %s\n' \
  "$region" "$cluster_name" "$spend_limit"
if [[ "${1:-}" != "--apply" ]]; then
  printf 'Dry by default. Re-run with --apply after reviewing the runbook.\n'
  exit 0
fi

"$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/cockroach_preflight.sh"
help_text="$(ccloud cluster create basic --help)"
if [[ "$help_text" != *"--spend-limit"* ]]; then
  printf 'Installed ccloud no longer advertises --spend-limit; use the Cloud Console and stop before accepting paid capacity.\n' >&2
  exit 4
fi
ccloud cluster create basic \
  "$cluster_name" \
  "$region" \
  --cloud AWS \
  --spend-limit "$spend_limit"
