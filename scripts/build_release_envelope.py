"""Build a fail-closed release envelope from reviewed public receipts."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from continuum.drilldown import build_public_episode_drilldown
from continuum.release_guardian import build_public_release_guardian
from continuum.release_guardian_replication import (
    build_public_release_guardian_replication,
)


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
ENVELOPE_ASSET = "continuum-release-envelope-v2.json"
SANDBOX_ASSET = "sandbox-provider-proof.json"
ABLATION_ASSET = "agent-ablation-v3.json"
DRILLDOWN_ASSET = "episode-drilldown-v1.json"
RELEASE_GUARDIAN_ASSET = "release-guardian-v1.json"
RELEASE_GUARDIAN_REPLICATION_ASSET = "release-guardian-replication-v1.json"
SIGNATURE_BUNDLE_ASSET = "continuum-release-envelope-v2.sigstore.jsonl"


def build_public_ablation_aggregate(
    report: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the exact non-observation projection safe for public judges."""

    fields = (
        "schema_version",
        "source_head",
        "deployment_artifact_sha256",
        "evaluation_id",
        "generated_at",
        "agent_model",
        "agent_region",
        "embedding_model",
        "embedding_region",
        "migration_version",
        "provider",
        "retained_for_judge_evidence",
        "seed_semantics",
        "synthetic_non_effecting",
        "methodology",
        "arms",
        "continuum_lift_percentage_points",
        "paired_comparisons",
        "paired_safety_comparisons",
        "variant_counts",
    )
    missing = [field for field in fields if field not in report]
    if missing:
        raise RuntimeError(
            "ablation report is missing public fields: " + ", ".join(missing)
        )
    return {field: deepcopy(report[field]) for field in fields}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def repository_text_bytes(value: bytes) -> bytes:
    """Match the LF-normalized Git blob and GitHub Pages representation."""

    return value.replace(b"\r\n", b"\n")


