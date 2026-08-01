#!/usr/bin/env bash
set -euo pipefail

caller_arn="$(aws sts get-caller-identity --query Arn --output text)"
case "$caller_arn" in
  arn:aws:sts::*:assumed-role/continuum-hackathon-deployer/*) ;;
  *)
    printf 'Deployment requires an assumed continuum-hackathon-deployer session.\n' >&2
    exit 4
    ;;
esac
