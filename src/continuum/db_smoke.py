"""Synthetic end-to-end smoke test against a real CockroachDB connection."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from typing import Any
from uuid import uuid4

from continuum.migrate import Migrator, psycopg_connection_factory
from continuum.retrieval import HashingEmbedder, MemoryRetrievalStore
from continuum.store import CockroachMemoryStore


INITIAL_HEAD = "0" * 64


def run_smoke(
    database_url: str,
    *,
    retain: bool = False,
) -> dict[str, Any]:
    """Migrate, promote, embed, retrieve, audit, and optionally clean up."""

    connect = psycopg_connection_factory(database_url)
    migration_report = Migrator(connect).migrate()
    tenant_id = str(uuid4())
    incident_id = str(uuid4())
    candidate_id = str(uuid4())
    now = datetime.now(timezone.utc)
    store = CockroachMemoryStore(connect)
    retrieval = MemoryRetrievalStore(connect)
    embedder = HashingEmbedder()
    created = False

    try:
        with connect() as connection:
            connection.execute(
                """
                INSERT INTO incidents (
                    incident_id,
                    tenant_id,
                    service_name,
                    status,
                    current_head
                )
                VALUES (%s, %s, 'continuum-smoke', 'open', %s)
                """,
                (incident_id, tenant_id, INITIAL_HEAD),
            )
            connection.execute(
                """
                INSERT INTO memory_candidates (
                    candidate_id,
                    tenant_id,
                    incident_id,
                    parent_hash,
                    source_kind,
                    action_class,
                    payload,
                    created_at,
                    expires_at
                )
                VALUES (
                    %s, %s, %s, %s, 'tool', 'observe', %s::JSONB, %s, %s
                )
                """,
                (
                    candidate_id,
                    tenant_id,
                    incident_id,
                    INITIAL_HEAD,
                    json.dumps(
                        {
                            "kind": "migration-smoke",
                            "service": "continuum-smoke",
                            "synthetic": True,
                        }
                    ),
                    now - timedelta(seconds=1),
                    now + timedelta(minutes=10),
                ),
            )
        created = True

        promoted = store.promote_candidate(candidate_id, now=now)
        retrieval.index_memory(
            tenant_id=tenant_id,
            incident_id=incident_id,
            memory_id=promoted.memory_id,
            embedder=embedder,
            now=now,
        )
        result = retrieval.search(
            tenant_id=tenant_id,
            incident_id=incident_id,
            query="continuum migration smoke",
            embedder=embedder,
            min_similarity=-1.0,
        )
        document = retrieval.fetch_memory(
            tenant_id=tenant_id,
            incident_id=incident_id,
            memory_id=promoted.memory_id,
        )
        if [hit.memory_id for hit in result.hits] != [promoted.memory_id]:
            raise RuntimeError("smoke retrieval did not return the promoted memory")
        if document.memory_id != promoted.memory_id:
            raise RuntimeError("smoke fetch returned the wrong memory")

        return {
            "ok": True,
            "migration": migration_report.as_dict(),
            "tenant_id": tenant_id,
            "incident_id": incident_id,
            "candidate_id": candidate_id,
            "memory_id": promoted.memory_id,
            "retrieval_id": result.retrieval_id,
            "retained": retain,
        }
    finally:
        if created and not retain:
            with connect() as connection:
                connection.execute(
                    """
                    DELETE FROM retrieval_audit
                    WHERE tenant_id = %s AND incident_id = %s
                    """,
                    (tenant_id, incident_id),
                )
                connection.execute(
                    """
                    DELETE FROM action_attempts
                    WHERE tenant_id = %s AND incident_id = %s
                    """,
                    (tenant_id, incident_id),
                )
                connection.execute(
                    """
                    DELETE FROM canonical_memories
                    WHERE tenant_id = %s AND incident_id = %s
                    """,
                    (tenant_id, incident_id),
                )
                connection.execute(
                    """
                    DELETE FROM memory_candidates
                    WHERE tenant_id = %s AND incident_id = %s
                    """,
                    (tenant_id, incident_id),
                )
                connection.execute(
                    """
                    DELETE FROM incidents
                    WHERE tenant_id = %s AND incident_id = %s
                    """,
                    (tenant_id, incident_id),
                )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a synthetic Continuum CockroachDB smoke test."
    )
    parser.add_argument(
        "--retain",
        action="store_true",
        help="retain the generated synthetic rows for reviewer evidence",
    )
    args = parser.parse_args()
    database_url = os.environ.get("CONTINUUM_DATABASE_URL", "")
    if not database_url:
        parser.error("CONTINUUM_DATABASE_URL is required")
    print(
        json.dumps(
            run_smoke(database_url, retain=args.retain),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
