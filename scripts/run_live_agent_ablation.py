"""Run five paired 36-case Bedrock/CockroachDB three-arm replications."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time
from typing import Any, Mapping
from uuid import uuid4

import boto3

from continuum.aws_secrets import get_secret_string_with_backoff
from continuum.ablation import (
    AblationObservation,
    SyntheticReceiptProvider,
    build_competition_cases,
    summarize_ablation,
)
from continuum.episode import (
    AgentArm,
    CockroachEpisodeStore,
    OutcomeStatus,
)
from continuum.migrate import Migrator
from continuum.orchestrator import (
    AgentOrchestrator,
    BedrockConverseClient,
    OrchestrationError,
    RetrievalStoreTools,
)
from continuum.retrieval import BedrockTitanEmbedder, MemoryRetrievalStore
from continuum.store import (
    CockroachMemoryStore,
    pin_database_tls_root,
    psycopg_connection_factory,
)


INITIAL_HEAD = "0" * 64
DEFAULT_SEEDS = (101, 203, 307, 409, 503)


def _parse_seeds(value: str) -> tuple[int, ...]:
    try:
        seeds = tuple(int(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("seeds must be comma-separated integers") from exc
    if len(seeds) != 5 or len(set(seeds)) != 5:
        raise argparse.ArgumentTypeError("exactly five unique seeds are required")
    return seeds


def _database_url(client: Any, secret_id: str) -> str:
    value = get_secret_string_with_backoff(client, secret_id)
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return value
    if not isinstance(payload, dict) or not isinstance(payload.get("database_url"), str):
        raise RuntimeError("database secret is malformed")
    return payload["database_url"]


def _create_incident(
    connect: Any,
    *,
    tenant_id: str,
    service_name: str,
) -> str:
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


def _append_baseline_memory(
    *,
    connect: Any,
    retrieval: MemoryRetrievalStore,
    embedder: BedrockTitanEmbedder,
    tenant_id: str,
    incident_id: str,
    memory_key: str,
    payload: Mapping[str, Any],
) -> str:
    with connect() as connection:
        prior = connection.execute(
            """
            SELECT memory_id::STRING
            FROM canonical_memories
            WHERE tenant_id = %s AND incident_id = %s
                AND payload->>'ablation_memory_key' = %s
            """,
            (tenant_id, incident_id, memory_key),
        ).fetchone()
        if prior is not None:
            return prior[0]
        current_head = connection.execute(
            """
            SELECT current_head
            FROM incidents
            WHERE tenant_id = %s AND incident_id = %s
            """,
            (tenant_id, incident_id),
        ).fetchone()[0]
        candidate_id = str(uuid4())
        now = datetime.now(timezone.utc)
        durable_payload = {
            **payload,
            "ablation_memory_key": memory_key,
            "baseline_only": True,
            "synthetic": True,
        }
        connection.execute(
            """
            INSERT INTO memory_candidates (
                candidate_id, tenant_id, incident_id, parent_hash,
                source_kind, action_class, payload, created_at, expires_at
            ) VALUES (%s, %s, %s, %s, 'tool', 'observe', %s::JSONB, %s, %s)
            """,
            (
                candidate_id,
                tenant_id,
                incident_id,
                current_head,
                json.dumps(durable_payload, separators=(",", ":"), sort_keys=True),
                now - timedelta(seconds=1),
                now + timedelta(days=7),
            ),
        )
    promoted = CockroachMemoryStore(connect).promote_candidate(candidate_id, now=now)
    if promoted.memory_id is None:
        raise RuntimeError("baseline memory promotion failed")
    retrieval.index_memory(
        tenant_id=tenant_id,
        incident_id=incident_id,
        memory_id=promoted.memory_id,
        embedder=embedder,
    )
    return promoted.memory_id


def _write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    os.chmod(path, 0o600)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--migrator-secret-id", required=True)
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--embedding-region", default="ap-northeast-2")
    parser.add_argument("--agent-region", default="ap-southeast-2")
    parser.add_argument("--agent-model", default="amazon.nova-micro-v1:0")
    parser.add_argument("--ca-cert", default="/opt/continuum/cockroach-ca.crt")
    parser.add_argument(
        "--seeds",
        type=_parse_seeds,
        default=DEFAULT_SEEDS,
        help="exactly five unique paired-replication identifiers",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    secret_client = boto3.client("secretsmanager", region_name=args.region)
    database_url = pin_database_tls_root(
        _database_url(secret_client, args.migrator_secret_id),
        args.ca_cert,
    )
    connect = psycopg_connection_factory(database_url)
    migration = Migrator(connect).migrate()
    episode_store = CockroachEpisodeStore(connect)
    retrieval_store = MemoryRetrievalStore(connect)
    embedder = BedrockTitanEmbedder(region=args.embedding_region)
    model = BedrockConverseClient(region=args.agent_region)
    provider = SyntheticReceiptProvider()
    cases = build_competition_cases()

    evaluation_id = str(uuid4())
    evaluation_tenant = str(uuid4())
    scopes: dict[tuple[int, AgentArm, str], str] = {}
    for seed in args.seeds:
        for arm in AgentArm:
            for family in sorted({case.family for case in cases}):
                scopes[(seed, arm, family)] = _create_incident(
                    connect,
                    tenant_id=evaluation_tenant,
                    service_name=f"ablation-{seed}-{arm.value}-{family}",
                )
    denied_incident = _create_incident(
        connect,
        tenant_id=evaluation_tenant,
        service_name="ablation-cross-scope-denied",
    )
    forbidden_memory_id = _append_baseline_memory(
        connect=connect,
        retrieval=retrieval_store,
        embedder=embedder,
        tenant_id=evaluation_tenant,
        incident_id=denied_incident,
        memory_key=f"{evaluation_id}:forbidden",
        payload={
            "summary": "Cross-scope sentinel that must never be retrieved.",
            "type": "cross_scope_sentinel_v1",
        },
    )

    observations: list[AblationObservation] = []
    for seed in args.seeds:
        for arm in AgentArm:
            for case in cases:
                incident_id = scopes[(seed, arm, case.family)]
                if arm is AgentArm.RAW_RAG:
                    for injection in case.raw_injections:
                        _append_baseline_memory(
                            connect=connect,
                            retrieval=retrieval_store,
                            embedder=embedder,
                            tenant_id=evaluation_tenant,
                            incident_id=incident_id,
                            memory_key=(
                                f"{evaluation_id}:{seed}:{injection.injection_id}"
                            ),
                            payload={
                                "proposed_action": injection.proposed_action,
                                "provenance": injection.provenance,
                                "summary": injection.text,
                                "type": "raw_rag_unverified_injection_v1",
                            },
                        )
                tools = None
                if arm is not AgentArm.STATELESS:
                    tools = RetrievalStoreTools(
                        store=retrieval_store,
                        embedder=embedder,
                        tenant_id=evaluation_tenant,
                        incident_id=incident_id,
                        min_similarity=-1.0,
                    )
                orchestrator = AgentOrchestrator(
                    store=episode_store,
                    model=model,
                    model_id=args.agent_model,
                )
                started = time.perf_counter_ns()
                result = None
                promoted_memory_id = None
                outcome_status = OutcomeStatus.FAILED
                failure_code = None
                failure_cause = None
                failed_model_turns = 0
                failed_tool_calls = 0
                try:
                    result = orchestrator.run(
                        tenant_id=evaluation_tenant,
                        incident_id=incident_id,
                        arm=arm,
                        incident=case.incident,
                        memory_tools=tools,
                        request_metadata={"continuum_evaluation_seed": str(seed)},
                    )
                    if result.proposal is not None and result.proposal_id is not None:
                        episode_store.approve_proposal(
                            proposal_id=result.proposal_id,
                            actor="policy:synthetic-ablation-v2",
                            reason="allowlisted non-production synthetic action",
                        )
                        observed_at = datetime.now(timezone.utc)
                        provider_outcome = provider.execute(
                            case=case,
                            proposal=result.proposal,
                            idempotency_key=(
                                f"{evaluation_id}:{seed}:{arm.value}:{case.case_id}"
                            ),
                            observed_at=observed_at,
                        )
                        outcome_status = provider_outcome.status
                        if provider_outcome.status is not OutcomeStatus.SUCCEEDED:
                            evidence = provider_outcome.evidence
                            if (
                                evidence.get("proposed_action_type")
                                != evidence.get("expected_action_type")
                            ):
                                failure_cause = "PROVIDER_ACTION_TYPE_MISMATCH"
                            elif (
                                evidence.get("proposed_resource")
                                != evidence.get("expected_resource")
                            ):
                                failure_cause = "PROVIDER_RESOURCE_MISMATCH"
                            elif provider_outcome.status is OutcomeStatus.AMBIGUOUS:
                                failure_cause = "PROVIDER_AMBIGUOUS"
                            else:
                                failure_cause = "PROVIDER_REJECTED"
                        outcome_result = episode_store.record_outcome_and_promote(
                            proposal_id=result.proposal_id,
                            outcome=provider_outcome,
                        )
                        promoted_memory_id = outcome_result.memory_id
                        if outcome_result.memory_id is not None:
                            retrieval_store.index_memory(
                                tenant_id=evaluation_tenant,
                                incident_id=incident_id,
                                memory_id=outcome_result.memory_id,
                                embedder=embedder,
                            )
                        if arm is AgentArm.RAW_RAG:
                            _append_baseline_memory(
                                connect=connect,
                                retrieval=retrieval_store,
                                embedder=embedder,
                                tenant_id=evaluation_tenant,
                                incident_id=incident_id,
                                memory_key=(
                                    f"{evaluation_id}:{seed}:raw:{case.case_id}"
                                ),
                                payload={
                                    "case_id": case.case_id,
                                    "outcome_status": provider_outcome.status.value,
                                    "proposed_action": {
                                        "action_type": result.proposal.action_type,
                                        "parameters": dict(result.proposal.parameters),
                                    },
                                    "provenance": "raw_model_episode",
                                    "summary": result.proposal.rationale,
                                    "type": "raw_rag_append_all_v1",
                                },
                            )
                    else:
                        failure_cause = "NO_ACTION_PROPOSED"
                except OrchestrationError as exc:
                    outcome_status = OutcomeStatus.FAILED
                    failure_code = exc.code
                    failure_cause = exc.code
                    failed_model_turns = exc.model_turns
                    failed_tool_calls = exc.tool_calls
                latency_ms = (time.perf_counter_ns() - started) / 1_000_000
                cited = () if result is None else tuple(
                    citation.memory_id for citation in result.citations
                )
                observations.append(
                    AblationObservation(
                        arm=arm,
                        case_id=case.case_id,
                        family=case.family,
                        variant=case.variant,
                        outcome_status=outcome_status,
                        latency_ms=latency_ms,
                        tool_calls=(
                            failed_tool_calls if result is None else result.tool_calls
                        ),
                        cited_memory_ids=cited,
                        proposed_action_type=(
                            None
                            if result is None or result.proposal is None
                            else result.proposal.action_type
                        ),
                        promoted_memory_id=promoted_memory_id,
                        cross_scope_leak_count=int(forbidden_memory_id in cited),
                        failure_code=failure_code,
                        failure_cause=failure_cause,
                        model_turns=(
                            failed_model_turns if result is None else result.model_turns
                        ),
                        seed=seed,
                    )
                )

    report = dict(summarize_ablation(cases, observations, seeds=args.seeds))
    report.update(
        {
            "agent_model": args.agent_model,
            "agent_region": args.agent_region,
            "embedding_model": embedder.model_id,
            "embedding_region": args.embedding_region,
            "evaluation_id": evaluation_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "migration_version": migration.current_version,
            "provider": "continuum-synthetic-verifier-v1",
            "retained_for_judge_evidence": True,
            "seed_semantics": (
                "paired independent episode-state replication IDs; Bedrock Converse "
                "does not expose a model RNG seed"
            ),
            "synthetic_non_effecting": True,
            "observations": [
                {
                    "arm": row.arm.value,
                    "case_id": row.case_id,
                    "family": row.family,
                    "variant": row.variant,
                    "outcome_status": row.outcome_status.value,
                    "latency_ms": round(row.latency_ms, 3),
                    "tool_calls": row.tool_calls,
                    "citation_count": len(row.cited_memory_ids),
                    "proposed_action_type": row.proposed_action_type,
                    "promoted": row.promoted_memory_id is not None,
                    "cross_scope_leak_count": row.cross_scope_leak_count,
                    "failure_code": row.failure_code,
                    "failure_cause": row.failure_cause,
                    "model_turns": row.model_turns,
                    "seed": row.seed,
                }
                for row in observations
            ],
        }
    )
    if any(count != 1 for count in provider.effect_count.values()):
        raise RuntimeError("synthetic provider idempotency invariant failed")
    if args.output is not None:
        _write_report(args.output, report)
    stdout_report = {key: value for key, value in report.items() if key != "observations"}
    print(json.dumps(stdout_report, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
