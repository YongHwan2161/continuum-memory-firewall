"""Bounded concurrent-agent pressure proof over synthetic CockroachDB data.

The workload models 70% vector retrieval, 20% trusted memory promotion, and
10% idempotent action claims. It owns a run-specific tenant, reuses only the
non-sensitive 50k vector benchmark table for reads, and removes all application
rows it creates before returning a PASS report.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from threading import Barrier, Lock
import time
from typing import Any, Callable, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import NAMESPACE_URL, uuid4, uuid5

from continuum.scale_benchmark import (
    ALLOWED_INCIDENT,
    ALLOWED_TENANT,
    MODEL_NAME,
    TABLE_NAME,
    synthetic_vector,
    vector_literal,
)
from continuum.store import CockroachMemoryStore, PsycopgConnectionPool


DEFAULT_CONCURRENCY = (10, 25, 50)
OPERATIONS_PER_AGENT = 10
VECTOR_READS_PER_AGENT = 7
PROMOTIONS_PER_AGENT = 2
ACTION_CLAIMS_PER_AGENT = 1
MAX_POOL_SIZE = 20


def summarize_latency_ms(samples: Sequence[float]) -> dict[str, float | int]:
    if not samples:
        raise ValueError("latency samples are required")
    ordered = sorted(float(value) for value in samples)
    if not all(math.isfinite(value) and value >= 0 for value in ordered):
        raise ValueError("latencies must be finite and non-negative")

    def percentile(value: float) -> float:
        index = max(0, math.ceil(value * len(ordered)) - 1)
        return round(ordered[index], 3)

    return {
        "count": len(ordered),
        "p50": percentile(0.50),
        "p95": percentile(0.95),
        "p99": percentile(0.99),
        "max": round(ordered[-1], 3),
    }


def _pin_tls(database_url: str, ca_cert: str) -> str:
    parts = urlsplit(database_url)
    query = [
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if name not in {"sslmode", "sslrootcert"}
    ]
    query.extend((("sslmode", "verify-full"), ("sslrootcert", ca_cert)))
    return urlunsplit(parts._replace(query=urlencode(query)))


def _secret_database_url(
    *,
    region: str,
    secret_id: str,
    ca_cert: str,
    attempts: int = 12,
    delay_seconds: float = 5.0,
) -> str:
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - live-only boundary
        raise RuntimeError("boto3 is required for the live pressure proof") from exc
    client = boto3.client("secretsmanager", region_name=region)
    value = None
    for attempt in range(attempts):
        try:
            value = client.get_secret_value(SecretId=secret_id)["SecretString"]
            break
        except Exception as exc:
            response = getattr(exc, "response", {})
            code = response.get("Error", {}).get("Code")
            if code not in {"AccessDenied", "AccessDeniedException"}:
                raise
            if attempt + 1 == attempts:
                raise RuntimeError(
                    "temporary pressure secret access did not propagate"
                ) from exc
            time.sleep(delay_seconds)
    if value is None:  # pragma: no cover - bounded loop defensive guard
        raise RuntimeError("database secret is unavailable")
    payload = json.loads(value)
    if not isinstance(payload, dict) or not isinstance(payload.get("database_url"), str):
        raise RuntimeError("database secret is malformed")
    return _pin_tls(payload["database_url"], ca_cert)


@dataclass(frozen=True, slots=True)
class OperationReceipt:
    kind: str
    elapsed_ms: float
    outcome: str
    leaked_rows: int = 0


class ReceiptBook:
    def __init__(self) -> None:
        self._lock = Lock()
        self._receipts: list[OperationReceipt] = []
        self._errors: list[str] = []

    def receipt(self, value: OperationReceipt) -> None:
        with self._lock:
            self._receipts.append(value)

    def error(self, exc: BaseException) -> None:
        with self._lock:
            self._errors.append(type(exc).__name__)

    @property
    def receipts(self) -> tuple[OperationReceipt, ...]:
        return tuple(self._receipts)

    @property
    def errors(self) -> tuple[str, ...]:
        return tuple(self._errors)


def _timed(kind: str, operation: Callable[[], tuple[str, int]]) -> OperationReceipt:
    started = time.perf_counter_ns()
    outcome, leaked_rows = operation()
    return OperationReceipt(
        kind,
        (time.perf_counter_ns() - started) / 1_000_000,
        outcome,
        leaked_rows,
    )


def _vector_read(pool: PsycopgConnectionPool, target_id: int) -> tuple[str, int]:
    query_vector = vector_literal(synthetic_vector(target_id))
    with pool() as connection:
        connection.execute("SET vector_search_beam_size = 128")
        rows = connection.execute(
            f"""
            SELECT benchmark_id, tenant_id::STRING, incident_id::STRING
            FROM {TABLE_NAME}
            WHERE tenant_id = %s
              AND incident_id = %s
              AND embedding_model = %s
            ORDER BY embedding <=> %s::VECTOR
            LIMIT 5
            """,
            (ALLOWED_TENANT, ALLOWED_INCIDENT, MODEL_NAME, query_vector),
        ).fetchall()
    leaked = sum(
        str(row[1]) != ALLOWED_TENANT or str(row[2]) != ALLOWED_INCIDENT
        for row in rows
    )
    if not rows:
        raise RuntimeError("vector read returned no rows")
    return "HIT", leaked


def _promote(
    pool: PsycopgConnectionPool,
    *,
    tenant_id: str,
    incident_id: str,
    agent: int,
    ordinal: int,
    run_id: str,
) -> tuple[str, int]:
    candidate_id = str(uuid4())
    now = datetime.now(timezone.utc)
    with pool() as connection:
        head = connection.execute(
            "SELECT current_head FROM incidents WHERE incident_id = %s",
            (incident_id,),
        ).fetchone()[0]
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
                head,
                json.dumps(
                    {
                        "agent_pressure_run": run_id,
                        "agent": agent,
                        "ordinal": ordinal,
                        "synthetic": True,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                now - timedelta(milliseconds=1),
                now + timedelta(hours=1),
            ),
        )
    result = CockroachMemoryStore(pool, max_attempts=8).promote_candidate(
        candidate_id, now=now
    )
    if not result.accepted:
        raise RuntimeError(f"synthetic promotion failed: {result.decision_code.value}")
    return result.decision_code.value, 0


def _claim(
    pool: PsycopgConnectionPool,
    *,
    tenant_id: str,
    incident_id: str,
    expected_head: str,
    agent: int,
    run_id: str,
) -> tuple[str, int]:
    result = CockroachMemoryStore(pool, max_attempts=8).claim_action(
        tenant_id=tenant_id,
        incident_id=incident_id,
        expected_head=expected_head,
        action_key=f"pressure-action-{run_id}",
        action_payload={"agent_pressure_run": run_id, "synthetic": True},
        worker_id=f"agent-{agent:02d}",
    )
    return result.code.value, 0


def _create_scope(
    pool: PsycopgConnectionPool,
    *,
    tenant_id: str,
    run_id: str,
    concurrency: int,
) -> tuple[list[str], str, str]:
    agent_incidents = [
        str(uuid5(NAMESPACE_URL, f"{run_id}:{concurrency}:agent:{agent}"))
        for agent in range(concurrency)
    ]
    action_incident = str(
        uuid5(NAMESPACE_URL, f"{run_id}:{concurrency}:shared-action")
    )
    rows: list[tuple[str, str, str, str]] = []
    for agent, incident_id in enumerate(agent_incidents):
        head = hashlib.sha256(
            f"{run_id}:{concurrency}:{agent}:genesis".encode("utf-8")
        ).hexdigest()
        rows.append((incident_id, tenant_id, f"agent-pressure-{concurrency}", head))
    action_head = hashlib.sha256(
        f"{run_id}:{concurrency}:action:genesis".encode("utf-8")
    ).hexdigest()
    rows.append(
        (action_incident, tenant_id, f"agent-pressure-action-{concurrency}", action_head)
    )
    with pool() as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO incidents (
                    incident_id, tenant_id, service_name, status, current_head
                ) VALUES (%s, %s, %s, 'open', %s)
                """,
                rows,
            )
    return agent_incidents, action_incident, action_head


