"""Validation and public projection for the live KMS authority lifecycle proof."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping


PROOF_KIND = "continuum.kms-outcome-authority-lifecycle"
PROOF_SCHEMA_VERSION = 1


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def receipt_sha256(report: Mapping[str, Any]) -> str:
    payload = dict(report)
    payload.pop("receipt_sha256", None)
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def seal_kms_authority_proof(report: Mapping[str, Any]) -> dict[str, Any]:
    sealed = dict(report)
    sealed["receipt_sha256"] = receipt_sha256(sealed)
    validate_kms_authority_proof(sealed)
    return sealed


def _assert_no_private_authority(value: Any, *, path: str = "root") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            lowered = str(key).lower()
            if lowered in {
                "handle",
                "raw_handle",
                "key_arn",
                "database_url",
                "bucket",
                "object_key",
            }:
                raise ValueError(f"public proof exposes private authority at {path}.{key}")
            _assert_no_private_authority(nested, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _assert_no_private_authority(nested, path=f"{path}[{index}]")
    elif isinstance(value, str) and value.startswith("v2."):
        raise ValueError(f"public proof exposes a raw handle at {path}")


def validate_kms_authority_proof(report: Mapping[str, Any]) -> None:
    if (
        report.get("schema_version") != PROOF_SCHEMA_VERSION
        or report.get("kind") != PROOF_KIND
    ):
        raise ValueError("KMS authority proof contract is invalid")
    if report.get("gate", {}).get("status") != "PASS":
        raise ValueError("KMS authority proof gate did not pass")
    checks = report.get("gate", {}).get("checks")
    if not isinstance(checks, Mapping) or len(checks) != 18:
        raise ValueError("KMS authority proof check count changed")
    if not all(value is True for value in checks.values()):
        raise ValueError("KMS authority proof contains a failed check")
    source = report.get("source")
    if (
        not isinstance(source, Mapping)
        or re.fullmatch(r"[0-9a-f]{40}", str(source.get("head"))) is None
        or not isinstance(source.get("workflow_run_id"), int)
        or source.get("workflow_run_id", 0) < 1
        or not isinstance(source.get("workflow_run_attempt"), int)
        or source.get("workflow_run_attempt", 0) < 1
        or re.fullmatch(
            r"[0-9a-f]{64}", str(source.get("deployment_artifact_sha256"))
        )
        is None
    ):
        raise ValueError("KMS authority source identity is invalid")
    aws = report.get("aws")
    if (
        not isinstance(aws, Mapping)
        or aws.get("region") != "ap-southeast-1"
        or aws.get("key_spec") != "ECC_NIST_P256"
        or aws.get("signing_algorithm") != "ECDSA_SHA_256"
        or aws.get("verifier_key_count") != 2
        or aws.get("kms_sign_calls") != 4
        or aws.get("kms_get_public_key_calls") != 2
        or aws.get("s3_head_get_lookups") != 4
        or aws.get("action_worker_kms_sign_denied") is not True
        or aws.get("action_worker_kms_error_code") != "AccessDenied"
        or re.fullmatch(
            r"[0-9a-f]{64}", str(aws.get("verifier_role_arn_sha256"))
        )
        is None
        or re.fullmatch(
            r"[0-9a-f]{64}", str(aws.get("action_worker_arn_sha256"))
        )
        is None
    ):
        raise ValueError("KMS authority AWS boundary is invalid")
    lifecycle = report.get("lifecycle")
    if (
        not isinstance(lifecycle, Mapping)
        or lifecycle.get("keyring_versions") != [1, 2, 3]
        or lifecycle.get("authority_epochs") != [1, 2, 3]
        or lifecycle.get("transitions")
        != ["ACTIVATE_KEY_A", "ROTATE_TO_KEY_B", "ROLLBACK_TO_KEY_A"]
        or lifecycle.get("dual_key_overlap_verified") is not True
        or lifecycle.get("rollback_verified") is not True
        or lifecycle.get("restart_verified_offline") is not True
        or lifecycle.get("old_handle_replayed_without_resigning") is not True
        or lifecycle.get("private_handoff_objects_remaining") != 0
    ):
        raise ValueError("KMS authority lifecycle is invalid")
    manifests = lifecycle.get("manifest_sha256")
    if (
        not isinstance(manifests, list)
        or len(manifests) != 3
        or len(set(manifests)) != 3
        or any(re.fullmatch(r"[0-9a-f]{64}", str(item)) is None for item in manifests)
    ):
        raise ValueError("KMS authority manifest chain is invalid")
    attestation = report.get("attestation")
    if (
        not isinstance(attestation, Mapping)
        or attestation.get("issuer") != "s3-provider-origin-verifier-kms-v2"
        or attestation.get("policy_version") != "s3-receipt-lookup-kms-v2"
        or attestation.get("ttl_seconds") != 300
        or attestation.get("consumed_rows") != 3
        or attestation.get("canonical_promotions") != 3
        or attestation.get("distinct_public_keys") != 2
        or attestation.get("persisted_authority_epochs") != [1, 2, 3]
        or attestation.get("persisted_algorithm") != "ECDSA_SHA_256"
        or attestation.get("persisted_key_arn_digests") != 3
        or attestation.get("raw_handle_persisted") is not False
        or attestation.get("exact_replay_rows") != 1
    ):
        raise ValueError("KMS authority attestation evidence is invalid")
    negative = report.get("negative_paths")
    if negative != {
        "expired": "OUTCOME_ATTESTATION_EXPIRED",
        "forged": "OUTCOME_ATTESTATION_INVALID",
        "unknown_key_epoch": "OUTCOME_ATTESTATION_INVALID",
        "worker_kms_sign": "AccessDenied",
    }:
        raise ValueError("KMS authority negative matrix is invalid")
    database = report.get("cockroachdb")
    if (
        not isinstance(database, Mapping)
        or database.get("migration_version") != 38
        or database.get("attestation_rows") != 3
        or database.get("outcome_rows") != 3
        or database.get("canonical_memory_rows") != 3
        or database.get("rls_scope_visible_rows") != 3
        or database.get("runtime_attestation_insert_sqlstate") != "42501"
    ):
        raise ValueError("KMS authority CockroachDB evidence is invalid")
    receipt = report.get("receipt_sha256")
    if re.fullmatch(r"[0-9a-f]{64}", str(receipt)) is None:
        raise ValueError("KMS authority receipt digest is invalid")
    if receipt != receipt_sha256(report):
        raise ValueError("KMS authority receipt digest mismatch")
    _assert_no_private_authority(report)
