"""Execute one bounded synthetic CI fault on an ephemeral workspace."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

from continuum.ci_recovery import CI_PATCH_POLICIES, build_ci_recovery_cases


NO_PATCH = "no_patch"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _contract_test(family: str) -> str:
    checks = {
        "python-runtime": """
        value = json.loads((ROOT / "runtime.json").read_text(encoding="utf-8"))
        self.assertEqual(value["python_version"], "3.12")
""",
        "dependency-lock": """
        lines = (ROOT / "requirements.lock").read_text(encoding="utf-8").splitlines()
        self.assertIn("continuum-core==1.0.0", lines)
""",
        "matrix-axis": """
        value = json.loads((ROOT / "matrix.json").read_text(encoding="utf-8"))
        self.assertIn("python", value)
        self.assertNotIn("python-version", value)
""",
        "artifact-path": """
        target = ROOT / "dist" / "evidence.json"
        self.assertTrue(target.is_file())
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["gate"], "PASS")
""",
        "gate-schema": """
        value = json.loads((ROOT / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(value["gate"]["status"], "PASS")
        self.assertNotIn("status", value)
""",
        "package-root": """
        value = json.loads((ROOT / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(value["module_root"], "src")
""",
    }
    body = checks[family].strip("\n")
    indented = "\n".join("        " + line.lstrip() for line in body.splitlines())
    return (
        "import json\n"
        "from pathlib import Path\n"
        "import unittest\n\n"
        "ROOT = Path(__file__).parents[1]\n\n"
        "class ContractTest(unittest.TestCase):\n"
        "    def test_ci_contract(self):\n"
        f"{indented}\n\n"
        "if __name__ == '__main__':\n"
        "    unittest.main()\n"
    )


def build_fault_workspace(root: Path, family: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if family == "python-runtime":
        _write_json(root / "runtime.json", {"python_version": "3.10"})
    elif family == "dependency-lock":
        (root / "requirements.lock").write_text(
            "support-lib==2.0.0\n", encoding="utf-8"
        )
    elif family == "matrix-axis":
        _write_json(root / "matrix.json", {"python-version": ["3.12"]})
    elif family == "artifact-path":
        _write_json(root / "build" / "evidence.json", {"gate": "PASS"})
    elif family == "gate-schema":
        _write_json(root / "report.json", {"status": "PASS"})
    elif family == "package-root":
        _write_json(root / "settings.json", {"module_root": "app"})
    else:
        raise ValueError(f"unsupported CI fault family: {family}")
    tests = root / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "test_contract.py").write_text(
        _contract_test(family), encoding="utf-8"
    )


def apply_reviewed_patch(root: Path, patch_id: str) -> None:
    if patch_id == NO_PATCH:
        return
    if patch_id not in CI_PATCH_POLICIES:
        raise ValueError("patch_id is not a reviewed remediation")
    if patch_id == "set_python_312" and (root / "runtime.json").is_file():
        _write_json(root / "runtime.json", {"python_version": "3.12"})
    elif patch_id == "restore_dependency_lock" and (
        root / "requirements.lock"
    ).is_file():
        (root / "requirements.lock").write_text(
            "support-lib==2.0.0\ncontinuum-core==1.0.0\n", encoding="utf-8"
        )
    elif patch_id == "repair_matrix_axis" and (root / "matrix.json").is_file():
        _write_json(root / "matrix.json", {"python": ["3.12"]})
    elif patch_id == "restore_artifact_path" and (
        root / "build" / "evidence.json"
    ).is_file():
        target = root / "dist" / "evidence.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(root / "build" / "evidence.json", target)
    elif patch_id == "repair_gate_schema" and (root / "report.json").is_file():
        _write_json(root / "report.json", {"gate": {"status": "PASS"}})
    elif patch_id == "normalize_package_root" and (
        root / "settings.json"
    ).is_file():
        _write_json(root / "settings.json", {"module_root": "src"})


def run_fixture(*, case_id: str, patch_id: str) -> tuple[dict[str, object], str]:
    cases = {case.case_id: case for case in build_ci_recovery_cases()}
    if case_id not in cases:
        raise ValueError("case_id is not in the registered CI recovery population")
    case = cases[case_id]
    started = datetime.now(timezone.utc)
    started_ns = time.perf_counter_ns()
    output = ""
    workspace_path = ""
    exercise_passed = False
    with tempfile.TemporaryDirectory(prefix="continuum-ci-recovery-") as temporary:
        workspace = Path(temporary)
        workspace_path = str(workspace)
        build_fault_workspace(workspace, case.family)
        apply_reviewed_patch(workspace, patch_id)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-v",
            ],
            cwd=workspace,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout + result.stderr
        exercise_passed = result.returncode == 0
    cleanup_residual_count = int(Path(workspace_path).exists())
    completed = datetime.now(timezone.utc)
    return (
        {
            "schema_version": 1,
            "kind": "continuum-ci-recovery-child-receipt",
            "case_id": case.case_id,
            "family": case.family,
            "variant": case.variant,
            "patch_id": patch_id,
            "exercise_passed": exercise_passed,
            "test_command": "python -m unittest discover -s tests -v",
            "test_output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
            "started_at": started.isoformat(),
            "completed_at": completed.isoformat(),
            "duration_ms": round((time.perf_counter_ns() - started_ns) / 1_000_000, 3),
            "repository_mutation": False,
            "ephemeral_workspace": True,
            "cleanup_residual_count": cleanup_residual_count,
        },
        output,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--patch-id", required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--correlation-id", required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.phase not in {
        "baseline",
        "calibration_wrong",
        "calibration_green",
        "evaluation",
    }:
        raise ValueError("phase is invalid")
    if re.fullmatch(r"[a-z0-9-]{8,96}", args.correlation_id) is None:
        raise ValueError("correlation-id is invalid")
    if re.fullmatch(r"[0-9a-f]{40}", args.source_head) is None:
        raise ValueError("source-head is invalid")
    receipt, output = run_fixture(case_id=args.case_id, patch_id=args.patch_id)
    receipt.update(
        {
            "phase": args.phase,
            "correlation_id": args.correlation_id,
            "source_head": args.source_head,
        }
    )
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(output, end="")
    print(
        json.dumps(
            {
                "case_id": args.case_id,
                "patch_id": args.patch_id,
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
