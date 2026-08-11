"""Join live provider receipts to scoped CockroachDB memory and back again."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping
from uuid import uuid4

import boto3

from continuum.adaptive_diagnosis import candidate_projection
from continuum.adaptive_diagnosis_agent import AdaptiveDiagnosisAgent
from continuum.aws_secrets import get_secret_string_with_backoff
from continuum.ci_recovery import validate_ci_workflow_receipt
from continuum.episode import (
    AgentArm,
    CockroachEpisodeStore,
    OutcomeStatus,
    ProposedAction,
    ProviderOutcome,
    RetrievedCitation,
    RiskClass,
    canonical_json_bytes,
)
from continuum.migrate import Migrator
from continuum.online_lineage import TransferAdmissionTools, family_for_patch
from continuum.orchestrator import BedrockConverseClient, RetrievalStoreTools
from continuum.retrieval import BedrockTitanEmbedder, MemoryRetrievalStore
from continuum.scope_roles import verify_scope_role
from continuum.store import (
    CockroachMemoryStore,
    pin_database_tls_root,
    psycopg_connection_factory,
)
from continuum.tenant_control import DatabaseTenantControlPlane


INITIAL_HEAD = "0" * 64
RLS_MIGRATIONS = (
    "0009_enable_canonical_memory_rls.sql",
    "0010_enable_retrieval_audit_rls.sql",
    "0011_enable_incident_rls.sql",
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("online lineage input must be a JSON object")
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    os.chmod(path, 0o600)


def _migration_receipt(repo_root: Path, names: tuple[str, ...]) -> dict[str, Any]:
    root = repo_root / "src" / "continuum" / "migrations"
    files = []
    for name in names:
        path = root / name
        if not path.is_file():
            raise RuntimeError(f"required migration is missing: {name}")
        content = path.read_bytes().replace(b"\r\n", b"\n")
        files.append(
            {
                "path": path.relative_to(repo_root).as_posix(),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    combined = "".join(
        f"{item['path']}:{item['sha256']}\n" for item in files
    ).encode("utf-8")
    return {
        "files": files,
        "combined_sha256": hashlib.sha256(combined).hexdigest(),
    }


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


def _parse_time(value: object) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _receipt_id(receipt: Mapping[str, Any]) -> str:
    return (
        f"github-actions:{int(receipt['workflow_run_id'])}:"
        f"{int(receipt['artifact_id'])}"
    )


def _provider_outcome(
    receipt: Mapping[str, Any],
    *,
    canonical_memory: Mapping[str, str],
) -> ProviderOutcome:
    validate_ci_workflow_receipt(receipt)
    succeeded = receipt.get("conclusion") == "success"
    return ProviderOutcome(
        provider="github-actions",
        status=OutcomeStatus.SUCCEEDED if succeeded else OutcomeStatus.FAILED,
        provider_receipt_id=_receipt_id(receipt) if succeeded else None,
        evidence={
            "artifact_digest": receipt.get("artifact_digest"),
            "receipt_sha256": receipt.get("receipt_sha256"),
            "workflow_run_id": receipt.get("workflow_run_id"),
            **({"canonical_memory": dict(canonical_memory)} if succeeded else {}),
        },
        observed_at=_parse_time(receipt["created_at"]),
        verified_at=_parse_time(receipt["completed_at"]) if succeeded else None,
    )


def _runtime_context(
    *,
    secrets_client: Any,
    runtime_secret_id: str,
    ca_cert: str,
) -> tuple[dict[str, Any], str, str, str, str]:
    payload = _secret_payload(secrets_client, runtime_secret_id)
    if not isinstance(payload, dict):
        raise RuntimeError("runtime secret must be a JSON object")
    callers = payload.get("caller_scopes")
    if not isinstance(callers, dict) or len(callers) != 1:
        raise RuntimeError("online lineage requires one registered demo caller")
    caller_id, configured = next(iter(callers.items()))
    if not isinstance(configured, Mapping):
        raise RuntimeError("runtime caller scope is invalid")
    control_url = payload.get("control_plane_database_url")
    scope_urls = payload.get("scope_database_urls")
    if not isinstance(control_url, str) or not isinstance(scope_urls, Mapping):
        raise RuntimeError("audited runtime database registry is incomplete")
    control_url = pin_database_tls_root(control_url, ca_cert)
    identity = DatabaseTenantControlPlane(
        psycopg_connection_factory(control_url)
    ).resolve(str(caller_id))
    runtime_url = scope_urls.get(identity.sql_role)
    if not isinstance(runtime_url, str):
        raise RuntimeError("resolved SQL role has no runtime connection")
    return (
        payload,
        pin_database_tls_root(runtime_url, ca_cert),
        str(caller_id),
        identity.tenant_id,
        identity.incident_id,
    )


def _create_forbidden_memory(
    *,
    connect: Any,
    retrieval: MemoryRetrievalStore,
    embedder: BedrockTitanEmbedder,
    tenant_id: str,
) -> tuple[str, str]:
    incident_id = str(uuid4())
    candidate_id = str(uuid4())
    now = datetime.now(timezone.utc)
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO incidents (
                incident_id, tenant_id, service_name, status, current_head
            ) VALUES (%s, %s, 'online-lineage-forbidden', 'open', %s)
            """,
            (incident_id, tenant_id, INITIAL_HEAD),
        )
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
                INITIAL_HEAD,
                json.dumps(
                    {
                        "summary": "Cross-scope online lineage sentinel.",
                        "synthetic": True,
                        "type": "online_lineage_cross_scope_sentinel_v1",
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                now - timedelta(seconds=1),
                now + timedelta(days=30),
            ),
        )
    promoted = CockroachMemoryStore(connect).promote_candidate(candidate_id, now=now)
    if promoted.memory_id is None:
        raise RuntimeError("cross-scope sentinel promotion failed")
    retrieval.index_memory(
        tenant_id=tenant_id,
        incident_id=incident_id,
        memory_id=promoted.memory_id,
        embedder=embedder,
    )
    return incident_id, promoted.memory_id


