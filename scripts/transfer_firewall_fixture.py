"""Execute one sealed cross-environment transfer exercise in GitHub Actions."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile
import time
from typing import Any

from continuum.adaptive_diagnosis import (
    ADAPTIVE_DIAGNOSIS_FAMILIES,
    PROBES,
    diagnostic_observation,
)
from continuum.blind_holdout import canonical_json_bytes
from continuum.ci_recovery import CI_PATCH_POLICIES
from continuum.transfer_firewall import (
    ENVIRONMENT_PROFILES,
    TRANSFER_CONTRACT,
)
from scripts.adaptive_diagnosis_fixture import (
    _read_probe,
    _run_contract,
    _workspace_digest,
    build_adaptive_workspace,
)
from scripts.ci_recovery_fixture import NO_PATCH, apply_reviewed_patch


_FAMILY_BY_ID = {item.family: item for item in ADAPTIVE_DIAGNOSIS_FAMILIES}
ATTESTATION_OPERATION = "attest_causal_signature"


def _materialize_environment(root: Path, profile_id: str) -> None:
    profile = ENVIRONMENT_PROFILES.get(profile_id)
    if profile is None:
        raise ValueError("transfer environment profile is invalid")
    metadata = root / ".continuum-environment"
    metadata.mkdir(parents=True, exist_ok=True)
    (metadata / "profile.json").write_bytes(canonical_json_bytes(dict(profile)))
    layout = str(profile["repository_layout"])
    if layout == "python-monorepo":
        path = root / "packages" / "continuum-memory"
    elif layout == "service-workspace":
        path = root / "services" / "memory-firewall"
    else:
        path = root / "container" / "workspace"
    path.mkdir(parents=True, exist_ok=True)
    (path / "environment.txt").write_text(
        "\n".join(f"{key}={value}" for key, value in sorted(profile.items())) + "\n",
        encoding="utf-8",
    )


def _workspace_causal_signature(root: Path, fixture_id: str) -> tuple[str, dict[str, Any]]:
    family = _FAMILY_BY_ID[fixture_id]
    facts = _read_probe(root, family.fault_probe_id)
    expected = diagnostic_observation(fixture_id, family.fault_probe_id)
    if facts != expected["facts"] or expected["finding"] != "anomaly":
        raise RuntimeError("transfer provider facts drifted from the causal contract")
    body = {
        "contract": TRANSFER_CONTRACT,
        "probe_id": family.fault_probe_id,
        "finding": "anomaly",
        "facts": facts,
    }
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest(), body


def run_transfer_fixture(
    *,
    case_id: str,
    fixture_id: str,
    environment_profile_id: str,
    environment_fingerprint: str,
    operation_kind: str,
    operation_id: str,
    commitment_sha256: str,
) -> tuple[dict[str, Any], str]:
    if re.fullmatch(r"tf-[0-9a-f]{20}", case_id) is None:
        raise ValueError("transfer case ID is invalid")
    family = _FAMILY_BY_ID.get(fixture_id)
    if family is None:
        raise ValueError("transfer fixture ID is invalid")
    if environment_profile_id not in ENVIRONMENT_PROFILES:
        raise ValueError("transfer environment profile ID is invalid")
    if re.fullmatch(r"env-[0-9a-f]{20}", environment_fingerprint) is None:
        raise ValueError("transfer environment fingerprint is invalid")
    if operation_kind not in {
        "source-calibration",
        "target-attestation",
        "diagnostic",
        "remediation",
    }:
        raise ValueError("transfer operation kind is invalid")
    if re.fullmatch(r"[0-9a-f]{64}", commitment_sha256) is None:
        raise ValueError("transfer commitment digest is invalid")
    if operation_kind == "target-attestation":
        if operation_id != ATTESTATION_OPERATION:
            raise ValueError("transfer attestation operation is invalid")
    elif operation_kind == "diagnostic":
        if operation_id not in PROBES:
            raise ValueError("transfer diagnostic probe ID is invalid")
        if operation_id not in {family.fault_probe_id, family.paired_probe_id}:
            raise ValueError("transfer probe is outside the ambiguity pair")
    elif operation_id != NO_PATCH and operation_id not in CI_PATCH_POLICIES:
        raise ValueError("transfer patch ID is invalid")

    started = datetime.now(timezone.utc)
    started_ns = time.perf_counter_ns()
    output = ""
    workspace_path = ""
    exercise_passed = False
    provider_payload: dict[str, Any]
    with tempfile.TemporaryDirectory(prefix="continuum-transfer-firewall-") as temporary:
        workspace = Path(temporary)
        workspace_path = str(workspace)
        build_adaptive_workspace(workspace, fixture_id)
        _materialize_environment(workspace, environment_profile_id)
        before = _workspace_digest(workspace)
        if operation_kind == "target-attestation":
            signature, evidence = _workspace_causal_signature(workspace, fixture_id)
            after = _workspace_digest(workspace)
            if before != after:
                raise RuntimeError("transfer attestation mutated its workspace")
            exercise_passed = True
            provider_payload = {
                "schema_version": 1,
                "kind": "continuum.transfer-firewall.attestation",
                "transfer_contract": TRANSFER_CONTRACT,
                "environment_fingerprint": environment_fingerprint,
                "environment_profile_id": environment_profile_id,
                "causal_signature": signature,
                "causal_evidence_sha256": hashlib.sha256(
                    canonical_json_bytes(evidence)
                ).hexdigest(),
                "read_only": True,
                "workspace_sha256_before": before,
                "workspace_sha256_after": after,
            }
            output = json.dumps(provider_payload, separators=(",", ":"), sort_keys=True)
        elif operation_kind == "diagnostic":
            facts = _read_probe(workspace, operation_id)
            expected = diagnostic_observation(fixture_id, operation_id)
            if facts != expected["facts"]:
                raise RuntimeError("transfer diagnostic facts drifted from the contract")
            after = _workspace_digest(workspace)
            if before != after:
                raise RuntimeError("transfer diagnostic probe mutated its workspace")
            exercise_passed = True
            provider_payload = {
                "schema_version": 1,
                "kind": "continuum.adaptive-diagnosis.probe",
                "probe_id": operation_id,
                "finding": expected["finding"],
                "facts": facts,
                "read_only": True,
                "environment_fingerprint": environment_fingerprint,
                "environment_profile_id": environment_profile_id,
                "workspace_sha256_before": before,
                "workspace_sha256_after": after,
            }
            output = json.dumps(provider_payload, separators=(",", ":"), sort_keys=True)
        else:
            source_signature = None
            source_evidence = None
            if operation_kind == "source-calibration":
                source_signature, source_evidence = _workspace_causal_signature(
                    workspace, fixture_id
                )
            apply_reviewed_patch(workspace, operation_id)
            exercise_passed, output = _run_contract(workspace)
            provider_payload = {
                "schema_version": 1,
                "kind": "continuum.transfer-firewall.remediation",
                "operation_kind": operation_kind,
                "patch_id": operation_id,
                "contract_passed": exercise_passed,
                "environment_fingerprint": environment_fingerprint,
                "environment_profile_id": environment_profile_id,
                "workspace_sha256_before": before,
                "workspace_sha256_after": _workspace_digest(workspace),
            }
            if source_signature is not None and source_evidence is not None:
                provider_payload.update(
                    {
                        "transfer_contract": TRANSFER_CONTRACT,
                        "causal_signature": source_signature,
                        "causal_evidence_sha256": hashlib.sha256(
                            canonical_json_bytes(source_evidence)
                        ).hexdigest(),
                    }
                )
    cleanup_residual_count = int(Path(workspace_path).exists())
    completed = datetime.now(timezone.utc)
    receipt = {
        "schema_version": 1,
        "kind": "continuum-transfer-firewall-child-receipt",
        "case_id": case_id,
        "fixture_id": fixture_id,
        "environment_profile_id": environment_profile_id,
        "environment_fingerprint": environment_fingerprint,
        "patch_id": operation_id,
        "phase": operation_kind,
        "commitment_sha256": commitment_sha256,
        "exercise_passed": exercise_passed,
        "test_output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "duration_ms": round((time.perf_counter_ns() - started_ns) / 1_000_000, 3),
        "repository_mutation": False,
        "ephemeral_workspace": True,
        "cleanup_residual_count": cleanup_residual_count,
        "provider_payload": provider_payload,
    }
    return receipt, output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--fixture-id", required=True)
    parser.add_argument("--environment-profile-id", required=True)
    parser.add_argument("--environment-fingerprint", required=True)
    parser.add_argument("--operation-kind", required=True)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--correlation-id", required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--commitment-sha256", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if re.fullmatch(r"[a-z0-9-]{8,96}", args.correlation_id) is None:
        raise ValueError("transfer correlation ID is invalid")
    if re.fullmatch(r"[0-9a-f]{40}", args.source_head) is None:
        raise ValueError("transfer source head is invalid")
    receipt, output = run_transfer_fixture(
        case_id=args.case_id,
        fixture_id=args.fixture_id,
        environment_profile_id=args.environment_profile_id,
        environment_fingerprint=args.environment_fingerprint,
        operation_kind=args.operation_kind,
        operation_id=args.operation_id,
        commitment_sha256=args.commitment_sha256,
    )
    receipt.update(
        {"correlation_id": args.correlation_id, "source_head": args.source_head}
    )
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(output)
    print(
        json.dumps(
            {
                "case_id": args.case_id,
                "operation_kind": args.operation_kind,
                "operation_id": args.operation_id,
                "exercise_passed": receipt["exercise_passed"],
                "cleanup_residual_count": receipt["cleanup_residual_count"],
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    raise SystemExit(0 if receipt["exercise_passed"] else 1)


if __name__ == "__main__":
    main()
