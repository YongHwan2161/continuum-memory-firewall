"""Reproducible, non-sensitive CockroachDB vector scale benchmark.

The benchmark owns one clearly named synthetic table. It never reads or writes
application memory rows. At 10k and 50k rows it compares natural ANN results to
an exact primary-index scan, records first-pass and immediate-repeat latency,
and verifies that the optimizer selected the expected prefixed vector index.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


DIMENSIONS = 512
TABLE_NAME = "continuum_vector_benchmark"
INDEX_NAME = "continuum_vector_benchmark_embedding_idx"
MODEL_NAME = "continuum-synthetic-xorshift32-v1/512"
INDEX_PREFIX_COLUMNS = ("tenant_id", "incident_id", "embedding_model")
ALLOWED_TENANT = "018f4ab7-419d-7c7d-8000-000000000001"
ALLOWED_INCIDENT = "018f4ab7-419d-7c7d-8000-000000000002"
FOREIGN_TENANT = "018f4ab7-419d-7c7d-8000-000000000003"
FOREIGN_INCIDENT = "018f4ab7-419d-7c7d-8000-000000000004"
DEFAULT_SCALES = (10_000, 50_000)
DEFAULT_BEAMS = (1, 4, 16, 32)
DEFAULT_CUTOFFS = (1, 5, 10)


def synthetic_vector(row_id: int, *, dimensions: int = DIMENSIONS) -> tuple[float, ...]:
    """Generate a stable dense unit vector without external data or API calls."""

    if row_id < 1:
        raise ValueError("row_id must be positive")
    if dimensions < 2:
        raise ValueError("dimensions must be at least two")
    state = (row_id ^ 0xA5A5_5A5A) & 0xFFFF_FFFF
    values: list[float] = []
    for _ in range(dimensions):
        state ^= (state << 13) & 0xFFFF_FFFF
        state ^= state >> 17
        state ^= (state << 5) & 0xFFFF_FFFF
        state &= 0xFFFF_FFFF
        values.append(((state / 0xFFFF_FFFF) * 2.0) - 1.0)
    norm = math.sqrt(sum(value * value for value in values))
    return tuple(value / norm for value in values)


def vector_literal(values: Sequence[float]) -> str:
    if len(values) != DIMENSIONS:
        raise ValueError(f"expected {DIMENSIONS} dimensions")
    encoded: list[str] = []
    for value in values:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("vector values must be finite")
        encoded.append(format(number, ".8g"))
    return "[" + ",".join(encoded) + "]"


def summarize_latency_ms(samples: Sequence[float]) -> dict[str, float | int]:
    if not samples:
        raise ValueError("latency samples are required")
    ordered = sorted(float(sample) for sample in samples)

    def nearest_rank(percentile: float) -> float:
        return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]

    return {
        "count": len(ordered),
        "p50": round(nearest_rank(0.50), 3),
        "p95": round(nearest_rank(0.95), 3),
        "max": round(ordered[-1], 3),
    }


def target_row_ids(row_count: int, query_count: int) -> tuple[int, ...]:
    """Choose stable, evenly spaced rows from the allowed 90% partition."""

    if row_count < 100 or query_count < 2 or query_count >= row_count:
        raise ValueError("row_count/query_count combination is not benchmarkable")
    selected: list[int] = []
    for index in range(1, query_count + 1):
        candidate = (index * row_count) // (query_count + 1)
        candidate = max(1, candidate)
        while candidate % 10 == 0 or candidate in selected:
            candidate += 1
        selected.append(candidate)
    return tuple(selected)


def pin_database_tls_root(database_url: str, ca_cert_path: str) -> str:
    if not database_url:
        raise ValueError("database URL is required")
    if not ca_cert_path.startswith("/"):
        raise ValueError("CA path must be absolute")
    parts = urlsplit(database_url)
    query = [
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if name not in {"sslmode", "sslrootcert"}
    ]
    query.extend((("sslmode", "verify-full"), ("sslrootcert", ca_cert_path)))
    return urlunsplit(parts._replace(query=urlencode(query)))


def _scope_for(row_id: int) -> tuple[str, str]:
    if row_id % 10 == 0:
        return FOREIGN_TENANT, FOREIGN_INCIDENT
    return ALLOWED_TENANT, ALLOWED_INCIDENT


def _rows(start: int, end: int) -> Iterable[tuple[object, ...]]:
    for row_id in range(start, end + 1):
        tenant_id, incident_id = _scope_for(row_id)
        yield (
            row_id,
            tenant_id,
            incident_id,
            vector_literal(synthetic_vector(row_id)),
            MODEL_NAME,
        )


def _recreate_table(connection: Any) -> None:
    connection.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
    connection.execute(
        f"""
        CREATE TABLE {TABLE_NAME} (
            benchmark_id INT8 PRIMARY KEY,
            tenant_id UUID NOT NULL,
            incident_id UUID NOT NULL,
            embedding VECTOR({DIMENSIONS}) NOT NULL,
            embedding_model STRING NOT NULL,
            synthetic BOOL NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CHECK (synthetic)
        )
        """
    )


def _copy_rows(connection: Any, start: int, end: int) -> float:
    started = time.perf_counter_ns()
    with connection.cursor() as cursor:
        with cursor.copy(
            f"COPY {TABLE_NAME} "
            "(benchmark_id, tenant_id, incident_id, embedding, embedding_model) "
            "FROM STDIN"
        ) as copy:
            for row in _rows(start, end):
                copy.write_row(row)
    return (time.perf_counter_ns() - started) / 1_000_000_000


def _create_index(connection: Any) -> float:
    started = time.perf_counter_ns()
    connection.execute("SET sql_safe_updates = false")
    connection.execute(
        f"""
        CREATE VECTOR INDEX {INDEX_NAME}
        ON {TABLE_NAME}
        (tenant_id, incident_id, embedding_model, embedding vector_cosine_ops)
        WITH (min_partition_size=16, max_partition_size=128)
        """
    )
    connection.execute(f"ANALYZE {TABLE_NAME}")
    return (time.perf_counter_ns() - started) / 1_000_000_000


def _drop_index(connection: Any) -> None:
    connection.execute(f"DROP INDEX IF EXISTS {TABLE_NAME}@{INDEX_NAME}")


def _query(connection: Any, query_vector: str, *, limit: int, exact: bool) -> list[int]:
    table = f"{TABLE_NAME}@primary" if exact else TABLE_NAME
    rows = connection.execute(
        f"""
        SELECT benchmark_id
        FROM {table}
        WHERE tenant_id = %s
          AND incident_id = %s
          AND embedding_model = %s
        ORDER BY embedding <=> %s::VECTOR
        LIMIT %s
        """,
        (ALLOWED_TENANT, ALLOWED_INCIDENT, MODEL_NAME, query_vector, limit),
    ).fetchall()
    return [int(row[0]) for row in rows]


def _redacted_plan(connection: Any, query_vector: str, *, limit: int) -> dict[str, Any]:
    rows = connection.execute(
        f"""
        EXPLAIN (REDACT)
        SELECT benchmark_id
        FROM {TABLE_NAME}
        WHERE tenant_id = %s
          AND incident_id = %s
          AND embedding_model = %s
        ORDER BY embedding <=> %s::VECTOR
        LIMIT %s
        """,
        (ALLOWED_TENANT, ALLOWED_INCIDENT, MODEL_NAME, query_vector, limit),
    ).fetchall()
    plan = "\n".join(str(row[0]) for row in rows)
    return {
        "expected_index": INDEX_NAME,
        "index_name_rendered": INDEX_NAME in plan,
        "reports_vector_search": "vector search" in plan.casefold(),
        "reports_full_scan": "FULL SCAN" in plan.upper(),
        "line_count": len(rows),
        "redacted_sha256": hashlib.sha256(plan.encode("utf-8")).hexdigest(),
    }


def _index_contract(connection: Any) -> dict[str, Any]:
    rows = connection.execute(
        f"""
        SELECT column_name, seq_in_index, visible, implicit
        FROM [SHOW INDEXES FROM {TABLE_NAME}]
        WHERE index_name = %s
        ORDER BY seq_in_index
        """,
        (INDEX_NAME,),
    ).fetchall()
    declared = [row for row in rows if not bool(row[3])]
    columns = [str(row[0]) for row in declared]
    return {
        "expected_index": INDEX_NAME,
        "present": bool(rows),
        "visible": bool(rows) and all(bool(row[2]) for row in rows),
        "columns": columns,
        "prefix_and_vector_match": columns
        == [*INDEX_PREFIX_COLUMNS, "embedding"],
        "implicit_column_count": len(rows) - len(declared),
    }


def _timed_query(
    connect: Any,
    query_vector: str,
    *,
    beam: int | None,
    limit: int,
    exact: bool,
) -> tuple[list[int], float]:
    started = time.perf_counter_ns()
    with connect() as connection:
        if beam is not None:
            connection.execute(f"SET vector_search_beam_size = {beam:d}")
        rows = _query(connection, query_vector, limit=limit, exact=exact)
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    return rows, elapsed_ms


def _benchmark_scale(
    connect: Any,
    *,
    row_count: int,
    query_count: int,
    beams: Sequence[int],
    cutoffs: Sequence[int],
    insert_seconds: float,
    index_build_seconds: float,
) -> dict[str, Any]:
    maximum_k = max(cutoffs)
    targets = target_row_ids(row_count, query_count)
    vectors = {row_id: vector_literal(synthetic_vector(row_id)) for row_id in targets}
    exact_results: dict[int, list[int]] = {}
    exact_latencies: list[float] = []
    for row_id, query_vector in vectors.items():
        rows, latency = _timed_query(
            connect,
            query_vector,
            beam=None,
            limit=maximum_k,
            exact=True,
        )
        exact_results[row_id] = rows
        exact_latencies.append(latency)

    with connect() as connection:
        index_contract = _index_contract(connection)

    beam_reports: list[dict[str, Any]] = []
    for beam in beams:
        recall_totals = {cutoff: 0.0 for cutoff in cutoffs}
        first_pass_latencies: list[float] = []
        warm_repeat_latencies: list[float] = []
        leaked_rows = 0
        for row_id, query_vector in vectors.items():
            started = time.perf_counter_ns()
            with connect() as connection:
                connection.execute(f"SET vector_search_beam_size = {beam:d}")
                first = _query(
                    connection,
                    query_vector,
                    limit=maximum_k,
                    exact=False,
                )
                first_pass_latencies.append(
                    (time.perf_counter_ns() - started) / 1_000_000
                )
                warm_started = time.perf_counter_ns()
                warm = _query(
                    connection,
                    query_vector,
                    limit=maximum_k,
                    exact=False,
                )
                warm_repeat_latencies.append(
                    (time.perf_counter_ns() - warm_started) / 1_000_000
                )
            expected = exact_results[row_id]
            for cutoff in cutoffs:
                denominator = max(1, len(expected[:cutoff]))
                recall_totals[cutoff] += len(
                    set(first[:cutoff]).intersection(expected[:cutoff])
                ) / denominator
            leaked_rows += sum(result % 10 == 0 for result in first)
            if warm != first:
                raise RuntimeError("immediate repeat returned a different ANN ordering")

        with connect() as connection:
            connection.execute(f"SET vector_search_beam_size = {beam:d}")
            plan = _redacted_plan(
                connection,
                next(iter(vectors.values())),
                limit=maximum_k,
            )
        beam_reports.append(
            {
                "beam_size": beam,
                "recall_by_k": {
                    str(cutoff): round(recall_totals[cutoff] / query_count, 6)
                    for cutoff in cutoffs
                },
                "cross_scope_leaked_rows": leaked_rows,
                "fresh_connection_first_pass_ms": summarize_latency_ms(
                    first_pass_latencies
                ),
                "same_connection_immediate_repeat_ms": summarize_latency_ms(
                    warm_repeat_latencies
                ),
                "query_plan": plan,
            }
        )

    return {
        "row_count": row_count,
        "allowed_scope_rows": row_count - (row_count // 10),
        "foreign_scope_rows": row_count // 10,
        "query_count": query_count,
        "insert_seconds_incremental": round(insert_seconds, 3),
        "index_build_and_analyze_seconds": round(index_build_seconds, 3),
        "exact_primary_scan_ms": summarize_latency_ms(exact_latencies),
        "index_contract": index_contract,
        "beams": beam_reports,
    }


def validate_report(report: dict[str, Any]) -> None:
    scales = report.get("scales")
    if not isinstance(scales, list) or [item.get("row_count") for item in scales] != [
        *DEFAULT_SCALES
    ]:
        raise RuntimeError("both 10k and 50k scale reports are required")
    for scale in scales:
        contract = scale["index_contract"]
        if not (
            contract["present"]
            and contract["visible"]
            and contract["prefix_and_vector_match"]
        ):
            raise RuntimeError("the synthetic vector index contract is invalid")
        for beam in scale["beams"]:
            plan = beam["query_plan"]
            if not plan["reports_vector_search"] or plan["reports_full_scan"]:
                raise RuntimeError("CockroachDB did not naturally select the ANN index")
            if beam["cross_scope_leaked_rows"] != 0:
                raise RuntimeError("synthetic prefix-scope leakage detected")
            if beam["recall_by_k"]["10"] < 0.75:
                raise RuntimeError("Recall@10 fell below the benchmark gate")


def run_benchmark(
    connect: Any,
    *,
    source_head: str,
    query_count: int = 16,
    beams: Sequence[int] = DEFAULT_BEAMS,
    cutoffs: Sequence[int] = DEFAULT_CUTOFFS,
) -> dict[str, Any]:
    if any(beam < 1 for beam in beams):
        raise ValueError("beam sizes must be positive")
    if sorted(set(cutoffs)) != list(cutoffs) or any(value < 1 for value in cutoffs):
        raise ValueError("cutoffs must be sorted unique positive integers")

    with connect() as connection:
        _recreate_table(connection)

    reports: list[dict[str, Any]] = []
    prior_scale = 0
    try:
        for scale in DEFAULT_SCALES:
            with connect() as connection:
                if prior_scale:
                    _drop_index(connection)
                insert_seconds = _copy_rows(connection, prior_scale + 1, scale)
                index_seconds = _create_index(connection)
            reports.append(
                _benchmark_scale(
                    connect,
                    row_count=scale,
                    query_count=query_count,
                    beams=beams,
                    cutoffs=cutoffs,
                    insert_seconds=insert_seconds,
                    index_build_seconds=index_seconds,
                )
            )
            prior_scale = scale
    except Exception:
        raise

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_head": source_head,
        "claim_boundary": (
            "Synthetic benchmark table only; no application memory rows were read "
            "or written. First-pass latency includes a fresh SQL connection but does "
            "not claim a server cache flush."
        ),
        "database": {
            "table": TABLE_NAME,
            "index": INDEX_NAME,
            "dimensions": DIMENSIONS,
            "model": MODEL_NAME,
            "prefix_columns": list(INDEX_PREFIX_COLUMNS),
            "retained_row_count": DEFAULT_SCALES[-1],
        },
        "cutoffs": list(cutoffs),
        "beam_sizes": list(beams),
        "scales": reports,
    }
    report["gate"] = {
        "status": "HOLD",
        "natural_ann_selected_at_all_scales": False,
        "cross_scope_leakage_zero": False,
        "minimum_recall_at_10": 0.75,
    }
    try:
        validate_report(report)
    except RuntimeError as error:
        report["gate"]["reason"] = str(error)
    else:
        report["gate"].update(
            {
                "status": "PASS",
                "natural_ann_selected_at_all_scales": True,
                "cross_scope_leakage_zero": True,
            }
        )
    return report


def _secret_string_with_retry(
    client: Any,
    secret_id: str,
    *,
    attempts: int = 12,
    delay_seconds: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    if attempts < 1 or delay_seconds < 0:
        raise ValueError("secret access retry bounds are invalid")
    for attempt in range(1, attempts + 1):
        try:
            return str(client.get_secret_value(SecretId=secret_id)["SecretString"])
        except Exception as error:
            response = getattr(error, "response", {})
            code = response.get("Error", {}).get("Code")
            if code != "AccessDeniedException" or attempt == attempts:
                raise
            sleep(delay_seconds)


def _database_url_from_secret(region: str, secret_id: str) -> str:
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - live-only dependency
        raise RuntimeError("boto3 is required for the live benchmark") from exc
    value = _secret_string_with_retry(
        boto3.client("secretsmanager", region_name=region),
        secret_id,
    )
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return str(value)
    if not isinstance(payload, dict) or not isinstance(payload.get("database_url"), str):
        raise RuntimeError("database secret is malformed")
    return payload["database_url"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--secret-id", required=True)
    parser.add_argument("--ca-cert", default="/opt/continuum/cockroach-ca.crt")
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--query-count", type=int, default=16)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - live-only dependency
        raise RuntimeError("psycopg is required for the live benchmark") from exc
    database_url = pin_database_tls_root(
        _database_url_from_secret(args.region, args.secret_id),
        args.ca_cert,
    )
    connect = lambda: psycopg.connect(database_url, autocommit=True)
    report = run_benchmark(
        connect,
        source_head=args.source_head,
        query_count=args.query_count,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    if report["gate"]["status"] != "PASS":
        raise SystemExit(str(report["gate"].get("reason", "benchmark gate failed")))


if __name__ == "__main__":
    main()