def _agent(
    *,
    agent: int,
    barrier: Barrier,
    book: ReceiptBook,
    pool: PsycopgConnectionPool,
    tenant_id: str,
    incident_id: str,
    action_incident: str,
    action_head: str,
    run_id: str,
) -> None:
    try:
        barrier.wait(timeout=30)
        for ordinal in range(VECTOR_READS_PER_AGENT):
            target = 1 + ((agent * VECTOR_READS_PER_AGENT + ordinal) * 37) % 49_999
            if target % 10 == 0:
                target += 1
            book.receipt(_timed("vector_read", lambda target=target: _vector_read(pool, target)))
        for ordinal in range(PROMOTIONS_PER_AGENT):
            book.receipt(
                _timed(
                    "promotion",
                    lambda ordinal=ordinal: _promote(
                        pool,
                        tenant_id=tenant_id,
                        incident_id=incident_id,
                        agent=agent,
                        ordinal=ordinal,
                        run_id=run_id,
                    ),
                )
            )
        for _ in range(ACTION_CLAIMS_PER_AGENT):
            book.receipt(
                _timed(
                    "action_claim",
                    lambda: _claim(
                        pool,
                        tenant_id=tenant_id,
                        incident_id=action_incident,
                        expected_head=action_head,
                        agent=agent,
                        run_id=run_id,
                    ),
                )
            )
    except BaseException as exc:  # collect every worker failure for a fail-closed gate
        book.error(exc)


