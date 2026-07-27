#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--apply" ]]; then
  printf 'Dry by default. Re-run with --apply after reviewing the runbook.\n'
  exit 2
fi
if [[ -z "${CONTINUUM_DATABASE_URL:-}" ]]; then
  printf 'CONTINUUM_DATABASE_URL is required.\n' >&2
  exit 2
fi

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
retain_argument=()
if [[ "${2:-}" == "--retain" ]]; then
  retain_argument=(--retain)
elif [[ -n "${2:-}" ]]; then
  printf 'Only --retain may follow --apply.\n' >&2
  exit 2
fi

PYTHONPATH="$repo_root/src" \
  python -m continuum.db_smoke "${retain_argument[@]}"
