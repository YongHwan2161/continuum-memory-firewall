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
    schema_version = report.get("schema_version")
    if schema_version not in {1, 2} or report.get("kind") not in allowed_kinds:
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
    attestation = report.get("attestation")
    if not all(
        isinstance(item, Mapping)
        for item in (workflow, migration, database, provider, cas, gate)
    ):
        raise ValueError("outcome replay proof sections are incomplete")
    if int(workflow.get("run_id", 0)) < 1 or int(workflow.get("run_attempt", 0)) < 1:
        raise ValueError("outcome replay workflow receipt is invalid")
    minimum_migration = 35 if schema_version == 2 else 33
    if int(migration.get("current_version", 0)) < minimum_migration:
        raise ValueError("outcome replay proof predates the CAS schema")
    expected_rls: dict[str, Any] = {
        "all_visible_reconciliations_in_scope": True,
        "proposal_visible_rows": 3,
    }
    if schema_version == 2:
        expected_rls.update(
            {
                "attestation_visible_rows": 1,
                "runtime_attestation_insert_sqlstate": "42501",
            }
        )
    if database.get("engine") != "CockroachDB" or database.get("rls") != expected_rls:
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
    if schema_version == 2 and (
        provider.get("lookup_method") != "s3:HeadObject+GetObject"
        or provider.get("lookup_count") != 7
    ):
        raise ValueError("outcome replay proof lacks provider-origin lookups")
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
    if schema_version == 2:
        if not isinstance(attestation, Mapping):
            raise ValueError("outcome attestation proof is missing")
        if (
            attestation.get("algorithm") != "HMAC-SHA256"
            or attestation.get("issuer") != "s3-provider-origin-verifier-v1"
            or attestation.get("policy_version") != "s3-receipt-lookup-v1"
            or attestation.get("ttl_seconds") != 300
            or attestation.get("consumed_rows") != 1
            or attestation.get("atomic_join_rows") != 1
            or attestation.get("raw_handle_persisted") is not False
            or attestation.get("negative_outcome_rows") != 0
        ):
            raise ValueError("outcome attestation admission evidence is invalid")
        for field in ("handle_digest", "stored_handle_digest", "stored_nonce_digest"):
            if not _sha256(attestation.get(field)):
                raise ValueError("outcome attestation digest is invalid")
        if attestation["handle_digest"] != attestation["stored_handle_digest"]:
            raise ValueError("outcome attestation consumption digest drifted")
        if not _uuid(attestation.get("consumed_outcome_id")):
            raise ValueError("outcome attestation consumed outcome is invalid")
        if not re.fullmatch(r"[0-9a-f]{16}", str(attestation.get("key_id"))):
            raise ValueError("outcome attestation key identity is invalid")
        expected_negative_codes = {
            "cross_proposal": "OUTCOME_ATTESTATION_BINDING_MISMATCH",
            "cross_provider": "OUTCOME_ATTESTATION_BINDING_MISMATCH",
            "expired_handle": "OUTCOME_ATTESTATION_EXPIRED",
            "forged_handle": "OUTCOME_ATTESTATION_INVALID",
            "missing_handle": "OUTCOME_ATTESTATION_REQUIRED",
            "receipt_mismatch": "OUTCOME_ATTESTATION_BINDING_MISMATCH",
        }
        if attestation.get("negative_codes") != expected_negative_codes:
            raise ValueError("outcome attestation negative controls are incomplete")
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
    if schema_version == 2 and attestation.get("consumed_outcome_id") != shared_outcome:
        raise ValueError("outcome attestation is not bound to the durable outcome")
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
    if schema_version == 2:
        expected_gate.update(
            {
                "provider_lookup_before_issue": True,
                "signed_handle_consumed_once": True,
                "atomic_attestation_outcome_promotion": True,
                "unauthorized_promotions_blocked": True,
                "raw_handle_absent": True,
            }
        )
    if any(gate.get(key) != value for key, value in expected_gate.items()):
        raise ValueError("outcome replay proof gate is not PASS")


def build_public_outcome_replay_proof(
    report: Mapping[str, Any],
) -> dict[str, Any]:
    validate_outcome_replay_proof(report, allowed_kinds=(RAW_KIND,))
    public = {
        "schema_version": report["schema_version"],
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
            if report["schema_version"] == 1
            else "One retained participant-cluster proposal with two real disposable "
            "S3 receipts. Schema v2 additionally proves provider-origin lookup, "
            "short-lived signed admission, and atomic handle consumption; this is "
            "an architectural closure, not a population estimate."
        ),
    }
    if report["schema_version"] == 2:
        public["attestation"] = dict(report["attestation"])
    validate_outcome_replay_proof(public, allowed_kinds=(PUBLIC_KIND,))
    return public
