"""Inject outbox crash points against the participant CockroachDB cluster."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

import boto3

from continuum.aws_secrets import get_secret_string_with_backoff
from continuum.episode import (
    AgentArm,
    CockroachEpisodeStore,
    ProposedAction,
    RiskClass,
)
from continuum.migrate import Migrator
from continuum.outbox import (
    CockroachOutboxStore,
    CrashPoint,
    InMemoryEffectProvider,
    InjectedCrash,
    OutboxStatus,
    TransactionalOutboxWorker,
)
from continuum.store import pin_database_tls_root, psycopg_connection_factory


INITIAL_HEAD = "0" * 64


def _database_url(client: Any, secret_id: str) -> str:
    value = get_secret_string_with_backoff(client, secret_id)
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return value
    if not isinstance(payload, dict) or not isinstance(payload.get("database_url"), str):
        raise RuntimeError("database secret is malformed")
    return payload["database_url"]


def _write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    os.chmod(path, 0o600)


def _create_incident(connect: Any, *, tenant_id: str, service_name: str) -> str:
    incident_id = str(uuid4())
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO incidents (
                incident_id, tenant_id, service_name, status, current_head
            ) VALUES (%s, %s, %s, 'open', %s)
            """,
            (incident_id, tenant_id, service_name, INITIAL_HEAD),
        )
    return incident_id


def _approved_proposal(
    episodes: CockroachEpisodeStore,
    *,
    tenant_id: str,
    incident_id: str,
    case_name: str,
    now: datetime,
) -> str:
    run = episodes.start_run(
        tenant_id=tenant_id,
        incident_id=incident_id,
        arm=AgentArm.STATELESS,
        model_id="fault-injection-driver-v1",
        input_payload={"case": case_name, "synthetic": True},
        now=now,
    )
    proposal_id = episodes.record_proposal(
        run=run,
        proposal=ProposedAction(
            action_key=f"fault-proof:{case_name}",
            action_type="inspect_service",
            parameters={"service": f"fault-proof-{case_name}"},
            rationale="Non-effecting transactional outbox fault proof.",
            citation_memory_ids=(),
            risk_class=RiskClass.READ_ONLY,
        ),
        now=now,
    )
    episodes.approve_proposal(
        proposal_id=proposal_id,
        actor="policy:outbox-live-proof-v1",
        reason="allowlisted non-effecting fault-injection action",
        now=now,
    )
    return proposal_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--migrator-secret-id", required=True)
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--ca-cert", default="/opt/continuum/cockroach-ca.crt")
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    secret_client = boto3.client("secretsmanager", region_name=args.region)
    database_url = pin_database_tls_root(
        _database_url(secret_client, args.migrator_secret_id),
        args.ca_cert,
    )
    connect = psycopg_connection_factory(database_url)
    migration = Migrator(connect).migrate()
    episodes = CockroachEpisodeStore(connect)
    outbox = CockroachOutboxStore(connect)
    tenant_id = str(uuid4())
    scenarios: list[Mapping[str, Any]] = []

    definitions = (
        ("before_send", CrashPoint.BEFORE_SEND, True),
        ("after_send_idempotent", CrashPoint.AFTER_SEND, True),
        ("before_ack", CrashPoint.BEFORE_ACK, True),
        ("after_send_non_idempotent", CrashPoint.AFTER_SEND, False),
    )
    for offset, (case_name, crash_point, supports_idempotency) in enumerate(
        definitions
    ):
        now = datetime.now(timezone.utc)
        incident_id = _create_incident(
            connect,
            tenant_id=tenant_id,
            service_name=f"outbox-{case_name}",
        )
        proposal_id = _approved_proposal(
            episodes,
            tenant_id=tenant_id,
            incident_id=incident_id,
            case_name=case_name,
            now=now,
        )
        provider = InMemoryEffectProvider(
            name=(
                "outbox-live-idempotent-v1"
                if supports_idempotency
                else "outbox-live-non-idempotent-v1"
            ),
            supports_idempotency=supports_idempotency,
            clock=lambda current=now: current,
        )
        item = outbox.enqueue_proposal(
            proposal_id=proposal_id,
            provider=provider.name,
            provider_supports_idempotency=supports_idempotency,
            now=now,
        )
        worker = TransactionalOutboxWorker(
            outbox=outbox,
            episodes=episodes,
            provider=provider,
            worker_id=f"outbox-live-{offset}",
        )
        try:
            worker.process_one(
                now=now,
                crash_at=crash_point,
                lease_seconds=1,
            )
        except InjectedCrash as error:
            if error.point is not crash_point:
                raise
        else:
            raise RuntimeError(f"fault injection did not fire for {case_name}")

        after_crash = outbox.get(item.outbox_id).status
        if crash_point is CrashPoint.BEFORE_SEND:
            requeued = worker.reconcile(
                outbox_id=item.outbox_id,
                now=now + timedelta(seconds=2),
            )
            if requeued.item.status is not OutboxStatus.PENDING:
                raise RuntimeError("before-send lease did not requeue")
            completed = worker.process_one(now=now + timedelta(seconds=3))
        else:
            completed = worker.reconcile(
                outbox_id=item.outbox_id,
                now=now + timedelta(seconds=1),
            )
        if completed is None:
            raise RuntimeError("fault scenario did not reach a terminal state")
        effects = sum(provider.effect_count.values())
        scenarios.append(
            {
                "after_crash_status": after_crash.value,
                "canonical_promoted": bool(
                    completed.promotion and completed.promotion.memory_id
                ),
                "case": case_name,
                "duplicate_effects": max(0, effects - 1),
                "logical_effects": effects,
                "provider_supports_idempotency": supports_idempotency,
                "terminal_outbox_status": completed.item.status.value,
                "terminal_outcome_status": (
                    None
                    if completed.promotion is None
                    else completed.promotion.status.value
                ),
            }
        )

    by_case = {row["case"]: row for row in scenarios}
    pass_gate = (
        all(row["duplicate_effects"] == 0 for row in scenarios)
        and by_case["before_send"]["terminal_outbox_status"] == "acknowledged"
        and by_case["after_send_idempotent"]["terminal_outbox_status"]
        == "acknowledged"
        and by_case["before_ack"]["terminal_outbox_status"] == "acknowledged"
        and by_case["after_send_non_idempotent"]["terminal_outbox_status"]
        == "ambiguous"
        and not by_case["after_send_non_idempotent"]["canonical_promoted"]
    )
    if not pass_gate:
        raise RuntimeError("transactional outbox fault gate failed")
    report = {
        "gate": {
            "ambiguous_without_blind_resend": True,
            "duplicate_effects_zero": True,
            "status": "PASS",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "migration_version": migration.current_version,
        "provider_mode": "non-effecting-in-memory-provider-with-durable-db-outbox",
        "retained_for_judge_evidence": True,
        "scenarios": scenarios,
        "schema_version": 1,
        "source_head": args.source_head,
        "synthetic_non_effecting": True,
    }
    if args.output is not None:
        _write_report(args.output, report)
    print(json.dumps(report, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
