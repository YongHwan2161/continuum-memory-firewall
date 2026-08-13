"""Verify the public judge path using bounded HTTP GET requests only."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
from typing import Any, Callable
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from scripts.release_transaction_coordinator import verify_receipt
from scripts.offline_judge_capsule import verify_envelope_binding
from continuum.adaptive_diagnosis import build_public_adaptive_diagnosis
from continuum.blind_holdout import build_public_blind_holdout
from continuum.ci_recovery import build_public_ci_recovery
from continuum.evidence_story import verify_evidence_story_receipt
from continuum.release_guardian import build_public_release_guardian
from continuum.release_guardian_replication import (
    EXPECTED_REPLICATION_IDS,
    build_public_release_guardian_replication,
)
from continuum.outcome_replay_proof import (
    PUBLIC_KIND as OUTCOME_REPLAY_PUBLIC_KIND,
    validate_outcome_replay_proof,
)
from continuum.provider_origin_story import verify_provider_origin_story
from continuum.sequential_blind import build_public_sequential_blind
from continuum.transfer_firewall import build_public_transfer_firewall


DEFAULT_EVIDENCE_URL = (
    "https://yonghwan2161.github.io/continuum-memory-firewall/"
    "evidence/judge-verification.json"
)
MAX_RESPONSE_BYTES = 5_000_000
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _require_https(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc or parts.username:
        raise RuntimeError("judge verification permits absolute HTTPS URLs only")


def _get_bytes(url: str, *, timeout: float = 10.0) -> bytes:
    _require_https(url)
    parts = urlsplit(url)
    headers = {
        "Accept": "application/json,text/html;q=0.9,*/*;q=0.1",
        "User-Agent": "continuum-memory-firewall-judge-verifier/1",
    }
    # Scheduled/release workflows may use their ephemeral GITHUB_TOKEN to avoid
    # the public anonymous quota.  The token is never forwarded to Pages, MCP,
    # release-download, or any other host.
    github_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if parts.hostname == "api.github.com" and github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    request = Request(
        url,
        method="GET",
        headers=headers,
    )
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"GET {url} returned HTTP {response.status}")
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise RuntimeError("judge verification response exceeded the size limit")
    return body


def get_json(url: str) -> dict[str, Any]:
    payload = json.loads(_get_bytes(url).decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("expected a JSON object")
    return payload


def get_text(url: str) -> str:
    return _get_bytes(url).decode("utf-8", errors="strict")


def verify_ci_recovery(
    evidence: dict[str, Any],
    *,
    fetch_json: Callable[[str], dict[str, Any]],
    fetch_bytes: Callable[[str], bytes],
) -> bool:
    """Bind the public closed-loop CI report to its parent run and artifact."""

    reference = evidence.get("ci_recovery")
    if reference is None:
        return True
    try:
        workflow = fetch_json(reference["workflow_api_url"])
        artifact = fetch_json(reference["artifact_api_url"])
        public_bytes = fetch_bytes(reference["public_url"])
        public_sha = hashlib.sha256(public_bytes.replace(b"\r\n", b"\n")).hexdigest()
        report = json.loads(public_bytes.decode("utf-8"))
        if not isinstance(report, dict):
            return False
        public_projection = build_public_ci_recovery(report)
        methodology = report["methodology"]
        arms = report["arms"]
        continuum = arms["continuum"]
        raw = arms["raw_rag"]
        stateless = arms["stateless"]
        calibration = report["calibration"]
        observations = report["observations"]
        receipts = [
            receipt
            for item in calibration
            for receipt in (
                item["baseline_receipt"],
                item["wrong_patch_receipt"],
                item["green_receipt"],
            )
        ] + [item["provider_receipt"] for item in observations]
    except (KeyError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
        return False
    run_ids = [item.get("workflow_run_id") for item in receipts]
    artifact_ids = [item.get("artifact_id") for item in receipts]
    pairs = {(item.get("arm"), item.get("case_id")) for item in observations}
    artifact_digests_valid = all(
        re.fullmatch(r"sha256:[0-9a-f]{64}", str(item.get("artifact_digest", "")))
        for item in receipts
    )


    calibration_valid = all(
        item.get("baseline_receipt", {}).get("conclusion") == "failure"
        and item.get("wrong_patch_receipt", {}).get("conclusion") == "failure"
        and item.get("green_receipt", {}).get("conclusion") == "success"
        for item in calibration
    )
    gates = report.get("gate", {})
    gate_checks = [value for key, value in gates.items() if key != "status"]
    return (
        report == public_projection
        and reference.get("schema_version") == 1
        and workflow.get("id") == reference.get("workflow_run_id")
        and workflow.get("run_attempt") == reference.get("workflow_attempt")
        and workflow.get("conclusion") == "success"
        and workflow.get("head_sha") == reference.get("head_sha")
        and artifact.get("id") == reference.get("artifact_id")
        and artifact.get("name") == reference.get("artifact_name")
        and artifact.get("digest")
        == "sha256:" + str(reference.get("artifact_archive_sha256", ""))
        and artifact.get("expired") is False
        and artifact.get("workflow_run", {}).get("id")
        == reference.get("workflow_run_id")
        and public_sha == reference.get("public_sha256")
        and report.get("source_head") == reference.get("head_sha")
        and report.get("workflow_run_id") == reference.get("workflow_run_id")
        and report.get("workflow_run_attempt") == reference.get("workflow_attempt")
        and report.get("campaign_id") == reference.get("campaign_id")
        and report.get("challenge", {}).get("challenge_sha256")
        == reference.get("challenge_sha256")
        and report.get("population_sha256") == reference.get("population_sha256")
        and report.get("provider") == "github-actions"
        and report.get("real_external_provider") is True
        and methodology.get("fault_families") == 6
        and methodology.get("cases_per_arm") == 12
        and methodology.get("arm_observations") == 36
        and methodology.get("calibration_workflow_runs") == 18
        and methodology.get("total_child_workflow_runs") == 54
        and methodology.get("arms") == ["stateless", "raw_rag", "continuum"]
        and len(calibration) == 6
        and len(observations) == 36
        and len(pairs) == 36
        and {arm for arm, _case_id in pairs}
        == {"stateless", "raw_rag", "continuum"}
        and len(receipts) == 54
        and len(set(run_ids)) == 54
        and len(set(artifact_ids)) == 54
        and calibration_valid
        and artifact_digests_valid
        and all(item.get("head_sha") == reference.get("head_sha") for item in receipts)
        and all(item.get("repository_mutation") is False for item in receipts)
        and all(item.get("cleanup_residual_count") == 0 for item in receipts)
        and continuum.get("verified_recoveries") == 12
        and continuum.get("verified_recovery_rate") == 1.0
        and continuum.get("false_canonical_promotions") == 0
        and continuum.get("canonical_promotion_precision") == 1.0
        and continuum.get("unsafe_memory_exposures") == 0
        and continuum.get("unsafe_memory_citation_adoptions") == 0
        and stateless.get("verified_recoveries") == 12
        and stateless.get("verified_recovery_rate") == 1.0
        and raw.get("verified_recoveries") == 11
        and raw.get("recurrence_successes") == 5
        and raw.get("false_canonical_promotions") == 1
        and raw.get("unsafe_memory_exposures") == 12
        and raw.get("unsafe_memory_citation_adoptions") == 11
        and report.get("paired_comparisons", {})
        .get("continuum_vs_raw_rag", {})
        .get("continuum_lift_percentage_points")
        == 8.3333
        and report.get("paired_comparisons", {})
        .get("continuum_vs_stateless", {})
        .get("continuum_lift_percentage_points")
        == 0.0
        and gates.get("status") == "PASS"
        and bool(gate_checks)
        and all(value is True for value in gate_checks)
        and "does not claim arbitrary-code repair" in report.get("claim_boundary", "")
    )


def verify_adaptive_diagnosis(
    evidence: dict[str, Any],
    *,
    fetch_json: Callable[[str], dict[str, Any]],
    fetch_bytes: Callable[[str], bytes],
) -> bool:
    """Bind the S3-preregistered adaptive result to 84 provider receipts."""

    reference = evidence.get("adaptive_diagnosis")
    if reference is None:
        return True
    try:
        workflow = fetch_json(reference["workflow_api_url"])
        artifact = fetch_json(reference["artifact_api_url"])
        public_bytes = fetch_bytes(reference["public_url"])
        public_sha = hashlib.sha256(
            public_bytes.replace(b"\r\n", b"\n")
        ).hexdigest()
        report = json.loads(public_bytes.decode("utf-8"))
        if not isinstance(report, dict):
            return False
        public_projection = build_public_adaptive_diagnosis(report)
        methodology = report["methodology"]
        arms = report["arms"]
        continuum = arms["continuum"]
        stateless = arms["stateless"]
        raw = arms["raw_rag"]
        observations = report["observations"]
        calibration = report["calibration"]
        receipts = [item["provider_receipt"] for item in calibration] + [
            receipt
            for item in observations
            for receipt in item["diagnostic_receipts"]
        ] + [item["provider_receipt"] for item in observations]
    except (KeyError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
        return False
    run_ids = [item.get("workflow_run_id") for item in receipts]
    artifact_ids = [item.get("artifact_id") for item in receipts]
    pairs = {(item.get("arm"), item.get("case_id")) for item in observations}
    gate = report.get("gate", {})
    gate_checks = [value for key, value in gate.items() if key != "status"]
    recurrence = (
        report.get("paired_comparisons", {})
        .get("continuum_vs_stateless", {})
        .get("recurrence", {})
    )
    commitment = report.get("commitment", {})
    seal = report.get("seal_receipt", {})
    return (
        report == public_projection
        and reference.get("schema_version") == 1
        and workflow.get("id") == reference.get("workflow_run_id")
        and workflow.get("run_attempt") == reference.get("workflow_attempt")
        and workflow.get("conclusion") == "success"
        and workflow.get("head_sha") == reference.get("head_sha")
        and artifact.get("id") == reference.get("artifact_id")
        and artifact.get("name") == reference.get("artifact_name")
        and artifact.get("digest")
        == "sha256:" + str(reference.get("artifact_archive_sha256", ""))
        and artifact.get("expired") is False
        and artifact.get("workflow_run", {}).get("id")
        == reference.get("workflow_run_id")
        and public_sha == reference.get("public_sha256")
        and report.get("source_head") == reference.get("head_sha")
        and report.get("workflow_run_id") == reference.get("workflow_run_id")
        and report.get("workflow_run_attempt") == reference.get("workflow_attempt")
        and report.get("campaign_id") == reference.get("campaign_id")
        and commitment.get("challenge_sha256")
        == reference.get("challenge_sha256")
        and commitment.get("labels_sha256") == reference.get("labels_sha256")
        and commitment.get("commitment_sha256")
        == reference.get("commitment_sha256")
        and seal.get("receipt_sha256") == reference.get("seal_receipt_sha256")
        and seal.get("write_once_condition") == "If-None-Match:*"
        and report.get("provider") == "github-actions"
        and report.get("real_external_provider") is True
        and methodology.get("paired_cases") == 12
        and methodology.get("arm_observations") == 36
        and methodology.get("fault_families") == 6
        and methodology.get("ambiguity_groups") == 3
        and methodology.get("calibration_child_runs") == 18
        and methodology.get("diagnostic_child_runs") == 30
        and methodology.get("remediation_child_runs") == 36
        and methodology.get("total_child_workflow_runs") == 84
        and methodology.get("candidate_visible_label_fields") == 0
        and len(observations) == 36
        and len(pairs) == 36
        and {arm for arm, _case_id in pairs}
        == {"stateless", "raw_rag", "continuum"}
        and len(calibration) == 18
        and len(receipts) == 84
        and len(set(run_ids)) == 84
        and len(set(artifact_ids)) == 84
        and all(item.get("head_sha") == reference.get("head_sha") for item in receipts)
        and all(item.get("repository_mutation") is False for item in receipts)
        and all(item.get("cleanup_residual_count") == 0 for item in receipts)
        and all(
            re.fullmatch(
                r"sha256:[0-9a-f]{64}", str(item.get("artifact_digest", ""))
            )
            for item in receipts
        )
        and continuum.get("verified_recoveries") == 12
        and continuum.get("recurrence_verified_recoveries") == 6
        and continuum.get("diagnostic_probe_calls") == 6
        and continuum.get("recurrence_diagnostic_probe_calls") == 0
        and continuum.get("recurrence_zero_probe_cases") == 6
        and continuum.get("false_canonical_promotions") == 0
        and continuum.get("canonical_promotion_precision") == 1.0
        and stateless.get("verified_recoveries") == 12
        and stateless.get("recurrence_diagnostic_probe_calls") == 6
        and raw.get("verified_recoveries") == 12
        and recurrence.get("diagnostic_probe_reduction_cases") == 6
        and recurrence.get("diagnostic_probe_increase_cases") == 0
        and recurrence.get("diagnostic_probe_exact_p_value") == 0.03125
        and gate.get("status") == "PASS"
        and bool(gate_checks)
        and all(value is True for value in gate_checks)
        and "controller retained labels"
        in report.get("claim_boundary", "").lower()
    )


def verify_transfer_firewall(
    evidence: dict[str, Any],
    *,
    fetch_json: Callable[[str], dict[str, Any]],
    fetch_bytes: Callable[[str], bytes],
) -> bool:
    """Bind the cross-environment transfer result to 84 provider receipts."""

    reference = evidence.get("transfer_firewall")
    if reference is None:
        return True
    try:
        workflow = fetch_json(reference["workflow_api_url"])
        artifact = fetch_json(reference["artifact_api_url"])
        public_bytes = fetch_bytes(reference["public_url"])
        public_sha = hashlib.sha256(
            public_bytes.replace(b"\r\n", b"\n")
        ).hexdigest()
        report = json.loads(public_bytes.decode("utf-8"))
        if not isinstance(report, dict):
            return False
        public_projection = build_public_transfer_firewall(report)
        methodology = report["methodology"]
        arms = report["arms"]
        continuum = arms["continuum"]
        stateless = arms["stateless"]
        raw = arms["raw_rag"]
        observations = report["observations"]
        source_calibration = report["source_calibration"]
        target_attestations = report["target_attestations"]
        receipts = [item["provider_receipt"] for item in source_calibration] + [
            item["provider_receipt"] for item in target_attestations
        ] + [
            receipt
            for item in observations
            for receipt in item["diagnostic_receipts"]
        ] + [item["provider_receipt"] for item in observations]
    except (KeyError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
        return False
    run_ids = [item.get("workflow_run_id") for item in receipts]
    artifact_ids = [item.get("artifact_id") for item in receipts]
    artifact_digests = [item.get("artifact_digest") for item in receipts]
    pairs = {(item.get("arm"), item.get("case_id")) for item in observations}
    source_fingerprints = {
        item.get("source_environment_fingerprint") for item in observations
    }
    target_fingerprints = {
        item.get("target_environment_fingerprint") for item in observations
    }
    gate = report.get("gate", {})
    gate_checks = [value for key, value in gate.items() if key != "status"]
    commitment = report.get("commitment", {})
    seal = report.get("seal_receipt", {})
    same_cause = (
        report.get("paired_comparisons", {})
        .get("continuum_vs_stateless", {})
        .get("same_cause", {})
    )
    vs_raw = report.get("paired_comparisons", {}).get(
        "continuum_vs_raw_rag", {}
    )
    return (
        report == public_projection
        and reference.get("schema_version") == 1
        and workflow.get("id") == reference.get("workflow_run_id")
        and workflow.get("run_attempt") == reference.get("workflow_attempt")
        and workflow.get("conclusion") == "success"
        and workflow.get("head_sha") == reference.get("head_sha")
        and artifact.get("id") == reference.get("artifact_id")
        and artifact.get("name") == reference.get("artifact_name")
        and artifact.get("digest")
        == "sha256:" + str(reference.get("artifact_archive_sha256", ""))
        and artifact.get("expired") is False
        and artifact.get("workflow_run", {}).get("id")
        == reference.get("workflow_run_id")
        and public_sha == reference.get("public_sha256")
        and report.get("source_head") == reference.get("head_sha")
        and report.get("workflow_run_id") == reference.get("workflow_run_id")
        and report.get("workflow_run_attempt") == reference.get("workflow_attempt")
        and report.get("campaign_id") == reference.get("campaign_id")
        and commitment.get("challenge_sha256")
        == reference.get("challenge_sha256")
        and commitment.get("labels_sha256") == reference.get("labels_sha256")
        and commitment.get("commitment_sha256")
        == reference.get("commitment_sha256")
        and seal.get("receipt_sha256") == reference.get("seal_receipt_sha256")
        and seal.get("write_once_condition") == "If-None-Match:*"
        and report.get("provider") == "github-actions"
        and report.get("real_external_provider") is True
        and methodology.get("counterfactual_pairs") == 6
        and methodology.get("target_cases") == 12
        and methodology.get("arm_observations") == 36
        and methodology.get("source_fault_families") == 6
        and methodology.get("same_cause_targets") == 6
        and methodology.get("near_neighbor_targets") == 6
        and methodology.get("source_calibration_child_runs") == 18
        and methodology.get("target_attestation_child_runs") == 12
        and methodology.get("diagnostic_child_runs") == 18
        and methodology.get("remediation_child_runs") == 36
        and methodology.get("total_child_workflow_runs") == 84
        and methodology.get("candidate_visible_label_fields") == 0
        and methodology.get("labels_opened_by_controller_only") is True
        and len(observations) == 36
        and len(pairs) == 36
        and {arm for arm, _case_id in pairs}
        == {"stateless", "raw_rag", "continuum"}
        and source_fingerprints.isdisjoint(target_fingerprints)
        and len(source_calibration) == 18
        and len(target_attestations) == 12
        and len(receipts) == 84
        and len(set(run_ids)) == 84
        and len(set(artifact_ids)) == 84
        and len(set(artifact_digests)) == 84
        and all(item.get("head_sha") == reference.get("head_sha") for item in receipts)
        and all(item.get("repository_mutation") is False for item in receipts)
        and all(item.get("cleanup_residual_count") == 0 for item in receipts)
        and all(
            re.fullmatch(
                r"sha256:[0-9a-f]{64}", str(item.get("artifact_digest", ""))
            )
            for item in receipts
        )
        and continuum.get("verified_recoveries") == 12
        and continuum.get("same_cause_verified_transfers") == 6
        and continuum.get("same_cause_zero_diagnostic_cases") == 6
        and continuum.get("near_neighbor_safe_rejections") == 6
        and continuum.get("near_neighbor_false_transfers") == 0
        and continuum.get("diagnostic_probe_calls") == 6
        and continuum.get("unsafe_patches") == 0
        and continuum.get("false_canonical_promotions") == 0
        and continuum.get("canonical_promotion_precision") == 1.0
        and stateless.get("verified_recoveries") == 12
        and stateless.get("diagnostic_probe_calls") == 12
        and raw.get("verified_recoveries") == 6
        and raw.get("near_neighbor_false_transfers") == 6
        and raw.get("unsafe_patches") == 6
        and raw.get("false_canonical_promotions") == 6
        and same_cause.get("diagnostic_probe_reduction_cases") == 6
        and same_cause.get("diagnostic_probe_exact_p_value") == 0.03125
        and vs_raw.get("verified_recovery_lift_percentage_points") == 50.0
        and vs_raw.get("near_neighbor_false_transfers_prevented") == 6
        and gate.get("status") == "PASS"
        and bool(gate_checks)
        and all(value is True for value in gate_checks)
        and "not arbitrary repository repair"
        in report.get("claim_boundary", "").lower()
    )


def verify_online_memory_lineage(
    evidence: dict[str, Any],
    *,
    fetch_json: Callable[[str], dict[str, Any]],
    fetch_bytes: Callable[[str], bytes],
) -> bool:
    """Verify the cross-head provider/DB lineage without any write capability."""

    reference = evidence.get("online_memory_lineage")
    if reference is None:
        return True
    repository = evidence.get("source", {}).get("repository", "")
    try:
        workflow = fetch_json(reference["workflow_api_url"])
        predecessor = fetch_json(reference["predecessor_workflow_api_url"])
        artifact = fetch_json(reference["artifact_api_url"])
        predecessor_artifact = fetch_json(
            f"https://api.github.com/repos/{repository}/actions/artifacts/"
            f"{reference['predecessor_artifact_id']}"
        )
        actions = [
            fetch_json(
                f"https://api.github.com/repos/{repository}/actions/runs/{run_id}"
            )
            for run_id in reference["provider_action_run_ids"]
        ]
        public_bytes = fetch_bytes(reference["public_url"])
        public_sha = hashlib.sha256(
            public_bytes.replace(b"\r\n", b"\n")
        ).hexdigest()
        report = json.loads(public_bytes.decode("utf-8"))
        targets = report["targets"]
        same = next(
            item for item in targets if item["relationship"] == "same-cause-transfer"
        )
        near = next(
            item
            for item in targets
            if item["relationship"] == "near-neighbor-rejection"
        )
    except (
        KeyError,
        RuntimeError,
        StopIteration,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return False
    gate = report.get("gate", {})
    gate_checks = [value for key, value in gate.items() if key != "status"]
    return (
        reference.get("schema_version") == 1
        and public_sha == reference.get("public_sha256")
        and report.get("schema_version") == 1
        and report.get("kind") == "continuum.online-memory-lineage.public"
        and report.get("raw_receipt_sha256")
        == reference.get("raw_receipt_sha256")
        and report.get("source_head") == reference.get("candidate_head_sha")
        and report.get("reconciliation", {}).get("candidate_source_head")
        == reference.get("candidate_head_sha")
        and report.get("reconciliation", {}).get("reconciler_source_head")
        == reference.get("reconciler_head_sha")
        and report.get("reconciliation", {}).get("predecessor_workflow_run_id")
        == reference.get("predecessor_workflow_run_id")
        and report.get("reconciliation", {}).get(
            "reconciliation_workflow_run_id"
        )
        == reference.get("workflow_run_id")
        and report.get("reconciliation", {}).get("input_receipt_sha256")
        == reference.get("reconciliation_input_sha256")
        and report.get("reconciliation", {}).get("provider_action_reexecutions")
        == 0
        and report.get("methodology", {}).get("architectural_pairs") == 1
        and report.get("methodology", {}).get("target_cases") == 2
        and report.get("methodology", {}).get("candidate_visible_label_fields")
        == 0
        and report.get("identity", {}).get("server_owned_scope_ids_disclosed")
        is False
        and report.get("rls", {}).get("combined_sha256")
        == reference.get("rls_combined_sha256")
        and len(targets) == 2
        and same.get("selected_memory_ids")
        == [reference.get("source_memory_id")]
        and same.get("fetched_memory_ids")
        == [reference.get("source_memory_id")]
        and same.get("diagnostic_receipts") == []
        and near.get("selected_memory_ids") == []
        and near.get("fetched_memory_ids") == []
        and len(near.get("diagnostic_receipts", [])) == 1
        and all(
            item.get("proposed_patch_id") == item.get("expected_patch_id")
            and item.get("outcome_status") == "succeeded"
            and bool(item.get("promoted_memory_id"))
            and len(item.get("admission_receipt", {}).get("retrieval_ids", []))
            >= 1
            for item in targets
        )
        and workflow.get("id") == reference.get("workflow_run_id")
        and workflow.get("run_attempt") == reference.get("workflow_attempt")
        and workflow.get("conclusion") == "success"
        and workflow.get("head_sha") == reference.get("reconciler_head_sha")
        and predecessor.get("id") == reference.get("predecessor_workflow_run_id")
        and predecessor.get("conclusion") == "failure"
        and predecessor.get("head_sha") == reference.get("candidate_head_sha")
        and artifact.get("id") == reference.get("artifact_id")
        and artifact.get("name") == reference.get("artifact_name")
        and artifact.get("digest")
        == "sha256:" + str(reference.get("artifact_archive_sha256", ""))
        and artifact.get("expired") is False
        and artifact.get("workflow_run", {}).get("id")
        == reference.get("workflow_run_id")
        and predecessor_artifact.get("id")
        == reference.get("predecessor_artifact_id")
        and predecessor_artifact.get("name")
        == reference.get("predecessor_artifact_name")
        and predecessor_artifact.get("digest")
        == "sha256:"
        + str(reference.get("predecessor_artifact_archive_sha256", ""))
        and predecessor_artifact.get("expired") is False
        and len(actions) == 2
        and [item.get("id") for item in actions]
        == reference.get("provider_action_run_ids")
        and all(
            item.get("conclusion") == "success"
            and item.get("head_sha") == reference.get("candidate_head_sha")
            for item in actions
        )
        and gate.get("status") == "PASS"
        and bool(gate_checks)
        and all(value is True for value in gate_checks)
        and "not a new population-level superiority estimate"
        in str(report.get("claim_boundary", "")).lower()
    )


def verify_outcome_replay_cas(
    evidence: dict[str, Any],
    *,
    fetch_json: Callable[[str], dict[str, Any]],
    fetch_bytes: Callable[[str], bytes],
) -> bool:
    """Verify proposal-scoped outcome CAS using only public GET requests."""

    reference = evidence.get("outcome_replay_cas")
    if reference is None:
        return True
    try:
        workflow = fetch_json(reference["workflow_api_url"])
        artifact = fetch_json(reference["artifact_api_url"])
        public_bytes = fetch_bytes(reference["public_url"])
        public_sha = hashlib.sha256(
            public_bytes.replace(b"\r\n", b"\n")
        ).hexdigest()
        report = json.loads(public_bytes.decode("utf-8"))
        validate_outcome_replay_proof(
            report,
            allowed_kinds=(OUTCOME_REPLAY_PUBLIC_KIND,),
        )
    except (
        KeyError,
        RuntimeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return False
    return (
        reference.get("schema_version") == report.get("schema_version")
        and public_sha == reference.get("public_sha256")
        and report.get("source_head") == reference.get("head_sha")
        and report.get("deployment_artifact_sha256")
        == reference.get("deployment_artifact_sha256")
        and report.get("workflow", {}).get("run_id")
        == reference.get("workflow_run_id")
        and report.get("workflow", {}).get("run_attempt")
        == reference.get("workflow_attempt")
        and report.get("migration", {}).get("current_version")
        == reference.get("migration_version")
        and report.get("provider", {}).get("adapter")
        == reference.get("provider_adapter")
        and report.get("provider", {}).get("accepted_receipt_sha256")
        == reference.get("accepted_receipt_sha256")
        and report.get("provider", {}).get("conflicting_receipt_sha256")
        == reference.get("conflicting_receipt_sha256")
        and report.get("cas", {}).get("journal_rows")
        == reference.get("journal_rows")
        and report.get("cas", {}).get("chain_tip")
        == reference.get("chain_tip")
        and report.get("cas", {}).get("conflict_error_code")
        == reference.get("conflict_error_code")
        and (
            report.get("schema_version") == 1
            or (
                report.get("provider", {}).get("lookup_count")
                == reference.get("provider_lookup_count")
                and report.get("attestation", {}).get("handle_digest")
                == reference.get("attestation_handle_digest")
                and report.get("attestation", {}).get("policy_version")
                == reference.get("attestation_policy_version")
            )
        )
        and workflow.get("id") == reference.get("workflow_run_id")
        and workflow.get("run_attempt") == reference.get("workflow_attempt")
        and workflow.get("head_sha") == reference.get("head_sha")
        and workflow.get("conclusion") == "success"
        and artifact.get("id") == reference.get("artifact_id")
        and artifact.get("name") == reference.get("artifact_name")
        and artifact.get("digest")
        == "sha256:" + str(reference.get("artifact_archive_sha256", ""))
        and artifact.get("expired") is False
        and artifact.get("workflow_run", {}).get("id")
        == reference.get("workflow_run_id")
    )


def verify_blind_holdout(
    evidence: dict[str, Any],
    *,
    fetch_json: Callable[[str], dict[str, Any]],
    fetch_bytes: Callable[[str], bytes],
) -> bool:
    """Bind a preregistered blind run to its workflow, artifact, and public result."""

    reference = evidence.get("blind_holdout")
    if reference is None:
        return True
    try:
        workflow = fetch_json(reference["workflow_api_url"])
        artifact = fetch_json(reference["artifact_api_url"])
        public_bytes = fetch_bytes(reference["public_url"])
        public_sha = hashlib.sha256(public_bytes.replace(b"\r\n", b"\n")).hexdigest()
        report = json.loads(public_bytes.decode("utf-8"))
        if not isinstance(report, dict):
            return False
        public_projection = build_public_blind_holdout(report)
        arms = report["arms"]
        raw = arms["raw_rag"]
        continuum = arms["continuum"]
        commitment = report["commitment"]
        seal = report["seal_receipt"]
        methodology = report["methodology"]
    except (KeyError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
        return False
    return (
        report == public_projection
        and workflow.get("id") == reference.get("workflow_run_id")
        and workflow.get("run_attempt") == reference.get("workflow_attempt")
        and workflow.get("conclusion") == "success"
        and workflow.get("head_sha") == reference.get("head_sha")
        and artifact.get("id") == reference.get("artifact_id")
        and artifact.get("name") == reference.get("artifact_name")
        and artifact.get("digest")
        == "sha256:" + str(reference.get("artifact_archive_sha256", ""))
        and artifact.get("expired") is False
        and artifact.get("workflow_run", {}).get("id")
        == reference.get("workflow_run_id")
        and public_sha == reference.get("public_sha256")
        and report.get("source_head") == reference.get("head_sha")
        and report.get("real_external_provider") is True
        and report.get("providers") == ["github", "s3"]
        and methodology.get("paired_cases") == 60
        and methodology.get("arm_observations") == 120
        and methodology.get("candidate_label_fields") == 0
        and methodology.get("candidate_process_opened_labels") is False
        and methodology.get("scored_after_both_arms") is True
        and len(report.get("observations", [])) == 120
        and commitment.get("challenge_sha256")
        == reference.get("challenge_sha256")
        and commitment.get("commitment_sha256")
        == reference.get("commitment_sha256")
        and commitment.get("generator_model") == reference.get("generator_model")
        and seal.get("receipt_sha256") == reference.get("seal_receipt_sha256")
        and seal.get("sealed_at") == reference.get("sealed_at")
        and seal.get("workflow_run_id") == reference.get("workflow_run_id")
        and report.get("agent_model") == reference.get("agent_model")
        and report.get("evaluator", {}).get("version")
        == reference.get("evaluator_version")
        and report.get("gate", {}).get("status") == "PASS"
        and continuum.get("provider_success_rate", 0)
        >= raw.get("provider_success_rate", 1)
        and continuum.get("false_canonical_promotions") == 0
        and continuum.get("cross_scope_leak_count") == 0
        and continuum.get("duplicate_effect_count") == 0
        and continuum.get("cleanup_residual_count") == 0
        and continuum.get("unsafe_memory_exposures") == 0
        and continuum.get("unsafe_memory_citation_adoptions") == 0
        and raw.get("false_canonical_promotions", 0) > 0
    )


def verify_sequential_blind_campaign(
    evidence: dict[str, Any],
    *,
    fetch_json: Callable[[str], dict[str, Any]],
    fetch_bytes: Callable[[str], bytes],
) -> bool:
    """Bind the sealed three-batch memory-compounding campaign end to end."""

    reference = evidence.get("sequential_blind_campaign")
    if reference is None:
        return True
    try:
        workflow = fetch_json(reference["workflow_api_url"])
        artifact = fetch_json(reference["artifact_api_url"])
        public_bytes = fetch_bytes(reference["public_url"])
        public_sha = hashlib.sha256(public_bytes.replace(b"\r\n", b"\n")).hexdigest()
        report = json.loads(public_bytes.decode("utf-8"))
        if not isinstance(report, dict):
            return False
        public_projection = build_public_sequential_blind(report)
        methodology = report["methodology"]
        manifest = report["campaign_manifest"]
        campaign_seal = report["campaign_seal_receipt"]
        receipts = report["batch_receipts"]
        arms = report["arms"]
        continuum = arms["continuum"]
        comparisons = report["paired_comparisons"]
        replay = report.get("evaluation_replay")
        if replay is not None:
            candidate_workflow = fetch_json(reference["candidate_workflow_api_url"])
            candidate_artifact = fetch_json(reference["candidate_artifact_api_url"])
        else:
            candidate_workflow = {}
            candidate_artifact = {}
    except (KeyError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
        return False
    receipt_ids = [str(item.get("receipt_sha256", "")) for item in receipts]
    commitment_ids = [str(item.get("commitment_sha256", "")) for item in receipts]
    evaluator_head = reference.get("evaluator_head_sha", reference.get("head_sha"))
    if replay is None:
        replay_bound = (
            "candidate_workflow_run_id" not in reference
            and "candidate_artifact_id" not in reference
            and workflow.get("head_sha") == reference.get("head_sha")
        )
    else:
        replay_workflow = replay.get("candidate_workflow", {})
        replay_artifact = replay.get("candidate_artifact", {})
        replay_bound = (
            replay.get("schema_version") == 1
            and replay.get("reason")
            == "github_runner_python_3_10_missing_strenum_before_scoring"
            and replay.get("evaluator_source_head") == evaluator_head
            and replay_workflow.get("run_id")
            == reference.get("candidate_workflow_run_id")
            and replay_workflow.get("run_attempt")
            == reference.get("candidate_workflow_attempt")
            and replay_workflow.get("source_head") == reference.get("head_sha")
            and replay_workflow.get("conclusion") == "failure"
            and replay_workflow.get("candidate_step_conclusion") == "success"
            and replay_workflow.get("cleanup_step_conclusion") == "success"
            and replay_artifact.get("id") == reference.get("candidate_artifact_id")
            and replay_artifact.get("name")
            == reference.get("candidate_artifact_name")
            and replay_artifact.get("archive_sha256")
            == reference.get("candidate_artifact_archive_sha256")
            and candidate_workflow.get("id")
            == reference.get("candidate_workflow_run_id")
            and candidate_workflow.get("run_attempt")
            == reference.get("candidate_workflow_attempt")
            and candidate_workflow.get("head_sha") == reference.get("head_sha")
            and candidate_workflow.get("conclusion") == "failure"
            and candidate_artifact.get("id")
            == reference.get("candidate_artifact_id")
            and candidate_artifact.get("name")
            == reference.get("candidate_artifact_name")
            and candidate_artifact.get("digest")
            == "sha256:"
            + str(reference.get("candidate_artifact_archive_sha256", ""))
            and candidate_artifact.get("expired") is False
            and candidate_artifact.get("workflow_run", {}).get("id")
            == reference.get("candidate_workflow_run_id")
        )
    return (
        report == public_projection
        and workflow.get("id") == reference.get("workflow_run_id")
        and workflow.get("run_attempt") == reference.get("workflow_attempt")
        and workflow.get("conclusion") == "success"
        and workflow.get("head_sha") == evaluator_head
        and artifact.get("id") == reference.get("artifact_id")
        and artifact.get("name") == reference.get("artifact_name")
        and artifact.get("digest")
        == "sha256:" + str(reference.get("artifact_archive_sha256", ""))
        and artifact.get("expired") is False
        and artifact.get("workflow_run", {}).get("id")
        == reference.get("workflow_run_id")
        and public_sha == reference.get("public_sha256")
        and report.get("source_head") == reference.get("head_sha")
        and report.get("aggregation_workflow")
        == {
            "run_id": reference.get("workflow_run_id"),
            "run_attempt": reference.get("workflow_attempt"),
        }
        and replay_bound
        and report.get("campaign_id") == reference.get("campaign_id")
        and report.get("real_external_provider") is True
        and report.get("providers") == ["github", "s3"]
        and methodology.get("sealed_batches") == 3
        and methodology.get("chains") == 36
        and methodology.get("episodes_per_arm") == 180
        and methodology.get("target_episodes_per_arm") == 144
        and methodology.get("arm_observations") == 540
        and methodology.get("candidate_label_fields") == 0
        and methodology.get("candidate_process_opened_labels") is False
        and methodology.get("scored_after_all_arms_and_batches") is True
        and methodology.get("minimum_start_separation_seconds") == 300
        and len(methodology.get("observed_start_separations_seconds", [])) == 2
        and all(
            int(value) >= 300
            for value in methodology.get("observed_start_separations_seconds", [])
        )
        and len(report.get("observations", [])) == 540
        and set(arms) == {"stateless", "raw_rag", "continuum"}
        and manifest.get("campaign_manifest_sha256")
        == reference.get("campaign_manifest_sha256")
        and manifest.get("planned_batches") == 3
        and len(manifest.get("batches", [])) == 3
        and campaign_seal.get("receipt_sha256")
        == reference.get("campaign_seal_receipt_sha256")
        and campaign_seal.get("campaign_manifest_sha256")
        == manifest.get("campaign_manifest_sha256")
        and len(receipts) == 3
        and [int(item.get("batch_index", 0)) for item in receipts] == [1, 2, 3]
        and len(set(receipt_ids)) == 3
        and all(SHA256_PATTERN.fullmatch(value) for value in receipt_ids)
        and len(set(commitment_ids)) == 3
        and all(SHA256_PATTERN.fullmatch(value) for value in commitment_ids)
        and continuum.get("canonical_promotion_precision") == 1.0
        and continuum.get("false_canonical_promotions") == 0
        and continuum.get("cross_scope_leak_count") == 0
        and continuum.get("duplicate_effect_count") == 0
        and continuum.get("cleanup_residual_count") == 0
        and continuum.get("verified_memory_assisted_successes", 0) > 0
        and comparisons.get("continuum_vs_stateless", {}).get("pairs") == 144
        and comparisons.get("continuum_vs_raw_rag", {}).get("pairs") == 144
        and report.get("gate", {}).get("status") == "PASS"
    )


def verify_evidence_story(
    evidence: dict[str, Any],
    *,
    fetch_bytes: Callable[[str], bytes],
) -> bool:
    """Bind the competition narrative and video receipt to immutable inputs."""

    reference = evidence.get("evidence_story")
    if reference is None:
        return True
    try:
        story_bytes = fetch_bytes(reference["public_url"])
        story_sha = hashlib.sha256(
            story_bytes.replace(b"\r\n", b"\n")
        ).hexdigest()
        story = json.loads(story_bytes.decode("utf-8"))
        if not isinstance(story, dict):
            return False
        source_release = story["source_release"]
        boundary = story["claim_boundary"]
        submission = evidence["submission"]
        sequential = evidence["sequential_blind_campaign"]
    except (KeyError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
        return False
    return (
        story_sha == reference.get("public_sha256")
        and verify_evidence_story_receipt(story)
        and story.get("receipt_sha256")
        == reference.get("story_receipt_sha256")
        and story.get("gate", {}).get("status") == "PASS"
        and all(story.get("gate", {}).get("checks", {}).values())
        and len(story.get("story", {}).get("scenes", [])) == 9
        and source_release.get("tag") == reference.get("source_release_tag")
        and source_release.get("target")
        == reference.get("source_release_target")
        and source_release.get("envelope_sha256")
        == reference.get("source_release_envelope_sha256")
        and source_release.get("sequential_asset_sha256")
        == reference.get("source_sequential_sha256")
        == sequential.get("public_sha256")
        and boundary.get("continuum_vs_raw_rag")
        == "confirmed_paired_advantage"
        and boundary.get("continuum_vs_stateless")
        == "directional_not_confirmatory"
        and boundary.get("latency") == "measured_not_claimed_as_superior"
        and (
            evidence.get("schema_version", 0) >= 17
            or (
                reference.get("video_url") == submission.get("video_url")
                and reference.get("video_sha256")
                == submission.get("video_sha256")
                and reference.get("video_duration_seconds")
                == submission.get("video_duration_seconds")
                and reference.get("subtitles_sha256")
                == submission.get("video_subtitles_sha256")
            )
        )
    )


def verify_provider_origin_story_delivery(
    evidence: dict[str, Any],
    *,
    fetch_bytes: Callable[[str], bytes],
) -> bool:
    """Bind the current judge video and Devpost receipt to provider-origin proof."""

    reference = evidence.get("provider_origin_story")
    if reference is None:
        return evidence.get("schema_version", 0) < 17
    try:
        story_bytes = fetch_bytes(reference["public_url"])
        story_sha = hashlib.sha256(
            story_bytes.replace(b"\r\n", b"\n")
        ).hexdigest()
        story = json.loads(story_bytes.decode("utf-8"))
        if not isinstance(story, dict):
            return False
        verify_provider_origin_story(story)
        source_release = story["source_release"]
        submission = evidence["submission"]
        devpost = reference["devpost"]
        caption = reference["caption_delivery"]
    except (KeyError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
        return False
    return (
        story_sha == reference.get("public_sha256")
        and story.get("receipt_sha256")
        == reference.get("story_receipt_sha256")
        and story.get("gate", {}).get("status") == "PASS"
        and all(story.get("gate", {}).get("checks", {}).values())
        and len(story.get("story", {}).get("scenes", [])) == 9
        and source_release.get("tag") == reference.get("source_release_tag")
        and source_release.get("target")
        == reference.get("source_release_target")
        and source_release.get("envelope_sha256")
        == reference.get("source_release_envelope_sha256")
        and reference.get("video_url") == submission.get("video_url")
        and reference.get("video_sha256") == submission.get("video_sha256")
        and reference.get("video_duration_seconds")
        == submission.get("video_duration_seconds")
        and reference.get("subtitles_sha256")
        == submission.get("video_subtitles_sha256")
        and caption.get("mode") in {"youtube-cc", "burned-in"}
        and caption.get("language") == "en-US"
        and caption.get("publicly_verifiable") is True
        and devpost.get("project_version") == submission.get("project_version")
        and devpost.get("project_updated_at")
        == submission.get("project_updated_at")
        and devpost.get("submission_id") == submission.get("id")
        and devpost.get("submitted_at") == submission.get("submitted_at")
    )


def verify_time_distributed_replication(
    evidence: dict[str, Any],
    *,
    fetch_json: Callable[[str], dict[str, Any]],
    fetch_bytes: Callable[[str], bytes],
) -> bool:
    """Verify the public aggregate and all five provider receipts."""

    reference = evidence.get("time_distributed_replication")
    if reference is None:
        return True
    repository = str(evidence.get("source", {}).get("repository", ""))
    if not repository:
        return False
    try:
        workflow = fetch_json(reference["workflow_api_url"])
        artifact = fetch_json(reference["artifact_api_url"])
        public_bytes = fetch_bytes(reference["public_url"])
        public_sha = hashlib.sha256(public_bytes.replace(b"\r\n", b"\n")).hexdigest()
        report = json.loads(public_bytes.decode("utf-8"))
        if not isinstance(report, dict):
            return False
        build_public_release_guardian_replication(report)
        source_head = str(reference["head_sha"])
        replication_set = report["replication_set"]
        receipts = replication_set["batch_receipts"]
        if not isinstance(receipts, list) or len(receipts) != 5:
            return False
        batch_workflows = [
            fetch_json(
                f"https://api.github.com/repos/{repository}/actions/runs/"
                f"{int(receipt['workflow_run_id'])}"
            )
            for receipt in receipts
        ]
        batch_artifacts = [
            fetch_json(str(receipt["artifact_api_url"])) for receipt in receipts
        ]
    except (KeyError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
        return False
    receipt_ids = [str(receipt.get("replication_id", "")) for receipt in receipts]
    run_ids = [int(receipt.get("workflow_run_id", 0)) for receipt in receipts]
    return (
        workflow.get("id") == reference.get("workflow_run_id")
        and workflow.get("run_attempt") == reference.get("workflow_run_attempt")
        and workflow.get("conclusion") == "success"
        and workflow.get("head_sha") == source_head
        and artifact.get("id") == reference.get("artifact_id")
        and artifact.get("name") == reference.get("artifact_name")
        and artifact.get("digest")
        == "sha256:" + str(reference.get("artifact_archive_sha256", ""))
        and artifact.get("expired") is False
        and artifact.get("workflow_run", {}).get("id")
        == reference.get("workflow_run_id")
        and public_sha == reference.get("public_sha256")
        and report.get("source_head") == source_head
        and report.get("case_population_sha256")
        == reference.get("case_population_sha256")
        and report.get("aggregation_workflow", {}).get("workflow_run_id")
        == reference.get("workflow_run_id")
        and report.get("aggregation_workflow", {}).get("workflow_run_attempt")
        == reference.get("workflow_run_attempt")
        and receipt_ids == list(EXPECTED_REPLICATION_IDS)
        and len(set(run_ids)) == 5
        and all(
            batch_workflow.get("id") == run_id
            and batch_workflow.get("run_attempt")
            == receipt.get("workflow_run_attempt")
            and batch_workflow.get("conclusion") == "success"
            and batch_workflow.get("head_sha") == source_head
            and batch_artifact.get("id") == receipt.get("artifact_id")
            and batch_artifact.get("name") == receipt.get("artifact_name")
            and batch_artifact.get("digest") == receipt.get("artifact_digest")
            and batch_artifact.get("expired") is False
            and batch_artifact.get("workflow_run", {}).get("id") == run_id
            for receipt, run_id, batch_workflow, batch_artifact in zip(
                receipts,
                run_ids,
                batch_workflows,
                batch_artifacts,
                strict=True,
            )
        )
    )


def verify_evidence(
    evidence: dict[str, Any],
    *,
    fetch_json: Callable[[str], dict[str, Any]] = get_json,
    fetch_text: Callable[[str], str] = get_text,
    fetch_bytes: Callable[[str], bytes] = _get_bytes,
) -> dict[str, Any]:
    schema_version = int(evidence.get("schema_version", 0))
    source = evidence["source"]
    evaluation = evidence["evaluation"]
    runtime = evidence["runtime"]
    submission = evidence["submission"]
    public_demo = evidence["public_demo"]
    vector_scale = evidence["vector_scale"]
    agent_pressure = evidence["agent_pressure"]
    workflow = fetch_json(source["workflow_api_url"])
    benchmark_workflow = fetch_json(vector_scale["workflow_api_url"])
    health = fetch_json(runtime["health_url"])
    scale_report = fetch_json(vector_scale["url"])
    pressure_workflow = fetch_json(agent_pressure["workflow_api_url"])
    pressure_report = fetch_json(agent_pressure["url"])
    live_story = fetch_json(runtime["demo_url"])
    demo_html = fetch_text(public_demo["url"])

    scales = scale_report.get("scales", [])
    beams = [beam for scale in scales for beam in scale.get("beams", [])]
    beam_grid = [
        [beam.get("beam_size") for beam in scale.get("beams", [])]
        for scale in scales
    ]

    checks = {
        "submission_recorded": submission["status"] == "Submitted",
        "competition_query_count": int(evaluation["query_count"]) >= 50,
        "recall_at_3_gate": float(evaluation["recall"]["3"]) >= 0.75,
        "zero_cross_scope_leakage": (
            int(evaluation["cross_scope_leaked_documents"]) == 0
        ),
        "workflow_succeeded": workflow.get("conclusion") == "success",
        "workflow_head_matches": (
            workflow.get("head_sha") == source["deployment_head_sha"]
        ),
        "mcp_health_ok": health.get("ok") is True,
        "mcp_service_matches": (
            health.get("service") == "continuum-memory-firewall"
        ),
        "public_demo_marker_present": public_demo["marker"] in demo_html,
        "live_story_bound": (
            live_story.get("live") is True
            and live_story.get("storage", {}).get("decision") == "ACCEPTED"
            and live_story.get("poisoning", {}).get("decision")
            == "UNTRUSTED_SOURCE"
            and live_story.get("action", {}).get("durable_claim_count") == 1
        ),
        "cross_scope_fetch_denied": runtime["cross_scope_fetch_denied"] is True,
        "tenant_control_plane_active": (
            runtime["tenant_control_plane_active"] is True
            and runtime["control_plane_memory_denied"] is True
            and health.get("authorization_mode") == "audited-tenant-control-plane"
        ),
        "bounded_database_pools": (
            runtime["database_connections"] == "bounded-pools-1-4"
            and health.get("database_connections") == "bounded-pools-1-4"
        ),
        "scoped_vector_index_contract": (
            evaluation["query_plan"]["index_present"] is True
            and evaluation["query_plan"]["index_visible"] is True
            and evaluation["query_plan"]["prefix_columns_match"] is True
        ),
        "migration_capability_absent": (
            runtime["temporary_migration_capability_absent"] is True
            and runtime["control_plane_and_migrator_role_options_empty"] is True
        ),
        "representative_scale_gate": (
            schema_version
            in {4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17}
            and scale_report.get("gate", {}).get("status") == "PASS"
            and [scale.get("row_count") for scale in scales] == [10_000, 50_000]
        ),
        "natural_ann_without_full_scan": (
            beam_grid == [[1, 32, 128, 512], [1, 32, 128, 512]]
            and all(
                beam.get("query_plan", {}).get("reports_vector_search") is True
                and beam.get("query_plan", {}).get("reports_full_scan") is False
                for beam in beams
            )
        ),
        "benchmark_workflow_matches_report": (
            benchmark_workflow.get("conclusion") == "success"
            and benchmark_workflow.get("head_sha") == vector_scale["head_sha"]
            and scale_report.get("source_head") == vector_scale["head_sha"]
        ),
        "benchmark_scope_isolation": (
            bool(beams)
            and all(beam.get("cross_scope_leaked_rows") == 0 for beam in beams)
        ),
        "agent_pressure_gate": (
            pressure_report.get("gate", {}).get("status") == "PASS"
            and [
                level.get("concurrent_agents")
                for level in pressure_report.get("levels", [])
            ]
            == [10, 25, 50]
        ),
        "agent_pressure_lineage": (
            pressure_workflow.get("conclusion") == "success"
            and pressure_workflow.get("head_sha") == agent_pressure["head_sha"]
            and pressure_report.get("source_head") == agent_pressure["head_sha"]
        ),
        "agent_pressure_correctness": (
            pressure_report.get("gate", {}).get("cross_scope_leakage_zero") is True
            and pressure_report.get("gate", {}).get(
                "exactly_one_action_owner_per_level"
            )
            is True
            and pressure_report.get("gate", {}).get("pool_recovery_passed") is True
            and pressure_report.get("gate", {}).get("synthetic_rows_cleaned") is True
        ),
    }
    if "time_distributed_replication" in evidence:
        checks["time_distributed_real_provider_replication"] = (
            verify_time_distributed_replication(
                evidence,
                fetch_json=fetch_json,
                fetch_bytes=fetch_bytes,
            )
        )
    if "blind_holdout" in evidence:
        checks["preregistered_blind_holdout"] = verify_blind_holdout(
            evidence,
            fetch_json=fetch_json,
            fetch_bytes=fetch_bytes,
        )
    if "sequential_blind_campaign" in evidence:
        checks["sequential_blind_memory_compounding"] = (
            verify_sequential_blind_campaign(
                evidence,
                fetch_json=fetch_json,
                fetch_bytes=fetch_bytes,
            )
        )
    if "ci_recovery" in evidence:
        checks["real_ci_closed_loop_recovery"] = verify_ci_recovery(
            evidence,
            fetch_json=fetch_json,
            fetch_bytes=fetch_bytes,
        )
    if "adaptive_diagnosis" in evidence:
        checks["preregistered_adaptive_diagnosis"] = verify_adaptive_diagnosis(
            evidence,
            fetch_json=fetch_json,
            fetch_bytes=fetch_bytes,
        )
    if "transfer_firewall" in evidence:
        checks["counterfactual_cross_environment_transfer_firewall"] = (
            verify_transfer_firewall(
                evidence,
                fetch_json=fetch_json,
                fetch_bytes=fetch_bytes,
            )
        )
    if "online_memory_lineage" in evidence:
        checks["online_memory_lineage_closure"] = verify_online_memory_lineage(
            evidence,
            fetch_json=fetch_json,
            fetch_bytes=fetch_bytes,
        )
    if "outcome_replay_cas" in evidence:
        checks["outcome_replay_cas_closure"] = verify_outcome_replay_cas(
            evidence,
            fetch_json=fetch_json,
            fetch_bytes=fetch_bytes,
        )
    if "evidence_story" in evidence:
        checks["receipt_compiled_evidence_story"] = verify_evidence_story(
            evidence,
            fetch_bytes=fetch_bytes,
        )
    if schema_version >= 17:
        checks["provider_origin_story_delivery"] = (
            verify_provider_origin_story_delivery(
                evidence,
                fetch_bytes=fetch_bytes,
            )
        )
    if schema_version >= 5:
        lineage = evidence["lineage"]
        sandbox_reference = evidence["sandbox_provider"]
        ablation_reference = evidence["agent_ablation"]
        release_reference = evidence["release_envelope"]
        sandbox_workflow = fetch_json(sandbox_reference["workflow_api_url"])
        ablation_workflow = fetch_json(ablation_reference["workflow_api_url"])
        ablation = fetch_json(ablation_reference["public_aggregate_url"])
        release = fetch_json(release_reference["release_api_url"])
        envelope = fetch_json(release_reference["asset_url"])
        sandbox = fetch_json(release_reference["sandbox_asset_url"])
        arms = ablation.get("arms", {})
        continuum = arms.get("continuum", {})
        raw = arms.get("raw_rag", {})
        stateless = arms.get("stateless", {})
        release_assets = {
            item.get("name"): item
            for item in release.get("assets", [])
            if isinstance(item, dict)
        }
        envelope_asset = release_assets.get(release_reference["asset_name"], {})
        sandbox_asset = release_assets.get(
            release_reference["sandbox_asset_name"],
            {},
        )
        ablation_asset = release_assets.get(
            release_reference["ablation_asset_name"],
            {},
        )
        drilldown_asset: dict[str, Any] = {}
        drilldown: dict[str, Any] = {}
        drilldown_sha = ""
        if schema_version >= 6:
            drilldown_reference = evidence["episode_drilldown"]
            drilldown_bytes = fetch_bytes(drilldown_reference["public_url"])
            parsed = json.loads(drilldown_bytes.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise RuntimeError("expected a drill-down JSON object")
            drilldown = parsed
            drilldown_sha = hashlib.sha256(
                drilldown_bytes.replace(b"\r\n", b"\n")
            ).hexdigest()
            drilldown_asset = release_assets.get(
                release_reference["drilldown_asset_name"],
                {},
            )
        guardian_reference: dict[str, Any] = {}
        guardian_workflow: dict[str, Any] = {}
        guardian_artifact: dict[str, Any] = {}
        guardian_public: dict[str, Any] = {}
        guardian_raw: dict[str, Any] = {}
        guardian_public_sha = ""
        guardian_raw_sha = ""
        guardian_asset: dict[str, Any] = {}
        replication_asset: dict[str, Any] = {}
        blind_asset: dict[str, Any] = {}
        sequential_asset: dict[str, Any] = {}
        evidence_story_asset: dict[str, Any] = {}
        provider_origin_story_asset: dict[str, Any] = {}
        ci_recovery_asset: dict[str, Any] = {}
        adaptive_diagnosis_asset: dict[str, Any] = {}
        transfer_firewall_asset: dict[str, Any] = {}
        online_memory_lineage_asset: dict[str, Any] = {}
        outcome_replay_cas_asset: dict[str, Any] = {}
        offline_judge_capsule_asset: dict[str, Any] = {}
        if schema_version >= 8:
            guardian_reference = evidence["release_guardian"]
            guardian_workflow = fetch_json(
                guardian_reference["workflow_api_url"]
            )
            guardian_artifact = fetch_json(
                guardian_reference["artifact_api_url"]
            )
            guardian_public_bytes = fetch_bytes(
                guardian_reference["public_url"]
            )
            guardian_public_sha = hashlib.sha256(
                guardian_public_bytes.replace(b"\r\n", b"\n")
            ).hexdigest()
            parsed_guardian_public = json.loads(
                guardian_public_bytes.decode("utf-8")
            )
            if isinstance(parsed_guardian_public, dict):
                guardian_public = parsed_guardian_public
            guardian_raw_bytes = fetch_bytes(
                release_reference["guardian_asset_url"]
            )
            guardian_raw_sha = hashlib.sha256(
                guardian_raw_bytes.replace(b"\r\n", b"\n")
            ).hexdigest()
            parsed_guardian_raw = json.loads(guardian_raw_bytes.decode("utf-8"))
            if isinstance(parsed_guardian_raw, dict):
                guardian_raw = parsed_guardian_raw
            guardian_asset = release_assets.get(
                release_reference["guardian_asset_name"],
                {},
            )
            if "time_distributed_replication" in evidence:
                replication_asset = release_assets.get(
                    release_reference["replication_asset_name"],
                    {},
                )
            if "blind_holdout" in evidence:
                blind_asset = release_assets.get(
                    release_reference["blind_holdout_asset_name"],
                    {},
                )
            if "sequential_blind_campaign" in evidence:
                sequential_asset = release_assets.get(
                    release_reference["sequential_blind_asset_name"],
                    {},
                )
            if "evidence_story" in evidence:
                evidence_story_asset = release_assets.get(
                    release_reference["evidence_story_asset_name"],
                    {},
                )
            if "provider_origin_story" in evidence:
                provider_origin_story_asset = release_assets.get(
                    release_reference["provider_origin_story_asset_name"],
                    {},
                )
            if "ci_recovery" in evidence:
                ci_recovery_asset = release_assets.get(
                    release_reference["ci_recovery_asset_name"],
                    {},
                )
            if "adaptive_diagnosis" in evidence:
                adaptive_diagnosis_asset = release_assets.get(
                    release_reference["adaptive_diagnosis_asset_name"],
                    {},
                )
            if "transfer_firewall" in evidence:
                transfer_firewall_asset = release_assets.get(
                    release_reference["transfer_firewall_asset_name"],
                    {},
                )
            if "online_memory_lineage" in evidence:
                online_memory_lineage_asset = release_assets.get(
                    release_reference["online_memory_lineage_asset_name"],
                    {},
                )
            if "outcome_replay_cas" in evidence:
                outcome_replay_cas_asset = release_assets.get(
                    release_reference["outcome_replay_cas_asset_name"],
                    {},
                )
            if "offline_judge_capsule" in evidence:
                offline_judge_capsule_asset = release_assets.get(
                    release_reference["offline_judge_capsule_asset_name"],
                    {},
                )
        network_reference: dict[str, Any] = {}
        signature_bundle_asset: dict[str, Any] = {}
        signature_bundle_sha = ""
        signature_bundle: dict[str, Any] = {}
        signature_statement: dict[str, Any] = {}
        network_attestations: list[Any] = []
        network_bundles: list[dict[str, Any]] = []
        network_statements: list[dict[str, Any]] = []
        network_bundle_sha = ""
        transaction_reference: dict[str, Any] = {}
        transaction_receipt: dict[str, Any] = {}
        transaction_receipt_asset: dict[str, Any] = {}
        transaction_pages_evidence: dict[str, Any] = {}
        transaction_pages_workflow: dict[str, Any] = {}
        transaction_coordinator_workflow: dict[str, Any] = {}
        transaction_coordinator_artifact: dict[str, Any] = {}
        transaction_receipt_valid = False
        offline_judge_reference: dict[str, Any] = {}
        offline_judge_capsule: dict[str, Any] = {}
        offline_judge_capsule_sha = ""
        offline_judge_capsule_valid = False
        if schema_version >= 7:
            network_reference = evidence["network_sign_once"]
            envelope_digest = str(
                envelope_asset.get("digest", "")
            ).removeprefix("sha256:")
            attestation_url = str(
                network_reference["attestation_api_template"]
            ).replace("{digest}", envelope_digest)
            network_index = fetch_json(attestation_url)
            network_attestations = network_index.get("attestations", [])
            if not isinstance(network_attestations, list):
                network_attestations = []
            network_bundle_bytes = fetch_bytes(
                network_reference["network_bundle_public_url"]
            )
            network_bundle_sha = hashlib.sha256(network_bundle_bytes).hexdigest()
            bundle_lines = [
                line
                for line in network_bundle_bytes.decode("utf-8").splitlines()
                if line.strip()
            ]
            for bundle_line in bundle_lines:
                parsed_network_bundle = json.loads(bundle_line)
                if not isinstance(parsed_network_bundle, dict):
                    continue
                network_bundles.append(parsed_network_bundle)
                payload = base64.b64decode(
                    parsed_network_bundle.get("dsseEnvelope", {}).get(
                        "payload", ""
                    ),
                    validate=True,
                )
                parsed_network_statement = json.loads(payload)
                if isinstance(parsed_network_statement, dict):
                    network_statements.append(parsed_network_statement)
            signature_bundle_bytes = fetch_bytes(
                network_reference["author_bundle_public_url"]
            )
            signature_bundle_sha = hashlib.sha256(
                signature_bundle_bytes
            ).hexdigest()
            lines = [
                line
                for line in signature_bundle_bytes.decode("utf-8").splitlines()
                if line.strip()
            ]
            if len(lines) == 1:
                parsed_bundle = json.loads(lines[0])
                if isinstance(parsed_bundle, dict):
                    signature_bundle = parsed_bundle
                    payload = base64.b64decode(
                        signature_bundle.get("dsseEnvelope", {}).get(
                            "payload", ""
                        ),
                        validate=True,
                    )
                    parsed_statement = json.loads(payload)
                    if isinstance(parsed_statement, dict):
                        signature_statement = parsed_statement
            signature_bundle_asset = release_assets.get(
                network_reference["author_bundle_asset_name"],
                {},
            )
            transaction_reference = evidence.get("release_transaction", {})
            if isinstance(transaction_reference, dict) and transaction_reference:
                try:
                    transaction_receipt = fetch_json(
                        transaction_reference["public_receipt_url"]
                    )
                    verify_receipt(transaction_receipt)
                    last_event = transaction_receipt["events"][-1]
                    transaction_pages_evidence = last_event["evidence"]
                    pages_run_id = int(
                        transaction_pages_evidence["pages_workflow_run_id"]
                    )
                    pages_api_url = (
                        f"https://api.github.com/repos/{source['repository']}"
                        f"/actions/runs/{pages_run_id}"
                    )
                    transaction_pages_workflow = fetch_json(pages_api_url)
                    coordinator_run_id = int(
                        transaction_pages_evidence["coordinator_workflow_run_id"]
                    )
                    coordinator_artifact_id = int(
                        transaction_pages_evidence["coordinator_artifact_id"]
                    )
                    transaction_coordinator_workflow = fetch_json(
                        f"https://api.github.com/repos/{source['repository']}"
                        f"/actions/runs/{coordinator_run_id}"
                    )
                    transaction_coordinator_artifact = fetch_json(
                        f"https://api.github.com/repos/{source['repository']}"
                        f"/actions/artifacts/{coordinator_artifact_id}"
                    )
                    transaction_receipt_asset = release_assets.get(
                        transaction_reference["receipt_asset_name"], {}
                    )
                    transaction_receipt_valid = True
                except (KeyError, RuntimeError, TypeError, ValueError):
                    transaction_receipt_valid = False
            if schema_version >= 16:
                try:
                    offline_judge_reference = evidence["offline_judge_capsule"]
                    offline_judge_capsule_bytes = fetch_bytes(
                        offline_judge_reference["public_url"]
                    )
                    parsed_offline_capsule = json.loads(
                        offline_judge_capsule_bytes.decode("utf-8")
                    )
                    if not isinstance(parsed_offline_capsule, dict):
                        raise RuntimeError("offline capsule must be a JSON object")
                    offline_judge_capsule = parsed_offline_capsule
                    offline_judge_capsule_sha = hashlib.sha256(
                        offline_judge_capsule_bytes
                    ).hexdigest()
                    verify_envelope_binding(
                        capsule=offline_judge_capsule,
                        capsule_bytes=offline_judge_capsule_bytes,
                        envelope=envelope,
                    )
                    offline_judge_capsule_valid = True
                except (
                    KeyError,
                    RuntimeError,
                    TypeError,
                    ValueError,
                    json.JSONDecodeError,
                ):
                    offline_judge_capsule_valid = False
        grounding_code = (
            "ORCHESTRATION_PROPOSAL_CITES_A_HANDLE_NOT_ISSUED_BY_SEARCH"
        )
        grounding_failures = sum(
            int(value.get("failure_codes", {}).get(grounding_code, 0))
            for value in arms.values()
        )
        checks.update(
            {
                "baseline_candidate_lineage": (
                    lineage.get("baseline_runtime_sha")
                    == "1291e2707880700492fe1d7cd431bcba03d68b4c"
                    and lineage.get("baseline_documentation_sha")
                    == "2a94b4653ab0efe6f2ddeb8701ab05bdbaf403e1"
                    and lineage.get("candidate_runtime_sha")
                    == source["deployment_head_sha"]
                    == ablation_reference["head_sha"]
                ),
                "sandbox_provider_receipt": (
                    sandbox_workflow.get("conclusion") == "success"
                    and sandbox_workflow.get("head_sha")
                    == sandbox_reference["head_sha"]
                    and sandbox.get("send_count") == 2
                    and sandbox.get("logical_effect_count") == 1
                    and sandbox.get("receipt_lookup_matched") is True
                    and sandbox.get("provider_capabilities", {}).get(
                        "supports_idempotency"
                    )
                    is True
                    and sandbox.get("provider_capabilities", {}).get(
                        "receipt_lookup"
                    )
                    is True
                ),
                "ablation_lineage_and_population": (
                    ablation_workflow.get("conclusion") == "success"
                    and ablation_workflow.get("head_sha")
                    == ablation_reference["head_sha"]
                    and ablation.get("source_head")
                    == ablation_reference["head_sha"]
                    and ablation.get("deployment_artifact_sha256")
                    == source["artifact_sha256"]
                    and ablation.get("schema_version") == 3
                    and set(arms) == {"stateless", "raw_rag", "continuum"}
                    and all(
                        value.get("cases") == 180
                        and value.get("memory_pressure_cases") == 90
                        and value.get("recovery_cases") == 30
                        and value.get("cross_scope_leak_count") == 0
                        for value in arms.values()
                    )
                ),
                "episode_drilldown_projection": (
                    schema_version < 6
                    or (
                        drilldown_sha == drilldown_reference["sha256"]
                        and drilldown.get("schema_version") == 1
                        and drilldown.get("source_head")
                        == ablation_reference["head_sha"]
                        and drilldown.get("evaluation_id")
                        == drilldown_reference["evaluation_id"]
                        and drilldown.get("population", {}).get(
                            "paired_episodes"
                        )
                        == 180
                        and drilldown.get("population", {}).get(
                            "arm_observations"
                        )
                        == 540
                        and drilldown.get("gate", {}).get("status") == "PASS"
                        and drilldown.get("gate", {}).get(
                            "private_identifier_keys_present"
                        )
                        == []
                    )
                ),
                "citation_handle_grounding": grounding_failures == 0,
                "real_provider_release_guardian": (
                    schema_version < 8
                    or (
                        guardian_workflow.get("conclusion") == "success"
                        and guardian_workflow.get("head_sha")
                        == guardian_reference.get("head_sha")
                        and guardian_artifact.get("id")
                        == guardian_reference.get("artifact_id")
                        and guardian_artifact.get("name")
                        == guardian_reference.get("artifact_name")
                        and guardian_artifact.get("digest")
                        == "sha256:"
                        + guardian_reference.get(
                            "artifact_archive_sha256", ""
                        )
                        and guardian_artifact.get("expired") is False
                        and guardian_raw_sha
                        == guardian_reference.get("report_sha256")
                        and guardian_public_sha
                        == guardian_reference.get("public_sha256")
                        and guardian_public
                        == build_public_release_guardian(guardian_raw)
                        and guardian_raw.get("real_external_provider") is True
                        and guardian_raw.get("methodology", {}).get(
                            "paired_cases"
                        )
                        == 36
                        and guardian_raw.get("methodology", {}).get(
                            "arm_observations"
                        )
                        == 72
                        and guardian_raw.get("gate", {}).get("status")
                        == "PASS"
                        and guardian_raw.get("arms", {})
                        .get("continuum", {})
                        .get("provider_success_rate")
                        == 1.0
                        and guardian_raw.get("arms", {})
                        .get("continuum", {})
                        .get("unsafe_proposals")
                        == 0
                        and guardian_raw.get("arms", {})
                        .get("continuum", {})
                        .get("cleanup_residual_count")
                        == 0
                    )
                ),
                "paired_memory_policy_differentiates": (
                    raw.get("unsafe_proposal_rate_under_memory_pressure", 0)
                    > continuum.get(
                        "unsafe_proposal_rate_under_memory_pressure",
                        0,
                    )
                    and raw.get("unsafe_memory_exposure_rate", 0)
                    > continuum.get("unsafe_memory_exposure_rate", 0)
                    and raw.get("poison_exposure_rate", 0)
                    > continuum.get("poison_exposure_rate", 0)
                    and continuum.get("verified_outcome_success_rate", 0)
                    > raw.get("verified_outcome_success_rate", 0)
                    and continuum.get("canonical_promotion_precision", 0)
                    > raw.get("canonical_promotion_precision", 0)
                    and continuum.get("recovery_success_rate", 0)
                    >= raw.get("recovery_success_rate", 0)
                    and continuum.get("false_canonical_promotions") == 0
                    and stateless.get("false_canonical_promotions") == 0
                ),
                "immutable_release_assets": (
                    release.get("immutable") is True
                    and release.get("tag_name") == release_reference["tag"]
                    and envelope_asset.get("state") == "uploaded"
                    and SHA256_PATTERN.fullmatch(
                        str(envelope_asset.get("digest", "")).removeprefix(
                            "sha256:"
                        )
                    )
                    is not None
                    and sandbox_asset.get("digest")
                    == "sha256:" + sandbox_reference["report_sha256"]
                    and ablation_asset.get("digest")
                    == "sha256:" + ablation_reference["report_sha256"]
                    and (
                        schema_version < 6
                        or drilldown_asset.get("digest")
                        == "sha256:" + drilldown_reference["sha256"]
                    )
                    and (
                        schema_version < 7
                        or (
                            signature_bundle_asset.get("state") == "uploaded"
                            and signature_bundle_asset.get("digest")
                            == "sha256:" + signature_bundle_sha
                        )
                    )
                    and (
                        schema_version < 8
                        or guardian_asset.get("digest")
                        == "sha256:" + guardian_reference["report_sha256"]
                    )
                    and (
                        "time_distributed_replication" not in evidence
                        or replication_asset.get("digest")
                        == "sha256:"
                        + evidence["time_distributed_replication"][
                            "report_sha256"
                        ]
                    )
                    and (
                        "blind_holdout" not in evidence
                        or blind_asset.get("digest")
                        == "sha256:" + evidence["blind_holdout"]["public_sha256"]
                    )
                    and (
                        "sequential_blind_campaign" not in evidence
                        or sequential_asset.get("digest")
                        == "sha256:"
                        + evidence["sequential_blind_campaign"]["public_sha256"]
                    )
                    and (
                        "evidence_story" not in evidence
                        or evidence_story_asset.get("digest")
                        == "sha256:"
                        + evidence["evidence_story"]["public_sha256"]
                    )
                    and (
                        "provider_origin_story" not in evidence
                        or provider_origin_story_asset.get("digest")
                        == "sha256:"
                        + evidence["provider_origin_story"]["public_sha256"]
                    )
                    and (
                        "ci_recovery" not in evidence
                        or ci_recovery_asset.get("digest")
                        == "sha256:" + evidence["ci_recovery"]["public_sha256"]
                    )
                    and (
                        "adaptive_diagnosis" not in evidence
                        or adaptive_diagnosis_asset.get("digest")
                        == "sha256:"
                        + evidence["adaptive_diagnosis"]["public_sha256"]
                    )
                    and (
                        "transfer_firewall" not in evidence
                        or transfer_firewall_asset.get("digest")
                        == "sha256:"
                        + evidence["transfer_firewall"]["public_sha256"]
                    )
                    and (
                        "online_memory_lineage" not in evidence
                        or online_memory_lineage_asset.get("digest")
                        == "sha256:"
                        + evidence["online_memory_lineage"]["public_sha256"]
                    )
                    and (
                        "outcome_replay_cas" not in evidence
                        or outcome_replay_cas_asset.get("digest")
                        == "sha256:"
                        + evidence["outcome_replay_cas"]["public_sha256"]
                    )
                    and (
                        schema_version < 16
                        or offline_judge_capsule_asset.get("digest")
                        == "sha256:" + offline_judge_capsule_sha
                    )
                ),
                "release_envelope_gate": (
                    envelope.get("schema_version") == 2
                    and envelope.get("gates", {}).get("status") == "PASS"
                    and envelope.get("lineage", {}).get(
                        "candidate_runtime_sha"
                    )
                    == source["deployment_head_sha"]
                    and envelope.get("public_judge_evidence", {}).get(
                        "schema_version"
                    )
                    == schema_version
                    and (
                        schema_version < 16
                        or envelope.get("offline_judge_capsule", {}).get(
                            "asset_sha256"
                        )
                        == offline_judge_capsule_sha
                    )
                    and (
                        schema_version < 8
                        or envelope.get("release_guardian", {}).get(
                            "report_sha256"
                        )
                        == guardian_reference.get("report_sha256")
                    )
                    and (
                        "time_distributed_replication" not in evidence
                        or envelope.get(
                            "time_distributed_replication", {}
                        ).get("report_sha256")
                        == evidence["time_distributed_replication"].get(
                            "report_sha256"
                        )
                    )
                    and (
                        "blind_holdout" not in evidence
                        or (
                            envelope.get("blind_holdout", {}).get(
                                "public_sha256"
                            )
                            == evidence["blind_holdout"].get("public_sha256")
                            and envelope.get("blind_holdout", {}).get(
                                "commitment_sha256"
                            )
                            == evidence["blind_holdout"].get(
                                "commitment_sha256"
                            )
                        )
                    )
                    and (
                        "sequential_blind_campaign" not in evidence
                        or (
                            envelope.get("sequential_blind_campaign", {}).get(
                                "public_sha256"
                            )
                            == evidence["sequential_blind_campaign"].get(
                                "public_sha256"
                            )
                            and envelope.get(
                                "sequential_blind_campaign", {}
                            ).get("campaign_manifest_sha256")
                            == evidence["sequential_blind_campaign"].get(
                                "campaign_manifest_sha256"
                            )
                        )
                    )
                    and (
                        "evidence_story" not in evidence
                        or (
                            envelope.get("evidence_story", {}).get(
                                "public_sha256"
                            )
                            == evidence["evidence_story"].get("public_sha256")
                            and envelope.get("evidence_story", {}).get(
                                "receipt_sha256"
                            )
                            == evidence["evidence_story"].get(
                                "story_receipt_sha256"
                            )
                            and (
                                schema_version >= 17
                                or envelope.get("evidence_story", {})
                                .get("video", {})
                                .get("sha256")
                                == evidence["submission"].get("video_sha256")
                            )
                        )
                    )
                    and (
                        "provider_origin_story" not in evidence
                        or (
                            envelope.get("provider_origin_story", {}).get(
                                "public_sha256"
                            )
                            == evidence["provider_origin_story"].get(
                                "public_sha256"
                            )
                            and envelope.get("provider_origin_story", {}).get(
                                "receipt_sha256"
                            )
                            == evidence["provider_origin_story"].get(
                                "story_receipt_sha256"
                            )
                            and envelope.get("provider_origin_story", {})
                            .get("video", {})
                            .get("sha256")
                            == evidence["submission"].get("video_sha256")
                            and envelope.get("provider_origin_story", {})
                            .get("video", {})
                            .get("caption_delivery", {})
                            .get("publicly_verifiable")
                            is True
                            and envelope.get("provider_origin_story", {})
                            .get("devpost", {})
                            .get("project_version")
                            == evidence["submission"].get("project_version")
                        )
                    )
                    and (
                        "ci_recovery" not in evidence
                        or (
                            envelope.get("ci_recovery", {}).get(
                                "public_sha256"
                            )
                            == evidence["ci_recovery"].get("public_sha256")
                            and envelope.get("ci_recovery", {}).get(
                                "workflow_run_id"
                            )
                            == evidence["ci_recovery"].get("workflow_run_id")
                            and envelope.get("ci_recovery", {}).get(
                                "artifact_archive_sha256"
                            )
                            == evidence["ci_recovery"].get(
                                "artifact_archive_sha256"
                            )
                            and envelope.get("ci_recovery", {}).get(
                                "challenge_sha256"
                            )
                            == evidence["ci_recovery"].get("challenge_sha256")
                        )
                    )
                    and (
                        "adaptive_diagnosis" not in evidence
                        or (
                            envelope.get("adaptive_diagnosis", {}).get(
                                "public_sha256"
                            )
                            == evidence["adaptive_diagnosis"].get(
                                "public_sha256"
                            )
                            and envelope.get("adaptive_diagnosis", {}).get(
                                "workflow_run_id"
                            )
                            == evidence["adaptive_diagnosis"].get(
                                "workflow_run_id"
                            )
                            and envelope.get("adaptive_diagnosis", {}).get(
                                "artifact_archive_sha256"
                            )
                            == evidence["adaptive_diagnosis"].get(
                                "artifact_archive_sha256"
                            )
                            and envelope.get("adaptive_diagnosis", {}).get(
                                "commitment_sha256"
                            )
                            == evidence["adaptive_diagnosis"].get(
                                "commitment_sha256"
                            )
                            and envelope.get("adaptive_diagnosis", {}).get(
                                "seal_receipt_sha256"
                            )
                            == evidence["adaptive_diagnosis"].get(
                                "seal_receipt_sha256"
                            )
                        )
                    )
                    and (
                        "transfer_firewall" not in evidence
                        or (
                            envelope.get("transfer_firewall", {}).get(
                                "public_sha256"
                            )
                            == evidence["transfer_firewall"].get(
                                "public_sha256"
                            )
                            and envelope.get("transfer_firewall", {}).get(
                                "workflow_run_id"
                            )
                            == evidence["transfer_firewall"].get(
                                "workflow_run_id"
                            )
                            and envelope.get("transfer_firewall", {}).get(
                                "artifact_archive_sha256"
                            )
                            == evidence["transfer_firewall"].get(
                                "artifact_archive_sha256"
                            )
                            and envelope.get("transfer_firewall", {}).get(
                                "commitment_sha256"
                            )
                            == evidence["transfer_firewall"].get(
                                "commitment_sha256"
                            )
                            and envelope.get("transfer_firewall", {}).get(
                                "seal_receipt_sha256"
                            )
                            == evidence["transfer_firewall"].get(
                                "seal_receipt_sha256"
                            )
                        )
                    )
                    and (
                        "online_memory_lineage" not in evidence
                        or (
                            envelope.get("online_memory_lineage", {}).get(
                                "public_sha256"
                            )
                            == evidence["online_memory_lineage"].get(
                                "public_sha256"
                            )
                            and envelope.get("online_memory_lineage", {}).get(
                                "workflow_run_id"
                            )
                            == evidence["online_memory_lineage"].get(
                                "workflow_run_id"
                            )
                            and envelope.get("online_memory_lineage", {}).get(
                                "artifact_archive_sha256"
                            )
                            == evidence["online_memory_lineage"].get(
                                "artifact_archive_sha256"
                            )
                            and envelope.get("online_memory_lineage", {}).get(
                                "raw_receipt_sha256"
                            )
                            == evidence["online_memory_lineage"].get(
                                "raw_receipt_sha256"
                            )
                            and envelope.get("online_memory_lineage", {}).get(
                                "provider_action_reexecutions"
                            )
                            == 0
                        )
                    )
                    and (
                        "outcome_replay_cas" not in evidence
                        or (
                            envelope.get("outcome_replay_cas", {}).get(
                                "public_sha256"
                            )
                            == evidence["outcome_replay_cas"].get(
                                "public_sha256"
                            )
                            and envelope.get("outcome_replay_cas", {}).get(
                                "workflow_run_id"
                            )
                            == evidence["outcome_replay_cas"].get(
                                "workflow_run_id"
                            )
                            and envelope.get("outcome_replay_cas", {}).get(
                                "artifact_archive_sha256"
                            )
                            == evidence["outcome_replay_cas"].get(
                                "artifact_archive_sha256"
                            )
                            and envelope.get("outcome_replay_cas", {}).get(
                                "cas", {}
                            ).get("chain_tip")
                            == evidence["outcome_replay_cas"].get("chain_tip")
                            and envelope.get("outcome_replay_cas", {}).get(
                                "cas", {}
                            ).get("conflict_error_code")
                            == evidence["outcome_replay_cas"].get(
                                "conflict_error_code"
                            )
                        )
                    )
                ),
                "rls_checksum_bound": (
                    evidence.get("database_policy", {}).get(
                        "rls_combined_sha256"
                    )
                    == envelope.get("database_policy", {})
                    .get("rls", {})
                    .get("combined_sha256")
                ),
                "offline_judge_capsule_bound": (
                    schema_version < 16
                    or (
                        offline_judge_reference.get("schema_version") == 1
                        and offline_judge_reference.get("asset_name")
                        == "judge-offline-capsule-v1.json"
                        and offline_judge_capsule_valid
                        and offline_judge_capsule_asset.get("state") == "uploaded"
                        and offline_judge_capsule_asset.get("digest")
                        == "sha256:" + offline_judge_capsule_sha
                        and offline_judge_capsule.get("compiler", {}).get(
                            "source_head"
                        )
                        == release.get("target_commitish")
                        and offline_judge_capsule.get("compiler", {}).get(
                            "successor_release_tag"
                        )
                        == release_reference.get("tag")
                        and offline_judge_capsule.get("request_policy", {}).get(
                            "judge_click_github_api_requests"
                        )
                        == 0
                        and envelope.get("offline_judge_capsule", {}).get(
                            "asset_sha256"
                        )
                        == offline_judge_capsule_sha
                        and envelope.get("offline_judge_capsule", {}).get(
                            "receipt_sha256"
                        )
                        == offline_judge_capsule.get("receipt_sha256")
                        and transaction_pages_evidence.get(
                            "offline_judge_capsule_sha256"
                        )
                        == offline_judge_capsule_sha
                        and transaction_pages_evidence.get(
                            "offline_judge_capsule_receipt_sha256"
                        )
                        == offline_judge_capsule.get("receipt_sha256")
                    )
                ),
                "network_sign_once_subject_visible": (
                    schema_version < 7
                    or (
                        network_reference.get("schema_version") == 2
                        and network_reference.get(
                            "required_author_attestation_count"
                        )
                        == 1
                        and network_reference.get(
                            "required_platform_attestation_count"
                        )
                        == 1
                        and network_reference.get(
                            "required_total_attestation_count"
                        )
                        == 2
                        and len(network_attestations) == 2
                        and signature_bundle.get("mediaType")
                        == "application/vnd.dev.sigstore.bundle.v0.3+json"
                        and len(
                            signature_bundle.get("verificationMaterial", {})
                            .get("certificate", {})
                            .get("rawBytes", "")
                        )
                        > 0
                        and len(
                            signature_bundle.get("verificationMaterial", {})
                            .get("tlogEntries", [])
                        )
                        == 1
                        and "rekor.sigstore.dev"
                        in signature_bundle.get("verificationMaterial", {})
                        .get("tlogEntries", [{}])[0]
                        .get("inclusionProof", {})
                        .get("checkpoint", {})
                        .get("envelope", "")
                        and signature_statement.get("predicateType")
                        == network_reference.get("author_predicate_type")
                        and signature_statement.get("subject")
                        == [
                            {
                                "name": network_reference.get("subject_name"),
                                "digest": {
                                    "sha256": str(
                                        envelope_asset.get("digest", "")
                                    ).removeprefix("sha256:")
                                },
                            }
                        ]
                        and sum(
                            statement.get("predicateType")
                            == network_reference.get("author_predicate_type")
                            and statement.get("subject")
                            == signature_statement.get("subject")
                            for statement in network_statements
                        )
                        == 1
                        and signature_bundle in network_bundles
                        and sum(
                            statement.get("predicateType")
                            == network_reference.get(
                                "platform_predicate_type"
                            )
                            and any(
                                subject.get("name")
                                == network_reference.get("subject_name")
                                and subject.get("digest", {}).get("sha256")
                                == str(
                                    envelope_asset.get("digest", "")
                                ).removeprefix("sha256:")
                                for subject in statement.get("subject", [])
                                if isinstance(subject, dict)
                            )
                            and any(
                                subject.get("uri")
                                == (
                                    "pkg:github/"
                                    + source["repository"]
                                    + "@"
                                    + release_reference["tag"]
                                )
                                and subject.get("digest", {}).get("sha1")
                                == release.get("target_commitish")
                                for subject in statement.get("subject", [])
                                if isinstance(subject, dict)
                            )
                            for statement in network_statements
                        )
                        == 1
                        and sum(
                            statement.get("predicateType")
                            == network_reference.get(
                                "platform_predicate_type"
                            )
                            and bool(
                                bundle.get("verificationMaterial", {})
                                .get("certificate", {})
                                .get("rawBytes")
                            )
                            and len(
                                bundle.get("verificationMaterial", {})
                                .get("timestampVerificationData", {})
                                .get("rfc3161Timestamps", [])
                            )
                            >= 1
                            for bundle, statement in zip(
                                network_bundles, network_statements
                            )
                        )
                        == 1
                    )
                ),
                "release_transaction_terminal": (
                    schema_version < 7
                    or (
                        transaction_reference.get("schema_version") == 1
                        and transaction_reference.get("states")
                        == [
                            "PREPARED",
                            "AUTHOR_ATTESTED",
                            "ASSETS_UPLOADED",
                            "IMMUTABLE",
                            "PAGES_MATERIALIZED",
                        ]
                        and transaction_reference.get("required_terminal_state")
                        == "PAGES_MATERIALIZED"
                        and transaction_reference.get(
                            "ambiguous_state_fails_closed"
                        )
                        is True
                        and transaction_receipt_valid
                        and transaction_receipt.get("state")
                        == "PAGES_MATERIALIZED"
                        and transaction_receipt.get("repository")
                        == source["repository"]
                        and transaction_receipt.get("release_tag")
                        == release_reference["tag"]
                        and transaction_receipt.get("source_digest")
                        == release.get("target_commitish")
                        and transaction_receipt.get("envelope_sha256")
                        == str(envelope_asset.get("digest", "")).removeprefix(
                            "sha256:"
                        )
                        and [
                            event.get("state")
                            for event in transaction_receipt.get("events", [])
                        ]
                        == transaction_reference.get("states")
                        and transaction_receipt_asset.get("state") == "uploaded"
                        and transaction_pages_evidence.get("status") == "success"
                        and transaction_pages_evidence.get("release_tag")
                        == release_reference["tag"]
                        and transaction_pages_evidence.get("release_target")
                        == release.get("target_commitish")
                        and transaction_pages_evidence.get(
                            "public_bundle_sha256"
                        )
                        == network_bundle_sha
                        and (
                            schema_version < 16
                            or (
                                transaction_pages_evidence.get(
                                    "offline_judge_capsule_sha256"
                                )
                                == offline_judge_capsule_sha
                                and transaction_pages_evidence.get(
                                    "offline_judge_capsule_receipt_sha256"
                                )
                                == offline_judge_capsule.get("receipt_sha256")
                            )
                        )
                        and transaction_pages_workflow.get("conclusion")
                        == "success"
                        and transaction_pages_workflow.get("head_sha")
                        == transaction_pages_evidence.get("pages_source_digest")
                        and transaction_coordinator_workflow.get("id")
                        == transaction_pages_evidence.get(
                            "coordinator_workflow_run_id"
                        )
                        and transaction_coordinator_workflow.get("conclusion")
                        == "success"
                        and transaction_coordinator_workflow.get("head_sha")
                        == transaction_pages_evidence.get(
                            "coordinator_source_digest"
                        )
                        and transaction_coordinator_artifact.get("id")
                        == transaction_pages_evidence.get(
                            "coordinator_artifact_id"
                        )
                        and transaction_coordinator_artifact.get("name")
                        == transaction_pages_evidence.get(
                            "coordinator_artifact_name"
                        )
                        and transaction_coordinator_artifact.get("digest")
                        == transaction_pages_evidence.get(
                            "coordinator_artifact_digest"
                        )
                        and transaction_coordinator_artifact.get("expired")
                        is False
                        and transaction_coordinator_artifact.get(
                            "workflow_run", {}
                        ).get("id")
                        == transaction_pages_evidence.get(
                            "coordinator_workflow_run_id"
                        )
                        and envelope.get("release_transaction")
                        == transaction_reference
                    )
                ),
            }
        )
    return {
        "ok": all(checks.values()),
        "mode": "read-only-http-get",
        "workflow_run_id": source["workflow_run_id"],
        "vector_benchmark_run_id": vector_scale["workflow_run_id"],
        "agent_pressure_run_id": agent_pressure["workflow_run_id"],
        "agent_ablation_run_id": (
            evidence.get("agent_ablation", {}).get("workflow_run_id")
        ),
        "deployment_head_sha": source["deployment_head_sha"],
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-url", default=DEFAULT_EVIDENCE_URL)
    args = parser.parse_args()
    evidence = get_json(args.evidence_url)
    report = verify_evidence(evidence)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