def _finite_metric(value: Any) -> float:
    """Normalize optional report metrics without weakening release gates."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return float("nan")
    result = float(value)
    return (
        result
        if result == result and abs(result) != float("inf")
        else float("nan")
    )


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
                "sha256": sha256_bytes(repository_text_bytes(path.read_bytes())),
            }
        )
    combined = "".join(f"{item['path']}:{item['sha256']}\n" for item in files)
    return {"files": files, "combined_sha256": sha256_bytes(combined.encode("utf-8"))}


def build_envelope(
    judge: dict[str, Any],
    scale: dict[str, Any],
    pressure: dict[str, Any],
    sandbox: dict[str, Any],
    ablation: dict[str, Any],
    ablation_aggregate: dict[str, Any],
    episode_drilldown: dict[str, Any],
    release_guardian: dict[str, Any],
    release_guardian_public: dict[str, Any],
    release_guardian_replication: dict[str, Any] | None = None,
    *,
    judge_bytes: bytes,
    scale_bytes: bytes,
    pressure_bytes: bytes,
    sandbox_bytes: bytes,
    ablation_bytes: bytes,
    ablation_aggregate_bytes: bytes,
    episode_drilldown_bytes: bytes,
    release_guardian_bytes: bytes,
    release_guardian_public_bytes: bytes,
    release_guardian_replication_bytes: bytes = b"",
    repo_root: Path,
    repository: str,
    commit_sha: str,
    workflow_run_id: int,
    workflow_url: str,
    release_tag: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if judge.get("schema_version") != 8:
        raise RuntimeError("judge evidence schema 8 is required")
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
    lineage = judge["lineage"]
    sandbox_reference = judge["sandbox_provider"]
    ablation_reference = judge["agent_ablation"]
    drilldown_reference = judge["episode_drilldown"]
    guardian_reference = judge["release_guardian"]
    replication_reference = judge.get("time_distributed_replication")
    database_policy_reference = judge["database_policy"]
    release_reference = judge["release_envelope"]
    network_sign_once = judge["network_sign_once"]
    release_transaction = judge["release_transaction"]
    scales = scale.get("scales", [])
    beams = [beam for item in scales for beam in item.get("beams", [])]
    beam_grid = [
        [beam.get("beam_size") for beam in item.get("beams", [])]
        for item in scales
    ]
    scale_sha = sha256_bytes(repository_text_bytes(scale_bytes))
    pressure_sha = sha256_bytes(repository_text_bytes(pressure_bytes))
    judge_sha = sha256_bytes(repository_text_bytes(judge_bytes))
    sandbox_sha = sha256_bytes(repository_text_bytes(sandbox_bytes))
    ablation_sha = sha256_bytes(repository_text_bytes(ablation_bytes))
    ablation_aggregate_sha = sha256_bytes(
        repository_text_bytes(ablation_aggregate_bytes)
    )
    episode_drilldown_sha = sha256_bytes(
        repository_text_bytes(episode_drilldown_bytes)
    )
    release_guardian_sha = sha256_bytes(
        repository_text_bytes(release_guardian_bytes)
    )
    release_guardian_public_sha = sha256_bytes(
        repository_text_bytes(release_guardian_public_bytes)
    )
    release_guardian_replication_sha = (
        sha256_bytes(repository_text_bytes(release_guardian_replication_bytes))
        if release_guardian_replication is not None
        else ""
    )
    public_ablation = build_public_ablation_aggregate(ablation)
    public_drilldown = build_public_episode_drilldown(ablation)
    public_guardian = build_public_release_guardian(release_guardian)
    public_replication = (
        build_public_release_guardian_replication(release_guardian_replication)
        if release_guardian_replication is not None
        else None
    )
    ablation_arms = ablation.get("arms", {})
    continuum_metrics = ablation_arms.get("continuum", {})
    raw_metrics = ablation_arms.get("raw_rag", {})
    stateless_metrics = ablation_arms.get("stateless", {})
    grounding_failure_code = (
        "ORCHESTRATION_PROPOSAL_CITES_A_HANDLE_NOT_ISSUED_BY_SEARCH"
    )
    grounding_failures = sum(
        int(metrics.get("failure_codes", {}).get(grounding_failure_code, 0))
        for metrics in ablation_arms.values()
        if isinstance(metrics, Mapping)
    )
    rls_receipt = _migration_receipt(repo_root, RLS_MIGRATIONS)
    control_plane_receipt = _migration_receipt(
        repo_root,
        CONTROL_PLANE_MIGRATIONS,
    )
    vector_contract_receipt = _migration_receipt(
        repo_root,
        VECTOR_CONTRACT_MIGRATIONS,
    )
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
        "baseline_lineage_bound": (
            lineage.get("baseline_runtime_sha")
            == "1291e2707880700492fe1d7cd431bcba03d68b4c"
            and lineage.get("baseline_documentation_sha")
            == "2a94b4653ab0efe6f2ddeb8701ab05bdbaf403e1"
            and lineage.get("candidate_runtime_sha")
            == source.get("deployment_head_sha")
            and lineage.get("candidate_runtime_sha")
            == ablation_reference.get("head_sha")
        ),
        "runtime_matches_ablation": (
            source.get("workflow_run_id") == ablation_reference.get("workflow_run_id")
            and source.get("deployment_head_sha") == ablation.get("source_head")
            and source.get("artifact_sha256")
            == ablation.get("deployment_artifact_sha256")
        ),
        "sandbox_artifact_bound": (
            int(sandbox_reference.get("workflow_run_id", 0)) > 0
            and int(sandbox_reference.get("artifact_id", 0)) > 0
            and sandbox_reference.get("head_sha")
            == lineage.get("baseline_runtime_sha")
            and sandbox_reference.get("artifact_name")
            == f"aws-sandbox-provider-proof-{lineage.get('baseline_runtime_sha')}"
            and SHA256_PATTERN.fullmatch(
                sandbox_reference.get("artifact_archive_sha256", "")
            )
            is not None
            and sandbox_sha == sandbox_reference.get("report_sha256")
            and sandbox.get("source_head") == sandbox_reference.get("head_sha")
        ),
        "sandbox_contract_passed": (
            sandbox.get("schema_version") == 1
            and sandbox.get("send_count") == 2
            and sandbox.get("logical_effect_count") == 1
            and sandbox.get("receipt_lookup_matched") is True
            and sandbox.get("gate", {}).get("idempotency") == "PASS"
            and sandbox.get("gate", {}).get("receipt_lookup") == "PASS"
            and sandbox.get("gate", {}).get("sandbox_only") is True
            and sandbox.get("provider_capabilities", {}).get(
                "supports_idempotency"
            )
            is True
            and sandbox.get("provider_capabilities", {}).get("receipt_lookup")
            is True
            and sandbox.get("provider_capabilities", {}).get(
                "reconciliation_timeout_seconds"
            )
            == 30
        ),
        "ablation_artifact_bound": (
            int(ablation_reference.get("workflow_run_id", 0)) > 0
            and int(ablation_reference.get("artifact_id", 0)) > 0
            and ablation_reference.get("head_sha") == ablation.get("source_head")
            and ablation_reference.get("artifact_name")
            == f"continuum-agent-ablation-{ablation.get('source_head')}"
            and SHA256_PATTERN.fullmatch(
                ablation_reference.get("artifact_archive_sha256", "")
            )
            is not None
            and ablation_sha == ablation_reference.get("report_sha256")
            and ablation_aggregate_sha
            == ablation_reference.get("public_aggregate_sha256")
        ),
        "ablation_aggregate_matches_full_report": (
            ablation_aggregate == public_ablation
        ),
        "ablation_schema_and_population": (
            ablation.get("schema_version") == 3
            and ablation.get("episode_trace_schema_version") == 1
            and len(ablation.get("observations", [])) == 540
            and ablation.get("synthetic_non_effecting") is True
            and set(ablation_arms) == {"stateless", "raw_rag", "continuum"}
            and all(
                int(metrics.get("cases", 0)) == 180
                and int(metrics.get("memory_pressure_cases", 0)) == 90
                and int(metrics.get("recovery_cases", 0)) == 30
                and int(metrics.get("cross_scope_leak_count", -1)) == 0
                for metrics in ablation_arms.values()
            )
        ),
        "episode_drilldown_bound": (
            episode_drilldown == public_drilldown
            and episode_drilldown_sha == drilldown_reference.get("sha256")
            and episode_drilldown.get("source_head")
            == ablation_reference.get("head_sha")
            and episode_drilldown.get("evaluation_id")
            == drilldown_reference.get("evaluation_id")
            and episode_drilldown.get("population", {}).get("paired_episodes")
            == 180
            and episode_drilldown.get("population", {}).get("arm_observations")
            == 540
            and episode_drilldown.get("gate", {}).get("status") == "PASS"
            and episode_drilldown.get("gate", {}).get(
                "private_identifier_keys_present"
            )
            == []
        ),
        "release_guardian_artifact_bound": (
            guardian_reference.get("schema_version") == 1
            and int(guardian_reference.get("workflow_run_id", 0)) > 0
            and int(guardian_reference.get("artifact_id", 0)) > 0
            and guardian_reference.get("head_sha")
            == release_guardian.get("source_head")
            and guardian_reference.get("artifact_name")
            == (
                "continuum-release-guardian-"
                + str(release_guardian.get("source_head"))
            )
            and SHA256_PATTERN.fullmatch(
                guardian_reference.get("artifact_archive_sha256", "")
            )
            is not None
            and release_guardian_sha
            == guardian_reference.get("report_sha256")
            and release_guardian_public_sha
            == guardian_reference.get("public_sha256")
            and release_guardian_public == public_guardian
        ),
        "real_provider_guardian_passed": (
            release_guardian.get("schema_version") == 1
            and release_guardian.get("real_external_provider") is True
            and release_guardian.get("provider")
            == "github-releases-disposable-sandbox"
            and release_guardian.get("methodology", {}).get("paired_cases")
            == 36
            and release_guardian.get("methodology", {}).get(
                "arm_observations"
            )
            == 72
            and release_guardian.get("gate", {}).get("status") == "PASS"
            and release_guardian.get("arms", {})
            .get("continuum", {})
            .get("provider_success_rate")
            == 1.0
            and release_guardian.get("arms", {})
            .get("continuum", {})
            .get("unsafe_proposals")
            == 0
            and release_guardian.get("arms", {})
            .get("continuum", {})
            .get("cleanup_residual_count")
            == 0
        ),
        "time_distributed_replication_artifact_bound": (
            replication_reference is None
            or (
                release_guardian_replication is not None
                and replication_reference.get("schema_version") == 1
                and int(replication_reference.get("workflow_run_id", 0)) > 0
                and int(replication_reference.get("artifact_id", 0)) > 0
                and replication_reference.get("head_sha")
                == release_guardian_replication.get("source_head")
                and replication_reference.get("artifact_name")
                == (
                    "continuum-release-guardian-replication-"
                    + str(release_guardian_replication.get("source_head"))
                )
                and SHA256_PATTERN.fullmatch(
                    str(replication_reference.get("artifact_archive_sha256", ""))
                )
                is not None
                and release_guardian_replication_sha
                == replication_reference.get("report_sha256")
                == replication_reference.get("public_sha256")
                and release_guardian_replication == public_replication
            )
        ),
        "time_distributed_replication_passed": (
            replication_reference is None
            or (
                release_guardian_replication is not None
                and release_guardian_replication.get("schema_version") == 1
                and release_guardian_replication.get("real_external_provider")
                is True
                and release_guardian_replication.get("methodology", {}).get(
                    "paired_cases"
                )
                == 180
                and release_guardian_replication.get("methodology", {}).get(
                    "arm_observations"
                )
                == 360
                and release_guardian_replication.get("replication_set", {}).get(
                    "replication_count"
                )
                == 5
                and release_guardian_replication.get("replication_set", {}).get(
                    "minimum_observed_start_separation_seconds", 0
                )
                >= 300
                and release_guardian_replication.get("gate", {}).get("status")
                == "PASS"
                and release_guardian_replication.get("arms", {})
                .get("continuum", {})
                .get("unsafe_proposals")
                == 0
                and release_guardian_replication.get("arms", {})
                .get("continuum", {})
                .get("false_canonical_promotions")
                == 0
                and release_guardian_replication.get("arms", {})
                .get("continuum", {})
                .get("cleanup_residual_count")
                == 0
            )
        ),
        "citation_grounding_failures_zero": grounding_failures == 0,
        "public_rls_checksum_matches_source": (
            database_policy_reference.get("rls_combined_sha256")
            == rls_receipt["combined_sha256"]
        ),
        "paired_memory_pressure_differentiates": (
            _finite_metric(
                raw_metrics.get("unsafe_proposal_rate_under_memory_pressure")
            )
            > _finite_metric(
                continuum_metrics.get(
                    "unsafe_proposal_rate_under_memory_pressure",
                )
            )
            and _finite_metric(raw_metrics.get("unsafe_memory_exposure_rate"))
            > _finite_metric(
                continuum_metrics.get("unsafe_memory_exposure_rate")
            )
            and _finite_metric(raw_metrics.get("poison_exposure_rate"))
            > _finite_metric(continuum_metrics.get("poison_exposure_rate"))
            and _finite_metric(continuum_metrics.get("verified_outcome_success_rate"))
            > _finite_metric(raw_metrics.get("verified_outcome_success_rate"))
            and _finite_metric(continuum_metrics.get("canonical_promotion_precision"))
            > _finite_metric(raw_metrics.get("canonical_promotion_precision"))
            and _finite_metric(continuum_metrics.get("recovery_success_rate"))
            >= _finite_metric(raw_metrics.get("recovery_success_rate"))
            and int(continuum_metrics.get("false_canonical_promotions", -1)) == 0
            and int(stateless_metrics.get("false_canonical_promotions", -1)) == 0
        ),
        "migration_version_is_31": int(runtime.get("migration_version", 0)) >= 31,
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
            and release_reference.get("asset_name") == ENVELOPE_ASSET
            and release_reference.get("asset_url")
            == (
                f"https://github.com/{repository}/releases/download/"
                f"{release_tag}/{ENVELOPE_ASSET}"
            )
            and release_reference.get("sandbox_asset_name") == SANDBOX_ASSET
            and release_reference.get("sandbox_asset_url")
            == (
                f"https://github.com/{repository}/releases/download/"
                f"{release_tag}/{SANDBOX_ASSET}"
            )
            and release_reference.get("ablation_asset_name") == ABLATION_ASSET
            and release_reference.get("ablation_asset_url")
            == (
                f"https://github.com/{repository}/releases/download/"
                f"{release_tag}/{ABLATION_ASSET}"
            )
            and release_reference.get("drilldown_asset_name")
            == DRILLDOWN_ASSET
            and release_reference.get("drilldown_asset_url")
            == (
                f"https://github.com/{repository}/releases/download/"
                f"{release_tag}/{DRILLDOWN_ASSET}"
            )
            and release_reference.get("guardian_asset_name")
            == RELEASE_GUARDIAN_ASSET
            and release_reference.get("guardian_asset_url")
            == (
                f"https://github.com/{repository}/releases/download/"
                f"{release_tag}/{RELEASE_GUARDIAN_ASSET}"
            )
            and (
                replication_reference is None
                or (
                    release_reference.get("replication_asset_name")
                    == RELEASE_GUARDIAN_REPLICATION_ASSET
                    and release_reference.get("replication_asset_url")
                    == (
                        f"https://github.com/{repository}/releases/download/"
                        f"{release_tag}/{RELEASE_GUARDIAN_REPLICATION_ASSET}"
                    )
                )
            )
        ),
        "network_sign_once_contract_bound": (
            network_sign_once.get("schema_version") == 2
            and network_sign_once.get("attestation_api_template")
            == (
                f"https://api.github.com/repos/{repository}/attestations/"
                "sha256:{digest}"
            )
            and network_sign_once.get("author_bundle_public_url")
            == (
                judge["public_demo"]["url"].rstrip("/")
                + f"/evidence/{SIGNATURE_BUNDLE_ASSET}"
            )
            and network_sign_once.get("author_bundle_asset_name")
            == SIGNATURE_BUNDLE_ASSET
            and network_sign_once.get("network_bundle_public_url")
            == (
                judge["public_demo"]["url"].rstrip("/")
                + "/evidence/continuum-release-envelope-v2."
                "network-attestations.jsonl"
            )
            and network_sign_once.get("network_bundle_file_name")
            == "continuum-release-envelope-v2.network-attestations.jsonl"
            and network_sign_once.get("subject_name") == ENVELOPE_ASSET
            and network_sign_once.get("author_predicate_type")
            == "https://slsa.dev/provenance/v1"
            and network_sign_once.get("signer_workflow")
            == f"{repository}/.github/workflows/release-envelope.yml"
            and network_sign_once.get("source_ref") == "refs/heads/main"
            and network_sign_once.get("runner_environment")
            == "github-hosted"
            and network_sign_once.get("transparency_log")
            == "https://rekor.sigstore.dev"
            and network_sign_once.get("platform_predicate_type")
            == "https://in-toto.io/attestation/release/v0.2"
            and network_sign_once.get("platform_signer_identity")
            == "https://dotcom.releases.github.com"
            and network_sign_once.get(
                "required_author_attestation_count"
            )
            == 1
            and network_sign_once.get(
                "required_platform_attestation_count"
            )
            == 1
            and network_sign_once.get("required_total_attestation_count")
            == 2
        ),
        "release_transaction_contract_bound": (
            release_transaction.get("schema_version") == 1
            and release_transaction.get("coordinator_script")
            == "scripts/release_transaction_coordinator.py"
            and release_transaction.get("receipt_asset_name")
            == "release-transaction-receipt.json"
            and release_transaction.get("public_receipt_url")
            == (
                judge["public_demo"]["url"].rstrip("/")
                + "/evidence/release-transaction-receipt.json"
            )
            and release_transaction.get("states")
            == [
                "PREPARED",
                "AUTHOR_ATTESTED",
                "ASSETS_UPLOADED",
                "IMMUTABLE",
                "PAGES_MATERIALIZED",
            ]
            and release_transaction.get("required_terminal_state")
            == "PAGES_MATERIALIZED"
            and release_transaction.get("ambiguous_state_fails_closed") is True
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
        "schema_version": 2,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "claim_boundary": "One immutable competition release receipt; no credential values or database rows are included.",
        "release": {
            "repository": repository,
            "commit_sha": commit_sha,
            "workflow_run_id": workflow_run_id,
            "workflow_url": workflow_url,
            "tag": release_tag,
            "publication_contract": "GitHub immutable release; workflow verifies immutable=true after draft publication.",
            "assets": {
                "envelope": release_reference["asset_url"],
                "author_signature_bundle": (
                    f"https://github.com/{repository}/releases/download/"
                    f"{release_tag}/{SIGNATURE_BUNDLE_ASSET}"
                ),
                "sandbox_provider": release_reference["sandbox_asset_url"],
                "agent_ablation": release_reference["ablation_asset_url"],
                "episode_drilldown": release_reference[
                    "drilldown_asset_url"
                ],
                "release_guardian": release_reference[
                    "guardian_asset_url"
                ],
                **(
                    {
                        "time_distributed_replication": release_reference[
                            "replication_asset_url"
                        ]
                    }
                    if replication_reference is not None
                    else {}
                ),
            },
        },
        "lineage": {
            "baseline_runtime_sha": lineage["baseline_runtime_sha"],
            "baseline_documentation_sha": lineage[
                "baseline_documentation_sha"
            ],
            "candidate_runtime_sha": lineage["candidate_runtime_sha"],
            "release_documentation_sha": commit_sha,
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
        "sandbox_provider": {
            "head_sha": sandbox_reference["head_sha"],
            "workflow_run_id": sandbox_reference["workflow_run_id"],
            "workflow_url": sandbox_reference["workflow_url"],
            "artifact_id": sandbox_reference["artifact_id"],
            "artifact_name": sandbox_reference["artifact_name"],
            "artifact_archive_sha256": sandbox_reference[
                "artifact_archive_sha256"
            ],
            "report_sha256": sandbox_sha,
            "immutable_release_asset_url": release_reference[
                "sandbox_asset_url"
            ],
            "provider_capabilities": sandbox["provider_capabilities"],
            "gate": sandbox["gate"],
        },
        "agent_ablation": {
            "head_sha": ablation_reference["head_sha"],
            "deployment_artifact_sha256": ablation[
                "deployment_artifact_sha256"
            ],
            "workflow_run_id": ablation_reference["workflow_run_id"],
            "workflow_url": ablation_reference["workflow_url"],
            "artifact_id": ablation_reference["artifact_id"],
            "artifact_name": ablation_reference["artifact_name"],
            "artifact_archive_sha256": ablation_reference[
                "artifact_archive_sha256"
            ],
            "report_sha256": ablation_sha,
            "public_aggregate_sha256": ablation_aggregate_sha,
            "public_aggregate_url": ablation_reference[
                "public_aggregate_url"
            ],
            "immutable_release_asset_url": release_reference[
                "ablation_asset_url"
            ],
            "methodology": ablation["methodology"],
            "arms": ablation["arms"],
            "paired_comparisons": ablation["paired_comparisons"],
            "paired_safety_comparisons": ablation[
                "paired_safety_comparisons"
            ],
        },
        "episode_drilldown": {
            "schema_version": episode_drilldown["schema_version"],
            "source_head": episode_drilldown["source_head"],
            "evaluation_id": episode_drilldown["evaluation_id"],
            "sha256": episode_drilldown_sha,
            "public_url": drilldown_reference["public_url"],
            "page_url": drilldown_reference["page_url"],
            "immutable_release_asset_url": release_reference[
                "drilldown_asset_url"
            ],
            "population": episode_drilldown["population"],
            "gate": episode_drilldown["gate"],
        },
        "release_guardian": {
            "head_sha": guardian_reference["head_sha"],
            "deployment_artifact_sha256": release_guardian[
                "deployment_artifact_sha256"
            ],
            "workflow_run_id": guardian_reference["workflow_run_id"],
            "workflow_url": guardian_reference["workflow_url"],
            "artifact_id": guardian_reference["artifact_id"],
            "artifact_name": guardian_reference["artifact_name"],
            "artifact_archive_sha256": guardian_reference[
                "artifact_archive_sha256"
            ],
            "report_sha256": release_guardian_sha,
            "public_sha256": release_guardian_public_sha,
            "public_url": guardian_reference["public_url"],
            "page_url": guardian_reference["page_url"],
            "immutable_release_asset_url": release_reference[
                "guardian_asset_url"
            ],
            "provider": release_guardian["provider"],
            "provider_capability_manifest": release_guardian[
                "provider_capability_manifest"
            ],
            "methodology": release_guardian["methodology"],
            "arms": release_guardian["arms"],
            "paired_comparison": release_guardian["paired_comparison"],
            "gate": release_guardian["gate"],
        },
        **(
            {
                "time_distributed_replication": {
                    "head_sha": replication_reference["head_sha"],
                    "workflow_run_id": replication_reference[
                        "workflow_run_id"
                    ],
                    "workflow_url": replication_reference["workflow_url"],
                    "artifact_id": replication_reference["artifact_id"],
                    "artifact_name": replication_reference["artifact_name"],
                    "artifact_archive_sha256": replication_reference[
                        "artifact_archive_sha256"
                    ],
                    "report_sha256": release_guardian_replication_sha,
                    "public_sha256": replication_reference["public_sha256"],
                    "public_url": replication_reference["public_url"],
                    "page_url": replication_reference["page_url"],
                    "immutable_release_asset_url": release_reference[
                        "replication_asset_url"
                    ],
                    "case_population_sha256": release_guardian_replication[
                        "case_population_sha256"
                    ],
                    "replication_set": release_guardian_replication[
                        "replication_set"
                    ],
                    "methodology": release_guardian_replication[
                        "methodology"
                    ],
                    "arms": release_guardian_replication["arms"],
                    "paired_comparison": release_guardian_replication[
                        "paired_comparison"
                    ],
                    "gate": release_guardian_replication["gate"],
                }
            }
            if replication_reference is not None
            and release_guardian_replication is not None
            else {}
        ),
        "public_judge_evidence": {
            "url": judge["public_demo"]["evidence_url"],
            "sha256": judge_sha,
            "schema_version": judge["schema_version"],
        },
        "public_release_reference": release_reference,
        "network_sign_once": network_sign_once,
        "release_transaction": release_transaction,
        "database_policy": {
            "rls": rls_receipt,
            "tenant_control_plane": control_plane_receipt,
            "vector_contract": vector_contract_receipt,
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
    parser.add_argument("--sandbox-evidence", type=Path, required=True)
    parser.add_argument("--ablation-evidence", type=Path, required=True)
    parser.add_argument("--ablation-aggregate", type=Path, required=True)
    parser.add_argument("--episode-drilldown", type=Path, required=True)
    parser.add_argument("--release-guardian-evidence", type=Path, required=True)
    parser.add_argument("--release-guardian-public", type=Path, required=True)
    parser.add_argument("--release-guardian-replication", type=Path)
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
    sandbox_bytes = args.sandbox_evidence.read_bytes()
    ablation_bytes = args.ablation_evidence.read_bytes()
    ablation_aggregate_bytes = args.ablation_aggregate.read_bytes()
    episode_drilldown_bytes = args.episode_drilldown.read_bytes()
    release_guardian_bytes = args.release_guardian_evidence.read_bytes()
    release_guardian_public_bytes = args.release_guardian_public.read_bytes()
    release_guardian_replication_bytes = (
        args.release_guardian_replication.read_bytes()
        if args.release_guardian_replication is not None
        else b""
    )
    envelope = build_envelope(
        json.loads(judge_bytes),
        json.loads(scale_bytes),
        json.loads(pressure_bytes),
        json.loads(sandbox_bytes),
        json.loads(ablation_bytes),
        json.loads(ablation_aggregate_bytes),
        json.loads(episode_drilldown_bytes),
        json.loads(release_guardian_bytes),
        json.loads(release_guardian_public_bytes),
        (
            json.loads(release_guardian_replication_bytes)
            if release_guardian_replication_bytes
            else None
        ),
        judge_bytes=judge_bytes,
        scale_bytes=scale_bytes,
        pressure_bytes=pressure_bytes,
        sandbox_bytes=sandbox_bytes,
        ablation_bytes=ablation_bytes,
        ablation_aggregate_bytes=ablation_aggregate_bytes,
        episode_drilldown_bytes=episode_drilldown_bytes,
        release_guardian_bytes=release_guardian_bytes,
        release_guardian_public_bytes=release_guardian_public_bytes,
        release_guardian_replication_bytes=release_guardian_replication_bytes,
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
