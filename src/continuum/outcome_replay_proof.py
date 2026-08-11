"""Public-safe verification contract for the live outcome replay CAS proof."""

from __future__ import annotations

from datetime import datetime
import hashlib
import re
from typing import Any, Mapping, Sequence

from continuum.episode import (
    OUTCOME_RECONCILIATION_GENESIS_HASH,
    OUTCOME_REPLAY_CONFLICT,
    OutcomeReplayIdentity,
    OutcomeStatus,
    build_outcome_reconciliation_entry,
)


RAW_KIND = "continuum.outcome-replay-cas.report"
PUBLIC_KIND = "continuum.outcome-replay-cas.public"
EXPECTED_DECISIONS = ("accepted", "exact_replay", "conflict")


def _sha256(value: object) -> bool:
    return re.fullmatch(r"[0-9a-f]{64}", str(value)) is not None


def _commit(value: object) -> bool:
    return re.fullmatch(r"[0-9a-f]{40}", str(value)) is not None


def _uuid(value: object) -> bool:
    return re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
        str(value),
    ) is not None


def _identity(value: Mapping[str, Any]) -> OutcomeReplayIdentity:
    return OutcomeReplayIdentity(
        provider=str(value["provider"]),
        status=OutcomeStatus(str(value["status"])),
        provider_receipt_id=(
            str(value["provider_receipt_id"])
            if value.get("provider_receipt_id") is not None
            else None
        ),
        receipt_digest=(
            str(value["receipt_digest"])
            if value.get("receipt_digest") is not None
            else None
        ),
    )


