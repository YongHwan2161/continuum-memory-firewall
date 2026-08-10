"""Promote one exact adaptive-diagnosis artifact into public judge evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from continuum.adaptive_diagnosis import build_public_adaptive_diagnosis


SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _repository_bytes(value: bytes) -> bytes:
    return value.replace(b"\r\n", b"\n")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(_repository_bytes(value)).hexdigest()


def _all_receipts(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return [item["provider_receipt"] for item in raw["calibration"]] + [
        receipt
        for item in raw["observations"]
        for receipt in item["diagnostic_receipts"]
    ] + [item["provider_receipt"] for item in raw["observations"]]


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
        raise RuntimeError("adaptive diagnosis source head is invalid")
    if run_id < 1 or attempt < 1 or artifact_id < 1:
        raise RuntimeError("adaptive diagnosis workflow lineage is invalid")
    expected_artifact = f"continuum-adaptive-diagnosis-{head}-{run_id}-{attempt}"
    if artifact_name != expected_artifact:
        raise RuntimeError("adaptive diagnosis artifact name is not exact-head bound")
    if SHA256_PATTERN.fullmatch(artifact_archive_sha256) is None:
        raise RuntimeError("adaptive diagnosis archive digest is invalid")
    if public != build_public_adaptive_diagnosis(raw):
        raise RuntimeError("public adaptive report is not the raw-report projection")
    if raw.get("gate", {}).get("status") != "PASS":
        raise RuntimeError("adaptive diagnosis benchmark gate did not pass")
    if raw.get("real_external_provider") is not True:
        raise RuntimeError("adaptive diagnosis is not a real provider run")
    if raw.get("provider") != "github-actions":
        raise RuntimeError("adaptive diagnosis provider is not GitHub Actions")
    methodology = raw.get("methodology", {})
    expected_cardinality = {
        "paired_cases": 12,
        "arm_observations": 36,
        "fault_families": 6,
        "ambiguity_groups": 3,
        "calibration_child_runs": 18,
        "diagnostic_child_runs": 30,
        "remediation_child_runs": 36,
        "total_child_workflow_runs": 84,
        "candidate_visible_label_fields": 0,
    }
    if any(methodology.get(key) != value for key, value in expected_cardinality.items()):
        raise RuntimeError("adaptive diagnosis live cardinality is invalid")
    receipts = _all_receipts(raw)
    run_ids = [int(item["workflow_run_id"]) for item in receipts]
    if len(receipts) != 84 or len(set(run_ids)) != 84:
        raise RuntimeError("adaptive diagnosis receipts are not exact and unique")
    if any(
        item.get("head_sha") != head
        or item.get("repository_mutation") is not False
        or item.get("cleanup_residual_count") != 0
        for item in receipts
    ):
        raise RuntimeError("adaptive diagnosis receipt boundary failed")
    arms = raw.get("arms", {})
    continuum = arms.get("continuum", {})
    stateless = arms.get("stateless", {})
    raw_rag = arms.get("raw_rag", {})
    comparison = raw.get("paired_comparisons", {}).get(
        "continuum_vs_stateless", {}
    )
    recurrence = comparison.get("recurrence", {})
    if not (
        continuum.get("verified_recoveries") == 12
        and continuum.get("recurrence_diagnostic_probe_calls") == 0
        and continuum.get("recurrence_zero_probe_cases") == 6
        and continuum.get("false_canonical_promotions") == 0
        and continuum.get("canonical_promotion_precision") == 1.0
        and stateless.get("verified_recoveries") == 12
        and stateless.get("recurrence_diagnostic_probe_calls") == 6
        and raw_rag.get("verified_recoveries") == 12
        and recurrence.get("diagnostic_probe_reduction_cases") == 6
        and recurrence.get("diagnostic_probe_exact_p_value") == 0.03125
    ):
        raise RuntimeError("adaptive diagnosis result does not match the live claim")
    commitment = raw.get("commitment", {})
    seal = raw.get("seal_receipt", {})
    for value in (
        commitment.get("challenge_sha256"),
        commitment.get("labels_sha256"),
        commitment.get("commitment_sha256"),
        seal.get("receipt_sha256"),
    ):
        if SHA256_PATTERN.fullmatch(str(value or "")) is None:
            raise RuntimeError("adaptive diagnosis commitment lineage is invalid")
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
            f"https://api.github.com/repos/{repository}/actions/artifacts/{artifact_id}"
        ),
        "artifact_archive_sha256": artifact_archive_sha256,
        "public_sha256": _sha256(public_bytes),
        "public_url": public_url,
        "page_url": page_url,
        "campaign_id": raw["campaign_id"],
        "challenge_sha256": commitment["challenge_sha256"],
        "labels_sha256": commitment["labels_sha256"],
        "commitment_sha256": commitment["commitment_sha256"],
        "seal_receipt_sha256": seal["receipt_sha256"],
        "agent_model": raw["agent_model"],
        "provider": raw["provider"],
        "paired_cases": methodology["paired_cases"],
        "child_workflow_runs": methodology["total_child_workflow_runs"],
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
    judge["schema_version"] = 12
    judge["generated_at"] = raw["generated_at"]
    judge["claim_boundary"] = (
        "Read-only verification of live identity-bound memory, an S3-preregistered "
        "ambiguity-first three-arm diagnosis benchmark over twelve synthetic CI "
        "fixtures, real GitHub Actions probe and remediation receipts, prior "
        "CockroachDB vector/RLS evidence, AWS receipts, an immutable release, and "
        "Devpost lineage. The adaptive result proves exact-fingerprint verified "
        "memory can remove one diagnostic step on this registered population at "
        "equal 12/12 recovery; it does not prove broad repository generalization."
    )
    judge["adaptive_diagnosis"] = reference
    if release_tag is not None:
        if not release_tag or any(character.isspace() for character in release_tag):
            raise RuntimeError("release tag is invalid")
        release = judge["release_envelope"]
        release["tag"] = release_tag
        release["release_url"] = (
            f"https://github.com/{raw['repository']}/releases/tag/{release_tag}"
        )
        release["release_api_url"] = (
            f"https://api.github.com/repos/{raw['repository']}/releases/tags/"
            f"{release_tag}"
        )
        release["adaptive_diagnosis_asset_name"] = "adaptive-diagnosis-v1.json"
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
            "adaptive_diagnosis_asset_name": "adaptive_diagnosis_asset_url",
        }
        for name_field, url_field in asset_name_fields.items():
            asset_name = release.get(name_field)
            if asset_name:
                release[url_field] = (
                    f"https://github.com/{raw['repository']}/releases/download/"
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
    print(
        json.dumps(
            promote(
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
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
