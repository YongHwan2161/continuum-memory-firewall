"""Redacted, read-only evidence for the scoped vector retrieval plan."""

from __future__ import annotations

from collections.abc import Sequence
import hashlib
from typing import Any, Callable

from continuum.retrieval import EMBEDDING_DIMENSIONS, vector_literal


EXPECTED_VECTOR_INDEX = "canonical_memories_embedding_idx"
EXPECTED_PREFIX_COLUMNS = ("tenant_id", "incident_id", "embedding")


def collect_query_plan_evidence(
    connect: Callable[[], Any],
    *,
    tenant_id: str,
    incident_id: str,
    embedding_model: str,
    query_vector: Sequence[float],
) -> dict[str, Any]:
    """Inspect index metadata and a redacted plan through the runtime login."""

    encoded_vector = vector_literal(
        query_vector,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    with connect() as connection:
        current_user = connection.execute("SELECT current_user").fetchone()[0]
        index_rows = connection.execute(
            """
            SELECT column_name, seq_in_index, direction, visible, implicit
            FROM [SHOW INDEXES FROM canonical_memories]
            WHERE index_name = %s
            ORDER BY seq_in_index
            """,
            (EXPECTED_VECTOR_INDEX,),
        ).fetchall()
        plan_rows = connection.execute(
            """
            EXPLAIN (REDACT)
            SELECT memory_id::STRING
            FROM canonical_memories
            WHERE tenant_id = %s
              AND incident_id = %s
              AND embedding IS NOT NULL
              AND embedding_model = %s
            ORDER BY embedding <=> %s::VECTOR
            LIMIT 5
            """,
            (tenant_id, incident_id, embedding_model, encoded_vector),
        ).fetchall()
    plan = "\n".join(str(row[0]) for row in plan_rows)
    declared_rows = [row for row in index_rows if not bool(row[4])]
    columns = tuple(str(row[0]) for row in declared_rows)
    visible = bool(index_rows) and all(bool(row[3]) for row in index_rows)
    directions = tuple(str(row[2]) for row in declared_rows)
    result = {
        "current_user": str(current_user),
        "expected_index": EXPECTED_VECTOR_INDEX,
        "index_present": bool(index_rows),
        "index_visible": visible,
        "index_columns": list(columns),
        "index_directions": list(directions),
        "implicit_column_count": len(index_rows) - len(declared_rows),
        "prefix_columns_match": columns == EXPECTED_PREFIX_COLUMNS,
        "plan_uses_expected_index": EXPECTED_VECTOR_INDEX in plan,
        "plan_reports_full_scan": "FULL SCAN" in plan.upper(),
        "plan_line_count": len(plan_rows),
        "redacted_plan_sha256": hashlib.sha256(plan.encode("utf-8")).hexdigest(),
    }
    if not (
        result["index_present"]
        and result["index_visible"]
        and result["prefix_columns_match"]
    ):
        raise RuntimeError("scoped vector index metadata does not match the contract")
    return result
