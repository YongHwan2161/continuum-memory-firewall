#!/usr/bin/env bash
set -euo pipefail

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
output_path="${1:-$repo_root/build/aws/continuum-mcp-host.zip}"
case "$output_path" in
  /*) ;;
  *) output_path="$repo_root/$output_path" ;;
esac

stage="$(mktemp -d)"
cleanup() {
  rm -rf -- "$stage"
}
trap cleanup EXIT

mkdir -p "$stage/src" "$stage/scripts" "$stage/evals" "$(dirname -- "$output_path")"
cp "$repo_root/pyproject.toml" "$repo_root/README.md" "$stage/"
cp -R "$repo_root/src/continuum" "$stage/src/"
cp "$repo_root/scripts/load_mcp_secret.py" "$stage/scripts/"
cp "$repo_root/scripts/bootstrap_mcp_host.sh" "$stage/scripts/"
cp "$repo_root/scripts/cutover_scope_identity.py" "$stage/scripts/"
cp "$repo_root/scripts/live_semantic_eval.py" "$stage/scripts/"
cp "$repo_root/scripts/run_live_agent_ablation.py" "$stage/scripts/"
cp "$repo_root/scripts/run_live_release_guardian.py" "$stage/scripts/"
cp "$repo_root/scripts/generate_blind_holdout.py" "$stage/scripts/"
cp "$repo_root/scripts/seal_blind_holdout.py" "$stage/scripts/"
cp "$repo_root/scripts/run_live_blind_holdout.py" "$stage/scripts/"
cp "$repo_root/scripts/cleanup_blind_holdout.py" "$stage/scripts/"
cp "$repo_root/scripts/generate_sequential_blind_batch.py" "$stage/scripts/"
cp "$repo_root/scripts/seal_sequential_blind_batch.py" "$stage/scripts/"
cp "$repo_root/scripts/seal_sequential_blind_campaign.py" "$stage/scripts/"
cp "$repo_root/scripts/run_live_sequential_blind.py" "$stage/scripts/"
cp "$repo_root/scripts/run_live_outbox_faults.py" "$stage/scripts/"
cp "$repo_root/scripts/run_online_memory_lineage.py" "$stage/scripts/"
cp "$repo_root/scripts/run_outcome_replay_cas_proof.py" "$stage/scripts/"
cp "$repo_root/scripts/seed_judge_story.py" "$stage/scripts/"
cp "$repo_root/scripts/remote_oidc_smoke.py" "$stage/scripts/"
cp "$repo_root/evals/semantic-retrieval-v1.json" "$stage/evals/"
cp "$repo_root/evals/adversarial-semantic-retrieval-v2.json" "$stage/evals/"
if [[ -n "${CONTINUUM_CA_CERT_PATH:-}" ]]; then
  if [[ ! -f "$CONTINUUM_CA_CERT_PATH" ]]; then
    printf 'CONTINUUM_CA_CERT_PATH does not exist.\n' >&2
    exit 2
  fi
  cp "$CONTINUUM_CA_CERT_PATH" "$stage/cockroach-ca.crt"
fi
find "$stage" -type d -name __pycache__ -prune -exec rm -rf -- {} +
find "$stage" -type f -name '*.pyc' -delete
rm -f -- "$output_path"
python - "$stage" "$output_path" <<'PY'
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

source = Path(sys.argv[1])
output = Path(sys.argv[2])
with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
    for path in sorted(item for item in source.rglob("*") if item.is_file()):
        relative = path.relative_to(source).as_posix()
        info = ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, path.read_bytes())
PY
printf 'MCP host package: %s\n' "$output_path"
