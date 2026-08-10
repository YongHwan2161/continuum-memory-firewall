"""Execute one sealed adaptive-diagnosis probe or remediation in CI."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping

from continuum.adaptive_diagnosis import (
    ADAPTIVE_DIAGNOSIS_FAMILIES,
    PROBES,
    diagnostic_observation,
)
from continuum.ci_recovery import CI_PATCH_POLICIES
from scripts.ci_recovery_fixture import (
    NO_PATCH,
    _write_json,
    apply_reviewed_patch,
    build_fault_workspace,
)


_FAMILY_BY_ID = {item.family: item for item in ADAPTIVE_DIAGNOSIS_FAMILIES}


def _workspace_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def build_adaptive_workspace(root: Path, family_id: str) -> None:
    build_fault_workspace(root, family_id)
    family = _FAMILY_BY_ID[family_id]
    if family.ambiguity_group == "bootstrap-resolution":
        if not (root / "runtime.json").exists():
            _write_json(root / "runtime.json", {"python_version": "3.12"})
        if not (root / "settings.json").exists():
            _write_json(root / "settings.json", {"module_root": "src"})
    elif family.ambiguity_group == "dependency-expansion":
        if not (root / "requirements.lock").exists():
            (root / "requirements.lock").write_text(
                "support-lib==2.0.0\ncontinuum-core==1.0.0\n",
                encoding="utf-8",
            )
        if not (root / "matrix.json").exists():
            _write_json(root / "matrix.json", {"python": ["3.12"]})
    elif family.ambiguity_group == "evidence-publication":
        if not (root / "dist" / "evidence.json").exists() and family_id != (
            "artifact-path"
        ):
            _write_json(root / "dist" / "evidence.json", {"gate": "PASS"})
        if not (root / "report.json").exists():
            _write_json(root / "report.json", {"gate": {"status": "PASS"}})


def _read_probe(root: Path, probe_id: str) -> Mapping[str, Any]:
    if probe_id == "inspect_runtime_manifest":
        value = json.loads((root / "runtime.json").read_text(encoding="utf-8"))
        return {"python_version": value.get("python_version"), "manifest_present": True}
    if probe_id == "inspect_package_settings":
        value = json.loads((root / "settings.json").read_text(encoding="utf-8"))
        return {"module_root": value.get("module_root"), "settings_present": True}
    if probe_id == "inspect_dependency_lock":
        lines = (root / "requirements.lock").read_text(encoding="utf-8").splitlines()
        pin = next(
            (
                line.split("==", 1)[1]
                for line in lines
                if line.startswith("continuum-core==")
            ),
            None,
        )
        return {"continuum_core_pin": pin, "lock_present": True}
    if probe_id == "inspect_matrix_manifest":
        value = json.loads((root / "matrix.json").read_text(encoding="utf-8"))
        return {"matrix_keys": sorted(value), "manifest_present": True}
    if probe_id == "inspect_artifact_tree":
        return {
            "build_evidence": (root / "build" / "evidence.json").is_file(),
            "dist_evidence": (root / "dist" / "evidence.json").is_file(),
        }
    if probe_id == "inspect_report_schema":
        value = json.loads((root / "report.json").read_text(encoding="utf-8"))
        gate = value.get("gate")
        return {
            "top_level_keys": sorted(value),
            "gate_status": gate.get("status") if isinstance(gate, Mapping) else None,
        }
    raise ValueError("adaptive diagnostic probe is invalid")


def _run_contract(root: Path) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode == 0, result.stdout + result.stderr


def run_adaptive_fixture(
    *,
    case_id: str,
    fixture_id: str,
    operation_kind: str,
    operation_id: str,
    commitment_sha256: str,
) -> tuple[dict[str, Any], str]:
    if re.fullmatch(r"ad-[0-9a-f]{20}", case_id) is None:
        raise ValueError("adaptive case ID is invalid")
    family = _FAMILY_BY_ID.get(fixture_id)
    if family is None:
        raise ValueError("adaptive fixture ID is invalid")
    if operation_kind not in {"calibration", "diagnostic", "remediation"}:
        raise ValueError("adaptive operation kind is invalid")
    if re.fullmatch(r"[0-9a-f]{64}", commitment_sha256) is None:
        raise ValueError("adaptive commitment digest is invalid")
    if operation_kind == "diagnostic":
        if operation_id not in PROBES:
            raise ValueError("adaptive probe ID is invalid")
        if operation_id not in {family.fault_probe_id, family.paired_probe_id}:
            raise ValueError("adaptive probe is outside the ambiguity pair")
    elif operation_id != NO_PATCH and operation_id not in CI_PATCH_POLICIES:
        raise ValueError("adaptive patch ID is invalid")

    started = datetime.now(timezone.utc)
    started_ns = time.perf_counter_ns()
    output = ""
    workspace_path = ""
    exercise_passed = False
    provider_payload: dict[str, Any]
    with tempfile.TemporaryDirectory(prefix="continuum-adaptive-diagnosis-") as temporary:
        workspace = Path(temporary)
        workspace_path = str(workspace)
        build_adaptive_workspace(workspace, fixture_id)
        before = _workspace_digest(workspace)
        if operation_kind == "diagnostic":
            facts = _read_probe(workspace, operation_id)
            expected = diagnostic_observation(fixture_id, operation_id)
            if facts != expected["facts"]:
                raise RuntimeError("adaptive probe facts drifted from the sealed contract")
            after = _workspace_digest(workspace)
            if before != after:
                raise RuntimeError("read-only adaptive probe mutated its workspace")
            exercise_passed = True
            provider_payload = {
                "schema_version": 1,
                "kind": "continuum.adaptive-diagnosis.probe",
                "probe_id": operation_id,
                "finding": expected["finding"],
                "facts": facts,
                "read_only": True,
                "workspace_sha256_before": before,
                "workspace_sha256_after": after,
            }
            output = json.dumps(provider_payload, separators=(",", ":"), sort_keys=True)
        else:
            apply_reviewed_patch(workspace, operation_id)
            exercise_passed, output = _run_contract(workspace)
            provider_payload = {
                "schema_version": 1,
                "kind": "continuum.adaptive-diagnosis.remediation",
                "operation_kind": operation_kind,
                "patch_id": operation_id,
                "contract_passed": exercise_passed,
                "workspace_sha256_before": before,
                "workspace_sha256_after": _workspace_digest(workspace),
            }
    cleanup_residual_count = int(Path(workspace_path).exists())
    completed = datetime.now(timezone.utc)
    receipt = {
        "schema_version": 1,
        "kind": "continuum-adaptive-diagnosis-child-receipt",
        "case_id": case_id,
        "fixture_id": fixture_id,
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
    parser.add_argument("--operation-kind", required=True)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--correlation-id", required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--commitment-sha256", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if re.fullmatch(r"[a-z0-9-]{8,96}", args.correlation_id) is None:
        raise ValueError("adaptive correlation ID is invalid")
    if re.fullmatch(r"[0-9a-f]{40}", args.source_head) is None:
        raise ValueError("adaptive source head is invalid")
    receipt, output = run_adaptive_fixture(
        case_id=args.case_id,
        fixture_id=args.fixture_id,
        operation_kind=args.operation_kind,
        operation_id=args.operation_id,
        commitment_sha256=args.commitment_sha256,
    )
    receipt.update(
        {
            "correlation_id": args.correlation_id,
            "source_head": args.source_head,
        }
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
