"""Promote a verified five-batch guardian aggregate to the public judge bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from continuum.release_guardian_replication import (
    build_public_release_guardian_replication,
)


def _load(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = path.read_bytes().replace(b"\r\n", b"\n")
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise RuntimeError(f"expected a JSON object: {path}")
    return value, payload


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def promote(
    *,
    full_report_path: Path,
    public_report_path: Path,
    judge_evidence_path: Path,
    public_destination: Path,
    workflow_run_id: int,
    workflow_run_attempt: int,
    artifact_id: int,
    artifact_name: str,
    artifact_archive_sha256: str,
    release_tag: str,
) -> dict[str, Any]:
    full, full_payload = _load(full_report_path)
    public, _ = _load(public_report_path)
    expected_public = build_public_release_guardian_replication(full)
    if public != expected_public:
        raise RuntimeError("public aggregate is not the exact redacted full report")
    aggregation = full.get("aggregation_workflow", {})
    if aggregation.get("workflow_run_id") != workflow_run_id:
        raise RuntimeError("aggregation workflow run does not match report")
    if aggregation.get("workflow_run_attempt") != workflow_run_attempt:
        raise RuntimeError("aggregation workflow attempt does not match report")
    if len(artifact_archive_sha256) != 64 or any(
        character not in "0123456789abcdef"
        for character in artifact_archive_sha256
    ):
        raise RuntimeError("artifact archive digest must be lowercase SHA-256")

    _write(public_destination, public)
    public_payload = public_destination.read_bytes().replace(b"\r\n", b"\n")
    judge, _ = _load(judge_evidence_path)
    repository = str(judge.get("source", {}).get("repository", ""))
    if not repository:
        raise RuntimeError("judge evidence repository is missing")
    if not release_tag or any(character.isspace() for character in release_tag):
        raise RuntimeError("release tag is invalid")
    judge["time_distributed_replication"] = {
        "schema_version": 1,
        "head_sha": full["source_head"],
        "case_population_sha256": full["case_population_sha256"],
        "workflow_run_id": workflow_run_id,
        "workflow_run_attempt": workflow_run_attempt,
        "workflow_url": (
            f"https://github.com/{repository}/actions/runs/{workflow_run_id}"
        ),
        "workflow_api_url": (
            f"https://api.github.com/repos/{repository}/actions/runs/"
            f"{workflow_run_id}"
        ),
        "artifact_id": artifact_id,
        "artifact_name": artifact_name,
        "artifact_archive_sha256": artifact_archive_sha256,
        "artifact_api_url": (
            f"https://api.github.com/repos/{repository}/actions/artifacts/"
            f"{artifact_id}"
        ),
        "public_url": (
            "https://yonghwan2161.github.io/continuum-memory-firewall/"
            "evidence/release-guardian-replication-v1.json"
        ),
        "public_sha256": hashlib.sha256(public_payload).hexdigest(),
        "report_sha256": hashlib.sha256(full_payload).hexdigest(),
        "page_url": (
            "https://yonghwan2161.github.io/continuum-memory-firewall/"
            "release-guardian-replication.html"
        ),
        "paired_cases": full["methodology"]["paired_cases"],
        "arm_observations": full["methodology"]["arm_observations"],
        "replication_count": full["replication_set"]["replication_count"],
        "minimum_start_separation_seconds": full["replication_set"][
            "minimum_observed_start_separation_seconds"
        ],
    }
    release = judge["release_envelope"]
    release.update(
        {
            "tag": release_tag,
            "release_url": (
                f"https://github.com/{repository}/releases/tag/{release_tag}"
            ),
            "release_api_url": (
                f"https://api.github.com/repos/{repository}/releases/tags/"
                f"{release_tag}"
            ),
            "asset_url": (
                f"https://github.com/{repository}/releases/download/"
                f"{release_tag}/continuum-release-envelope-v2.json"
            ),
            "sandbox_asset_url": (
                f"https://github.com/{repository}/releases/download/"
                f"{release_tag}/sandbox-provider-proof.json"
            ),
            "ablation_asset_url": (
                f"https://github.com/{repository}/releases/download/"
                f"{release_tag}/agent-ablation-v3.json"
            ),
            "drilldown_asset_url": (
                f"https://github.com/{repository}/releases/download/"
                f"{release_tag}/episode-drilldown-v1.json"
            ),
            "guardian_asset_url": (
                f"https://github.com/{repository}/releases/download/"
                f"{release_tag}/release-guardian-v1.json"
            ),
            "replication_asset_name": "release-guardian-replication-v1.json",
            "replication_asset_url": (
                f"https://github.com/{repository}/releases/download/"
                f"{release_tag}/release-guardian-replication-v1.json"
            ),
        }
    )
    _write(judge_evidence_path, judge)
    return judge["time_distributed_replication"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-report", type=Path, required=True)
    parser.add_argument("--public-report", type=Path, required=True)
    parser.add_argument("--judge-evidence", type=Path, required=True)
    parser.add_argument("--public-destination", type=Path, required=True)
    parser.add_argument("--workflow-run-id", type=int, required=True)
    parser.add_argument("--workflow-run-attempt", type=int, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--artifact-archive-sha256", required=True)
    parser.add_argument("--release-tag", default="hackathon-v12")
    args = parser.parse_args()
    reference = promote(
        full_report_path=args.full_report,
        public_report_path=args.public_report,
        judge_evidence_path=args.judge_evidence,
        public_destination=args.public_destination,
        workflow_run_id=args.workflow_run_id,
        workflow_run_attempt=args.workflow_run_attempt,
        artifact_id=args.artifact_id,
        artifact_name=args.artifact_name,
        artifact_archive_sha256=args.artifact_archive_sha256,
        release_tag=args.release_tag,
    )
    print(json.dumps(reference, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
