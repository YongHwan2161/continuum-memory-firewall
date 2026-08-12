#!/usr/bin/env python3
"""Prove outcome replay CAS on the participant CockroachDB with real S3 receipts."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

import boto3

from continuum.aws_secrets import get_secret_string_with_backoff
from continuum.episode import (
    AgentArm,
    CockroachEpisodeStore,
    OutcomeReplayConflictError,
    OutcomeStatus,
    ProposedAction,
    ProviderOutcome,
    RiskClass,
    outcome_candidate_id,
)
from continuum.migrate import Migrator
from continuum.outbox import CockroachOutboxStore, ProviderCapabilityManifest
from continuum.outcome_attestation import (
    OUTCOME_ATTESTATION_BINDING_MISMATCH,
    OUTCOME_ATTESTATION_EXPIRED,
    OUTCOME_ATTESTATION_INVALID,
    OUTCOME_ATTESTATION_REQUIRED,
    OutcomeAttestationError,
    ProviderOutcomeAttestationAuthority,
)
from continuum.outcome_replay_proof import (
    build_public_outcome_replay_proof,
    validate_outcome_replay_proof,
)
from continuum.scope_roles import configure_scope_read_policies, verify_scope_role
from continuum.store import pin_database_tls_root, psycopg_connection_factory
from continuum.tenant_control import DatabaseTenantControlPlane


def _sha256(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def _secret_payload(client: Any, secret_id: str) -> Any:
    raw = get_secret_string_with_backoff(client, secret_id)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _database_url(value: Any) -> str:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, Mapping) and isinstance(value.get("database_url"), str):
        return str(value["database_url"])
    raise RuntimeError("database secret does not contain database_url")


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    os.chmod(path, 0o600)


def _runtime_context(
    *,
    secret_client: Any,
    runtime_secret_id: str,
    ca_cert: str,
) -> tuple[str, str, str, str]:
    payload = _secret_payload(secret_client, runtime_secret_id)
    if not isinstance(payload, Mapping):
        raise RuntimeError("runtime secret must be a JSON object")
    callers = payload.get("caller_scopes")
    control_url = payload.get("control_plane_database_url")
    scope_urls = payload.get("scope_database_urls")
    if not isinstance(callers, Mapping) or len(callers) != 1:
        raise RuntimeError("proof requires exactly one registered demo caller")
    if not isinstance(control_url, str) or not isinstance(scope_urls, Mapping):
        raise RuntimeError("audited runtime database registry is incomplete")
    caller_id = str(next(iter(callers)))
    control_url = pin_database_tls_root(control_url, ca_cert)
    identity = DatabaseTenantControlPlane(
        psycopg_connection_factory(control_url)
    ).resolve(caller_id)
    runtime_url = scope_urls.get(identity.sql_role)
    if not isinstance(runtime_url, str):
        raise RuntimeError("resolved SQL role has no runtime connection")
    return (
        pin_database_tls_root(runtime_url, ca_cert),
        identity.tenant_id,
        identity.incident_id,
        identity.sql_role,
    )


def _put_provider_object(
    client: Any,
    *,
    bucket: str,
    key: str,
    source_head: str,
    label: str,
) -> None:
    body = json.dumps(
        {
            "kind": "continuum.outcome-replay-cas.provider-object",
            "label": label,
            "source_head": source_head,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
        Metadata={"continuum-source-head": source_head},
    )


class S3ReceiptLookupProvider:
    """Re-read an S3 object before minting a promotion capability."""

    name = "aws-s3"

    def __init__(
        self,
        *,
        client: Any,
        bucket: str,
        source_head: str,
        workflow_run_id: int,
    ) -> None:
        self.client = client
        self.bucket = bucket
        self.source_head = source_head
        self.workflow_run_id = workflow_run_id
        self.keys: dict[str, str] = {}
        self.lookup_count = 0

    def register(self, *, idempotency_key: str, object_key: str) -> None:
        self.keys[idempotency_key] = object_key

    def lookup(self, *, idempotency_key: str) -> ProviderOutcome | None:
        key = self.keys.get(idempotency_key)
        if key is None:
            return None
        head = self.client.head_object(Bucket=self.bucket, Key=key)
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        body = response["Body"].read()
        if head.get("Metadata", {}).get("continuum-source-head") != self.source_head:
            raise RuntimeError("S3 receipt source identity drifted")
        if int(head["ContentLength"]) != len(body):
            raise RuntimeError("S3 receipt length drifted between HEAD and GET")
        etag = str(head["ETag"]).strip('"')
        version_id = str(head.get("VersionId") or "unversioned")
        receipt_id = "aws-s3:" + _sha256(
            f"{self.bucket}\x00{key}\x00{etag}\x00{version_id}"
        )
        observed_at = head["LastModified"]
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        self.lookup_count += 1
        return ProviderOutcome(
            provider=self.name,
            status=OutcomeStatus.SUCCEEDED,
            provider_receipt_id=receipt_id,
            evidence={
                "content_length": len(body),
                "etag_sha256": _sha256(etag),
                "object_key_sha256": _sha256(key),
                "object_sha256": _sha256(body),
                "provider_lookup": "s3:HeadObject+GetObject",
                "source_head": self.source_head,
                "version_id_sha256": _sha256(version_id),
                "workflow_run_id": self.workflow_run_id,
            },
            observed_at=observed_at,
            verified_at=datetime.now(timezone.utc),
        )


S3_CAPABILITIES = ProviderCapabilityManifest(
    supports_idempotency=True,
    receipt_lookup=True,
    reconciliation_timeout=timedelta(seconds=0),
)


def _approved_enqueued_proposal(
    *,
    episodes: CockroachEpisodeStore,
    outbox: CockroachOutboxStore,
    tenant_id: str,
    incident_id: str,
    workflow_run_id: int,
    case: str,
) -> tuple[str, str]:
    run = episodes.start_run(
        tenant_id=tenant_id,
        incident_id=incident_id,
        arm=AgentArm.CONTINUUM,
        model_id="provider-outcome-attestation-proof-v1",
        input_payload={
            "case": case,
            "provider": "aws-s3",
            "workflow_run_id": workflow_run_id,
        },
    )
    proposal_id = episodes.record_proposal(
        run=run,
        proposal=ProposedAction(
            action_key=f"provider-outcome-attestation:{workflow_run_id}:{case}",
            action_type="put_disposable_evidence_object",
            parameters={"case": case, "provider": "aws-s3"},
            rationale="Bind a real provider lookup to one bounded proposal.",
            citation_memory_ids=(),
            risk_class=RiskClass.REVERSIBLE,
        ),
    )
    episodes.approve_proposal(
        proposal_id=proposal_id,
        actor="policy:provider-outcome-attestation-proof-v1",
        reason="disposable evidence prefix only",
    )
    item = outbox.enqueue_proposal(
        proposal_id=proposal_id,
        provider="aws-s3",
        provider_capabilities=S3_CAPABILITIES,
    )
    return proposal_id, item.idempotency_key


def _journal_rows(connection: Any, proposal_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            reconciliation_id::STRING,
            proposal_id::STRING,
            outcome_id::STRING,
            run_id::STRING,
            tenant_id::STRING,
            incident_id::STRING,
            decision,
            incoming_provider,
            incoming_status,
            incoming_provider_receipt_id,
            incoming_receipt_digest,
            durable_provider,
            durable_status,
            durable_provider_receipt_id,
            durable_receipt_digest,
            error_code,
            sequence_no,
            previous_entry_hash,
            entry_hash,
            recorded_at
        FROM outcome_reconciliation_journal
        WHERE proposal_id = %s
        ORDER BY sequence_no
        """,
        (proposal_id,),
    ).fetchall()
    result = []
    for row in rows:
        result.append(
            {
                "reconciliation_id": row[0],
                "proposal_id": row[1],
                "outcome_id": row[2],
                "run_id": row[3],
                "tenant_id": row[4],
                "incident_id": row[5],
                "decision": row[6],
                "incoming": {
                    "provider": row[7],
                    "status": row[8],
                    "provider_receipt_id": row[9],
                    "receipt_digest": row[10],
                },
                "durable": {
                    "provider": row[11],
                    "status": row[12],
                    "provider_receipt_id": row[13],
                    "receipt_digest": row[14],
                },
                "error_code": row[15],
                "sequence_no": int(row[16]),
                "previous_entry_hash": row[17],
                "entry_hash": row[18],
                "recorded_at": row[19].isoformat(),
            }
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--migrator-secret-id", required=True)
    parser.add_argument("--runtime-secret-id", required=True)
    parser.add_argument("--ca-cert", required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--deployment-artifact-sha256", required=True)
    parser.add_argument("--workflow-run-id", required=True, type=int)
    parser.add_argument("--workflow-run-attempt", required=True, type=int)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--public-output", required=True, type=Path)
    args = parser.parse_args()
    if re.fullmatch(r"[0-9a-f]{40}", args.source_head) is None:
        raise ValueError("source-head must be a full lowercase commit")
    if re.fullmatch(r"[0-9a-f]{64}", args.deployment_artifact_sha256) is None:
        raise ValueError("deployment artifact must be SHA-256")
    expected_prefix = (
        f"evidence/outcome-replay-cas/{args.source_head}/"
        f"{args.workflow_run_id}-{args.workflow_run_attempt}"
    )
    if args.prefix != expected_prefix:
        raise ValueError("evidence prefix is not checksum-addressed")

    secrets = boto3.client("secretsmanager", region_name=args.region)
    s3 = boto3.client("s3", region_name=args.region)
    migrator_url = pin_database_tls_root(
        _database_url(_secret_payload(secrets, args.migrator_secret_id)),
        args.ca_cert,
    )
    runtime_url, tenant_id, incident_id, sql_role = _runtime_context(
        secret_client=secrets,
        runtime_secret_id=args.runtime_secret_id,
        ca_cert=args.ca_cert,
    )
    connect = psycopg_connection_factory(migrator_url)
    migration = Migrator(connect).migrate()
    configure_scope_read_policies(
        migrator_url,
        tenant_id=tenant_id,
        incident_id=incident_id,
    )

    accepted_key = f"{args.prefix}/provider/accepted.json"
    conflicting_key = f"{args.prefix}/provider/conflicting.json"
    _put_provider_object(
        s3,
        bucket=args.bucket,
        key=accepted_key,
        source_head=args.source_head,
        label="accepted",
    )
    _put_provider_object(
        s3,
        bucket=args.bucket,
        key=conflicting_key,
        source_head=args.source_head,
        label="conflicting",
    )

    authority = ProviderOutcomeAttestationAuthority.ephemeral(
        issuer="s3-provider-origin-verifier-v1"
    )
    episodes = CockroachEpisodeStore(connect, attestation_verifier=authority)
    outbox = CockroachOutboxStore(connect)
    provider = S3ReceiptLookupProvider(
        client=s3,
        bucket=args.bucket,
        source_head=args.source_head,
        workflow_run_id=args.workflow_run_id,
    )
    proposal_id, idempotency_key = _approved_enqueued_proposal(
        episodes=episodes,
        outbox=outbox,
        tenant_id=tenant_id,
        incident_id=incident_id,
        workflow_run_id=args.workflow_run_id,
        case="accepted",
    )
    provider.register(
        idempotency_key=idempotency_key,
        object_key=accepted_key,
    )
    accepted_outcome, accepted_handle = authority.verify_and_issue(
        proposal_id=proposal_id,
        idempotency_key=idempotency_key,
        provider=provider,
        policy_version="s3-receipt-lookup-v1",
    )
    first = episodes.record_outcome_and_promote(
        proposal_id=proposal_id,
        outcome=accepted_outcome,
        outcome_attestation=accepted_handle,
    )
    exact = episodes.record_outcome_and_promote(
        proposal_id=proposal_id,
        outcome=accepted_outcome,
        outcome_attestation=accepted_handle,
    )

    provider.register(
        idempotency_key=idempotency_key,
        object_key=conflicting_key,
    )
    conflicting_outcome, conflicting_handle = authority.verify_and_issue(
        proposal_id=proposal_id,
        idempotency_key=idempotency_key,
        provider=provider,
        policy_version="s3-receipt-lookup-v1",
    )
    if (
        accepted_outcome.provider_receipt_id
        == conflicting_outcome.provider_receipt_id
    ):
        raise RuntimeError("S3 provider receipts did not diverge")
    try:
        episodes.record_outcome_and_promote(
            proposal_id=proposal_id,
            outcome=conflicting_outcome,
            outcome_attestation=conflicting_handle,
        )
    except OutcomeReplayConflictError as conflict:
        conflict_error = conflict
    else:
        raise RuntimeError("conflicting provider outcome was not rejected")

    negative_codes: dict[str, str] = {}
    negative_proposal_ids: list[str] = []

    def negative_proposal(case: str) -> tuple[str, str]:
        negative_id, negative_key = _approved_enqueued_proposal(
            episodes=episodes,
            outbox=outbox,
            tenant_id=tenant_id,
            incident_id=incident_id,
            workflow_run_id=args.workflow_run_id,
            case=case,
        )
        negative_proposal_ids.append(negative_id)
        provider.register(
            idempotency_key=negative_key,
            object_key=accepted_key,
        )
        return negative_id, negative_key

    missing_id, _ = negative_proposal("missing-handle")
    try:
        episodes.record_outcome_and_promote(
            proposal_id=missing_id,
            outcome=accepted_outcome,
        )
    except OutcomeAttestationError as error:
        negative_codes["missing_handle"] = error.code

    forged_id, forged_key = negative_proposal("forged-handle")
    forged_outcome, issued_handle = authority.verify_and_issue(
        proposal_id=forged_id,
        idempotency_key=forged_key,
        provider=provider,
        policy_version="s3-receipt-lookup-v1",
    )
    version, payload, signature = issued_handle.split(".")
    forged_signature = ("A" if signature[0] != "A" else "B") + signature[1:]
    try:
        episodes.record_outcome_and_promote(
            proposal_id=forged_id,
            outcome=forged_outcome,
            outcome_attestation=f"{version}.{payload}.{forged_signature}",
        )
    except OutcomeAttestationError as error:
        negative_codes["forged_handle"] = error.code

    expired_id, expired_key = negative_proposal("expired-handle")
    expired_outcome, expired_handle = authority.verify_and_issue(
        proposal_id=expired_id,
        idempotency_key=expired_key,
        provider=provider,
        policy_version="s3-receipt-lookup-v1",
        issued_at=datetime.now(timezone.utc) - timedelta(minutes=6),
    )
    try:
        episodes.record_outcome_and_promote(
            proposal_id=expired_id,
            outcome=expired_outcome,
            outcome_attestation=expired_handle,
        )
    except OutcomeAttestationError as error:
        negative_codes["expired_handle"] = error.code

    source_id, source_key = negative_proposal("cross-proposal-source")
    source_outcome, source_handle = authority.verify_and_issue(
        proposal_id=source_id,
        idempotency_key=source_key,
        provider=provider,
        policy_version="s3-receipt-lookup-v1",
    )
    target_id, _ = negative_proposal("cross-proposal-target")
    try:
        episodes.record_outcome_and_promote(
            proposal_id=target_id,
            outcome=source_outcome,
            outcome_attestation=source_handle,
        )
    except OutcomeAttestationError as error:
        negative_codes["cross_proposal"] = error.code

    mismatch_id, mismatch_key = negative_proposal("receipt-mismatch")
    _, mismatch_handle = authority.verify_and_issue(
        proposal_id=mismatch_id,
        idempotency_key=mismatch_key,
        provider=provider,
        policy_version="s3-receipt-lookup-v1",
    )
    try:
        episodes.record_outcome_and_promote(
            proposal_id=mismatch_id,
            outcome=conflicting_outcome,
            outcome_attestation=mismatch_handle,
        )
    except OutcomeAttestationError as error:
        negative_codes["receipt_mismatch"] = error.code

    provider_id, provider_key = negative_proposal("provider-mismatch")
    provider_outcome, provider_handle = authority.verify_and_issue(
        proposal_id=provider_id,
        idempotency_key=provider_key,
        provider=provider,
        policy_version="s3-receipt-lookup-v1",
    )
    try:
        episodes.record_outcome_and_promote(
            proposal_id=provider_id,
            outcome=ProviderOutcome(
                provider="github-actions",
                status=provider_outcome.status,
                provider_receipt_id=provider_outcome.provider_receipt_id,
                evidence=provider_outcome.evidence,
                observed_at=provider_outcome.observed_at,
                verified_at=provider_outcome.verified_at,
            ),
            outcome_attestation=provider_handle,
        )
    except OutcomeAttestationError as error:
        negative_codes["cross_provider"] = error.code

    candidate_id = outcome_candidate_id(proposal_id, str(first.receipt_digest))
    with connect() as connection:
        outcome_rows = int(
            connection.execute(
                "SELECT count(*) FROM outcome_evidence WHERE proposal_id = %s",
                (proposal_id,),
            ).fetchone()[0]
        )
        canonical_promotions = int(
            connection.execute(
                "SELECT count(*) FROM canonical_memories WHERE source_candidate_id = %s",
                (candidate_id,),
            ).fetchone()[0]
        )
        journal = _journal_rows(connection, proposal_id)
        attestation_row = connection.execute(
            """
            SELECT
                handle_digest,
                nonce_digest,
                consumed_outcome_id::STRING,
                issuer,
                key_id,
                policy_version
            FROM provider_outcome_attestations
            WHERE proposal_id = %s
            """,
            (proposal_id,),
        ).fetchone()
        attestation_rows = int(
            connection.execute(
                """
                SELECT count(*) FROM provider_outcome_attestations
                WHERE proposal_id = %s
                """,
                (proposal_id,),
            ).fetchone()[0]
        )
        atomic_join_rows = int(
            connection.execute(
                """
                SELECT count(*)
                FROM provider_outcome_attestations AS a
                JOIN outcome_evidence AS o
                    ON o.outcome_id = a.consumed_outcome_id
                    AND o.proposal_id = a.proposal_id
                    AND o.receipt_digest = a.receipt_digest
                JOIN canonical_memories AS m
                    ON m.source_candidate_id = %s
                WHERE a.proposal_id = %s
                    AND o.outcome_id = %s
                """,
                (candidate_id, proposal_id, first.outcome_id),
            ).fetchone()[0]
        )
        negative_outcome_rows = int(
            connection.execute(
                """
                SELECT count(*) FROM outcome_evidence
                WHERE proposal_id = ANY(%s::UUID[])
                """,
                (negative_proposal_ids,),
            ).fetchone()[0]
        )
        raw_handle_columns = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                    AND table_name = 'provider_outcome_attestations'
                """
            ).fetchall()
            if str(row[0]) in {"handle", "raw_handle", "token"}
        }
    if attestation_row is None:
        raise RuntimeError("successful promotion lacks a consumed attestation")

    scope_connect = psycopg_connection_factory(runtime_url)
    with scope_connect() as connection:
        current_user = connection.execute("SELECT current_user").fetchone()[0]
        proposal_visible_rows = int(
            connection.execute(
                """
                SELECT count(*) FROM outcome_reconciliation_journal
                WHERE proposal_id = %s
                """,
                (proposal_id,),
            ).fetchone()[0]
        )
        attestation_visible_rows = int(
            connection.execute(
                """
                SELECT count(*) FROM provider_outcome_attestations
                WHERE proposal_id = %s
                """,
                (proposal_id,),
            ).fetchone()[0]
        )
    with scope_connect() as connection:
        try:
            connection.execute(
                "INSERT INTO provider_outcome_attestations DEFAULT VALUES"
            )
        except Exception as error:
            connection.rollback()
            runtime_insert_sqlstate = getattr(error, "sqlstate", None)
        else:
            connection.rollback()
            runtime_insert_sqlstate = "UNEXPECTED_SUCCESS"
    isolation = verify_scope_role(
        runtime_url,
        tenant_id=tenant_id,
        incident_id=incident_id,
    )

    report = {
        "schema_version": 2,
        "kind": "continuum.outcome-replay-cas.report",
        "source_head": args.source_head,
        "deployment_artifact_sha256": args.deployment_artifact_sha256,
        "workflow": {
            "run_id": args.workflow_run_id,
            "run_attempt": args.workflow_run_attempt,
        },
        "migration": migration.as_dict(),
        "database": {
            "engine": "CockroachDB",
            "scope_sql_role": current_user,
            "rls": {
                "all_visible_reconciliations_in_scope": isolation[
                    "all_visible_reconciliations_in_scope"
                ],
                "proposal_visible_rows": proposal_visible_rows,
                "attestation_visible_rows": attestation_visible_rows,
                "runtime_attestation_insert_sqlstate": runtime_insert_sqlstate,
            },
        },
        "provider": {
            "adapter": "aws-s3",
            "capability_manifest": {
                "supports_idempotency": True,
                "receipt_lookup": True,
                "reconciliation_timeout_seconds": 0,
            },
            "lookup_method": "s3:HeadObject+GetObject",
            "lookup_count": provider.lookup_count,
            "accepted_object_sha256": accepted_outcome.evidence["object_sha256"],
            "conflicting_object_sha256": conflicting_outcome.evidence[
                "object_sha256"
            ],
            "accepted_receipt_sha256": _sha256(
                str(accepted_outcome.provider_receipt_id)
            ),
            "conflicting_receipt_sha256": _sha256(
                str(conflicting_outcome.provider_receipt_id)
            ),
        },
        "attestation": {
            "algorithm": "HMAC-SHA256",
            "issuer": attestation_row[3],
            "key_id": attestation_row[4],
            "policy_version": attestation_row[5],
            "ttl_seconds": 300,
            "handle_digest": first.attestation_digest,
            "stored_handle_digest": attestation_row[0],
            "stored_nonce_digest": attestation_row[1],
            "consumed_outcome_id": attestation_row[2],
            "consumed_rows": attestation_rows,
            "atomic_join_rows": atomic_join_rows,
            "raw_handle_persisted": bool(raw_handle_columns),
            "negative_outcome_rows": negative_outcome_rows,
            "negative_codes": negative_codes,
        },
        "cas": {
            "outcome_rows": outcome_rows,
            "canonical_promotions": canonical_promotions,
            "journal_rows": len(journal),
            "first_replayed": first.replayed,
            "exact_replayed": exact.replayed,
            "conflict_error_code": conflict_error.code,
            "journal": journal,
            "chain_tip": journal[-1]["entry_hash"] if journal else None,
        },
        "gate": {
            "one_durable_outcome": outcome_rows == 1,
            "one_canonical_promotion": canonical_promotions == 1,
            "exact_replay_idempotent": exact.replayed
            and exact.outcome_id == first.outcome_id,
            "conflicting_replay_rejected": conflict_error.code
            == "OUTCOME_REPLAY_CONFLICT",
            "conflict_committed_before_error": len(journal) == 3
            and journal[-1]["reconciliation_id"]
            == conflict_error.reconciliation_id,
            "journal_hash_chain_valid": len(journal) == 3,
            "scope_rls_valid": current_user == sql_role
            and proposal_visible_rows == 3
            and attestation_visible_rows == 1
            and runtime_insert_sqlstate == "42501"
            and isolation["all_visible_reconciliations_in_scope"] is True,
            "provider_lookup_before_issue": provider.lookup_count == 7,
            "signed_handle_consumed_once": attestation_rows == 1
            and first.attestation_digest == attestation_row[0]
            and first.outcome_id == attestation_row[2],
            "atomic_attestation_outcome_promotion": atomic_join_rows == 1,
            "unauthorized_promotions_blocked": negative_codes
            == {
                "cross_proposal": OUTCOME_ATTESTATION_BINDING_MISMATCH,
                "cross_provider": OUTCOME_ATTESTATION_BINDING_MISMATCH,
                "expired_handle": OUTCOME_ATTESTATION_EXPIRED,
                "forged_handle": OUTCOME_ATTESTATION_INVALID,
                "missing_handle": OUTCOME_ATTESTATION_REQUIRED,
                "receipt_mismatch": OUTCOME_ATTESTATION_BINDING_MISMATCH,
            }
            and negative_outcome_rows == 0,
            "raw_handle_absent": not raw_handle_columns,
            "status": "PASS",
        },
    }
    validate_outcome_replay_proof(report)
    public = build_public_outcome_replay_proof(report)
    _write(args.output, report)
    _write(args.public_output, public)
    print(
        json.dumps(
            {
                "ok": True,
                "status": "PASS",
                "migration_version": migration.current_version,
                "outcome_rows": outcome_rows,
                "canonical_promotions": canonical_promotions,
                "journal_rows": len(journal),
                "provider_lookups": provider.lookup_count,
                "attestation_rows": attestation_rows,
                "chain_tip": report["cas"]["chain_tip"],
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