def _run_level(
    pool: PsycopgConnectionPool,
    *,
    concurrency: int,
    tenant_id: str,
    run_id: str,
) -> dict[str, Any]:
    incidents, action_incident, action_head = _create_scope(
        pool,
        tenant_id=tenant_id,
        run_id=run_id,
        concurrency=concurrency,
    )
    barrier = Barrier(concurrency)
    book = ReceiptBook()
    started = time.perf_counter_ns()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(
                _agent,
                agent=agent,
                barrier=barrier,
                book=book,
                pool=pool,
                tenant_id=tenant_id,
                incident_id=incidents[agent],
                action_incident=action_incident,
                action_head=action_head,
                run_id=f"{run_id}-{concurrency}",
            )
            for agent in range(concurrency)
        ]
        for future in as_completed(futures):
            future.result()
    elapsed_seconds = (time.perf_counter_ns() - started) / 1_000_000_000
    receipts = book.receipts
    by_kind: dict[str, list[OperationReceipt]] = defaultdict(list)
    for receipt in receipts:
        by_kind[receipt.kind].append(receipt)
    outcomes = Counter(receipt.outcome for receipt in receipts)
    with pool() as connection:
        durable_claims = int(
            connection.execute(
                """
                SELECT count(*) FROM action_attempts
                WHERE tenant_id = %s AND incident_id = %s
                  AND action_payload->>'agent_pressure_run' = %s
                """,
                (tenant_id, action_incident, f"{run_id}-{concurrency}"),
            ).fetchone()[0]
        )
    expected_operations = concurrency * OPERATIONS_PER_AGENT
    return {
        "concurrent_agents": concurrency,
        "operations": len(receipts),
        "expected_operations": expected_operations,
        "mix": {"vector_read": "70%", "promotion": "20%", "action_claim": "10%"},
        "elapsed_seconds": round(elapsed_seconds, 3),
        "throughput_ops_per_second": round(len(receipts) / elapsed_seconds, 3),
        "latency_ms": summarize_latency_ms([item.elapsed_ms for item in receipts]),
        "latency_by_operation_ms": {
            kind: summarize_latency_ms([item.elapsed_ms for item in values])
            for kind, values in sorted(by_kind.items())
        },
        "outcomes": dict(sorted(outcomes.items())),
        "worker_errors": list(book.errors),
        "cross_scope_leaked_rows": sum(item.leaked_rows for item in receipts),
        "durable_action_claims": durable_claims,
        "gate": (
            "PASS"
            if len(receipts) == expected_operations
            and not book.errors
            and sum(item.leaked_rows for item in receipts) == 0
            and outcomes["HIT"] == concurrency * VECTOR_READS_PER_AGENT
            and outcomes["ACCEPTED"] == concurrency * PROMOTIONS_PER_AGENT
            and outcomes["CLAIMED"] == 1
            and outcomes["DUPLICATE"] == concurrency - 1
            and durable_claims == 1
            else "HOLD"
        ),
    }


def _cleanup(pool: PsycopgConnectionPool, tenant_id: str) -> int:
    with pool() as connection:
        for table in (
            "retrieval_audit",
            "action_attempts",
            "canonical_memories",
            "memory_candidates",
        ):
            connection.execute(f"DELETE FROM {table} WHERE tenant_id = %s", (tenant_id,))
        connection.execute("DELETE FROM incidents WHERE tenant_id = %s", (tenant_id,))
        remaining = connection.execute(
            "SELECT count(*) FROM incidents WHERE tenant_id = %s", (tenant_id,)
        ).fetchone()[0]
    return int(remaining)


