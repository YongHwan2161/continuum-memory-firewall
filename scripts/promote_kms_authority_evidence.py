"""Promote one exact live KMS outcome-authority lifecycle receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from continuum.kms_authority_proof import validate_kms_authority_proof


COMMIT = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _repository_bytes(value: bytes) -> bytes:
    return value.replace(b"\r\n", b"\n")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(_repository_bytes(value)).hexdigest()


def build_reference(
    receipt: dict[str, Any],
    *,
    public_bytes: bytes,
    repository: str,
    artifact_id: int,
    artifact_name: str,
    artifact_archive_sha256: str,
    page_url: str,
    public_url: str,
) -> dict[str, Any]:
    validate_kms_authority_proof(receipt)
    source = receipt["source"]
    head = str(source["head"])
    run_id = int(source["workflow_run_id"])
    attempt = int(source["workflow_run_attempt"])
    if COMMIT.fullmatch(head) is None:
        raise RuntimeError("KMS authority source head is invalid")
    expected_name = f"continuum-kms-authority-{head}-{run_id}-{attempt}"
    if artifact_id < 1 or artifact_name != expected_name:
        raise RuntimeError("KMS authority artifact is not exact-run bound")
    if DIGEST.fullmatch(artifact_archive_sha256) is None:
        raise RuntimeError("KMS authority artifact digest is invalid")
    aws = receipt["aws"]
    lifecycle = receipt["lifecycle"]
    attestation = receipt["attestation"]
    database = receipt["cockroachdb"]
    return {
        "schema_version": receipt["schema_version"],
        "head_sha": head,
        "workflow_run_id": run_id,
        "workflow_attempt": attempt,
        "workflow_url": f"https://github.com/{repository}/actions/runs/{run_id}",
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
        "receipt_sha256": receipt["receipt_sha256"],
        "public_url": public_url,
        "page_url": page_url,
        "deployment_artifact_sha256": source["deployment_artifact_sha256"],
        "migration_version": database["migration_version"],
        "region": aws["region"],
        "verifier_key_count": aws["verifier_key_count"],
        "kms_sign_calls": aws["kms_sign_calls"],
        "kms_get_public_key_calls": aws["kms_get_public_key_calls"],
        "s3_head_get_lookups": aws["s3_head_get_lookups"],
        "action_worker_kms_sign_denied": aws[
            "action_worker_kms_sign_denied"
        ],
        "authority_epochs": lifecycle["authority_epochs"],
        "canonical_promotions": attestation["canonical_promotions"],
        "private_handoff_objects_remaining": lifecycle[
            "private_handoff_objects_remaining"
        ],
        "gate_check_count": len(receipt["gate"]["checks"]),
    }


def promote(
    *,
    receipt_path: Path,
    judge_path: Path,
    output_path: Path,
    repository: str,
    artifact_id: int,
    artifact_name: str,
    artifact_archive_sha256: str,
    page_url: str,
    public_url: str,
    release_tag: str,
    generated_at: str,
) -> dict[str, Any]:
    receipt = json.loads(receipt_path.read_bytes())
    validate_kms_authority_proof(receipt)
    public_bytes = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    reference = build_reference(
        receipt,
        public_bytes=public_bytes,
        repository=repository,
        artifact_id=artifact_id,
        artifact_name=artifact_name,
        artifact_archive_sha256=artifact_archive_sha256,
        page_url=page_url,
        public_url=public_url,
    )
    if not release_tag or any(character.isspace() for character in release_tag):
        raise RuntimeError("release tag is invalid")
    judge = json.loads(judge_path.read_bytes())
    judge["schema_version"] = max(int(judge.get("schema_version", 0)), 19)
    judge["generated_at"] = generated_at
    judge["claim_boundary"] = (
        "Read-only verification of one retained participant-cluster KMS "
        "authority lifecycle: the action worker could not sign; an independent "
        "verifier re-read real S3 receipts and signed four proposal-bound "
        "attestations across activate, rotate, and rollback epochs; CockroachDB "
        "persisted only the algorithm, authority epoch, and key ARN digest, "
        "then verified restart and exact replay without re-signing. This is an "
        "architectural closure, not a population estimate."
    )
    judge["kms_outcome_authority"] = reference
    judge["browser_verification"]["required_ui_check_count"] = 39
    release = judge["release_envelope"]
    release["tag"] = release_tag
    release["release_url"] = (
        f"https://github.com/{repository}/releases/tag/{release_tag}"
    )
    release["release_api_url"] = (
        f"https://api.github.com/repos/{repository}/releases/tags/{release_tag}"
    )
    release["kms_outcome_authority_asset_name"] = (
        "kms-authority-lifecycle-v1.json"
    )
    for name_field, asset_name in tuple(release.items()):
        if name_field == "asset_name":
            url_field = "asset_url"
        elif name_field.endswith("_asset_name"):
            url_field = name_field.removesuffix("_name") + "_url"
        else:
            continue
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
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--judge", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--artifact-archive-sha256", required=True)
    parser.add_argument("--page-url", required=True)
    parser.add_argument("--public-url", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--generated-at", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            promote(
                receipt_path=args.receipt,
                judge_path=args.judge,
                output_path=args.output,
                repository=args.repository,
                artifact_id=args.artifact_id,
                artifact_name=args.artifact_name,
                artifact_archive_sha256=args.artifact_archive_sha256,
                page_url=args.page_url,
                public_url=args.public_url,
                release_tag=args.release_tag,
                generated_at=args.generated_at,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
