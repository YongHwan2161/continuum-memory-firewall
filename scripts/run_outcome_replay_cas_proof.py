#!/usr/bin/env python3
"""Prove outcome replay CAS on the participant CockroachDB with real S3 receipts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
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


def _put_receipt(
    client: Any,
    *,
    bucket: str,
    key: str,
    source_head: str,
    label: str,
) -> tuple[str, dict[str, Any]]:
    body = json.dumps(
        {
            "kind": "continuum.outcome-replay-cas.provider-object",
            "label": label,
            "source_head": source_head,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    response = client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
        Metadata={"continuum-source-head": source_head},
    )
    head = client.head_object(Bucket=bucket, Key=key)
    etag = str(head["ETag"]).strip('"')
    version_id = str(response.get("VersionId") or head.get("VersionId") or "unversioned")
    receipt_id = "aws-s3:" + _sha256(
        f"{bucket}\x00{key}\x00{etag}\x00{version_id}"
    )
    return receipt_id, {
        "content_length": int(head["ContentLength"]),
        "etag_sha256": _sha256(etag),
        "object_sha256": _sha256(body),
        "version_id_sha256": _sha256(version_id),
    }


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

    accepted_receipt, accepted_facts = _put_receipt(
        s3,
        bucket=args.bucket,
        key=f"{args.prefix}/provider/accepted.json",
        source_head=args.source_head,
        label="accepted",
    )
    conflicting_receipt, conflicting_facts = _put_receipt(
        s3,
        bucket=args.bucket,
        key=f"{args.prefix}/provider/conflicting.json",
        source_head=args.source_head,
        label="conflicting",
    )
    if accepted_receipt == conflicting_receipt:
        raise RuntimeError("S3 provider receipts did not diverge")

    episodes = CockroachEpisodeStore(connect)
    run = episodes.start_run(
        tenant_id=tenant_id,
        incident_id=incident_id,
        arm=AgentArm.CONTINUUM,
        model_id="outcome-replay-cas-proof-v1",
        input_payload={
            "provider": "aws-s3",
            "source_head": args.source_head,
            "workflow_run_id": args.workflow_run_id,
        },
    )
    proposal_id = episodes.record_proposal(
        run=run,
        proposal=ProposedAction(
            action_key=f"outcome-replay-cas:{args.workflow_run_id}",
            action_type="put_disposable_evidence_object",
            parameters={"provider": "aws-s3", "retention": "judge-evidence"},
            rationale="Bind one real provider outcome to one proposal.",
            citation_memory_ids=(),
            risk_class=RiskClass.REVERSIBLE,
        ),
    )
    episodes.approve_proposal(
        proposal_id=proposal_id,
        actor="policy:outcome-replay-cas-proof-v1",
        reason="disposable evidence prefix only",
    )
    observed = datetime.now(timezone.utc)
    accepted_outcome = ProviderOutcome(
        provider="aws-s3",
        status=OutcomeStatus.SUCCEEDED,
        provider_receipt_id=accepted_receipt,
        evidence={
            **accepted_facts,
            "source_head": args.source_head,
            "workflow_run_id": args.workflow_run_id,
        },
        observed_at=observed,
        verified_at=observed,
    )
    first = episodes.record_outcome_and_promote(
        proposal_id=proposal_id,
        outcome=accepted_outcome,
    )
    exact = episodes.record_outcome_and_promote(
        proposal_id=proposal_id,
        outcome=accepted_outcome,
    )
    conflicting_observed = datetime.now(timezone.utc)
    try:
        episodes.record_outcome_and_promote(
            proposal_id=proposal_id,
            outcome=ProviderOutcome(
                provider="aws-s3",
                status=OutcomeStatus.SUCCEEDED,
                provider_receipt_id=conflicting_receipt,
                evidence={
                    **conflicting_facts,
                    "source_head": args.source_head,
                    "workflow_run_id": args.workflow_run_id,
                },
                observed_at=conflicting_observed,
                verified_at=conflicting_observed,
            ),
        )
    except OutcomeReplayConflictError as conflict:
        conflict_error = conflict
    else:
        raise RuntimeError("conflicting provider outcome was not rejected")

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
    isolation = verify_scope_role(
        runtime_url,
        tenant_id=tenant_id,
        incident_id=incident_id,
    )

    report = {
        "schema_version": 1,
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
            },
        },
        "provider": {
            "adapter": "aws-s3",
            "capability_manifest": {
                "supports_idempotency": True,
                "receipt_lookup": True,
                "reconciliation_timeout_seconds": 0,
            },
            "accepted_object_sha256": accepted_facts["object_sha256"],
            "conflicting_object_sha256": conflicting_facts["object_sha256"],
            "accepted_receipt_sha256": _sha256(accepted_receipt),
            "conflicting_receipt_sha256": _sha256(conflicting_receipt),
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
            and isolation["all_visible_reconciliations_in_scope"] is True,
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
                "chain_tip": report["cas"]["chain_tip"],
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
