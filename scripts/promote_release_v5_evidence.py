from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from scripts.build_release_envelope import (
    RLS_MIGRATIONS,
    _migration_receipt,
    build_public_ablation_aggregate,
    repository_text_bytes,
)


SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
BASELINE_RUNTIME_SHA = "1291e2707880700492fe1d7cd431bcba03d68b4c"
BASELINE_DOCUMENTATION_SHA = "2a94b4653ab0efe6f2ddeb8701ab05bdbaf403e1"
ABLATION_PUBLIC_NAME = "agent-ablation-v3.json"
ENVELOPE_ASSET_NAME = "continuum-release-envelope-v2.json"
SANDBOX_ASSET_NAME = "sandbox-provider-proof.json"


def _load_object(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = path.read_bytes()
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise RuntimeError(f"expected a JSON object: {path}")
    return value, payload


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(repository_text_bytes(payload)).hexdigest()


def _require_sha(value: str, *, length: int, label: str) -> None:
    pattern = SHA_PATTERN if length == 40 else SHA256_PATTERN
    if pattern.fullmatch(value) is None:
        raise RuntimeError(f"{label} must be a lowercase {length}-character digest")


def _write_json(path: Path, value: dict[str, Any]) -> bytes:
    payload = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return payload


def promote_release_v5_evidence(
    *,
    repo_root: Path,
    judge_path: Path,
    ablation_report_path: Path,
    ablation_aggregate_path: Path,
    ablation_run_id: int,
    ablation_run_attempt: int,
    ablation_artifact_id: int,
    ablation_artifact_name: str,
    ablation_archive_sha256: str,
    sandbox_report_path: Path,
    sandbox_run_id: int,
    sandbox_artifact_id: int,
    sandbox_artifact_name: str,
    sandbox_archive_sha256: str,
    repository: str,
    release_tag: str,
) -> dict[str, Any]:
    judge, _ = _load_object(judge_path)
    ablation, ablation_bytes = _load_object(ablation_report_path)
    sandbox, sandbox_bytes = _load_object(sandbox_report_path)

    if ablation.get("schema_version") != 3:
        raise RuntimeError("ablation schema 3 is required")
    if len(ablation.get("observations", [])) != 540:
        raise RuntimeError("ablation must contain exactly 540 observations")
    if sandbox.get("schema_version") != 1:
        raise RuntimeError("sandbox schema 1 is required")
    if ablation_run_id < 1 or ablation_run_attempt < 1:
        raise RuntimeError("ablation workflow receipt is invalid")
    if ablation_artifact_id < 1 or sandbox_artifact_id < 1:
        raise RuntimeError("artifact receipt is invalid")

    source_head = str(ablation.get("source_head", ""))
    deployment_artifact_sha256 = str(
        ablation.get("deployment_artifact_sha256", "")
    )
    sandbox_head = str(sandbox.get("source_head", ""))
    _require_sha(source_head, length=40, label="ablation source head")
    _require_sha(
        deployment_artifact_sha256,
        length=64,
        label="deployment artifact",
    )
    _require_sha(sandbox_head, length=40, label="sandbox source head")
    _require_sha(
        ablation_archive_sha256,
        length=64,
        label="ablation archive",
    )
    _require_sha(
        sandbox_archive_sha256,
        length=64,
        label="sandbox archive",
    )

    expected_ablation_name = f"continuum-agent-ablation-{source_head}"
    expected_sandbox_name = f"aws-sandbox-provider-proof-{sandbox_head}"
    if ablation_artifact_name != expected_ablation_name:
        raise RuntimeError("ablation artifact name does not bind the source head")
    if sandbox_artifact_name != expected_sandbox_name:
        raise RuntimeError("sandbox artifact name does not bind the source head")
    if sandbox_head != BASELINE_RUNTIME_SHA:
        raise RuntimeError("sandbox receipt does not bind the baseline runtime")

    aggregate = build_public_ablation_aggregate(ablation)
    aggregate_bytes = _write_json(ablation_aggregate_path, aggregate)
    demo_base = str(judge["public_demo"]["url"]).rstrip("/")
    repo_url = f"https://github.com/{repository}"
    api_url = f"https://api.github.com/repos/{repository}"
    ablation_workflow_url = f"{repo_url}/actions/runs/{ablation_run_id}"
    sandbox_workflow_url = f"{repo_url}/actions/runs/{sandbox_run_id}"

    judge["schema_version"] = 5
    judge["generated_at"] = str(ablation["generated_at"])
    judge["claim_boundary"] = (
        "Read-only public verification of exact-head agent memory, 540 paired "
        "episodes, CockroachDB vector/RLS evidence, AWS sandbox receipts, an "
        "immutable release, and Devpost submission lineage."
    )
    judge["source"].update(
        {
            "deployment_head_sha": source_head,
            "workflow_run_id": ablation_run_id,
            "workflow_attempt": ablation_run_attempt,
            "workflow_url": ablation_workflow_url,
            "workflow_api_url": f"{api_url}/actions/runs/{ablation_run_id}",
            "artifact_sha256": deployment_artifact_sha256,
        }
    )
    judge["runtime"]["migration_version"] = int(ablation["migration_version"])
    judge["lineage"] = {
        "baseline_runtime_sha": BASELINE_RUNTIME_SHA,
        "baseline_documentation_sha": BASELINE_DOCUMENTATION_SHA,
        "candidate_runtime_sha": source_head,
    }
    judge["sandbox_provider"] = {
        "workflow_run_id": sandbox_run_id,
        "workflow_url": sandbox_workflow_url,
        "workflow_api_url": f"{api_url}/actions/runs/{sandbox_run_id}",
        "head_sha": sandbox_head,
        "artifact_id": sandbox_artifact_id,
        "artifact_name": sandbox_artifact_name,
        "artifact_archive_sha256": sandbox_archive_sha256,
        "report_sha256": _sha256(sandbox_bytes),
    }
    judge["agent_ablation"] = {
        "workflow_run_id": ablation_run_id,
        "workflow_url": ablation_workflow_url,
        "workflow_api_url": f"{api_url}/actions/runs/{ablation_run_id}",
        "head_sha": source_head,
        "artifact_id": ablation_artifact_id,
        "artifact_name": ablation_artifact_name,
        "artifact_archive_sha256": ablation_archive_sha256,
        "report_sha256": _sha256(ablation_bytes),
        "public_aggregate_sha256": _sha256(aggregate_bytes),
        "public_aggregate_url": f"{demo_base}/evidence/{ABLATION_PUBLIC_NAME}",
    }
    judge["database_policy"] = {
        "rls_combined_sha256": _migration_receipt(
            repo_root,
            RLS_MIGRATIONS,
        )["combined_sha256"]
    }
    judge["release_envelope"] = {
        "tag": release_tag,
        "release_url": f"{repo_url}/releases/tag/{release_tag}",
        "release_api_url": f"{api_url}/releases/tags/{release_tag}",
        "asset_url": (
            f"{repo_url}/releases/download/{release_tag}/{ENVELOPE_ASSET_NAME}"
        ),
        "asset_name": ENVELOPE_ASSET_NAME,
        "sandbox_asset_url": (
            f"{repo_url}/releases/download/{release_tag}/{SANDBOX_ASSET_NAME}"
        ),
        "sandbox_asset_name": SANDBOX_ASSET_NAME,
        "ablation_asset_url": (
            f"{repo_url}/releases/download/{release_tag}/{ABLATION_PUBLIC_NAME}"
        ),
        "ablation_asset_name": ABLATION_PUBLIC_NAME,
    }
    _write_json(judge_path, judge)
    return judge


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--judge-evidence", type=Path, required=True)
    parser.add_argument("--ablation-report", type=Path, required=True)
    parser.add_argument("--ablation-aggregate", type=Path, required=True)
    parser.add_argument("--ablation-run-id", type=int, required=True)
    parser.add_argument("--ablation-run-attempt", type=int, required=True)
    parser.add_argument("--ablation-artifact-id", type=int, required=True)
    parser.add_argument("--ablation-artifact-name", required=True)
    parser.add_argument("--ablation-archive-sha256", required=True)
    parser.add_argument("--sandbox-report", type=Path, required=True)
    parser.add_argument("--sandbox-run-id", type=int, required=True)
    parser.add_argument("--sandbox-artifact-id", type=int, required=True)
    parser.add_argument("--sandbox-artifact-name", required=True)
    parser.add_argument("--sandbox-archive-sha256", required=True)
    parser.add_argument(
        "--repository",
        default="YongHwan2161/continuum-memory-firewall",
    )
    parser.add_argument("--release-tag", default="hackathon-v5")
    args = parser.parse_args()
    promote_release_v5_evidence(
        repo_root=args.repo_root.resolve(),
        judge_path=args.judge_evidence,
        ablation_report_path=args.ablation_report,
        ablation_aggregate_path=args.ablation_aggregate,
        ablation_run_id=args.ablation_run_id,
        ablation_run_attempt=args.ablation_run_attempt,
        ablation_artifact_id=args.ablation_artifact_id,
        ablation_artifact_name=args.ablation_artifact_name,
        ablation_archive_sha256=args.ablation_archive_sha256,
        sandbox_report_path=args.sandbox_report,
        sandbox_run_id=args.sandbox_run_id,
        sandbox_artifact_id=args.sandbox_artifact_id,
        sandbox_artifact_name=args.sandbox_artifact_name,
        sandbox_archive_sha256=args.sandbox_archive_sha256,
        repository=args.repository,
        release_tag=args.release_tag,
    )


if __name__ == "__main__":
    main()
