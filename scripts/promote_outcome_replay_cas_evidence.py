"""Promote one exact participant-cluster outcome replay CAS proof."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from continuum.outcome_replay_proof import (
    build_public_outcome_replay_proof,
    validate_outcome_replay_proof,
)
from scripts.build_release_envelope import RLS_MIGRATIONS, _migration_receipt


COMMIT = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _repository_bytes(value: bytes) -> bytes:
    return value.replace(b"\r\n", b"\n")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(_repository_bytes(value)).hexdigest()


def build_reference(
    raw: dict[str, Any],
    public: dict[str, Any],
    *,
    private_bytes: bytes,
    public_bytes: bytes,
    repository: str,
    artifact_id: int,
    artifact_name: str,
    artifact_archive_sha256: str,
    page_url: str,
    public_url: str,
) -> dict[str, Any]:
    validate_outcome_replay_proof(raw)
    validate_outcome_replay_proof(public)
    if public != build_public_outcome_replay_proof(raw):
        raise RuntimeError("public outcome replay proof is not the exact projection")
    source_head = str(raw["source_head"])
    run_id = int(raw["workflow"]["run_id"])
    attempt = int(raw["workflow"]["run_attempt"])
    if COMMIT.fullmatch(source_head) is None:
        raise RuntimeError("outcome replay source head is invalid")
    expected_name = (
        f"continuum-outcome-replay-cas-{source_head}-{run_id}-{attempt}"
    )
    if artifact_id < 1 or artifact_name != expected_name:
        raise RuntimeError("outcome replay artifact is not exact-run bound")
    if DIGEST.fullmatch(artifact_archive_sha256) is None:
        raise RuntimeError("outcome replay artifact digest is invalid")
    journal = public["cas"]["journal"]
    return {
        "schema_version": public["schema_version"],
        "head_sha": source_head,
        "workflow_run_id": run_id,
        "workflow_attempt": attempt,
        "workflow_url": (
            f"https://github.com/{repository}/actions/runs/{run_id}"
        ),
        "workflow_api_url": (
            f"https://api.github.com/repos/{repository}/actions/runs/{run_id}"
        ),
        "artifact_id": artifact_id,
        "artifact_name": artifact_name,
        "artifact_api_url": (
            f"https://api.github.com/repos/{repository}/actions/artifacts/{artifact_id}"
        ),
        "artifact_archive_sha256": artifact_archive_sha256,
        "private_report_sha256": _sha256(private_bytes),
        "public_sha256": _sha256(public_bytes),
        "public_url": public_url,
        "page_url": page_url,
        "deployment_artifact_sha256": public["deployment_artifact_sha256"],
        "migration_version": public["migration"]["current_version"],
        "provider_adapter": public["provider"]["adapter"],
        "accepted_receipt_sha256": public["provider"][
            "accepted_receipt_sha256"
        ],
        "conflicting_receipt_sha256": public["provider"][
            "conflicting_receipt_sha256"
        ],
        "journal_rows": public["cas"]["journal_rows"],
        "chain_genesis": journal[0]["previous_entry_hash"],
        "chain_tip": public["cas"]["chain_tip"],
        "conflict_error_code": public["cas"]["conflict_error_code"],
        **(
            {
                "provider_lookup_count": public["provider"]["lookup_count"],
                "attestation_handle_digest": public["attestation"][
                    "handle_digest"
                ],
                "attestation_policy_version": public["attestation"][
                    "policy_version"
                ],
            }
            if public["schema_version"] >= 2
            else {}
        ),
    }


def promote(
    *,
    raw_path: Path,
    public_path: Path,
    judge_path: Path,
    output_path: Path,
    repository: str,
    artifact_id: int,
    artifact_name: str,
    artifact_archive_sha256: str,
    page_url: str,
    public_url: str,
    release_tag: str | None = None,
) -> dict[str, Any]:
    private_bytes = raw_path.read_bytes()
    raw = json.loads(private_bytes)
    supplied_public = json.loads(public_path.read_bytes())
    public = build_public_outcome_replay_proof(raw)
    if supplied_public != public:
        raise RuntimeError("downloaded public outcome replay proof drifted")
    public_bytes = (json.dumps(public, indent=2, sort_keys=True) + "\n").encode()
    judge = json.loads(judge_path.read_bytes())
    reference = build_reference(
        raw,
        public,
        private_bytes=private_bytes,
        public_bytes=public_bytes,
        repository=repository,
        artifact_id=artifact_id,
        artifact_name=artifact_name,
        artifact_archive_sha256=artifact_archive_sha256,
        page_url=page_url,
        public_url=public_url,
    )
    # Promotion must never downgrade newer judge contracts (for example the
    # schema-16 offline capsule added after the CAS proof was introduced).
    judge["schema_version"] = max(int(judge.get("schema_version", 0)), 15)
    judge["generated_at"] = public["cas"]["journal"][-1]["recorded_at"]
    judge["claim_boundary"] = (
        "Read-only verification of one retained participant-cluster proposal: "
        "a real S3 HEAD+GET lookup issued one short-lived, proposal-bound "
        "promotion handle; CockroachDB consumed it atomically with the outcome "
        "and canonical memory. Exact replay stayed idempotent, while missing, "
        "forged, expired, cross-proposal, cross-provider, and receipt-mismatched "
        "handles were rejected. This "
        "is an architectural closure, not a population estimate."
    )
    judge["outcome_replay_cas"] = reference
    judge["database_policy"] = {
        "rls_combined_sha256": _migration_receipt(
            Path(__file__).parents[1],
            RLS_MIGRATIONS,
        )["combined_sha256"]
    }
    if release_tag is not None:
        if not release_tag or any(character.isspace() for character in release_tag):
            raise RuntimeError("release tag is invalid")
        release = judge["release_envelope"]
        release["tag"] = release_tag
        release["release_url"] = (
            f"https://github.com/{repository}/releases/tag/{release_tag}"
        )
        release["release_api_url"] = (
            f"https://api.github.com/repos/{repository}/releases/tags/{release_tag}"
        )
        release["outcome_replay_cas_asset_name"] = "outcome-replay-cas-v1.json"
        name_fields = {
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
            "transfer_firewall_asset_name": "transfer_firewall_asset_url",
            "online_memory_lineage_asset_name": "online_memory_lineage_asset_url",
            "outcome_replay_cas_asset_name": "outcome_replay_cas_asset_url",
            "offline_judge_capsule_asset_name": "offline_judge_capsule_asset_url",
        }
        for name_field, url_field in name_fields.items():
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
    parser.add_argument("--repository", required=True)
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
                repository=args.repository,
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