def _canonical_source_facts(prepared: Mapping[str, Any]) -> dict[str, str]:
    source = prepared["source"]
    receipt = source["green_receipt"]
    payload = receipt["provider_payload"]
    return {
        "causal_evidence_sha256": str(payload["causal_evidence_sha256"]),
        "causal_signature": str(payload["causal_signature"]),
        "environment_fingerprint": str(source["environment_fingerprint"]),
        "environment_profile_id": str(source["environment_profile_id"]),
        "family": str(source["family"]),
        "patch_id": str(source["expected_patch_id"]),
        "provider_conclusion": "success",
        "provider_receipt_sha256": str(receipt["receipt_sha256"]),
        "summary": (
            "Provider-verified recovery for an ambiguous bootstrap-resolution "
            "failure; the reviewed Python 3.12 patch passed the disposable CI contract."
        ),
        "transfer_contract": str(payload["transfer_contract"]),
    }


def prepare(args: argparse.Namespace) -> None:
    prepared = _load(args.provider_preparation)
    if prepared.get("kind") != (
        "continuum.online-memory-lineage.provider-preparation"
    ) or prepared.get("source_head") != args.source_head:
        raise RuntimeError("online lineage provider preparation is invalid")
    secret_client = boto3.client("secretsmanager", region_name=args.region)
    migrator_url = pin_database_tls_root(
        _database_url(_secret_payload(secret_client, args.migrator_secret_id)),
        args.ca_cert,
    )
    runtime_payload, runtime_url, caller_id, tenant_id, incident_id = (
        _runtime_context(
            secrets_client=secret_client,
            runtime_secret_id=args.runtime_secret_id,
            ca_cert=args.ca_cert,
        )
    )
    connect = psycopg_connection_factory(migrator_url)
    runtime_connect = psycopg_connection_factory(runtime_url)
    migration = Migrator(connect).migrate()
    episodes = CockroachEpisodeStore(connect)
    retrieval = MemoryRetrievalStore(connect)
    scoped_retrieval = MemoryRetrievalStore(runtime_connect)
    embedder = BedrockTitanEmbedder(region=args.embedding_region)
    model = BedrockConverseClient(region=args.agent_region)

    source_receipt = prepared["source"]["green_receipt"]
    source_run = episodes.start_run(
        tenant_id=tenant_id,
        incident_id=incident_id,
        arm=AgentArm.CONTINUUM,
        model_id="provider-verified-source-import-v1",
        input_payload={
            "campaign_id": prepared["campaign_id"],
            "provider_receipt_sha256": source_receipt["receipt_sha256"],
            "provider_receipt": source_receipt,
            "embedding_model": embedder.model_id,
            "source_family": prepared["source"]["family"],
        },
    )
    source_proposal = ProposedAction(
        action_key=f"{prepared['campaign_id']}:source",
        action_type=str(prepared["source"]["expected_patch_id"]),
        parameters={},
        rationale="Import one independently verified source recovery outcome.",
        citation_memory_ids=(),
        risk_class=RiskClass.REVERSIBLE,
    )
    source_proposal_id = episodes.record_proposal(
        run=source_run,
        proposal=source_proposal,
    )
    episodes.approve_proposal(
        proposal_id=source_proposal_id,
        actor="policy:online-lineage-source-import-v1",
        reason="exact provider-success receipt passed the registered CI contract",
    )
    source_promotion = episodes.record_outcome_and_promote(
        proposal_id=source_proposal_id,
        outcome=_provider_outcome(
            source_receipt,
            canonical_memory=_canonical_source_facts(prepared),
        ),
    )
    if source_promotion.memory_id is None:
        raise RuntimeError("provider-success source outcome was not promoted")
    retrieval.index_memory(
        tenant_id=tenant_id,
        incident_id=incident_id,
        memory_id=source_promotion.memory_id,
        embedder=embedder,
    )
    with connect() as connection:
        source_embedding_model = connection.execute(
            """
            SELECT embedding_model
            FROM canonical_memories
            WHERE memory_id = %s AND tenant_id = %s AND incident_id = %s
            """,
            (source_promotion.memory_id, tenant_id, incident_id),
        ).fetchone()[0]
    if source_embedding_model != embedder.model_id:
        raise RuntimeError("source canonical memory was not indexed by Titan")
    forbidden_incident_id, forbidden_memory_id = _create_forbidden_memory(
        connect=connect,
        retrieval=retrieval,
        embedder=embedder,
        tenant_id=tenant_id,
    )
    scope_proof = verify_scope_role(
        runtime_url,
        tenant_id=tenant_id,
        incident_id=incident_id,
        forbidden_memory_id=forbidden_memory_id,
    )
    identity = DatabaseTenantControlPlane(
        psycopg_connection_factory(
            pin_database_tls_root(
                str(runtime_payload["control_plane_database_url"]),
                args.ca_cert,
            )
        )
    ).resolve(caller_id)

    proposals: list[dict[str, Any]] = []
    for case in prepared["target_cases"]:
        run = episodes.start_run(
            tenant_id=identity.tenant_id,
            incident_id=identity.incident_id,
            arm=AgentArm.CONTINUUM,
            model_id=args.agent_model,
            input_payload={
                "campaign_id": prepared["campaign_id"],
                "case_id": case["case_id"],
                "incident": case["candidate_incident"],
            },
        )
        base_tools = RetrievalStoreTools(
            store=scoped_retrieval,
            embedder=embedder,
            tenant_id=identity.tenant_id,
            incident_id=identity.incident_id,
            min_similarity=-1.0,
        )
        admitted_tools = TransferAdmissionTools(
            base=base_tools,
            target_attestation_receipt=case["target_attestation_receipt"],
            allowed_source_memory_ids=(source_promotion.memory_id,),
        )
        diagnostics = case.get("diagnostic_receipts", {})

        def run_probe(probe_id: str) -> Mapping[str, Any]:
            receipt = diagnostics.get(probe_id)
            if not isinstance(receipt, Mapping):
                raise RuntimeError("model requested an unprepared diagnostic receipt")
            return receipt

        result = AdaptiveDiagnosisAgent(
            model=model,
            model_id=args.agent_model,
        ).run(
            arm=AgentArm.CONTINUUM,
            incident=candidate_projection(
                {"incident": case["candidate_incident"]}
            ),
            memory_tools=admitted_tools,
            run_probe=run_probe,
            request_metadata={"continuum_online_lineage": "v1"},
        )
        hits = admitted_tools.issued_hits
        episodes.record_citations(
            run=run,
            citations=tuple(
                RetrievedCitation(
                    memory_id=hit.memory_id,
                    rank=rank,
                    payload=hit.payload,
                    similarity=hit.similarity,
                    retrieval_id=hit.retrieval_id,
                )
                for rank, hit in enumerate(hits, start=1)
            ),
        )
        proposal = ProposedAction(
            action_key=f"{prepared['campaign_id']}:{case['case_id']}",
            action_type=result.proposed_patch_id,
            parameters={},
            rationale=result.rationale,
            citation_memory_ids=result.selected_memory_ids,
            risk_class=RiskClass.REVERSIBLE,
        )
        proposal_id = episodes.record_proposal(run=run, proposal=proposal)
        admission_receipt = admitted_tools.receipt().as_dict()
        proposals.append(
            {
                "case_id": case["case_id"],
                "relationship": case["relationship"],
                "target_family": str(case["provider_route"]["target_fixture_id"]),
                "expected_patch_id": case["evaluator"]["expected_patch_id"],
                "proposed_patch_id": result.proposed_patch_id,
                "run_id": run.run_id,
                "proposal_id": proposal_id,
                "selected_memory_ids": list(result.selected_memory_ids),
                "fetched_memory_ids": list(result.fetched_memory_ids),
                "diagnostic_receipts": list(result.diagnostic_receipts),
                "model_turns": result.model_turns,
                "tool_calls": result.tool_calls,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "episode_latency_ms": result.episode_latency_ms,
                "admission_receipt": admission_receipt,
                "target_attestation_receipt": case[
                    "target_attestation_receipt"
                ],
            }
        )
    prepared_at = datetime.now(timezone.utc)
    output = {
        "schema_version": 1,
        "kind": "continuum.online-memory-lineage.proposals",
        "generated_at": prepared_at.isoformat(),
        "proposal_prepared_at": prepared_at.isoformat(),
        "source_head": args.source_head,
        "deployment_artifact_sha256": args.deployment_artifact_sha256,
        "repository": prepared["repository"],
        "campaign_id": prepared["campaign_id"],
        "migration_version": migration.current_version,
        "embedding_model": embedder.model_id,
        "agent_model": args.agent_model,
        "agent_region": args.agent_region,
        "source": {
            "run_id": source_run.run_id,
            "proposal_id": source_proposal_id,
            "outcome_id": source_promotion.outcome_id,
            "memory_id": source_promotion.memory_id,
            "event_hash": source_promotion.event_hash,
            "receipt_digest": source_promotion.receipt_digest,
            "embedding_model": source_embedding_model,
            "provider_receipt": source_receipt,
            "provider_receipt_sha256": source_receipt["receipt_sha256"],
        },
        "identity": {
            "caller_id_sha256": hashlib.sha256(caller_id.encode("utf-8")).hexdigest(),
            "sql_role_sha256": hashlib.sha256(
                str(identity.sql_role).encode("utf-8")
            ).hexdigest(),
            "binding_version": identity.binding_version,
            "tenant_id": tenant_id,
            "incident_id": incident_id,
            "current_user": scope_proof["current_user"],
        },
        "isolation": {
            "forbidden_incident_id": forbidden_incident_id,
            "forbidden_memory_id": forbidden_memory_id,
            "forbidden_memory_visible": scope_proof["forbidden_memory_visible"],
            "all_visible_rows_in_scope": scope_proof[
                "all_visible_rows_in_scope"
            ],
            "all_visible_incidents_in_scope": scope_proof[
                "all_visible_incidents_in_scope"
            ],
            "all_visible_audits_in_scope": scope_proof[
                "all_visible_audits_in_scope"
            ],
            "negative_checks": scope_proof["denied"],
        },
        "rls": _migration_receipt(Path(__file__).parents[1], RLS_MIGRATIONS),
        "proposals": proposals,
    }
    _write(args.output, output)
    migrator_url = ""
    runtime_url = ""


