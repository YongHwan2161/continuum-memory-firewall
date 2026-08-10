"""Promote one exact CI-recovery artifact into public judge evidence.

The workflow artifact remains the authority.  This command refuses to publish
unless its public file is the deterministic projection of the private report
and all supplied GitHub receipt fields match that report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from continuum.ci_recovery import build_public_ci_recovery


SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _repository_bytes(value: bytes) -> bytes:
    return value.replace(b"\r\n", b"\n")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(_repository_bytes(value)).hexdigest()


def build_reference(
    raw: dict[str, Any],
    public: dict[str, Any],
    *,
    public_bytes: bytes,
    artifact_id: int,
    artifact_name: str,
    artifact_archive_sha256: str,
    page_url: str,
    public_url: str,
) -> dict[str, Any]:
    head = str(raw.get("source_head", ""))
    run_id = int(raw.get("workflow_run_id", 0))
    attempt = int(raw.get("workflow_run_attempt", 0))
    repository = str(raw.get("repository", ""))
    if SHA_PATTERN.fullmatch(head) is None:
        raise RuntimeError("CI recovery source head is invalid")
    if run_id < 1 or attempt < 1 or artifact_id < 1:
        raise RuntimeError("CI recovery workflow lineage is invalid")
    expected_artifact = f"continuum-ci-recovery-{head}-{run_id}-{attempt}"
    if artifact_name != expected_artifact:
        raise RuntimeError("CI recovery artifact name is not exact-head bound")
    if SHA256_PATTERN.fullmatch(artifact_archive_sha256) is None:
        raise RuntimeError("CI recovery archive digest is invalid")
    if public != build_public_ci_recovery(raw):
        raise RuntimeError("public CI recovery file is not the raw-report projection")
    if raw.get("gate", {}).get("status") != "PASS":
        raise RuntimeError("CI recovery benchmark gate did not pass")
    if raw.get("real_external_provider") is not True:
        raise RuntimeError("CI recovery benchmark is not a real provider run")
    if raw.get("provider") != "github-actions":
        raise RuntimeError("CI recovery provider is not GitHub Actions")
    if raw.get("methodology", {}).get("total_child_workflow_runs") != 54:
        raise RuntimeError("CI recovery child-workflow cardinality is invalid")
    continuum = raw.get("arms", {}).get("continuum", {})
    stateless = raw.get("arms", {}).get("stateless", {})
    raw_rag = raw.get("arms", {}).get("raw_rag", {})
    if not (
        continuum.get("verified_recoveries") == 12
        and continuum.get("false_canonical_promotions") == 0
        and continuum.get("canonical_promotion_precision") == 1.0
        and stateless.get("verified_recoveries") == 12
        and raw_rag.get("verified_recoveries") == 11
        and raw_rag.get("false_canonical_promotions") == 1
    ):
        raise RuntimeError("CI recovery result does not match the bounded live claim")
    challenge_sha = str(raw.get("challenge", {}).get("challenge_sha256", ""))
    if SHA256_PATTERN.fullmatch(challenge_sha) is None:
        raise RuntimeError("CI recovery challenge digest is invalid")
    return {
        "schema_version": 1,
        "head_sha": head,
        "workflow_run_id": run_id,
        "workflow_attempt": attempt,
        "workflow_url": raw["workflow_url"],
        "workflow_api_url": (
            f"https://api.github.com/repos/{repository}/actions/runs/{run_id}"
        ),
        "artifact_id": artifact_id,
        "artifact_name": artifact_name,
        "artifact_api_url": (
            f"https://api.github.com/repos/{repository}/actions/artifacts/"
            f"{artifact_id}"
        ),
        "artifact_archive_sha256": artifact_archive_sha256,
        "public_sha256": _sha256(public_bytes),
        "public_url": public_url,
        "page_url": page_url,
        "campaign_id": raw["campaign_id"],
        "challenge_sha256": challenge_sha,
        "population_sha256": raw["population_sha256"],
        "agent_model": raw["agent_model"],
        "provider": raw["provider"],
        "fault_families": raw["methodology"]["fault_families"],
        "cases_per_arm": raw["methodology"]["cases_per_arm"],
        "child_workflow_runs": raw["methodology"]["total_child_workflow_runs"],
    }


def promote(
    *,
    raw_path: Path,
    public_path: Path,
    judge_path: Path,
    output_path: Path,
    artifact_id: int,
    artifact_name: str,
    artifact_archive_sha256: str,
    page_url: str,
    public_url: str,
    release_tag: str | None = None,
) -> dict[str, Any]:
    raw = json.loads(raw_path.read_bytes())
    public_bytes = _repository_bytes(public_path.read_bytes())
    public = json.loads(public_bytes)
    judge = json.loads(judge_path.read_bytes())
    reference = build_reference(
        raw,
        public,
        public_bytes=public_bytes,
        artifact_id=artifact_id,
        artifact_name=artifact_name,
        artifact_archive_sha256=artifact_archive_sha256,
        page_url=page_url,
        public_url=public_url,
    )
    judge["schema_version"] = 11
    judge["generated_at"] = raw["generated_at"]
    judge["claim_boundary"] = (
        "Read-only verification of live identity-bound memory, real GitHub "
        "Actions closed-loop red-to-green recovery over twelve source-defined "
        "synthetic fixtures, a label-hidden three-batch sequential GitHub and "
        "S3 campaign, prior CockroachDB vector/RLS evidence, AWS receipts, an "
        "immutable release, and Devpost lineage. The CI benchmark proves "
        "receipt-bound recovery and failed-memory isolation, not arbitrary-code "
        "repair or superiority over a stateless arm."
    )
    judge["ci_recovery"] = reference
    if release_tag is not None:
        if not release_tag or any(character.isspace() for character in release_tag):
            raise RuntimeError("release tag is invalid")
        repository = raw["repository"]
        release = judge["release_envelope"]
        release["tag"] = release_tag
        release["release_url"] = (
            f"https://github.com/{repository}/releases/tag/{release_tag}"
        )
        release["release_api_url"] = (
            f"https://api.github.com/repos/{repository}/releases/tags/{release_tag}"
        )
        release["ci_recovery_asset_name"] = "ci-recovery-v1.json"
        asset_name_fields = {
            "asset_name": "asset_url",
            "sandbox_asset_name": "sandbox_asset_url",
            "ablation_asset_name": "ablation_asset_url",
            "drilldown_asset_name": "drilldown_asset_url",
            "guardian_asset_name": "guardian_asset_url",
            "replication_asset_name": "replication_asset_url",
            "blind_holdout_asset_name": "blind_holdout_asset_url",
            "sequential_blind_asset_name": "sequential_blind_asset_url",
            "evidence_story_asset_name": "evidence_story_asset_url",
            "ci_recovery_asset_name": "ci_recovery_asset_url",
        }
        for name_field, url_field in asset_name_fields.items():
            asset_name = release.get(name_field)
            if asset_name:
                release[url_field] = (
                    f"https://github.com/{repository}/releases/download/"
                    f"{release_tag}/{asset_name}"
                )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(public_bytes)
    judge_path.write_text(
        json.dumps(judge, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return reference


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--judge", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--artifact-archive-sha256", required=True)
    parser.add_argument("--page-url", required=True)
    parser.add_argument("--public-url", required=True)
    parser.add_argument("--release-tag")
    args = parser.parse_args()
    reference = promote(
        raw_path=args.raw,
        public_path=args.public,
        judge_path=args.judge,
        output_path=args.output,
        artifact_id=args.artifact_id,
        artifact_name=args.artifact_name,
        artifact_archive_sha256=args.artifact_archive_sha256,
        page_url=args.page_url,
        public_url=args.public_url,
        release_tag=args.release_tag,
    )
    print(json.dumps(reference, sort_keys=True))


if __name__ == "__main__":
    main()
