#!/usr/bin/env bash
set -euo pipefail

command -v ccloud >/dev/null || {
  printf 'CockroachDB Cloud CLI (ccloud) is required.\n' >&2
  exit 3
}
ccloud version
ccloud auth whoami
ccloud cluster list >/dev/null
printf 'CockroachDB Cloud authentication preflight passed.\n'
