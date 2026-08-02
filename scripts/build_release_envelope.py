"""Build a fail-closed release envelope from reviewed public receipts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any


SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
RLS_MIGRATIONS = (
    "0009_enable_canonical_memory_rls.sql",
    "0010_enable_retrieval_audit_rls.sql",
    "0011_enable_incident_rls.sql",
)
CONTROL_PLANE_MIGRATIONS = (
    "0012_create_tenant_control_plane.sql",
    "0013_index_tenant_scope_bindings.sql",
    "0014_create_tenant_scope_binding_audit.sql",
    "0015_index_tenant_scope_binding_audit.sql",
)
VECTOR_CONTRACT_MIGRATIONS = (
    "0016_create_model_scoped_vector_index.sql",
    "0017_drop_incomplete_vector_index.sql",
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def repository_text_bytes(value: bytes) -> bytes:
    """Match the LF-normalized Git blob and GitHub Pages representation."""

    return value.replace(b"\r\n", b"\n")


def _migration_receipt(repo_root: Path, names: tuple[str, ...]) -> dict[str, Any]:
    root = repo_root / "src" / "continuum" / "migrations"
    files = []
    for name in names:
        path = root / name
        if not path.is_file():
            raise RuntimeError(f"required migration is missing: {name}")
        files.append(
            {
                "path": path.relative_to(repo_root).as_posix(),
                "sha256": sha256_bytes(path.read_bytes()),
            }
        )
    combined = "".join(f"{item['path']}:{item['sha256']}\n" for item in files)
    return {"files": files, "combined_sha256": sha256_bytes(combined.encode("utf-8"))}


def build_envelope(
    judge: dict[str, Any],
    scale: dict[str, Any],
    pressure: dict[str, Any],
    *,
    judge_bytes: bytes,
    scale_bytes: bytes,
    pressure_bytes: bytes,
    repo_root: Path,
    repository: str,
    commit_sha: str,
    workflow_run_id: int,
    workflow_url: str,
    release_tag: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if judge.get("schema_version") != 4:
        raise RuntimeError("judge evidence schema 4 is required")
    if not SHA_PATTERN.fullmatch(commit_sha):
        raise RuntimeError("release commit must be a full lowercase SHA")
    if workflow_run_id < 1 or not workflow_url.startswith("https://github.com/"):
        raise RuntimeError("release workflow lineage is invalid")
    if not release_tag or any(character.isspace() for character in release_tag):
        raise RuntimeError("release tag is invalid")

    source = judge["source"]
    vector = judge["vector_scale"]
    pressure_reference = judge["agent_pressure"]
    runtime = judge["runtime"]
    submission = judge["submission"]
    managed = judge["managed_mcp"]
    release_reference = judge["release_envelope"]
    scales = scale.get("scales", [])
    beams = [beam for item in scales for beam in item.get("beams", [])]
    beam_grid = [
        [beam.get("beam_size") for beam in item.get("beams", [])]
        for item in scales
    ]
    scale_sha = sha256_bytes(repository_text_bytes(scale_bytes))
    pressure_sha = sha256_bytes(repository_text_bytes(pressure_bytes))
    judge_sha = sha256_bytes(repository_text_bytes(judge_bytes))
    checks = {
        "submission_receipt_bound": (
            int(submission.get("id", 0)) > 0
            and submission.get("status") == "Submitted"
            and submission.get("project_url", "").startswith("https://devpost.com/")
            and submission.get("video_url", "").startswith("https://youtu")
            and bool(submission.get("project_updated_at"))
            and 90 <= float(submission.get("video_duration_seconds", 0)) <= 120
            and (
                SHA256_PATTERN.fullmatch(submission.get("video_sha256", ""))
                is not None
            )
        ),
        "application_workflow_bound": (
            int(source.get("workflow_run_id", 0)) > 0
            and SHA_PATTERN.fullmatch(source.get("deployment_head_sha", "")) is not None
            and (
                SHA256_PATTERN.fullmatch(source.get("artifact_sha256", ""))
                is not None
            )
        ),
        "migration_version_is_17": int(runtime.get("migration_version", 0)) >= 17,
        "migration_checksum_drift_absent": (
            runtime.get("migration_checksum_drift_absent") is True
        ),
        "runtime_scope_enforcement_passed": (
            runtime.get("authorization_mode") == "audited-tenant-control-plane"
            and runtime.get("cross_scope_fetch_denied") is True
            and runtime.get("forbidden_memory_visible") is False
            and runtime.get("tenant_control_plane_active") is True
            and runtime.get("control_plane_memory_denied") is True
            and runtime.get("temporary_migration_capability_absent") is True
            and runtime.get("control_plane_and_migrator_role_options_empty") is True
            and runtime.get("database_connections") == "bounded-pools-1-4"
        ),
        "vector_report_checksum_matches": scale_sha == vector.get("report_sha256"),
        "vector_workflow_head_matches": (
            scale.get("source_head") == vector.get("head_sha")
        ),
        "representative_scales_present": [
            item.get("row_count") for item in scales
        ]
        == [10_000, 50_000],
        "ann_selected_without_full_scan": (
            beam_grid == [[1, 32, 128, 512], [1, 32, 128, 512]]
            and all(
                beam.get("query_plan", {}).get("reports_vector_search") is True
                and beam.get("query_plan", {}).get("reports_full_scan") is False
                for beam in beams
            )
        ),
        "zero_benchmark_scope_leakage": bool(beams)
        and all(beam.get("cross_scope_leaked_rows") == 0 for beam in beams),
        "vector_gate_passed": scale.get("gate", {}).get("status") == "PASS",
        "agent_pressure_checksum_matches": (
            pressure_sha == pressure_reference.get("report_sha256")
        ),
        "agent_pressure_workflow_head_matches": (
            pressure.get("source_head") == pressure_reference.get("head_sha")
        ),
        "agent_pressure_artifact_digest_bound": (
            SHA256_PATTERN.fullmatch(
                pressure_reference.get("workflow_artifact_sha256", "")
            )
            is not None
        ),
        "agent_pressure_levels_present": [
            item.get("concurrent_agents") for item in pressure.get("levels", [])
        ]
        == [10, 25, 50],
        "agent_pressure_gate_passed": (
            pressure.get("gate", {}).get("status") == "PASS"
            and pressure.get("gate", {}).get("all_operations_completed") is True
            and pressure.get("gate", {}).get("cross_scope_leakage_zero") is True
            and pressure.get("gate", {}).get(
                "exactly_one_action_owner_per_level"
            )
            is True
            and pressure.get("gate", {}).get("pool_recovery_passed") is True
            and pressure.get("gate", {}).get("synthetic_rows_cleaned") is True
        ),
        "public_release_reference_matches": (
            release_reference.get("tag") == release_tag
            and release_reference.get("release_url")
            == f"https://github.com/{repository}/releases/tag/{release_tag}"
            and release_reference.get("release_api_url")
            == f"https://api.github.com/repos/{repository}/releases/tags/{release_tag}"
            and release_reference.get("asset_name")
            == "continuum-release-envelope-v1.json"
            and release_reference.get("asset_url")
            == (
                f"https://github.com/{repository}/releases/download/"
                f"{release_tag}/continuum-release-envelope-v1.json"
            )
        ),
        "key_rotation_retired_old_material": (
            int(managed.get("rotation_workflow_run_id", 0)) > 0
            and managed.get("read_tools") == ["list_databases", "list_tables"]
            and managed.get("write_denied_before_secret_access") is True
            and managed.get("old_provider_key_deleted") is True
            and managed.get("temporary_github_secret_deleted") is True
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError("release envelope gates failed: " + ", ".join(failed))

    return {
        "schema_version": 1,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "claim_boundary": "One immutable competition release receipt; no credential values or database rows are included.",
        "release": {
            "repository": repository,
            "commit_sha": commit_sha,
            "workflow_run_id": workflow_run_id,
            "workflow_url": workflow_url,
            "tag": release_tag,
            "publication_contract": "GitHub immutable release; workflow verifies immutable=true after draft publication.",
        },
        "application_deployment": {
            "head_sha": source["deployment_head_sha"],
            "workflow_run_id": source["workflow_run_id"],
            "workflow_attempt": source["workflow_attempt"],
            "workflow_url": source["workflow_url"],
            "artifact_sha256": source["artifact_sha256"],
            "migration_version": runtime["migration_version"],
            "migration_checksum_drift_absent": runtime[
                "migration_checksum_drift_absent"
            ],
            "authorization_mode": runtime["authorization_mode"],
            "binding_version": runtime["binding_version"],
            "binding_event": runtime["binding_event"],
        },
        "vector_benchmark": {
            "head_sha": vector["head_sha"],
            "workflow_run_id": vector["workflow_run_id"],
            "workflow_url": vector["workflow_url"],
            "report_sha256": scale_sha,
            "row_counts": [item["row_count"] for item in scales],
            "beam_sizes": scale["beam_sizes"],
            "gate": scale["gate"],
        },
        "agent_pressure": {
            "head_sha": pressure_reference["head_sha"],
            "workflow_run_id": pressure_reference["workflow_run_id"],
            "workflow_url": pressure_reference["workflow_url"],
            "report_sha256": pressure_sha,
            "workflow_artifact_sha256": pressure_reference[
                "workflow_artifact_sha256"
            ],
            "concurrent_agents": [
                item["concurrent_agents"] for item in pressure["levels"]
            ],
            "bounded_connection_pool_max": pressure["database"][
                "bounded_connection_pool_max"
            ],
            "gate": pressure["gate"],
        },
        "public_judge_evidence": {
            "url": judge["public_demo"]["evidence_url"],
            "sha256": judge_sha,
            "schema_version": judge["schema_version"],
        },
        "public_release_reference": release_reference,
        "database_policy": {
            "rls": _migration_receipt(repo_root, RLS_MIGRATIONS),
            "tenant_control_plane": _migration_receipt(repo_root, CONTROL_PLANE_MIGRATIONS),
            "vector_contract": _migration_receipt(repo_root, VECTOR_CONTRACT_MIGRATIONS),
        },
        "managed_mcp_key_rotation": managed,
        "devpost": submission,
        "public_endpoints": {
            "demo": judge["public_demo"]["url"],
            "verifier": judge["public_demo"]["verifier_url"],
            "mcp_health": runtime["health_url"],
            "video": submission["video_url"],
        },
        "gates": {"status": "PASS", "checks": checks},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge-evidence", type=Path, required=True)
    parser.add_argument("--scale-evidence", type=Path, required=True)
    parser.add_argument("--pressure-evidence", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--workflow-run-id", type=int, required=True)
    parser.add_argument("--workflow-url", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    judge_bytes = args.judge_evidence.read_bytes()
    scale_bytes = args.scale_evidence.read_bytes()
    pressure_bytes = args.pressure_evidence.read_bytes()
    envelope = build_envelope(
        json.loads(judge_bytes),
        json.loads(scale_bytes),
        json.loads(pressure_bytes),
        judge_bytes=judge_bytes,
        scale_bytes=scale_bytes,
        pressure_bytes=pressure_bytes,
        repo_root=args.repo_root.resolve(),
        repository=args.repository,
        commit_sha=args.commit_sha,
        workflow_run_id=args.workflow_run_id,
        workflow_url=args.workflow_url,
        release_tag=args.release_tag,
    )
    encoded = (json.dumps(envelope, indent=2, sort_keys=True) + "\n").encode("utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        f"{sha256_bytes(encoded)}  {args.output.name}\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "envelope_sha256": sha256_bytes(encoded)}, sort_keys=True))


if __name__ == "__main__":
    main()
