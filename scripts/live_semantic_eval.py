"""Seed synthetic semantic memories and measure live Recall@K plus RLS leakage."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from uuid import uuid4

import boto3

from continuum.evaluation import assert_competition_gate, load_dataset
from continuum.migrate import Migrator
from continuum.retrieval import BedrockTitanEmbedder, MemoryRetrievalStore
from continuum.scope_roles import verify_scope_role
from continuum.store import (
    CockroachMemoryStore,
    pin_database_tls_root,
    psycopg_connection_factory,
)


INITIAL_HEAD = "0" * 64


def _database_url(client: object, secret_id: str) -> tuple[str, dict[str, object] | None]:
    value = client.get_secret_value(SecretId=secret_id)["SecretString"]
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return value, None
    if not isinstance(payload, dict) or not isinstance(payload.get("database_url"), str):
        raise RuntimeError("database secret is malformed")
    return payload["database_url"], payload


def _ensure_denied_incident(connect: object) -> tuple[str, str]:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT tenant_id::STRING, incident_id::STRING
            FROM incidents
            WHERE service_name = 'continuum-eval-denied'
            ORDER BY created_at
            LIMIT 1
            """
        ).fetchone()
        if row:
            return row[0], row[1]
        tenant_id, incident_id = str(uuid4()), str(uuid4())
        connection.execute(
            """
            INSERT INTO incidents (
                incident_id, tenant_id, service_name, status, current_head
            ) VALUES (%s, %s, 'continuum-eval-denied', 'open', %s)
            """,
            (incident_id, tenant_id, INITIAL_HEAD),
        )
        return tenant_id, incident_id


def _seed_document(
    *,
    connect: object,
    tenant_id: str,
    incident_id: str,
    evaluation_id: str,
    text: str,
    embedder: BedrockTitanEmbedder,
) -> str:
    with connect() as connection:
        existing = connection.execute(
            """
            SELECT memory_id::STRING
            FROM canonical_memories
            WHERE tenant_id = %s AND incident_id = %s
              AND payload->>'evaluation_id' = %s
            """,
            (tenant_id, incident_id, evaluation_id),
        ).fetchone()
        if existing:
            memory_id = existing[0]
        else:
            current_head = connection.execute(
                "SELECT current_head FROM incidents WHERE incident_id = %s",
                (incident_id,),
            ).fetchone()[0]
            candidate_id = str(uuid4())
            now = datetime.now(timezone.utc)
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
                    json.dumps(
                        {
                            "evaluation_id": evaluation_id,
                            "summary": text,
                            "synthetic": True,
                            "title": evaluation_id.replace("-", " ").title(),
                        },
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    now - timedelta(seconds=1),
                    now + timedelta(minutes=20),
                ),
            )
    if not existing:
        memory_id = CockroachMemoryStore(connect).promote_candidate(
            candidate_id, now=now
        ).memory_id
    assert memory_id is not None
    MemoryRetrievalStore(connect).index_memory(
        tenant_id=tenant_id,
        incident_id=incident_id,
        memory_id=memory_id,
        embedder=embedder,
    )
    return memory_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-secret-id", required=True)
    parser.add_argument("--migrator-secret-id", required=True)
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/semantic-retrieval-v1.json"),
    )
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--minimum-recall", type=float, default=0.75)
    parser.add_argument(
        "--ca-cert",
        default="/opt/continuum/cockroach-ca.crt",
    )
    parser.add_argument(
        "--state-output",
        type=Path,
        help=(
            "Write ephemeral cross-scope smoke state to a mode-0600 file. "
            "The state is intentionally excluded from stdout evidence."
        ),
    )
    args = parser.parse_args()

    secret_client = boto3.client("secretsmanager", region_name=args.region)
    migrator_url, _ = _database_url(secret_client, args.migrator_secret_id)
    runtime_url, runtime_payload = _database_url(secret_client, args.runtime_secret_id)
    migrator_url = pin_database_tls_root(migrator_url, args.ca_cert)
    runtime_url = pin_database_tls_root(runtime_url, args.ca_cert)
    if runtime_payload is None:
        raise RuntimeError("runtime secret must be a JSON object")
    caller_scopes = runtime_payload.get("caller_scopes")
    if not isinstance(caller_scopes, dict) or len(caller_scopes) != 1:
        raise RuntimeError("evaluation requires exactly one demo caller")
    scope = next(iter(caller_scopes.values()))
    if not isinstance(scope, dict):
        raise RuntimeError("runtime caller scope is malformed")
    allowed_tenant = str(scope["tenant_id"])
    allowed_incident = str(scope["incident_id"])

    migrator_connect = psycopg_connection_factory(migrator_url)
    Migrator(migrator_connect).migrate()
    embedder = BedrockTitanEmbedder(region=args.region)
    documents, queries = load_dataset(args.dataset)
    denied_tenant, denied_incident = _ensure_denied_incident(migrator_connect)
    memory_ids: dict[str, str] = {}
    for document in documents:
        if document.tenant_id == "tenant-demo":
            tenant_id, incident_id = allowed_tenant, allowed_incident
        else:
            tenant_id, incident_id = denied_tenant, denied_incident
        memory_ids[document.document_id] = _seed_document(
            connect=migrator_connect,
            tenant_id=tenant_id,
            incident_id=incident_id,
            evaluation_id=document.document_id,
            text=document.text,
            embedder=embedder,
        )

    runtime_store = MemoryRetrievalStore(psycopg_connection_factory(runtime_url))
    query_reports: list[dict[str, object]] = []
    total_recall = 0.0
    leaked = 0
    denied_ids = {
        memory_ids[document.document_id]
        for document in documents
        if document.tenant_id != "tenant-demo"
    }
    for query in queries:
        result = runtime_store.search(
            tenant_id=allowed_tenant,
            incident_id=allowed_incident,
            query=query.text,
            embedder=embedder,
            limit=args.k,
            min_similarity=-1.0,
        )
        returned = [hit.memory_id for hit in result.hits]
        relevant = {memory_ids[item] for item in query.relevant_document_ids}
        recall = len(relevant.intersection(returned)) / len(relevant)
        query_leaks = denied_ids.intersection(returned)
        total_recall += recall
        leaked += len(query_leaks)
        query_reports.append(
            {
                "query_id": query.query_id,
                "recall_at_k": recall,
                "returned_count": len(returned),
                "cross_scope_leak_count": len(query_leaks),
            }
        )

    report = {
        "model": embedder.model_id,
        "dimensions": embedder.dimensions,
        "k": args.k,
        "query_count": len(queries),
        "mean_recall_at_k": total_recall / len(queries),
        "cross_scope_leaked_documents": leaked,
        "cross_scope_leakage_rate": 0.0 if leaked == 0 else leaked / len(queries),
        "queries": query_reports,
    }
    assert_competition_gate(report, minimum_recall=args.minimum_recall)
    rls = verify_scope_role(
        runtime_url,
        tenant_id=allowed_tenant,
        incident_id=allowed_incident,
        forbidden_memory_id=next(iter(denied_ids)),
    )
    report["database_row_isolation"] = {
        "all_visible_rows_in_scope": rls["all_visible_rows_in_scope"],
        "forbidden_memory_visible": rls["forbidden_memory_visible"],
        "negative_checks": rls["denied"],
    }
    if args.state_output is not None:
        args.state_output.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            args.state_output,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                {"forbidden_memory_id": next(iter(denied_ids))},
                handle,
                sort_keys=True,
            )
            handle.write("\n")
        os.chmod(args.state_output, 0o600)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
