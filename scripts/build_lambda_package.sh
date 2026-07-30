#!/usr/bin/env bash
set -euo pipefail

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
output_path="${1:-$repo_root/build/aws/continuum-managed-mcp-worker.zip}"
case "$output_path" in
  /*) ;;
  *) output_path="$repo_root/$output_path" ;;
esac

build_root="$(mktemp -d)"
package_root="$build_root/package"
cleanup() {
  rm -rf -- "$build_root"
}
trap cleanup EXIT

mkdir -p "$package_root" "$(dirname -- "$output_path")"
uv_bin="${UV_BIN:-uv}"
python_bin="${PYTHON_BIN:-python}"
if command -v "$uv_bin" >/dev/null 2>&1; then
  "$uv_bin" pip install \
    --python-platform x86_64-manylinux2014 \
    --python-version 3.12 \
    --only-binary=:all: \
    --requirement "$repo_root/infra/aws/requirements-lambda.txt" \
    --target "$package_root"
else
  "$python_bin" -m pip install \
    --disable-pip-version-check \
    --platform manylinux2014_x86_64 \
    --implementation cp \
    --python-version 3.12 \
    --only-binary=:all: \
    --requirement "$repo_root/infra/aws/requirements-lambda.txt" \
    --target "$package_root"
fi
rm -f -- "$package_root/.lock"
cp -R "$repo_root/src/continuum" "$package_root/"
find "$package_root" -type d -name __pycache__ -prune -exec rm -rf -- {} +
find "$package_root" -type f -name '*.pyc' -delete

(
  cd "$package_root"
  "$python_bin" -m zipfile -c "$output_path" .
)
printf 'Lambda package: %s\n' "$output_path"