def run_pressure(
    database_url: str,
    *,
    source_head: str,
    concurrency_levels: Sequence[int] = DEFAULT_CONCURRENCY,
    pool_factory: Callable[..., PsycopgConnectionPool] = PsycopgConnectionPool,
) -> dict[str, Any]:
    if tuple(concurrency_levels) != DEFAULT_CONCURRENCY:
        raise ValueError("the public proof requires exactly 10, 25, and 50 agents")
    run_id = uuid4().hex[:12]
    tenant_id = str(uuid5(NAMESPACE_URL, f"continuum-agent-pressure:{run_id}"))
    pool = pool_factory(
        database_url,
        min_size=1,
        max_size=MAX_POOL_SIZE,
        timeout_seconds=15,
    )
    levels: list[dict[str, Any]] = []
    recoveries: list[dict[str, Any]] = []
    cleanup_remaining = -1
    try:
        with pool() as connection:
            table = connection.execute(
                f"SELECT count(*), count(*) FILTER (WHERE synthetic) FROM {TABLE_NAME}"
            ).fetchone()
        if tuple(map(int, table)) != (50_000, 50_000):
            raise RuntimeError("the retained 50k synthetic vector corpus is unavailable")
        for concurrency in concurrency_levels:
            levels.append(
                _run_level(
                    pool,
                    concurrency=concurrency,
                    tenant_id=tenant_id,
                    run_id=run_id,
                )
            )
            pool_metrics = pool.metrics()
            pool.close()
            pool = pool_factory(
                database_url,
                min_size=1,
                max_size=MAX_POOL_SIZE,
                timeout_seconds=15,
            )
            started = time.perf_counter_ns()
            outcome, leaked = _vector_read(pool, concurrency * 101)
            recovery_ms = (time.perf_counter_ns() - started) / 1_000_000
            recoveries.append(
                {
                    "after_concurrent_agents": concurrency,
                    "injected_fault": "client_connection_pool_teardown",
                    "recovery_outcome": outcome,
                    "time_to_first_success_ms": round(recovery_ms, 3),
                    "cross_scope_leaked_rows": leaked,
                    "prior_pool_metrics": pool_metrics,
                    "gate": "PASS" if outcome == "HIT" and leaked == 0 else "HOLD",
                }
            )
    finally:
        try:
            cleanup_remaining = _cleanup(pool, tenant_id)
        finally:
            pool.close()

    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_head": source_head,
        "run_fingerprint": hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:16],
        "claim_boundary": (
            "Actual CockroachDB concurrency over a retained non-sensitive 50k vector "
            "table plus run-owned synthetic application rows. Recovery is a deliberate "
            "client-pool teardown, not a CockroachDB node-failover claim."
        ),
        "database": {
            "vector_rows": 50_000,
            "vector_table": TABLE_NAME,
            "application_rows_retained": cleanup_remaining,
            "bounded_connection_pool_max": MAX_POOL_SIZE,
        },
        "levels": levels,
        "recoveries": recoveries,
        "gate": {
            "status": "PASS",
            "all_operations_completed": all(item["gate"] == "PASS" for item in levels),
            "exactly_one_action_owner_per_level": all(
                item["durable_action_claims"] == 1 for item in levels
            ),
            "cross_scope_leakage_zero": all(
                item["cross_scope_leaked_rows"] == 0 for item in levels
            ),
            "pool_recovery_passed": all(item["gate"] == "PASS" for item in recoveries),
            "synthetic_rows_cleaned": cleanup_remaining == 0,
        },
    }
    if not all(value is True for key, value in report["gate"].items() if key != "status"):
        report["gate"]["status"] = "HOLD"
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--secret-id", required=True)
    parser.add_argument("--ca-cert", default="/opt/continuum/cockroach-ca.crt")
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = run_pressure(
        _secret_database_url(
            region=args.region,
            secret_id=args.secret_id,
            ca_cert=args.ca_cert,
        ),
        source_head=args.source_head,
    )
    Path(args.output).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True))
    if report["gate"]["status"] != "PASS":
        raise SystemExit("agent pressure gate failed")


if __name__ == "__main__":
    main()
