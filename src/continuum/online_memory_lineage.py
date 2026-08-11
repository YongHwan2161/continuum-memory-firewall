"""Validation and public projection for the online memory-lineage proof.

The raw report contains server-owned tenant and incident identifiers that are
useful to the private reconciler but unnecessary for a public judge.  This
module validates the complete receipt first and then emits a deliberately
smaller projection that preserves the provider, database, retrieval, proposal,
action, outcome, and reconciliation lineage.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import re
from typing import Any, Mapping

from continuum.ci_recovery import validate_ci_workflow_receipt
from continuum.episode import canonical_json_bytes


SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
EXPECTED_NEGATIVE_CHECKS = {
    "row_security_off",
    "canonical_update",
    "candidate_update",
    "action_update",
}


def _require_sha256(value: Any, label: str) -> str:
    result = str(value or "")
    if SHA256_PATTERN.fullmatch(result) is None:
        raise RuntimeError(f"online lineage {label} is not a SHA-256 digest")
    return result


def _require_uuid(value: Any, label: str) -> str:
    result = str(value or "")
    if UUID_PATTERN.fullmatch(result) is None:
        raise RuntimeError(f"online lineage {label} is not a UUID")
    return result


def _provider_receipts(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = report.get("source", {})
    targets = report.get("targets", [])
    if not isinstance(source, Mapping) or not isinstance(targets, list):
        raise RuntimeError("online lineage provider receipt containers are invalid")
    receipts: list[dict[str, Any]] = [dict(source.get("provider_receipt", {}))]
    for target in targets:
        if not isinstance(target, Mapping):
            raise RuntimeError("online lineage target is invalid")
        receipts.append(dict(target.get("target_attestation_receipt", {})))
        diagnostics = target.get("diagnostic_receipts", [])
        if not isinstance(diagnostics, list):
            raise RuntimeError("online lineage diagnostics are invalid")
        receipts.extend(dict(item) for item in diagnostics)
        receipts.append(dict(target.get("provider_receipt", {})))
    return receipts


def validate_online_memory_lineage(report: Mapping[str, Any]) -> None:
    """Fail closed unless one raw online lineage report proves the full seam."""

    if report.get("schema_version") != 1 or report.get("kind") != (
        "continuum.online-memory-lineage.report"
    ):
        raise RuntimeError("online lineage raw schema is invalid")
    body = dict(report)
    claimed_receipt = _require_sha256(
        body.pop("receipt_sha256", None), "self receipt"
    )
    actual_receipt = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
    if actual_receipt != claimed_receipt:
        raise RuntimeError("online lineage self receipt does not match")

    source_head = str(report.get("source_head", ""))
    if SHA_PATTERN.fullmatch(source_head) is None:
        raise RuntimeError("online lineage source head is invalid")
    _require_sha256(report.get("deployment_artifact_sha256"), "deployment artifact")
    if report.get("repository") != "YongHwan2161/continuum-memory-firewall":
        raise RuntimeError("online lineage repository is invalid")

    reconciliation = report.get("reconciliation", {})
    if not isinstance(reconciliation, Mapping):
        raise RuntimeError("online lineage reconciliation is missing")
    reconciler_head = str(reconciliation.get("reconciler_source_head", ""))
    if (
        reconciliation.get("mode") != "cross-head-resume"
        or reconciliation.get("candidate_source_head") != source_head
        or SHA_PATTERN.fullmatch(reconciler_head) is None
        or reconciler_head == source_head
        or int(reconciliation.get("predecessor_workflow_run_id", 0)) < 1
        or int(reconciliation.get("reconciliation_workflow_run_id", 0)) < 1
        or int(reconciliation.get("reconciliation_workflow_run_attempt", 0)) < 1
        or reconciliation.get("provider_action_reexecutions") != 0
    ):
        raise RuntimeError("online lineage reconciliation boundary is invalid")
    for key in (
        "candidate_deployment_artifact_sha256",
        "reconciler_deployment_artifact_sha256",
        "input_receipt_sha256",
    ):
        _require_sha256(reconciliation.get(key), f"reconciliation {key}")

    methodology = report.get("methodology", {})
    expected_methodology = {
        "architectural_pairs": 1,
        "target_cases": 2,
        "same_cause_cases": 1,
        "near_neighbor_cases": 1,
        "candidate_visible_label_fields": 0,
        "real_external_provider": True,
        "provider": "github-actions",
        "lineage_provider_receipts": 6,
        "database": "cockroachdb-cloud",
        "retrieval": "titan-v2-vector-search-through-non-bypass-rls-role",
    }
    if any(methodology.get(key) != value for key, value in expected_methodology.items()):
        raise RuntimeError("online lineage methodology cardinality is invalid")

    identity = report.get("identity", {})
    if not isinstance(identity, Mapping):
        raise RuntimeError("online lineage identity is missing")
    if (
        identity.get("binding_version") != 1
        or not str(identity.get("current_user", "")).startswith("continuum_scope_")
    ):
        raise RuntimeError("online lineage SQL identity is invalid")
    for key in ("caller_id_sha256", "sql_role_sha256"):
        _require_sha256(identity.get(key), key)
    for key in ("tenant_id", "incident_id"):
        _require_uuid(identity.get(key), key)

    isolation = report.get("isolation", {})
    if not isinstance(isolation, Mapping):
        raise RuntimeError("online lineage isolation proof is missing")
    if not (
        isolation.get("forbidden_memory_visible") is False
        and isolation.get("all_visible_rows_in_scope") is True
        and isolation.get("all_visible_incidents_in_scope") is True
        and isolation.get("all_visible_audits_in_scope") is True
        and set(isolation.get("negative_checks", [])) == EXPECTED_NEGATIVE_CHECKS
    ):
        raise RuntimeError("online lineage isolation proof failed")
    _require_uuid(isolation.get("forbidden_incident_id"), "forbidden incident")
    _require_uuid(isolation.get("forbidden_memory_id"), "forbidden memory")

    rls = report.get("rls", {})
    files = rls.get("files", []) if isinstance(rls, Mapping) else []
    if len(files) != 3:
        raise RuntimeError("online lineage RLS receipt cardinality is invalid")
    _require_sha256(rls.get("combined_sha256"), "RLS combined checksum")
    for item in files:
        if not isinstance(item, Mapping) or not str(item.get("path", "")).startswith(
            "src/continuum/migrations/"
        ):
            raise RuntimeError("online lineage RLS file receipt is invalid")
        _require_sha256(item.get("sha256"), "RLS file checksum")

    source = report.get("source", {})
    if not isinstance(source, Mapping):
        raise RuntimeError("online lineage source memory is missing")
    for key in ("memory_id", "outcome_id", "proposal_id", "run_id"):
        _require_uuid(source.get(key), f"source {key}")
    for key in ("event_hash", "provider_receipt_sha256", "receipt_digest"):
        _require_sha256(source.get(key), f"source {key}")
    if source.get("embedding_model") != report.get("embedding_model"):
        raise RuntimeError("online lineage embedding model is not bound")

    targets = report.get("targets", [])
    if not isinstance(targets, list) or len(targets) != 2:
        raise RuntimeError("online lineage target cardinality is invalid")
    by_relationship = {str(item.get("relationship", "")): item for item in targets}
    if set(by_relationship) != {"same-cause-transfer", "near-neighbor-rejection"}:
        raise RuntimeError("online lineage relationship pairing is invalid")
    if len({str(item.get("case_id", "")) for item in targets}) != 2:
        raise RuntimeError("online lineage target cases are not unique")
    for target in targets:
        if target.get("proposed_patch_id") != target.get("expected_patch_id"):
            raise RuntimeError("online lineage proposed patch is not exact")
        for key in ("run_id", "proposal_id", "outcome_id", "promoted_memory_id"):
            _require_uuid(target.get(key), f"target {key}")
        for key in ("outcome_receipt_digest", "promoted_event_hash"):
            _require_sha256(target.get(key), f"target {key}")
        admission = target.get("admission_receipt", {})
        if (
            not isinstance(admission, Mapping)
            or admission.get("kind") != "continuum.online-transfer-admission"
            or len(admission.get("retrieval_ids", [])) < 1
            or source.get("memory_id") not in admission.get("searched_memory_ids", [])
            or target.get("outcome_status") != "succeeded"
        ):
            raise RuntimeError("online lineage target database join is invalid")
        for retrieval_id in admission.get("retrieval_ids", []):
            _require_uuid(retrieval_id, "retrieval audit")

    same = by_relationship["same-cause-transfer"]
    near = by_relationship["near-neighbor-rejection"]
    if not (
        same.get("selected_memory_ids") == [source.get("memory_id")]
        and same.get("fetched_memory_ids") == [source.get("memory_id")]
        and same.get("diagnostic_receipts") == []
        and same.get("admission_receipt", {}).get("compatible_memory_ids")
        == [source.get("memory_id")]
        and near.get("selected_memory_ids") == []
        and near.get("fetched_memory_ids") == []
        and len(near.get("diagnostic_receipts", [])) == 1
        and near.get("admission_receipt", {}).get("compatible_memory_ids") == []
    ):
        raise RuntimeError("online lineage transfer/rejection behavior is invalid")

    receipts = _provider_receipts(report)
    if len(receipts) != 6:
        raise RuntimeError("online lineage provider receipt cardinality is invalid")
    run_ids: list[int] = []
    artifact_ids: list[int] = []
    for receipt in receipts:
        validate_ci_workflow_receipt(receipt, expected_conclusion="success")
        if (
            receipt.get("head_sha") != source_head
            or receipt.get("repository_mutation") is not False
            or receipt.get("cleanup_residual_count") != 0
        ):
            raise RuntimeError("online lineage provider receipt boundary failed")
        run_ids.append(int(receipt["workflow_run_id"]))
        artifact_ids.append(int(receipt["artifact_id"]))
    if len(set(run_ids)) != 6 or len(set(artifact_ids)) != 6:
        raise RuntimeError("online lineage provider receipts are not unique")

    gate = report.get("gate", {})
    checks = [value for key, value in gate.items() if key != "status"]
    if gate.get("status") != "PASS" or not checks or not all(value is True for value in checks):
        raise RuntimeError("online lineage report gate did not pass")
    if "not a new population-level superiority estimate" not in str(
        report.get("claim_boundary", "")
    ).lower():
        raise RuntimeError("online lineage claim boundary is missing")


def build_public_online_memory_lineage(
    report: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a raw report and remove server-owned scope identifiers."""

    validate_online_memory_lineage(report)
    identity = report["identity"]
    isolation = report["isolation"]
    return {
        "schema_version": 1,
        "kind": "continuum.online-memory-lineage.public",
        "generated_at": report["generated_at"],
        "source_head": report["source_head"],
        "deployment_artifact_sha256": report["deployment_artifact_sha256"],
        "repository": report["repository"],
        "campaign_id": report["campaign_id"],
        "migration_version": report["migration_version"],
        "embedding_model": report["embedding_model"],
        "agent_model": report["agent_model"],
        "agent_region": report["agent_region"],
        "raw_receipt_sha256": report["receipt_sha256"],
        "reconciliation": deepcopy(report["reconciliation"]),
        "methodology": deepcopy(report["methodology"]),
        "identity": {
            "binding_version": identity["binding_version"],
            "caller_id_sha256": identity["caller_id_sha256"],
            "sql_role_sha256": identity["sql_role_sha256"],
            "server_owned_scope_ids_disclosed": False,
        },
        "isolation": {
            "forbidden_memory_visible": isolation["forbidden_memory_visible"],
            "all_visible_rows_in_scope": isolation["all_visible_rows_in_scope"],
            "all_visible_incidents_in_scope": isolation[
                "all_visible_incidents_in_scope"
            ],
            "all_visible_audits_in_scope": isolation["all_visible_audits_in_scope"],
            "negative_checks": deepcopy(isolation["negative_checks"]),
        },
        "rls": deepcopy(report["rls"]),
        "source": deepcopy(report["source"]),
        "targets": deepcopy(report["targets"]),
        "gate": deepcopy(report["gate"]),
        "claim_boundary": report["claim_boundary"],
    }