def finalize(args: argparse.Namespace) -> None:
    state = _load(args.proposals)
    outcomes = _load(args.provider_outcomes)
    if state.get("kind") != "continuum.online-memory-lineage.proposals" or outcomes.get(
        "kind"
    ) != "continuum.online-memory-lineage.provider-outcomes":
        raise RuntimeError("online lineage finalization inputs are invalid")
    for key in ("source_head", "repository", "campaign_id"):
        if outcomes.get(key) != state.get(key):
            raise RuntimeError(f"online lineage outcome {key} drifted")
    candidate_head = str(state.get("source_head", ""))
    reconciler_head = str(args.reconciler_source_head or candidate_head)
    reconciler_artifact = str(
        args.reconciler_deployment_artifact_sha256
        or state.get("deployment_artifact_sha256", "")
    )
    if re.fullmatch(r"[0-9a-f]{40}", candidate_head) is None or re.fullmatch(
        r"[0-9a-f]{40}", reconciler_head
    ) is None:
        raise RuntimeError("online lineage reconciliation source head is invalid")
    if re.fullmatch(r"[0-9a-f]{64}", reconciler_artifact) is None:
        raise RuntimeError("online lineage reconciler artifact digest is invalid")
    cross_head_resume = reconciler_head != candidate_head
    reconciliation_input: dict[str, Any] = {}
    if cross_head_resume:
        if (
            args.predecessor_workflow_run_id < 1
            or args.reconciliation_workflow_run_id < 1
            or args.reconciliation_workflow_run_attempt < 1
            or args.reconciliation_input is None
        ):
            raise RuntimeError("cross-head reconciliation lineage is incomplete")
        reconciliation_input = _load(args.reconciliation_input)
        expected_input = {
            "kind": "continuum.online-memory-lineage.reconciliation-input",
            "candidate_source_head": candidate_head,
            "reconciler_source_head": reconciler_head,
            "predecessor_workflow_run_id": args.predecessor_workflow_run_id,
            "reconciliation_workflow_run_id": args.reconciliation_workflow_run_id,
            "reconciliation_workflow_run_attempt": (
                args.reconciliation_workflow_run_attempt
            ),
            "actions_permission": "read",
            "provider_action_dispatch_capability": False,
            "proposals_sha256": _sha256_file(args.proposals),
            "provider_outcomes_sha256": _sha256_file(args.provider_outcomes),
        }
        if any(
            reconciliation_input.get(key) != value
            for key, value in expected_input.items()
        ):
            raise RuntimeError("cross-head reconciliation input receipt drifted")
        if not str(state.get("campaign_id", "")).endswith(
            f"-{args.predecessor_workflow_run_id}"
        ):
            raise RuntimeError("predecessor run does not own the candidate campaign")
    elif args.predecessor_workflow_run_id:
        raise RuntimeError("same-head finalization cannot name a predecessor")
    secret_client = boto3.client("secretsmanager", region_name=args.region)
    migrator_url = pin_database_tls_root(
        _database_url(_secret_payload(secret_client, args.migrator_secret_id)),
        args.ca_cert,
    )
    connect = psycopg_connection_factory(migrator_url)
    episodes = CockroachEpisodeStore(connect)
    retrieval = MemoryRetrievalStore(connect)
    embedder = BedrockTitanEmbedder(region=args.embedding_region)
    outcomes_by_case = {
        str(item["case_id"]): item["provider_receipt"]
        for item in outcomes["outcomes"]
    }
    target_lineage: list[dict[str, Any]] = []
    prepared_at = _parse_time(state["proposal_prepared_at"])
    for proposal in state["proposals"]:
        case_id = str(proposal["case_id"])
        receipt = outcomes_by_case.get(case_id)
        if not isinstance(receipt, Mapping):
            raise RuntimeError("online lineage target outcome is missing")
        if _parse_time(receipt["created_at"]) < prepared_at:
            raise RuntimeError("provider action predates its durable proposal")
        attestation_payload = proposal["target_attestation_receipt"][
            "provider_payload"
        ]
        derived_family = family_for_patch(str(proposal["expected_patch_id"]))
        target_family = str(proposal.get("target_family", derived_family))
        if target_family != derived_family:
            raise RuntimeError("online lineage target family drifted")
        canonical = {
            "causal_signature": str(attestation_payload["causal_signature"]),
            "environment_fingerprint": str(
                attestation_payload["environment_fingerprint"]
            ),
            "environment_profile_id": str(
                attestation_payload["environment_profile_id"]
            ),
            "family": target_family,
            "patch_id": str(proposal["proposed_patch_id"]),
            "provider_conclusion": "success",
            "provider_receipt_sha256": str(receipt["receipt_sha256"]),
            "summary": (
                "The online lineage proposal was executed by the disposable "
                "GitHub Actions provider and independently verified."
            ),
        }
        episodes.approve_proposal(
            proposal_id=str(proposal["proposal_id"]),
            actor="policy:online-lineage-target-v1",
            reason="bounded disposable provider action after durable proposal",
        )
        promotion = episodes.record_outcome_and_promote(
            proposal_id=str(proposal["proposal_id"]),
            outcome=_provider_outcome(receipt, canonical_memory=canonical),
        )
        if promotion.memory_id is not None:
            retrieval.index_memory(
                tenant_id=str(state["identity"]["tenant_id"]),
                incident_id=str(state["identity"]["incident_id"]),
                memory_id=promotion.memory_id,
                embedder=embedder,
            )
        target_lineage.append(
            {
                **proposal,
                "provider_receipt": dict(receipt),
                "outcome_id": promotion.outcome_id,
                "outcome_status": promotion.status.value,
                "outcome_receipt_digest": promotion.receipt_digest,
                "promoted_memory_id": promotion.memory_id,
                "promoted_event_hash": promotion.event_hash,
            }
        )

    action_receipts = [item["provider_receipt"] for item in target_lineage]
    all_receipts = [state["source"]["provider_receipt"]]
    for item in target_lineage:
        all_receipts.append(item["target_attestation_receipt"])
        all_receipts.extend(item["diagnostic_receipts"])
        all_receipts.append(item["provider_receipt"])
    relationships = {item["relationship"]: item for item in target_lineage}
    same = relationships.get("same-cause-transfer", {})
    neighbor = relationships.get("near-neighbor-rejection", {})
    source_memory_id = state["source"]["memory_id"]
    database_rows_joined = True
    with connect() as connection:
        for item in target_lineage:
            joined = connection.execute(
                """
                SELECT count(*)
                FROM agent_runs AS r
                JOIN proposed_actions AS p
                    ON p.run_id = r.run_id
                    AND p.tenant_id = r.tenant_id
                    AND p.incident_id = r.incident_id
                JOIN outcome_evidence AS o
                    ON o.proposal_id = p.proposal_id
                    AND o.run_id = r.run_id
                JOIN canonical_memories AS cm
                    ON cm.tenant_id = r.tenant_id
                    AND cm.incident_id = r.incident_id
                    AND cm.payload->>'proposal_id' = p.proposal_id::STRING
                    AND cm.payload->>'receipt_digest' = o.receipt_digest
                WHERE r.run_id = %s AND p.proposal_id = %s
                    AND o.outcome_id = %s AND cm.memory_id = %s
                    AND cm.embedding_model = %s
                """,
                (
                    item["run_id"],
                    item["proposal_id"],
                    item["outcome_id"],
                    item["promoted_memory_id"],
                    state["embedding_model"],
                ),
            ).fetchone()[0]
            citation_lineage = 0
            for retrieval_id in item["admission_receipt"]["retrieval_ids"]:
                citation_lineage += connection.execute(
                    """
                    SELECT count(*)
                    FROM retrieval_audit AS a
                    JOIN retrieved_citations AS c
                        ON c.retrieval_id = a.retrieval_id
                        AND c.tenant_id = a.tenant_id
                        AND c.incident_id = a.incident_id
                    WHERE a.retrieval_id = %s AND c.run_id = %s
                        AND c.memory_id = %s
                        AND %s::UUID = ANY(a.accepted_memory_ids)
                    """,
                    (
                        retrieval_id,
                        item["run_id"],
                        source_memory_id,
                        source_memory_id,
                    ),
                ).fetchone()[0]
            database_rows_joined = (
                database_rows_joined
                and joined == 1
                and citation_lineage
                == len(item["admission_receipt"]["retrieval_ids"])
            )
    gate = {
        "exact_source_head": all(
            receipt.get("head_sha") == state["source_head"]
            for receipt in all_receipts
        ),
        "provider_actions_follow_durable_proposals": all(
            _parse_time(receipt["created_at"]) >= prepared_at
            for receipt in action_receipts
        ),
        "provider_receipts_unique": len(
            {receipt["workflow_run_id"] for receipt in all_receipts}
        )
        == len(all_receipts),
        "source_provider_outcome_canonical_and_indexed": bool(
            source_memory_id and state["source"]["receipt_digest"]
            and state["source"]["embedding_model"] == state["embedding_model"]
        ),
        "same_cause_memory_selected": source_memory_id
        in same.get("selected_memory_ids", []),
        "same_cause_zero_diagnostics": len(same.get("diagnostic_receipts", [])) == 0,
        "near_neighbor_memory_not_selected": source_memory_id
        not in neighbor.get("selected_memory_ids", []),
        "near_neighbor_current_diagnostic_used": len(
            neighbor.get("diagnostic_receipts", [])
        )
        == 1,
        "both_exact_patches_proposed": all(
            item["proposed_patch_id"] == item["expected_patch_id"]
            for item in target_lineage
        ),
        "both_provider_outcomes_succeeded": all(
            item["outcome_status"] == "succeeded" for item in target_lineage
        ),
        "both_verified_outcomes_promoted": all(
            item["promoted_memory_id"] is not None for item in target_lineage
        ),
        "retrieval_audit_ids_present": all(
            item["admission_receipt"]["retrieval_ids"] for item in target_lineage
        ),
        "database_episode_rows_joined": database_rows_joined,
        "scope_role_is_expected": str(state["identity"]["current_user"]).startswith(
            "continuum_scope_"
        ),
        "cross_scope_rows_zero": (
            state["isolation"]["forbidden_memory_visible"] is False
            and state["isolation"]["all_visible_rows_in_scope"] is True
            and state["isolation"]["all_visible_incidents_in_scope"] is True
            and state["isolation"]["all_visible_audits_in_scope"] is True
        ),
        "repository_mutations_zero": all(
            receipt.get("repository_mutation") is False for receipt in all_receipts
        ),
        "cleanup_residuals_zero": all(
            receipt.get("cleanup_residual_count") == 0 for receipt in all_receipts
        ),
        "reconciliation_lineage_bound": (
            not cross_head_resume
            or (
                reconciliation_input.get("provider_action_dispatch_capability")
                is False
                and reconciliation_input.get("actions_permission") == "read"
                and args.predecessor_workflow_run_id > 0
                and args.reconciliation_workflow_run_id > 0
            )
        ),
        "provider_action_reexecutions_zero": (
            not cross_head_resume
            or reconciliation_input.get("provider_action_dispatch_capability")
            is False
        ),
    }
    gate["status"] = "PASS" if all(gate.values()) else "FAIL"
    report_body = {
        "schema_version": 1,
        "kind": "continuum.online-memory-lineage.report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_head": state["source_head"],
        "deployment_artifact_sha256": state["deployment_artifact_sha256"],
        "repository": state["repository"],
        "campaign_id": state["campaign_id"],
        "migration_version": state["migration_version"],
        "embedding_model": state["embedding_model"],
        "agent_model": state["agent_model"],
        "agent_region": state["agent_region"],
        "reconciliation": {
            "mode": "cross-head-resume" if cross_head_resume else "same-head",
            "candidate_source_head": candidate_head,
            "candidate_deployment_artifact_sha256": state[
                "deployment_artifact_sha256"
            ],
            "reconciler_source_head": reconciler_head,
            "reconciler_deployment_artifact_sha256": reconciler_artifact,
            "predecessor_workflow_run_id": (
                args.predecessor_workflow_run_id or None
            ),
            "reconciliation_workflow_run_id": (
                args.reconciliation_workflow_run_id or None
            ),
            "reconciliation_workflow_run_attempt": (
                args.reconciliation_workflow_run_attempt or None
            ),
            "provider_action_reexecutions": 0,
            "input_receipt_sha256": (
                _sha256_file(args.reconciliation_input)
                if args.reconciliation_input is not None
                else None
            ),
        },
        "methodology": {
            "architectural_pairs": 1,
            "target_cases": 2,
            "same_cause_cases": 1,
            "near_neighbor_cases": 1,
            "candidate_visible_label_fields": 0,
            "real_external_provider": True,
            "provider": "github-actions",
            "lineage_provider_receipts": len(all_receipts),
            "database": "cockroachdb-cloud",
            "retrieval": "titan-v2-vector-search-through-non-bypass-rls-role",
            "claim_design": "end-to-end architectural closure, not a powered benchmark",
        },
        "identity": state["identity"],
        "isolation": state["isolation"],
        "rls": state["rls"],
        "source": state["source"],
        "targets": target_lineage,
        "gate": gate,
        "claim_boundary": (
            (
                "This candidate/reconciler-bound recovery reuses the exact two "
                "provider action receipts without redispatch after an evaluator "
                "failure. "
            )
            if cross_head_resume
            else "This exact-head run "
        )
        + (
            "proves one preregistered source family across one same-cause and one "
            "near-neighbor target. It closes provider receipt, canonical CockroachDB "
            "promotion, Titan vector retrieval, non-bypass RLS, server admission, "
            "durable proposal, later provider action, verified outcome, and next "
            "promotion. It is an architectural proof, not a new population-level "
            "superiority estimate."
        ),
    }
    report = {
        **report_body,
        "receipt_sha256": hashlib.sha256(canonical_json_bytes(report_body)).hexdigest(),
    }
    _write(args.output, report)
    if gate["status"] != "PASS":
        raise RuntimeError("online memory-lineage gate failed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "finalize"))
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--embedding-region", default="ap-northeast-2")
    parser.add_argument("--agent-region", default="ap-southeast-2")
    parser.add_argument("--agent-model", default="amazon.nova-micro-v1:0")
    parser.add_argument("--migrator-secret-id", required=True)
    parser.add_argument("--runtime-secret-id")
    parser.add_argument("--ca-cert", required=True)
    parser.add_argument("--source-head", default="")
    parser.add_argument("--deployment-artifact-sha256", default="")
    parser.add_argument("--provider-preparation", type=Path)
    parser.add_argument("--proposals", type=Path)
    parser.add_argument("--provider-outcomes", type=Path)
    parser.add_argument("--reconciler-source-head", default="")
    parser.add_argument("--reconciler-deployment-artifact-sha256", default="")
    parser.add_argument("--predecessor-workflow-run-id", type=int, default=0)
    parser.add_argument("--reconciliation-workflow-run-id", type=int, default=0)
    parser.add_argument("--reconciliation-workflow-run-attempt", type=int, default=0)
    parser.add_argument("--reconciliation-input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        if (
            not args.provider_preparation
            or not args.source_head
            or not args.runtime_secret_id
        ):
            parser.error(
                "prepare requires provider preparation, source head, and runtime secret"
            )
        prepare(args)
    else:
        if not args.proposals or not args.provider_outcomes:
            parser.error("finalize requires proposals and provider outcomes")
        finalize(args)


if __name__ == "__main__":
    main()