def validate_outcome_replay_proof(
    report: Mapping[str, Any],
    *,
    allowed_kinds: Sequence[str] = (RAW_KIND, PUBLIC_KIND),
) -> None:
    if report.get("schema_version") != 1 or report.get("kind") not in allowed_kinds:
        raise ValueError("outcome replay proof schema is invalid")
    if not _commit(report.get("source_head")) or not _sha256(
        report.get("deployment_artifact_sha256")
    ):
        raise ValueError("outcome replay proof source identity is invalid")
    workflow = report.get("workflow")
    migration = report.get("migration")
    database = report.get("database")
    provider = report.get("provider")
    cas = report.get("cas")
    gate = report.get("gate")
    if not all(
        isinstance(item, Mapping)
        for item in (workflow, migration, database, provider, cas, gate)
    ):
        raise ValueError("outcome replay proof sections are incomplete")
    if int(workflow.get("run_id", 0)) < 1 or int(workflow.get("run_attempt", 0)) < 1:
        raise ValueError("outcome replay workflow receipt is invalid")
    if int(migration.get("current_version", 0)) < 33:
        raise ValueError("outcome replay proof predates the CAS schema")
    if database.get("engine") != "CockroachDB" or database.get("rls") != {
        "all_visible_reconciliations_in_scope": True,
        "proposal_visible_rows": 3,
    }:
        raise ValueError("outcome replay proof lacks scoped RLS evidence")
    if not str(database.get("scope_sql_role", "")).startswith("continuum_scope_"):
        raise ValueError("outcome replay proof SQL identity is invalid")
    if provider.get("adapter") != "aws-s3":
        raise ValueError("outcome replay proof provider is invalid")
    if provider.get("capability_manifest") != {
        "supports_idempotency": True,
        "receipt_lookup": True,
        "reconciliation_timeout_seconds": 0,
    }:
        raise ValueError("outcome replay provider capability manifest is invalid")
    for field in (
        "accepted_object_sha256",
        "conflicting_object_sha256",
        "accepted_receipt_sha256",
        "conflicting_receipt_sha256",
    ):
        if not _sha256(provider.get(field)):
            raise ValueError("outcome replay provider commitment is invalid")
    if provider["accepted_receipt_sha256"] == provider["conflicting_receipt_sha256"]:
        raise ValueError("outcome replay proof requires two distinct real receipts")
    expected_cas = {
        "outcome_rows": 1,
        "canonical_promotions": 1,
        "journal_rows": 3,
        "first_replayed": False,
        "exact_replayed": True,
        "conflict_error_code": OUTCOME_REPLAY_CONFLICT,
    }
    if any(cas.get(key) != value for key, value in expected_cas.items()):
        raise ValueError("outcome replay CAS cardinality is invalid")
    journal = cas.get("journal")
    if not isinstance(journal, list) or len(journal) != 3:
        raise ValueError("outcome replay journal is incomplete")
    if tuple(item.get("decision") for item in journal) != EXPECTED_DECISIONS:
        raise ValueError("outcome replay journal decisions are invalid")
    previous_hash = OUTCOME_RECONCILIATION_GENESIS_HASH
    shared_proposal = None
    shared_outcome = None
    durable_identity = None
    incoming_identities = []
    for sequence, item in enumerate(journal, start=1):
        if not isinstance(item, Mapping):
            raise ValueError("outcome replay journal entry is invalid")
        required_ids = (
            "reconciliation_id",
            "proposal_id",
            "outcome_id",
            "run_id",
            "tenant_id",
            "incident_id",
        )
        if not all(_uuid(item.get(field)) for field in required_ids):
            raise ValueError("outcome replay journal identity is invalid")
        shared_proposal = shared_proposal or item["proposal_id"]
        shared_outcome = shared_outcome or item["outcome_id"]
        if item["proposal_id"] != shared_proposal or item["outcome_id"] != shared_outcome:
            raise ValueError("outcome replay journal crossed proposal identity")
        if item.get("sequence_no") != sequence or item.get(
            "previous_entry_hash"
        ) != previous_hash:
            raise ValueError("outcome replay journal chain ordering is invalid")
        incoming = item.get("incoming")
        durable = item.get("durable")
        if not isinstance(incoming, Mapping) or not isinstance(durable, Mapping):
            raise ValueError("outcome replay journal identities are missing")
        recorded_at = datetime.fromisoformat(str(item["recorded_at"]))
        parsed_incoming = _identity(incoming)
        parsed_durable = _identity(durable)
        if (
            parsed_incoming.status is OutcomeStatus.SUCCEEDED
            and (
                not parsed_incoming.provider_receipt_id
                or not _sha256(parsed_incoming.receipt_digest)
            )
        ):
            raise ValueError("outcome replay journal success identity is invalid")
        durable_identity = durable_identity or parsed_durable
        if parsed_durable != durable_identity:
            raise ValueError("outcome replay durable identity changed")
        incoming_identities.append(parsed_incoming)
        rebuilt = build_outcome_reconciliation_entry(
            reconciliation_id=str(item["reconciliation_id"]),
            proposal_id=str(item["proposal_id"]),
            outcome_id=str(item["outcome_id"]),
            run_id=str(item["run_id"]),
            tenant_id=str(item["tenant_id"]),
            incident_id=str(item["incident_id"]),
            decision=str(item["decision"]),
            incoming=parsed_incoming,
            durable=parsed_durable,
            sequence_no=sequence,
            previous_entry_hash=previous_hash,
            recorded_at=recorded_at,
        )
        if item.get("error_code") != rebuilt.error_code or item.get(
            "entry_hash"
        ) != rebuilt.entry_hash:
            raise ValueError("outcome replay journal hash is invalid")
        previous_hash = rebuilt.entry_hash
    if cas.get("chain_tip") != previous_hash:
        raise ValueError("outcome replay journal tip is invalid")
    if incoming_identities[:2] != [durable_identity, durable_identity] or (
        incoming_identities[2] == durable_identity
    ):
        raise ValueError("outcome replay CAS identity sequence is invalid")
    accepted_receipt = str(durable_identity.provider_receipt_id)
    conflicting_receipt = str(incoming_identities[2].provider_receipt_id)
    if hashlib.sha256(accepted_receipt.encode()).hexdigest() != provider.get(
        "accepted_receipt_sha256"
    ) or hashlib.sha256(conflicting_receipt.encode()).hexdigest() != provider.get(
        "conflicting_receipt_sha256"
    ):
        raise ValueError("outcome replay provider receipt binding is invalid")
    expected_gate = {
        "one_durable_outcome": True,
        "one_canonical_promotion": True,
        "exact_replay_idempotent": True,
        "conflicting_replay_rejected": True,
        "conflict_committed_before_error": True,
        "journal_hash_chain_valid": True,
        "scope_rls_valid": True,
        "status": "PASS",
    }
    if any(gate.get(key) != value for key, value in expected_gate.items()):
        raise ValueError("outcome replay proof gate is not PASS")


def build_public_outcome_replay_proof(
    report: Mapping[str, Any],
) -> dict[str, Any]:
    validate_outcome_replay_proof(report, allowed_kinds=(RAW_KIND,))
    public = {
        "schema_version": 1,
        "kind": PUBLIC_KIND,
        "source_head": report["source_head"],
        "deployment_artifact_sha256": report["deployment_artifact_sha256"],
        "workflow": dict(report["workflow"]),
        "migration": dict(report["migration"]),
        "database": dict(report["database"]),
        "provider": dict(report["provider"]),
        "cas": dict(report["cas"]),
        "gate": dict(report["gate"]),
        "claim_boundary": (
            "One retained participant-cluster proposal with two real disposable "
            "S3 receipts; this is an architectural closure, not a population estimate."
        ),
    }
    validate_outcome_replay_proof(public, allowed_kinds=(PUBLIC_KIND,))
    return public