def validate_public_online_memory_lineage(report: Mapping[str, Any]) -> None:
    """Validate the redacted projection without requiring private scope IDs."""

    encoded = canonical_json_bytes(report).decode("utf-8")
    if any(
        field in encoded for field in ('"tenant_id"', '"incident_id"', '"current_user"')
    ):
        raise RuntimeError("public online lineage discloses server-owned scope IDs")
    if (
        report.get("schema_version") != 1
        or report.get("kind") != "continuum.online-memory-lineage.public"
        or report.get("identity", {}).get("server_owned_scope_ids_disclosed")
        is not False
    ):
        raise RuntimeError("public online lineage schema is invalid")
    _require_sha256(report.get("raw_receipt_sha256"), "public raw receipt")
    source_head = str(report.get("source_head", ""))
    reconciliation = report.get("reconciliation", {})
    if (
        SHA_PATTERN.fullmatch(source_head) is None
        or reconciliation.get("candidate_source_head") != source_head
        or SHA_PATTERN.fullmatch(
            str(reconciliation.get("reconciler_source_head", ""))
        )
        is None
        or reconciliation.get("provider_action_reexecutions") != 0
    ):
        raise RuntimeError("public online lineage reconciliation is invalid")
    if report.get("methodology", {}).get("architectural_pairs") != 1 or report.get(
        "methodology", {}
    ).get("target_cases") != 2:
        raise RuntimeError("public online lineage cardinality is invalid")
    source = report.get("source", {})
    _require_uuid(source.get("memory_id"), "public source memory")
    targets = report.get("targets", [])
    if not isinstance(targets, list) or len(targets) != 2:
        raise RuntimeError("public online lineage targets are invalid")
    relationships = {item.get("relationship"): item for item in targets}
    if set(relationships) != {"same-cause-transfer", "near-neighbor-rejection"}:
        raise RuntimeError("public online lineage relationships are invalid")
    same = relationships["same-cause-transfer"]
    near = relationships["near-neighbor-rejection"]
    if not (
        same.get("selected_memory_ids") == [source.get("memory_id")]
        and same.get("fetched_memory_ids") == [source.get("memory_id")]
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
    ):
        raise RuntimeError("public online lineage behavior is invalid")
    receipts = _provider_receipts(report)
    if len(receipts) != 6:
        raise RuntimeError("public online lineage provider receipts are invalid")
    for receipt in receipts:
        validate_ci_workflow_receipt(receipt, expected_conclusion="success")
        if (
            receipt.get("head_sha") != source_head
            or receipt.get("repository_mutation") is not False
            or receipt.get("cleanup_residual_count") != 0
        ):
            raise RuntimeError("public online lineage receipt boundary failed")
    gate = report.get("gate", {})
    checks = [value for key, value in gate.items() if key != "status"]
    if gate.get("status") != "PASS" or not checks or not all(
        value is True for value in checks
    ):
        raise RuntimeError("public online lineage gate did not pass")
    if "not a new population-level superiority estimate" not in str(
        report.get("claim_boundary", "")
    ).lower():
        raise RuntimeError("public online lineage claim boundary is missing")
