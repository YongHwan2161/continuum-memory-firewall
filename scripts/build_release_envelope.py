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

from continuum.adaptive_diagnosis import build_public_adaptive_diagnosis
from continuum.blind_holdout import build_public_blind_holdout
from continuum.ci_recovery import build_public_ci_recovery
from continuum.drilldown import build_public_episode_drilldown
from continuum.evidence_story import verify_evidence_story_receipt
from continuum.release_guardian import build_public_release_guardian
from continuum.release_guardian_replication import (
    build_public_release_guardian_replication,
)
from continuum.online_memory_lineage import validate_public_online_memory_lineage
from continuum.outcome_replay_proof import validate_outcome_replay_proof
from continuum.sequential_blind import build_public_sequential_blind
from continuum.transfer_firewall import build_public_transfer_firewall
from scripts.offline_judge_capsule import (
    CAPSULE_ASSET_NAME,
    verify_capsule,
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
BLIND_HOLDOUT_ASSET = "blind-holdout-v1.json"
SEQUENTIAL_BLIND_ASSET = "sequential-blind-v1.json"
EVIDENCE_STORY_ASSET = "evidence-story-v1.json"
CI_RECOVERY_ASSET = "ci-recovery-v1.json"
ADAPTIVE_DIAGNOSIS_ASSET = "adaptive-diagnosis-v1.json"
TRANSFER_FIREWALL_ASSET = "transfer-firewall-v1.json"
ONLINE_MEMORY_LINEAGE_ASSET = "online-memory-lineage-v1.json"
OUTCOME_REPLAY_CAS_ASSET = "outcome-replay-cas-v1.json"
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
    blind_holdout_public: dict[str, Any] | None = None,
    sequential_blind_public: dict[str, Any] | None = None,
    evidence_story: dict[str, Any] | None = None,
    ci_recovery_public: dict[str, Any] | None = None,
    adaptive_diagnosis_public: dict[str, Any] | None = None,
    transfer_firewall_public: dict[str, Any] | None = None,
    online_memory_lineage_public: dict[str, Any] | None = None,
    outcome_replay_cas_public: dict[str, Any] | None = None,
    offline_judge_capsule: dict[str, Any] | None = None,
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
    blind_holdout_public_bytes: bytes = b"",
    sequential_blind_public_bytes: bytes = b"",
    evidence_story_bytes: bytes = b"",
    ci_recovery_public_bytes: bytes = b"",
    adaptive_diagnosis_public_bytes: bytes = b"",
    transfer_firewall_public_bytes: bytes = b"",
    online_memory_lineage_public_bytes: bytes = b"",
    outcome_replay_cas_public_bytes: bytes = b"",
    offline_judge_capsule_bytes: bytes = b"",
    repo_root: Path,
    repository: str,
    commit_sha: str,
    workflow_run_id: int,
    workflow_url: str,
    release_tag: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if judge.get("schema_version") not in {8, 9, 10, 11, 12, 13, 14, 15, 16}:
        raise RuntimeError("judge evidence schema 8 through 16 is required")
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
    blind_reference = judge.get("blind_holdout")
    sequential_reference = judge.get("sequential_blind_campaign")
    story_reference = judge.get("evidence_story")
    ci_recovery_reference = judge.get("ci_recovery")
    adaptive_diagnosis_reference = judge.get("adaptive_diagnosis")
    transfer_firewall_reference = judge.get("transfer_firewall")
    online_memory_lineage_reference = judge.get("online_memory_lineage")
    outcome_replay_cas_reference = judge.get("outcome_replay_cas")
    offline_judge_reference = judge.get("offline_judge_capsule")
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
    blind_holdout_public_sha = (
        sha256_bytes(repository_text_bytes(blind_holdout_public_bytes))
        if blind_holdout_public is not None
        else ""
    )
    sequential_blind_public_sha = (
        sha256_bytes(repository_text_bytes(sequential_blind_public_bytes))
        if sequential_blind_public is not None
        else ""
    )
    evidence_story_sha = (
        sha256_bytes(repository_text_bytes(evidence_story_bytes))
        if evidence_story is not None
        else ""
    )
    ci_recovery_public_sha = (
        sha256_bytes(repository_text_bytes(ci_recovery_public_bytes))
        if ci_recovery_public is not None
        else ""
    )
    adaptive_diagnosis_public_sha = (
        sha256_bytes(repository_text_bytes(adaptive_diagnosis_public_bytes))
        if adaptive_diagnosis_public is not None
        else ""
    )
    transfer_firewall_public_sha = (
        sha256_bytes(repository_text_bytes(transfer_firewall_public_bytes))
        if transfer_firewall_public is not None
        else ""
    )
    online_memory_lineage_public_sha = (
        sha256_bytes(repository_text_bytes(online_memory_lineage_public_bytes))
        if online_memory_lineage_public is not None
        else ""
    )
    outcome_replay_cas_public_sha = (
        sha256_bytes(repository_text_bytes(outcome_replay_cas_public_bytes))
        if outcome_replay_cas_public is not None
        else ""
    )
    offline_judge_capsule_sha = (
        sha256_bytes(offline_judge_capsule_bytes)
        if offline_judge_capsule is not None
        else ""
    )
    offline_judge_result = (
        verify_capsule(offline_judge_capsule)
        if offline_judge_capsule is not None
        else None
    )
    public_ablation = build_public_ablation_aggregate(ablation)
    public_drilldown = build_public_episode_drilldown(ablation)
    public_guardian = build_public_release_guardian(release_guardian)
    public_replication = (
        build_public_release_guardian_replication(release_guardian_replication)
        if release_guardian_replication is not None
        else None
    )
    public_blind_holdout = (
        build_public_blind_holdout(blind_holdout_public)
        if blind_holdout_public is not None
        else None
    )
    public_sequential_blind = (
        build_public_sequential_blind(sequential_blind_public)
        if sequential_blind_public is not None
        else None
    )
    public_ci_recovery = (
        build_public_ci_recovery(ci_recovery_public)
        if ci_recovery_public is not None
        else None
    )
    public_adaptive_diagnosis = (
        build_public_adaptive_diagnosis(adaptive_diagnosis_public)
        if adaptive_diagnosis_public is not None
        else None
    )
    public_transfer_firewall = (
        build_public_transfer_firewall(transfer_firewall_public)
        if transfer_firewall_public is not None
        else None
    )
    if online_memory_lineage_public is not None:
        validate_public_online_memory_lineage(online_memory_lineage_public)
    if outcome_replay_cas_public is not None:
        validate_outcome_replay_proof(outcome_replay_cas_public)
    adaptive_receipts = (
        [
            item["provider_receipt"]
            for item in adaptive_diagnosis_public.get("calibration", [])
        ]
        + [
            receipt
            for item in adaptive_diagnosis_public.get("observations", [])
            for receipt in item.get("diagnostic_receipts", [])
        ]
        + [
            item["provider_receipt"]
            for item in adaptive_diagnosis_public.get("observations", [])
        ]
        if adaptive_diagnosis_public is not None
        else []
    )
    transfer_receipts = (
        [
            item["provider_receipt"]
            for item in transfer_firewall_public.get("source_calibration", [])
        ]
        + [
            item["provider_receipt"]
            for item in transfer_firewall_public.get("target_attestations", [])
        ]
        + [
            receipt
            for item in transfer_firewall_public.get("observations", [])
            for receipt in item.get("diagnostic_receipts", [])
        ]
        + [
            item["provider_receipt"]
            for item in transfer_firewall_public.get("observations", [])
        ]
        if transfer_firewall_public is not None
        else []
    )
    transfer_observations = (
        transfer_firewall_public.get("observations", [])
        if transfer_firewall_public is not None
        else []
    )
    transfer_source_fingerprints = {
        item.get("source_environment_fingerprint")
        for item in transfer_observations
    }
    transfer_target_fingerprints = {
        item.get("target_environment_fingerprint")
        for item in transfer_observations
    }
    transfer_gate_checks = (
        [
            value
            for key, value in transfer_firewall_public.get("gate", {}).items()
            if key != "status"
        ]
        if transfer_firewall_public is not None
        else []
    )
    sequential_replay = (
        sequential_blind_public.get("evaluation_replay")
        if sequential_blind_public is not None
        and isinstance(
            sequential_blind_public.get("evaluation_replay"), Mapping
        )
        else None
    )
    sequential_evaluator_head = (
        sequential_reference.get(
            "evaluator_head_sha", sequential_reference.get("head_sha")
        )
        if sequential_reference is not None
        else None
    )
    sequential_expected_artifact_name = None
    sequential_replay_receipts_bound = sequential_replay is None
    if sequential_reference is not None:
        if sequential_replay is None:
            sequential_expected_artifact_name = (
                "continuum-sequential-blind-"
                + str(sequential_reference.get("head_sha", ""))
                + "-"
                + str(sequential_reference.get("workflow_run_id", ""))
                + "-"
                + str(sequential_reference.get("workflow_attempt", ""))
            )
        else:
            candidate_workflow = sequential_replay.get("candidate_workflow", {})
            candidate_artifact = sequential_replay.get("candidate_artifact", {})
            candidate_run_id = sequential_reference.get(
                "candidate_workflow_run_id"
            )
            sequential_expected_artifact_name = (
                "continuum-sequential-blind-evaluator-"
                + str(candidate_run_id or "")
                + "-"
                + str(sequential_evaluator_head or "")
                + "-"
                + str(sequential_reference.get("workflow_run_id", ""))
                + "-"
                + str(sequential_reference.get("workflow_attempt", ""))
            )
            sequential_replay_receipts_bound = (
                sequential_replay.get("reason")
                == "github_runner_python_3_10_missing_strenum_before_scoring"
                and sequential_replay.get("evaluator_source_head")
                == sequential_evaluator_head
                and candidate_workflow.get("run_id") == candidate_run_id
                and candidate_workflow.get("run_attempt")
                == sequential_reference.get("candidate_workflow_attempt")
                and candidate_workflow.get("source_head")
                == sequential_reference.get("head_sha")
                and candidate_workflow.get("conclusion") == "failure"
                and candidate_workflow.get("candidate_step_conclusion")
                == "success"
                and candidate_workflow.get("cleanup_step_conclusion")
                == "success"
                and candidate_artifact.get("id")
                == sequential_reference.get("candidate_artifact_id")
                and candidate_artifact.get("name")
                == sequential_reference.get("candidate_artifact_name")
                and candidate_artifact.get("archive_sha256")
                == sequential_reference.get("candidate_artifact_archive_sha256")
                and sequential_reference.get("candidate_artifact_name")
                == (
                    "continuum-sequential-blind-"
                    + str(sequential_reference.get("head_sha", ""))
                    + "-"
                    + str(candidate_run_id or "")
                    + "-"
                    + str(
                        sequential_reference.get(
                            "candidate_workflow_attempt", ""
                        )
                    )
                )
                and SHA256_PATTERN.fullmatch(
                    str(
                        sequential_reference.get(
                            "candidate_artifact_archive_sha256", ""
                        )
                    )
                )
                is not None
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
        "blind_holdout_artifact_bound": (
            blind_reference is None
            or (
                blind_holdout_public is not None
                and int(blind_reference.get("workflow_run_id", 0)) > 0
                and int(blind_reference.get("artifact_id", 0)) > 0
                and blind_reference.get("head_sha")
                == blind_holdout_public.get("source_head")
                and blind_reference.get("artifact_name")
                == "continuum-blind-holdout-" + blind_reference.get("head_sha", "")
                and SHA256_PATTERN.fullmatch(
                    str(blind_reference.get("artifact_archive_sha256", ""))
                )
                is not None
                and blind_holdout_public_sha
                == blind_reference.get("public_sha256")
                and blind_holdout_public == public_blind_holdout
            )
        ),
        "blind_holdout_passed": (
            blind_reference is None
            or (
                blind_holdout_public is not None
                and blind_holdout_public.get("real_external_provider") is True
                and blind_holdout_public.get("providers") == ["github", "s3"]
                and blind_holdout_public.get("methodology", {}).get("paired_cases")
                == 60
                and blind_holdout_public.get("methodology", {}).get(
                    "arm_observations"
                )
                == 120
                and blind_holdout_public.get("methodology", {}).get(
                    "candidate_label_fields"
                )
                == 0
                and blind_holdout_public.get("methodology", {}).get(
                    "candidate_process_opened_labels"
                )
                is False
                and blind_holdout_public.get("gate", {}).get("status") == "PASS"
                and blind_holdout_public.get("arms", {})
                .get("continuum", {})
                .get("false_canonical_promotions")
                == 0
                and blind_holdout_public.get("arms", {})
                .get("continuum", {})
                .get("cross_scope_leak_count")
                == 0
                and blind_holdout_public.get("arms", {})
                .get("continuum", {})
                .get("cleanup_residual_count")
                == 0
                and blind_holdout_public.get("commitment", {}).get(
                    "commitment_sha256"
                )
                == blind_reference.get("commitment_sha256")
                and blind_holdout_public.get("seal_receipt", {}).get(
                    "receipt_sha256"
                )
                == blind_reference.get("seal_receipt_sha256")
            )
        ),
        "sequential_blind_artifact_bound": (
            judge.get("schema_version") < 9
            or (
                sequential_reference is not None
                and sequential_blind_public is not None
                and int(sequential_reference.get("workflow_run_id", 0)) > 0
                and int(sequential_reference.get("artifact_id", 0)) > 0
                and sequential_reference.get("head_sha")
                == sequential_blind_public.get("source_head")
                and sequential_reference.get("artifact_name")
                == sequential_expected_artifact_name
                and SHA_PATTERN.fullmatch(str(sequential_evaluator_head or ""))
                is not None
                and sequential_replay_receipts_bound
                and SHA256_PATTERN.fullmatch(
                    str(sequential_reference.get("artifact_archive_sha256", ""))
                )
                is not None
                and sequential_blind_public_sha
                == sequential_reference.get("public_sha256")
                and sequential_blind_public == public_sequential_blind
                and sequential_blind_public.get("campaign_id")
                == sequential_reference.get("campaign_id")
                and sequential_blind_public.get("campaign_manifest", {}).get(
                    "campaign_manifest_sha256"
                )
                == sequential_reference.get("campaign_manifest_sha256")
                and sequential_blind_public.get("campaign_seal_receipt", {}).get(
                    "receipt_sha256"
                )
                == sequential_reference.get("campaign_seal_receipt_sha256")
            )
        ),
        "sequential_blind_memory_compounding_passed": (
            judge.get("schema_version") < 9
            or (
                sequential_blind_public is not None
                and sequential_blind_public.get("real_external_provider") is True
                and sequential_blind_public.get("providers") == ["github", "s3"]
                and sequential_blind_public.get("methodology", {}).get(
                    "sealed_batches"
                )
                == 3
                and sequential_blind_public.get("methodology", {}).get("chains")
                == 36
                and sequential_blind_public.get("methodology", {}).get(
                    "arm_observations"
                )
                == 540
                and sequential_blind_public.get("methodology", {}).get(
                    "target_episodes_per_arm"
                )
                == 144
                and sequential_blind_public.get("methodology", {}).get(
                    "candidate_label_fields"
                )
                == 0
                and sequential_blind_public.get("methodology", {}).get(
                    "candidate_process_opened_labels"
                )
                is False
                and sequential_blind_public.get("methodology", {}).get(
                    "scored_after_all_arms_and_batches"
                )
                is True
                and all(
                    int(value) >= 300
                    for value in sequential_blind_public.get("methodology", {}).get(
                        "observed_start_separations_seconds", []
                    )
                )
                and len(
                    sequential_blind_public.get("methodology", {}).get(
                        "observed_start_separations_seconds", []
                    )
                )
                == 2
                and sequential_blind_public.get("gate", {}).get("status")
                == "PASS"
                and sequential_blind_public.get("arms", {})
                .get("continuum", {})
                .get("canonical_promotion_precision")
                == 1.0
                and sequential_blind_public.get("arms", {})
                .get("continuum", {})
                .get("false_canonical_promotions")
                == 0
                and sequential_blind_public.get("arms", {})
                .get("continuum", {})
                .get("cross_scope_leak_count")
                == 0
                and sequential_blind_public.get("arms", {})
                .get("continuum", {})
                .get("verified_memory_assisted_successes", 0)
                > 0
            )
        ),
        "evidence_story_receipt_bound": (
            judge.get("schema_version") < 10
            or (
                story_reference is not None
                and evidence_story is not None
                and evidence_story_sha == story_reference.get("public_sha256")
                and verify_evidence_story_receipt(evidence_story)
                and evidence_story.get("gate", {}).get("status") == "PASS"
                and evidence_story.get("source_release", {}).get(
                    "sequential_asset_sha256"
                )
                == sequential_reference.get("public_sha256")
                == story_reference.get("source_sequential_sha256")
                and evidence_story.get("source_release", {}).get("tag")
                == story_reference.get("source_release_tag")
                and evidence_story.get("source_release", {}).get("target")
                == story_reference.get("source_release_target")
                and evidence_story.get("source_release", {}).get(
                    "envelope_sha256"
                )
                == story_reference.get("source_release_envelope_sha256")
                and evidence_story.get("receipt_sha256")
                == story_reference.get("story_receipt_sha256")
                and story_reference.get("video_url")
                == submission.get("video_url")
                and story_reference.get("video_sha256")
                == submission.get("video_sha256")
                and story_reference.get("video_duration_seconds")
                == submission.get("video_duration_seconds")
                and story_reference.get("subtitles_sha256")
                == submission.get("video_subtitles_sha256")
                and evidence_story.get("claim_boundary", {}).get(
                    "continuum_vs_raw_rag"
                )
                == "confirmed_paired_advantage"
                and evidence_story.get("claim_boundary", {}).get(
                    "continuum_vs_stateless"
                )
                == "directional_not_confirmatory"
                and evidence_story.get("claim_boundary", {}).get("latency")
                == "measured_not_claimed_as_superior"
                and len(evidence_story.get("story", {}).get("scenes", [])) == 9
            )
        ),
        "ci_recovery_artifact_bound": (
            ci_recovery_reference is None
            or (
                ci_recovery_reference is not None
                and ci_recovery_public is not None
                and ci_recovery_public == public_ci_recovery
                and ci_recovery_public_sha
                == ci_recovery_reference.get("public_sha256")
                and ci_recovery_public.get("source_head")
                == ci_recovery_reference.get("head_sha")
                and ci_recovery_public.get("workflow_run_id")
                == ci_recovery_reference.get("workflow_run_id")
                and ci_recovery_reference.get("artifact_name")
                == (
                    "continuum-ci-recovery-"
                    + str(ci_recovery_reference.get("head_sha", ""))
                    + "-"
                    + str(ci_recovery_reference.get("workflow_run_id", ""))
                    + "-"
                    + str(ci_recovery_reference.get("workflow_attempt", ""))
                )
                and int(ci_recovery_reference.get("artifact_id", 0)) > 0
                and SHA256_PATTERN.fullmatch(
                    str(ci_recovery_reference.get("artifact_archive_sha256", ""))
                )
                is not None
                and ci_recovery_public.get("challenge", {}).get(
                    "challenge_sha256"
                )
                == ci_recovery_reference.get("challenge_sha256")
                and ci_recovery_public.get("population_sha256")
                == ci_recovery_reference.get("population_sha256")
            )
        ),
        "ci_recovery_closed_loop_passed": (
            ci_recovery_reference is None
            or (
                ci_recovery_public is not None
                and ci_recovery_public.get("real_external_provider") is True
                and ci_recovery_public.get("provider") == "github-actions"
                and ci_recovery_public.get("methodology", {}).get(
                    "fault_families"
                )
                == 6
                and ci_recovery_public.get("methodology", {}).get(
                    "cases_per_arm"
                )
                == 12
                and ci_recovery_public.get("methodology", {}).get(
                    "total_child_workflow_runs"
                )
                == 54
                and len(ci_recovery_public.get("calibration", [])) == 6
                and len(ci_recovery_public.get("observations", [])) == 36
                and ci_recovery_public.get("gate", {}).get("status") == "PASS"
                and ci_recovery_public.get("arms", {})
                .get("continuum", {})
                .get("verified_recoveries")
                == 12
                and ci_recovery_public.get("arms", {})
                .get("continuum", {})
                .get("false_canonical_promotions")
                == 0
                and ci_recovery_public.get("arms", {})
                .get("continuum", {})
                .get("canonical_promotion_precision")
                == 1.0
                and ci_recovery_public.get("arms", {})
                .get("stateless", {})
                .get("verified_recoveries")
                == 12
                and ci_recovery_public.get("arms", {})
                .get("raw_rag", {})
                .get("verified_recoveries")
                == 11
                and ci_recovery_public.get("arms", {})
                .get("raw_rag", {})
                .get("false_canonical_promotions")
                == 1
                and "does not claim arbitrary-code repair"
                in ci_recovery_public.get("claim_boundary", "")
            )
        ),
        "adaptive_diagnosis_artifact_bound": (
            adaptive_diagnosis_reference is None
            or (
                adaptive_diagnosis_public is not None
                and adaptive_diagnosis_public == public_adaptive_diagnosis
                and adaptive_diagnosis_public_sha
                == adaptive_diagnosis_reference.get("public_sha256")
                and adaptive_diagnosis_public.get("source_head")
                == adaptive_diagnosis_reference.get("head_sha")
                and adaptive_diagnosis_public.get("workflow_run_id")
                == adaptive_diagnosis_reference.get("workflow_run_id")
                and adaptive_diagnosis_reference.get("artifact_name")
                == (
                    "continuum-adaptive-diagnosis-"
                    + str(adaptive_diagnosis_reference.get("head_sha", ""))
                    + "-"
                    + str(adaptive_diagnosis_reference.get("workflow_run_id", ""))
                    + "-"
                    + str(adaptive_diagnosis_reference.get("workflow_attempt", ""))
                )
                and int(adaptive_diagnosis_reference.get("artifact_id", 0)) > 0
                and SHA256_PATTERN.fullmatch(
                    str(
                        adaptive_diagnosis_reference.get(
                            "artifact_archive_sha256", ""
                        )
                    )
                )
                is not None
                and adaptive_diagnosis_public.get("commitment", {}).get(
                    "challenge_sha256"
                )
                == adaptive_diagnosis_reference.get("challenge_sha256")
                and adaptive_diagnosis_public.get("commitment", {}).get(
                    "labels_sha256"
                )
                == adaptive_diagnosis_reference.get("labels_sha256")
                and adaptive_diagnosis_public.get("commitment", {}).get(
                    "commitment_sha256"
                )
                == adaptive_diagnosis_reference.get("commitment_sha256")
                and adaptive_diagnosis_public.get("seal_receipt", {}).get(
                    "receipt_sha256"
                )
                == adaptive_diagnosis_reference.get("seal_receipt_sha256")
            )
        ),
        "adaptive_diagnosis_information_value_passed": (
            adaptive_diagnosis_reference is None
            or (
                adaptive_diagnosis_public is not None
                and adaptive_diagnosis_public.get("real_external_provider") is True
                and adaptive_diagnosis_public.get("provider") == "github-actions"
                and adaptive_diagnosis_public.get("methodology", {}).get(
                    "paired_cases"
                )
                == 12
                and adaptive_diagnosis_public.get("methodology", {}).get(
                    "arm_observations"
                )
                == 36
                and adaptive_diagnosis_public.get("methodology", {}).get(
                    "total_child_workflow_runs"
                )
                == 84
                and len(adaptive_receipts) == 84
                and len(
                    {item.get("workflow_run_id") for item in adaptive_receipts}
                )
                == 84
                and len(
                    {item.get("artifact_id") for item in adaptive_receipts}
                )
                == 84
                and all(
                    item.get("head_sha")
                    == adaptive_diagnosis_reference.get("head_sha")
                    and item.get("repository_mutation") is False
                    and item.get("cleanup_residual_count") == 0
                    for item in adaptive_receipts
                )
                and adaptive_diagnosis_public.get("gate", {}).get("status")
                == "PASS"
                and adaptive_diagnosis_public.get("arms", {})
                .get("continuum", {})
                .get("verified_recoveries")
                == 12
                and adaptive_diagnosis_public.get("arms", {})
                .get("continuum", {})
                .get("recurrence_diagnostic_probe_calls")
                == 0
                and adaptive_diagnosis_public.get("arms", {})
                .get("continuum", {})
                .get("false_canonical_promotions")
                == 0
                and adaptive_diagnosis_public.get("arms", {})
                .get("stateless", {})
                .get("verified_recoveries")
                == 12
                and adaptive_diagnosis_public.get("arms", {})
                .get("stateless", {})
                .get("recurrence_diagnostic_probe_calls")
                == 6
                and adaptive_diagnosis_public.get("paired_comparisons", {})
                .get("continuum_vs_stateless", {})
                .get("recurrence", {})
                .get("diagnostic_probe_exact_p_value")
                == 0.03125
            )
        ),
        "transfer_firewall_artifact_bound": (
            transfer_firewall_reference is None
            or (
                transfer_firewall_public is not None
                and transfer_firewall_public == public_transfer_firewall
                and transfer_firewall_public_sha
                == transfer_firewall_reference.get("public_sha256")
                and transfer_firewall_public.get("source_head")
                == transfer_firewall_reference.get("head_sha")
                and transfer_firewall_public.get("workflow_run_id")
                == transfer_firewall_reference.get("workflow_run_id")
                and transfer_firewall_reference.get("artifact_name")
                == (
                    "continuum-transfer-firewall-"
                    + str(transfer_firewall_reference.get("head_sha", ""))
                    + "-"
                    + str(transfer_firewall_reference.get("workflow_run_id", ""))
                    + "-"
                    + str(transfer_firewall_reference.get("workflow_attempt", ""))
                )
                and int(transfer_firewall_reference.get("artifact_id", 0)) > 0
                and SHA256_PATTERN.fullmatch(
                    str(
                        transfer_firewall_reference.get(
                            "artifact_archive_sha256", ""
                        )
                    )
                )
                is not None
                and transfer_firewall_public.get("commitment", {}).get(
                    "challenge_sha256"
                )
                == transfer_firewall_reference.get("challenge_sha256")
                and transfer_firewall_public.get("commitment", {}).get(
                    "labels_sha256"
                )
                == transfer_firewall_reference.get("labels_sha256")
                and transfer_firewall_public.get("commitment", {}).get(
                    "commitment_sha256"
                )
                == transfer_firewall_reference.get("commitment_sha256")
                and transfer_firewall_public.get("seal_receipt", {}).get(
                    "receipt_sha256"
                )
                == transfer_firewall_reference.get("seal_receipt_sha256")
            )
        ),
        "counterfactual_transfer_policy_passed": (
            transfer_firewall_reference is None
            or (
                transfer_firewall_public is not None
                and transfer_firewall_public.get("real_external_provider") is True
                and transfer_firewall_public.get("provider") == "github-actions"
                and transfer_firewall_public.get("methodology", {}).get(
                    "counterfactual_pairs"
                )
                == 6
                and transfer_firewall_public.get("methodology", {}).get(
                    "target_cases"
                )
                == 12
                and transfer_firewall_public.get("methodology", {}).get(
                    "arm_observations"
                )
                == 36
                and transfer_firewall_public.get("methodology", {}).get(
                    "source_fault_families"
                )
                == 6
                and transfer_firewall_public.get("methodology", {}).get(
                    "same_cause_targets"
                )
                == 6
                and transfer_firewall_public.get("methodology", {}).get(
                    "near_neighbor_targets"
                )
                == 6
                and transfer_firewall_public.get("methodology", {}).get(
                    "source_calibration_child_runs"
                )
                == 18
                and transfer_firewall_public.get("methodology", {}).get(
                    "target_attestation_child_runs"
                )
                == 12
                and transfer_firewall_public.get("methodology", {}).get(
                    "diagnostic_child_runs"
                )
                == 18
                and transfer_firewall_public.get("methodology", {}).get(
                    "remediation_child_runs"
                )
                == 36
                and transfer_firewall_public.get("methodology", {}).get(
                    "total_child_workflow_runs"
                )
                == 84
                and transfer_firewall_public.get("methodology", {}).get(
                    "candidate_visible_label_fields"
                )
                == 0
                and transfer_firewall_public.get("methodology", {}).get(
                    "labels_opened_by_controller_only"
                )
                is True
                and len(transfer_observations) == 36
                and len(
                    {
                        (item.get("arm"), item.get("case_id"))
                        for item in transfer_observations
                    }
                )
                == 36
                and transfer_source_fingerprints.isdisjoint(
                    transfer_target_fingerprints
                )
                and len(transfer_receipts) == 84
                and len(
                    {item.get("workflow_run_id") for item in transfer_receipts}
                )
                == 84
                and len({item.get("artifact_id") for item in transfer_receipts})
                == 84
                and len(
                    {item.get("artifact_digest") for item in transfer_receipts}
                )
                == 84
                and all(
                    item.get("head_sha")
                    == transfer_firewall_reference.get("head_sha")
                    and item.get("repository_mutation") is False
                    and item.get("cleanup_residual_count") == 0
                    for item in transfer_receipts
                )
                and transfer_firewall_public.get("gate", {}).get("status")
                == "PASS"
                and bool(transfer_gate_checks)
                and all(value is True for value in transfer_gate_checks)
                and transfer_firewall_public.get("arms", {})
                .get("continuum", {})
                .get("verified_recoveries")
                == 12
                and transfer_firewall_public.get("arms", {})
                .get("continuum", {})
                .get("same_cause_verified_transfers")
                == 6
                and transfer_firewall_public.get("arms", {})
                .get("continuum", {})
                .get("near_neighbor_safe_rejections")
                == 6
                and transfer_firewall_public.get("arms", {})
                .get("continuum", {})
                .get("near_neighbor_false_transfers")
                == 0
                and transfer_firewall_public.get("arms", {})
                .get("continuum", {})
                .get("false_canonical_promotions")
                == 0
                and transfer_firewall_public.get("arms", {})
                .get("raw_rag", {})
                .get("verified_recoveries")
                == 6
                and transfer_firewall_public.get("arms", {})
                .get("raw_rag", {})
                .get("near_neighbor_false_transfers")
                == 6
                and transfer_firewall_public.get("paired_comparisons", {})
                .get("continuum_vs_stateless", {})
                .get("same_cause", {})
                .get("diagnostic_probe_exact_p_value")
                == 0.03125
                and transfer_firewall_public.get("paired_comparisons", {})
                .get("continuum_vs_raw_rag", {})
                .get("verified_recovery_lift_percentage_points")
                == 50.0
                and "not arbitrary repository repair"
                in str(transfer_firewall_public.get("claim_boundary", "")).lower()
            )
        ),
        "online_memory_lineage_artifact_bound": (
            online_memory_lineage_reference is None
            or (
                online_memory_lineage_public is not None
                and online_memory_lineage_public_sha
                == online_memory_lineage_reference.get("public_sha256")
                and online_memory_lineage_public.get("source_head")
                == online_memory_lineage_reference.get("candidate_head_sha")
                and online_memory_lineage_public.get("raw_receipt_sha256")
                == online_memory_lineage_reference.get("raw_receipt_sha256")
                and online_memory_lineage_public.get("rls", {}).get(
                    "combined_sha256"
                )
                == online_memory_lineage_reference.get("rls_combined_sha256")
                and online_memory_lineage_public.get("reconciliation", {}).get(
                    "reconciler_source_head"
                )
                == online_memory_lineage_reference.get("reconciler_head_sha")
                and online_memory_lineage_public.get("reconciliation", {}).get(
                    "reconciliation_workflow_run_id"
                )
                == online_memory_lineage_reference.get("workflow_run_id")
                and online_memory_lineage_public.get("reconciliation", {}).get(
                    "provider_action_reexecutions"
                )
                == 0
                and online_memory_lineage_reference.get("artifact_name")
                == (
                    "continuum-online-memory-lineage-reconciliation-"
                    + str(
                        online_memory_lineage_reference.get(
                            "reconciler_head_sha", ""
                        )
                    )
                    + "-"
                    + str(online_memory_lineage_reference.get("workflow_run_id", ""))
                    + "-"
                    + str(online_memory_lineage_reference.get("workflow_attempt", ""))
                )
                and int(online_memory_lineage_reference.get("artifact_id", 0)) > 0
                and SHA256_PATTERN.fullmatch(
                    str(
                        online_memory_lineage_reference.get(
                            "artifact_archive_sha256", ""
                        )
                    )
                )
                is not None
                and online_memory_lineage_public.get("gate", {}).get("status")
                == "PASS"
                and all(
                    value is True
                    for key, value in online_memory_lineage_public.get(
                        "gate", {}
                    ).items()
                    if key != "status"
                )
            )
        ),
        "outcome_replay_cas_artifact_bound": (
            outcome_replay_cas_reference is None
            or (
                outcome_replay_cas_public is not None
                and outcome_replay_cas_public_sha
                == outcome_replay_cas_reference.get("public_sha256")
                and outcome_replay_cas_public.get("source_head")
                == outcome_replay_cas_reference.get("head_sha")
                and outcome_replay_cas_public.get("deployment_artifact_sha256")
                == outcome_replay_cas_reference.get(
                    "deployment_artifact_sha256"
                )
                and outcome_replay_cas_public.get("workflow", {}).get("run_id")
                == outcome_replay_cas_reference.get("workflow_run_id")
                and outcome_replay_cas_public.get("workflow", {}).get(
                    "run_attempt"
                )
                == outcome_replay_cas_reference.get("workflow_attempt")
                and outcome_replay_cas_public.get("migration", {}).get(
                    "current_version"
                )
                == outcome_replay_cas_reference.get("migration_version")
                and outcome_replay_cas_public.get("provider", {}).get("adapter")
                == outcome_replay_cas_reference.get("provider_adapter")
                and outcome_replay_cas_public.get("cas", {}).get("journal_rows")
                == outcome_replay_cas_reference.get("journal_rows")
                and outcome_replay_cas_public.get("cas", {}).get("chain_tip")
                == outcome_replay_cas_reference.get("chain_tip")
                and outcome_replay_cas_public.get("cas", {}).get(
                    "conflict_error_code"
                )
                == outcome_replay_cas_reference.get("conflict_error_code")
                and (
                    outcome_replay_cas_public.get("schema_version") == 1
                    or (
                        outcome_replay_cas_public.get("provider", {}).get(
                            "lookup_count"
                        )
                        == outcome_replay_cas_reference.get(
                            "provider_lookup_count"
                        )
                        and outcome_replay_cas_public.get("attestation", {}).get(
                            "handle_digest"
                        )
                        == outcome_replay_cas_reference.get(
                            "attestation_handle_digest"
                        )
                        and outcome_replay_cas_public.get("attestation", {}).get(
                            "policy_version"
                        )
                        == outcome_replay_cas_reference.get(
                            "attestation_policy_version"
                        )
                    )
                )
                and outcome_replay_cas_reference.get("artifact_name")
                == (
                    "continuum-outcome-replay-cas-"
                    + str(outcome_replay_cas_reference.get("head_sha", ""))
                    + "-"
                    + str(
                        outcome_replay_cas_reference.get("workflow_run_id", "")
                    )
                    + "-"
                    + str(
                        outcome_replay_cas_reference.get("workflow_attempt", "")
                    )
                )
                and int(outcome_replay_cas_reference.get("artifact_id", 0)) > 0
                and SHA256_PATTERN.fullmatch(
                    str(
                        outcome_replay_cas_reference.get(
                            "artifact_archive_sha256", ""
                        )
                    )
                )
                is not None
                and outcome_replay_cas_public.get("gate", {}).get("status")
                == "PASS"
                and all(
                    value is True
                    for key, value in outcome_replay_cas_public.get(
                        "gate", {}
                    ).items()
                    if key != "status"
                )
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
            and (
                sequential_reference is None
                or (
                    release_reference.get("sequential_blind_asset_name")
                    == SEQUENTIAL_BLIND_ASSET
                    and release_reference.get("sequential_blind_asset_url")
                    == (
                        f"https://github.com/{repository}/releases/download/"
                        f"{release_tag}/{SEQUENTIAL_BLIND_ASSET}"
                    )
                )
            )
            and (
                story_reference is None
                or (
                    release_reference.get("evidence_story_asset_name")
                    == EVIDENCE_STORY_ASSET
                    and release_reference.get("evidence_story_asset_url")
                    == (
                        f"https://github.com/{repository}/releases/download/"
                        f"{release_tag}/{EVIDENCE_STORY_ASSET}"
                    )
                )
            )
            and (
                ci_recovery_reference is None
                or (
                    release_reference.get("ci_recovery_asset_name")
                    == CI_RECOVERY_ASSET
                    and release_reference.get("ci_recovery_asset_url")
                    == (
                        f"https://github.com/{repository}/releases/download/"
                        f"{release_tag}/{CI_RECOVERY_ASSET}"
                    )
                )
            )
            and (
                adaptive_diagnosis_reference is None
                or (
                    release_reference.get("adaptive_diagnosis_asset_name")
                    == ADAPTIVE_DIAGNOSIS_ASSET
                    and release_reference.get("adaptive_diagnosis_asset_url")
                    == (
                        f"https://github.com/{repository}/releases/download/"
                        f"{release_tag}/{ADAPTIVE_DIAGNOSIS_ASSET}"
                    )
                )
            )
            and (
                transfer_firewall_reference is None
                or (
                    release_reference.get("transfer_firewall_asset_name")
                    == TRANSFER_FIREWALL_ASSET
                    and release_reference.get("transfer_firewall_asset_url")
                    == (
                        f"https://github.com/{repository}/releases/download/"
                        f"{release_tag}/{TRANSFER_FIREWALL_ASSET}"
                    )
                )
            )
            and (
                online_memory_lineage_reference is None
                or (
                    release_reference.get("online_memory_lineage_asset_name")
                    == ONLINE_MEMORY_LINEAGE_ASSET
                    and release_reference.get("online_memory_lineage_asset_url")
                    == (
                        f"https://github.com/{repository}/releases/download/"
                        f"{release_tag}/{ONLINE_MEMORY_LINEAGE_ASSET}"
                    )
                )
            )
            and (
                outcome_replay_cas_reference is None
                or (
                    release_reference.get("outcome_replay_cas_asset_name")
                    == OUTCOME_REPLAY_CAS_ASSET
                    and release_reference.get("outcome_replay_cas_asset_url")
                    == (
                        f"https://github.com/{repository}/releases/download/"
                        f"{release_tag}/{OUTCOME_REPLAY_CAS_ASSET}"
                    )
                )
            )
            and (
                offline_judge_reference is None
                or (
                    release_reference.get("offline_judge_capsule_asset_name")
                    == CAPSULE_ASSET_NAME
                    and release_reference.get("offline_judge_capsule_asset_url")
                    == (
                        f"https://github.com/{repository}/releases/download/"
                        f"{release_tag}/{CAPSULE_ASSET_NAME}"
                    )
                )
            )
        ),
        "offline_judge_capsule_bound": (
            judge.get("schema_version", 0) < 16
            or (
                offline_judge_reference is not None
                and offline_judge_capsule is not None
                and offline_judge_result is not None
                and offline_judge_result.get("ok") is True
                and offline_judge_reference.get("schema_version") == 1
                and offline_judge_reference.get("asset_name")
                == CAPSULE_ASSET_NAME
                and offline_judge_reference.get("public_url")
                == (
                    judge["public_demo"]["url"].rstrip("/")
                    + f"/evidence/{CAPSULE_ASSET_NAME}"
                )
                and offline_judge_capsule.get("compiler", {}).get("repository")
                == repository
                and offline_judge_capsule.get("compiler", {}).get("source_head")
                == commit_sha
                and offline_judge_capsule.get("compiler", {}).get(
                    "successor_release_tag"
                )
                == release_tag
                and offline_judge_capsule.get("predecessor", {}).get(
                    "release_tag"
                )
                != release_tag
                and SHA256_PATTERN.fullmatch(offline_judge_capsule_sha)
                is not None
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
                **(
                    {"blind_holdout": release_reference["blind_holdout_asset_url"]}
                    if blind_reference is not None
                    else {}
                ),
                **(
                    {
                        "sequential_blind_campaign": release_reference[
                            "sequential_blind_asset_url"
                        ]
                    }
                    if sequential_reference is not None
                    else {}
                ),
                **(
                    {
                        "evidence_story": release_reference[
                            "evidence_story_asset_url"
                        ]
                    }
                    if story_reference is not None
                    else {}
                ),
                **(
                    {
                        "ci_recovery": release_reference[
                            "ci_recovery_asset_url"
                        ]
                    }
                    if ci_recovery_reference is not None
                    else {}
                ),
                **(
                    {
                        "adaptive_diagnosis": release_reference[
                            "adaptive_diagnosis_asset_url"
                        ]
                    }
                    if adaptive_diagnosis_reference is not None
                    else {}
                ),
                **(
                    {
                        "transfer_firewall": release_reference[
                            "transfer_firewall_asset_url"
                        ]
                    }
                    if transfer_firewall_reference is not None
                    else {}
                ),
                **(
                    {
                        "online_memory_lineage": release_reference[
                            "online_memory_lineage_asset_url"
                        ]
                    }
                    if online_memory_lineage_reference is not None
                    else {}
                ),
                **(
                    {
                        "outcome_replay_cas": release_reference[
                            "outcome_replay_cas_asset_url"
                        ]
                    }
                    if outcome_replay_cas_reference is not None
                    else {}
                ),
                **(
                    {
                        "offline_judge_capsule": release_reference[
                            "offline_judge_capsule_asset_url"
                        ]
                    }
                    if offline_judge_reference is not None
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
        **(
            {
                "blind_holdout": {
                    "head_sha": blind_reference["head_sha"],
                    "workflow_run_id": blind_reference["workflow_run_id"],
                    "workflow_attempt": blind_reference["workflow_attempt"],
                    "workflow_url": blind_reference["workflow_url"],
                    "artifact_id": blind_reference["artifact_id"],
                    "artifact_name": blind_reference["artifact_name"],
                    "artifact_archive_sha256": blind_reference[
                        "artifact_archive_sha256"
                    ],
                    "report_sha256": blind_reference["report_sha256"],
                    "public_sha256": blind_holdout_public_sha,
                    "public_url": blind_reference["public_url"],
                    "immutable_release_asset_url": release_reference[
                        "blind_holdout_asset_url"
                    ],
                    "challenge_sha256": blind_holdout_public["commitment"][
                        "challenge_sha256"
                    ],
                    "commitment_sha256": blind_holdout_public["commitment"][
                        "commitment_sha256"
                    ],
                    "seal_receipt_sha256": blind_holdout_public[
                        "seal_receipt"
                    ]["receipt_sha256"],
                    "sealed_at": blind_holdout_public["seal_receipt"]["sealed_at"],
                    "generator_model": blind_holdout_public["generator_model"],
                    "agent_model": blind_holdout_public["agent_model"],
                    "evaluator": blind_holdout_public["evaluator"],
                    "methodology": blind_holdout_public["methodology"],
                    "arms": blind_holdout_public["arms"],
                    "paired_comparison": blind_holdout_public[
                        "paired_comparison"
                    ],
                    "gate": blind_holdout_public["gate"],
                }
            }
            if blind_reference is not None and blind_holdout_public is not None
            else {}
        ),
        **(
            {
                "sequential_blind_campaign": {
                    "head_sha": sequential_reference["head_sha"],
                    "evaluator_head_sha": sequential_reference.get(
                        "evaluator_head_sha", sequential_reference["head_sha"]
                    ),
                    "workflow_run_id": sequential_reference["workflow_run_id"],
                    "workflow_attempt": sequential_reference["workflow_attempt"],
                    "workflow_url": sequential_reference["workflow_url"],
                    "artifact_id": sequential_reference["artifact_id"],
                    "artifact_name": sequential_reference["artifact_name"],
                    "artifact_archive_sha256": sequential_reference[
                        "artifact_archive_sha256"
                    ],
                    "public_sha256": sequential_blind_public_sha,
                    "public_url": sequential_reference["public_url"],
                    "page_url": sequential_reference["page_url"],
                    "immutable_release_asset_url": release_reference[
                        "sequential_blind_asset_url"
                    ],
                    "campaign_id": sequential_blind_public["campaign_id"],
                    "campaign_manifest_sha256": sequential_blind_public[
                        "campaign_manifest"
                    ]["campaign_manifest_sha256"],
                    "campaign_seal_receipt_sha256": sequential_blind_public[
                        "campaign_seal_receipt"
                    ]["receipt_sha256"],
                    **(
                        {
                            "candidate_workflow_run_id": sequential_reference[
                                "candidate_workflow_run_id"
                            ],
                            "candidate_workflow_attempt": sequential_reference[
                                "candidate_workflow_attempt"
                            ],
                            "candidate_workflow_url": sequential_reference[
                                "candidate_workflow_url"
                            ],
                            "candidate_artifact_id": sequential_reference[
                                "candidate_artifact_id"
                            ],
                            "candidate_artifact_name": sequential_reference[
                                "candidate_artifact_name"
                            ],
                            "candidate_artifact_archive_sha256": sequential_reference[
                                "candidate_artifact_archive_sha256"
                            ],
                            "evaluation_replay": sequential_blind_public[
                                "evaluation_replay"
                            ],
                        }
                        if "evaluation_replay" in sequential_blind_public
                        else {}
                    ),
                    "methodology": sequential_blind_public["methodology"],
                    "arms": sequential_blind_public["arms"],
                    "paired_comparisons": sequential_blind_public[
                        "paired_comparisons"
                    ],
                    "gate": sequential_blind_public["gate"],
                }
            }
            if sequential_reference is not None
            and sequential_blind_public is not None
            else {}
        ),
        **(
            {
                "evidence_story": {
                    "schema_version": evidence_story["schema_version"],
                    "public_sha256": evidence_story_sha,
                    "receipt_sha256": evidence_story["receipt_sha256"],
                    "public_url": story_reference["public_url"],
                    "page_url": story_reference["page_url"],
                    "immutable_release_asset_url": release_reference[
                        "evidence_story_asset_url"
                    ],
                    "source_release": evidence_story["source_release"],
                    "source_artifacts": evidence_story["source_artifacts"],
                    "metrics": evidence_story["metrics"],
                    "claim_boundary": evidence_story["claim_boundary"],
                    "video": {
                        "url": story_reference["video_url"],
                        "duration_seconds": story_reference[
                            "video_duration_seconds"
                        ],
                        "sha256": story_reference["video_sha256"],
                        "subtitles_sha256": story_reference["subtitles_sha256"],
                    },
                    "gate": evidence_story["gate"],
                }
            }
            if story_reference is not None and evidence_story is not None
            else {}
        ),
        **(
            {
                "ci_recovery": {
                    "schema_version": ci_recovery_public["schema_version"],
                    "head_sha": ci_recovery_reference["head_sha"],
                    "workflow_run_id": ci_recovery_reference[
                        "workflow_run_id"
                    ],
                    "workflow_attempt": ci_recovery_reference[
                        "workflow_attempt"
                    ],
                    "workflow_url": ci_recovery_reference["workflow_url"],
                    "artifact_id": ci_recovery_reference["artifact_id"],
                    "artifact_name": ci_recovery_reference["artifact_name"],
                    "artifact_archive_sha256": ci_recovery_reference[
                        "artifact_archive_sha256"
                    ],
                    "public_sha256": ci_recovery_public_sha,
                    "public_url": ci_recovery_reference["public_url"],
                    "page_url": ci_recovery_reference["page_url"],
                    "immutable_release_asset_url": release_reference[
                        "ci_recovery_asset_url"
                    ],
                    "campaign_id": ci_recovery_public["campaign_id"],
                    "challenge_sha256": ci_recovery_public["challenge"][
                        "challenge_sha256"
                    ],
                    "population_sha256": ci_recovery_public[
                        "population_sha256"
                    ],
                    "methodology": ci_recovery_public["methodology"],
                    "arms": ci_recovery_public["arms"],
                    "paired_comparisons": ci_recovery_public[
                        "paired_comparisons"
                    ],
                    "gate": ci_recovery_public["gate"],
                    "claim_boundary": ci_recovery_public["claim_boundary"],
                }
            }
            if ci_recovery_reference is not None
            and ci_recovery_public is not None
            else {}
        ),
        **(
            {
                "adaptive_diagnosis": {
                    "schema_version": adaptive_diagnosis_public["schema_version"],
                    "head_sha": adaptive_diagnosis_reference["head_sha"],
                    "workflow_run_id": adaptive_diagnosis_reference[
                        "workflow_run_id"
                    ],
                    "workflow_attempt": adaptive_diagnosis_reference[
                        "workflow_attempt"
                    ],
                    "workflow_url": adaptive_diagnosis_reference["workflow_url"],
                    "artifact_id": adaptive_diagnosis_reference["artifact_id"],
                    "artifact_name": adaptive_diagnosis_reference[
                        "artifact_name"
                    ],
                    "artifact_archive_sha256": adaptive_diagnosis_reference[
                        "artifact_archive_sha256"
                    ],
                    "public_sha256": adaptive_diagnosis_public_sha,
                    "public_url": adaptive_diagnosis_reference["public_url"],
                    "page_url": adaptive_diagnosis_reference["page_url"],
                    "immutable_release_asset_url": release_reference[
                        "adaptive_diagnosis_asset_url"
                    ],
                    "campaign_id": adaptive_diagnosis_public["campaign_id"],
                    "challenge_sha256": adaptive_diagnosis_public["commitment"][
                        "challenge_sha256"
                    ],
                    "labels_sha256": adaptive_diagnosis_public["commitment"][
                        "labels_sha256"
                    ],
                    "commitment_sha256": adaptive_diagnosis_public["commitment"][
                        "commitment_sha256"
                    ],
                    "seal_receipt_sha256": adaptive_diagnosis_public[
                        "seal_receipt"
                    ]["receipt_sha256"],
                    "methodology": adaptive_diagnosis_public["methodology"],
                    "arms": adaptive_diagnosis_public["arms"],
                    "paired_comparisons": adaptive_diagnosis_public[
                        "paired_comparisons"
                    ],
                    "gate": adaptive_diagnosis_public["gate"],
                    "claim_boundary": adaptive_diagnosis_public[
                        "claim_boundary"
                    ],
                }
            }
            if adaptive_diagnosis_reference is not None
            and adaptive_diagnosis_public is not None
            else {}
        ),
        **(
            {
                "transfer_firewall": {
                    "schema_version": transfer_firewall_public["schema_version"],
                    "head_sha": transfer_firewall_reference["head_sha"],
                    "workflow_run_id": transfer_firewall_reference[
                        "workflow_run_id"
                    ],
                    "workflow_attempt": transfer_firewall_reference[
                        "workflow_attempt"
                    ],
                    "workflow_url": transfer_firewall_reference["workflow_url"],
                    "artifact_id": transfer_firewall_reference["artifact_id"],
                    "artifact_name": transfer_firewall_reference["artifact_name"],
                    "artifact_archive_sha256": transfer_firewall_reference[
                        "artifact_archive_sha256"
                    ],
                    "public_sha256": transfer_firewall_public_sha,
                    "public_url": transfer_firewall_reference["public_url"],
                    "page_url": transfer_firewall_reference["page_url"],
                    "immutable_release_asset_url": release_reference[
                        "transfer_firewall_asset_url"
                    ],
                    "campaign_id": transfer_firewall_public["campaign_id"],
                    "challenge_sha256": transfer_firewall_public["commitment"][
                        "challenge_sha256"
                    ],
                    "labels_sha256": transfer_firewall_public["commitment"][
                        "labels_sha256"
                    ],
                    "commitment_sha256": transfer_firewall_public["commitment"][
                        "commitment_sha256"
                    ],
                    "seal_receipt_sha256": transfer_firewall_public[
                        "seal_receipt"
                    ]["receipt_sha256"],
                    "methodology": transfer_firewall_public["methodology"],
                    "arms": transfer_firewall_public["arms"],
                    "paired_comparisons": transfer_firewall_public[
                        "paired_comparisons"
                    ],
                    "gate": transfer_firewall_public["gate"],
                    "claim_boundary": transfer_firewall_public["claim_boundary"],
                }
            }
            if transfer_firewall_reference is not None
            and transfer_firewall_public is not None
            else {}
        ),
        **(
            {
                "online_memory_lineage": {
                    "schema_version": online_memory_lineage_public[
                        "schema_version"
                    ],
                    "candidate_head_sha": online_memory_lineage_reference[
                        "candidate_head_sha"
                    ],
                    "reconciler_head_sha": online_memory_lineage_reference[
                        "reconciler_head_sha"
                    ],
                    "workflow_run_id": online_memory_lineage_reference[
                        "workflow_run_id"
                    ],
                    "workflow_attempt": online_memory_lineage_reference[
                        "workflow_attempt"
                    ],
                    "workflow_url": online_memory_lineage_reference[
                        "workflow_url"
                    ],
                    "predecessor_workflow_run_id": (
                        online_memory_lineage_reference[
                            "predecessor_workflow_run_id"
                        ]
                    ),
                    "artifact_id": online_memory_lineage_reference[
                        "artifact_id"
                    ],
                    "artifact_name": online_memory_lineage_reference[
                        "artifact_name"
                    ],
                    "artifact_archive_sha256": online_memory_lineage_reference[
                        "artifact_archive_sha256"
                    ],
                    "public_sha256": online_memory_lineage_public_sha,
                    "public_url": online_memory_lineage_reference["public_url"],
                    "page_url": online_memory_lineage_reference["page_url"],
                    "immutable_release_asset_url": release_reference[
                        "online_memory_lineage_asset_url"
                    ],
                    "raw_receipt_sha256": online_memory_lineage_reference[
                        "raw_receipt_sha256"
                    ],
                    "rls_combined_sha256": online_memory_lineage_reference[
                        "rls_combined_sha256"
                    ],
                    "provider_action_run_ids": online_memory_lineage_reference[
                        "provider_action_run_ids"
                    ],
                    "provider_action_reexecutions": 0,
                    "methodology": online_memory_lineage_public["methodology"],
                    "reconciliation": online_memory_lineage_public[
                        "reconciliation"
                    ],
                    "gate": online_memory_lineage_public["gate"],
                    "claim_boundary": online_memory_lineage_public[
                        "claim_boundary"
                    ],
                }
            }
            if online_memory_lineage_reference is not None
            and online_memory_lineage_public is not None
            else {}
        ),
        **(
            {
                "outcome_replay_cas": {
                    "schema_version": outcome_replay_cas_public[
                        "schema_version"
                    ],
                    "head_sha": outcome_replay_cas_reference["head_sha"],
                    "workflow_run_id": outcome_replay_cas_reference[
                        "workflow_run_id"
                    ],
                    "workflow_attempt": outcome_replay_cas_reference[
                        "workflow_attempt"
                    ],
                    "workflow_url": outcome_replay_cas_reference[
                        "workflow_url"
                    ],
                    "artifact_id": outcome_replay_cas_reference["artifact_id"],
                    "artifact_name": outcome_replay_cas_reference[
                        "artifact_name"
                    ],
                    "artifact_archive_sha256": outcome_replay_cas_reference[
                        "artifact_archive_sha256"
                    ],
                    "private_report_sha256": outcome_replay_cas_reference[
                        "private_report_sha256"
                    ],
                    "public_sha256": outcome_replay_cas_public_sha,
                    "public_url": outcome_replay_cas_reference["public_url"],
                    "page_url": outcome_replay_cas_reference["page_url"],
                    "immutable_release_asset_url": release_reference[
                        "outcome_replay_cas_asset_url"
                    ],
                    "deployment_artifact_sha256": outcome_replay_cas_public[
                        "deployment_artifact_sha256"
                    ],
                    "migration_version": outcome_replay_cas_public[
                        "migration"
                    ]["current_version"],
                    "provider": outcome_replay_cas_public["provider"],
                    "database": outcome_replay_cas_public["database"],
                    "cas": outcome_replay_cas_public["cas"],
                    **(
                        {
                            "attestation": outcome_replay_cas_public[
                                "attestation"
                            ]
                        }
                        if outcome_replay_cas_public["schema_version"] >= 2
                        else {}
                    ),
                    "gate": outcome_replay_cas_public["gate"],
                    "claim_boundary": outcome_replay_cas_public[
                        "claim_boundary"
                    ],
                }
            }
            if outcome_replay_cas_reference is not None
            and outcome_replay_cas_public is not None
            else {}
        ),
        "public_judge_evidence": {
            "url": judge["public_demo"]["evidence_url"],
            "sha256": judge_sha,
            "schema_version": judge["schema_version"],
        },
        "public_release_reference": release_reference,
        "network_sign_once": network_sign_once,
        **(
            {
                "offline_judge_capsule": {
                    "schema_version": 1,
                    "asset_name": CAPSULE_ASSET_NAME,
                    "asset_url": release_reference[
                        "offline_judge_capsule_asset_url"
                    ],
                    "public_url": offline_judge_reference["public_url"],
                    "asset_sha256": offline_judge_capsule_sha,
                    "receipt_sha256": offline_judge_capsule["receipt_sha256"],
                    "predecessor_release_tag": offline_judge_capsule[
                        "predecessor"
                    ]["release_tag"],
                    "predecessor_release_target": offline_judge_capsule[
                        "predecessor"
                    ]["release_target"],
                    "online_check_count": offline_judge_capsule[
                        "online_verification"
                    ]["check_count"],
                    "ui_check_count": len(offline_judge_capsule["ui_checks"]),
                    "github_api_requests_per_judge_click": 0,
                }
            }
            if offline_judge_capsule is not None
            else {}
        ),
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
    parser.add_argument("--blind-holdout-public", type=Path)
    parser.add_argument("--sequential-blind-public", type=Path)
    parser.add_argument("--evidence-story", type=Path)
    parser.add_argument("--ci-recovery-public", type=Path)
    parser.add_argument("--adaptive-diagnosis-public", type=Path)
    parser.add_argument("--transfer-firewall-public", type=Path)
    parser.add_argument("--online-memory-lineage-public", type=Path)
    parser.add_argument("--outcome-replay-cas-public", type=Path)
    parser.add_argument("--offline-judge-capsule", type=Path)
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
    blind_holdout_public_bytes = (
        args.blind_holdout_public.read_bytes()
        if args.blind_holdout_public is not None
        else b""
    )
    sequential_blind_public_bytes = (
        args.sequential_blind_public.read_bytes()
        if args.sequential_blind_public is not None
        else b""
    )
    evidence_story_bytes = (
        args.evidence_story.read_bytes()
        if args.evidence_story is not None
        else b""
    )
    ci_recovery_public_bytes = (
        args.ci_recovery_public.read_bytes()
        if args.ci_recovery_public is not None
        else b""
    )
    adaptive_diagnosis_public_bytes = (
        args.adaptive_diagnosis_public.read_bytes()
        if args.adaptive_diagnosis_public is not None
        else b""
    )
    transfer_firewall_public_bytes = (
        args.transfer_firewall_public.read_bytes()
        if args.transfer_firewall_public is not None
        else b""
    )
    online_memory_lineage_public_bytes = (
        args.online_memory_lineage_public.read_bytes()
        if args.online_memory_lineage_public is not None
        else b""
    )
    outcome_replay_cas_public_bytes = (
        args.outcome_replay_cas_public.read_bytes()
        if args.outcome_replay_cas_public is not None
        else b""
    )
    offline_judge_capsule_bytes = (
        args.offline_judge_capsule.read_bytes()
        if args.offline_judge_capsule is not None
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
        (
            json.loads(blind_holdout_public_bytes)
            if blind_holdout_public_bytes
            else None
        ),
        (
            json.loads(sequential_blind_public_bytes)
            if sequential_blind_public_bytes
            else None
        ),
        (
            json.loads(evidence_story_bytes)
            if evidence_story_bytes
            else None
        ),
        (
            json.loads(ci_recovery_public_bytes)
            if ci_recovery_public_bytes
            else None
        ),
        (
            json.loads(adaptive_diagnosis_public_bytes)
            if adaptive_diagnosis_public_bytes
            else None
        ),
        (
            json.loads(transfer_firewall_public_bytes)
            if transfer_firewall_public_bytes
            else None
        ),
        (
            json.loads(online_memory_lineage_public_bytes)
            if online_memory_lineage_public_bytes
            else None
        ),
        (
            json.loads(outcome_replay_cas_public_bytes)
            if outcome_replay_cas_public_bytes
            else None
        ),
        (
            json.loads(offline_judge_capsule_bytes)
            if offline_judge_capsule_bytes
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
        blind_holdout_public_bytes=blind_holdout_public_bytes,
        sequential_blind_public_bytes=sequential_blind_public_bytes,
        evidence_story_bytes=evidence_story_bytes,
        ci_recovery_public_bytes=ci_recovery_public_bytes,
        adaptive_diagnosis_public_bytes=adaptive_diagnosis_public_bytes,
        transfer_firewall_public_bytes=transfer_firewall_public_bytes,
        online_memory_lineage_public_bytes=online_memory_lineage_public_bytes,
        outcome_replay_cas_public_bytes=outcome_replay_cas_public_bytes,
        offline_judge_capsule_bytes=offline_judge_capsule_bytes,
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
