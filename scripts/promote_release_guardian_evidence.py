"""Promote a real-provider guardian receipt into the public judge contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from continuum.release_guardian import build_public_release_guardian
try:
    from scripts.build_release_envelope import repository_text_bytes
except ModuleNotFoundError:  # direct `python scripts/...py` execution
    from build_release_envelope import repository_text_bytes


SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REPORT_ASSET_NAME = "release-guardian-v1.json"
PUBLIC_NAME = "release-guardian-v1.json"


def _load(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = path.read_bytes()
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise RuntimeError(f"expected a JSON object: {path}")
    return value, payload


def _digest(payload: bytes) -> str:
    return hashlib.sha256(repository_text_bytes(payload)).hexdigest()


def _write(path: Path, value: dict[str, Any]) -> bytes:
    payload = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return payload


def promote_release_guardian_evidence(
    *,
    judge_path: Path,
    report_path: Path,
    public_path: Path,
    workflow_run_id: int,
    workflow_attempt: int,
    artifact_id: int,
    artifact_name: str,
    artifact_archive_sha256: str,
    repository: str,
    release_tag: str,
) -> dict[str, Any]:
    judge, _ = _load(judge_path)
    report, report_bytes = _load(report_path)
    if int(judge.get("schema_version", 0)) < 7:
        raise RuntimeError("judge schema 7 or later is required")
    if report.get("schema_version") != 1:
        raise RuntimeError("release guardian schema 1 is required")
    if report.get("gate", {}).get("status") != "PASS":
        raise RuntimeError("release guardian gate is not PASS")
    if report.get("real_external_provider") is not True:
        raise RuntimeError("release guardian provider must be real")
    source_head = str(report.get("source_head", ""))
    if SHA_PATTERN.fullmatch(source_head) is None:
        raise RuntimeError("release guardian source head is invalid")
    if workflow_run_id < 1 or workflow_attempt < 1 or artifact_id < 1:
        raise RuntimeError("release guardian workflow receipt is invalid")
    expected_name = f"continuum-release-guardian-{source_head}"
    if artifact_name != expected_name:
        raise RuntimeError("release guardian artifact name does not bind source")
    if SHA256_PATTERN.fullmatch(artifact_archive_sha256) is None:
        raise RuntimeError("release guardian archive digest is invalid")

    public = build_public_release_guardian(report)
    public_bytes = _write(public_path, public)
    demo_base = str(judge["public_demo"]["url"]).rstrip("/")
    repo_url = f"https://github.com/{repository}"
    api_url = f"https://api.github.com/repos/{repository}"
    workflow_url = f"{repo_url}/actions/runs/{workflow_run_id}"
    report_sha = _digest(report_bytes)
    public_sha = _digest(public_bytes)

    judge["schema_version"] = 8
    judge["generated_at"] = str(report["generated_at"])
    judge["claim_boundary"] = (
        "Read-only verification of live identity-bound memory, real GitHub "
        "draft-release effects across 36 paired incidents, CockroachDB vector/RLS "
        "evidence, AWS receipts, an immutable release, and Devpost lineage."
    )
    judge["release_guardian"] = {
        "schema_version": 1,
        "workflow_run_id": workflow_run_id,
        "workflow_attempt": workflow_attempt,
        "workflow_url": workflow_url,
        "workflow_api_url": f"{api_url}/actions/runs/{workflow_run_id}",
        "head_sha": source_head,
        "artifact_id": artifact_id,
        "artifact_name": artifact_name,
        "artifact_api_url": f"{api_url}/actions/artifacts/{artifact_id}",
        "artifact_archive_sha256": artifact_archive_sha256,
        "report_sha256": report_sha,
        "public_sha256": public_sha,
        "public_url": f"{demo_base}/evidence/{PUBLIC_NAME}",
        "page_url": f"{demo_base}/release-guardian.html",
        "provider": report["provider"],
        "real_external_provider": True,
        "paired_cases": int(report["methodology"]["paired_cases"]),
        "arm_observations": int(report["methodology"]["arm_observations"]),
    }
    release = judge["release_envelope"]
    release.update(
        {
            "tag": release_tag,
            "release_url": f"{repo_url}/releases/tag/{release_tag}",
            "release_api_url": f"{api_url}/releases/tags/{release_tag}",
            "asset_url": (
                f"{repo_url}/releases/download/{release_tag}/"
                "continuum-release-envelope-v2.json"
            ),
            "sandbox_asset_url": (
                f"{repo_url}/releases/download/{release_tag}/"
                "sandbox-provider-proof.json"
            ),
            "ablation_asset_url": (
                f"{repo_url}/releases/download/{release_tag}/"
                "agent-ablation-v3.json"
            ),
            "drilldown_asset_url": (
                f"{repo_url}/releases/download/{release_tag}/"
                "episode-drilldown-v1.json"
            ),
            "guardian_asset_url": (
                f"{repo_url}/releases/download/{release_tag}/"
                f"{REPORT_ASSET_NAME}"
            ),
            "guardian_asset_name": REPORT_ASSET_NAME,
        }
    )
    _write(judge_path, judge)
    return judge


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge-evidence", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--public-output", type=Path, required=True)
    parser.add_argument("--workflow-run-id", type=int, required=True)
    parser.add_argument("--workflow-attempt", type=int, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--artifact-archive-sha256", required=True)
    parser.add_argument(
        "--repository",
        default="YongHwan2161/continuum-memory-firewall",
    )
    parser.add_argument("--release-tag", default="hackathon-v11")
    args = parser.parse_args()
    promote_release_guardian_evidence(
        judge_path=args.judge_evidence,
        report_path=args.report,
        public_path=args.public_output,
        workflow_run_id=args.workflow_run_id,
        workflow_attempt=args.workflow_attempt,
        artifact_id=args.artifact_id,
        artifact_name=args.artifact_name,
        artifact_archive_sha256=args.artifact_archive_sha256,
        repository=args.repository,
        release_tag=args.release_tag,
    )


if __name__ == "__main__":
    main()
