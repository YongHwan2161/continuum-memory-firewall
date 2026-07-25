"""Tenant-scoped vector retrieval and durable retrieval evidence.

Embedding generation is deliberately outside retryable database transactions.
CockroachDB stores the accepted embedding, performs similarity search, and
durably records which candidate results passed the retrieval policy.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import unicodedata
from typing import Any, Protocol

from continuum.store import CockroachMemoryStore, ConnectionFactory


EMBEDDING_DIMENSIONS = 512
HASH_EMBEDDING_MODEL = "continuum-hash-512-v1"
RETRIEVAL_POLICY_VERSION = "continuum-retrieval-policy-v1"
_TOKEN_PATTERN = re.compile(r"[\w-]+", re.UNICODE)


class Embedder(Protocol):
    """Generate a fixed-size embedding without owning persistence."""

    model_id: str
    dimensions: int

    def embed(self, text: str) -> Sequence[float]: ...


class MemoryNotFoundError(LookupError):
    """Raised when a scoped canonical memory does not exist."""


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    memory_id: str
    payload: Mapping[str, Any]
    accepted_at: datetime
    similarity: float


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    retrieval_id: str
    query_digest: str
    policy_digest: str
    embedding_model: str
    evaluated_memory_ids: tuple[str, ...]
    hits: tuple[RetrievalHit, ...]


@dataclass(frozen=True, slots=True)
class MemoryDocument:
    memory_id: str
    tenant_id: str
    incident_id: str
    sequence_no: int
    payload: Mapping[str, Any]
    accepted_at: datetime
    embedding_model: str | None


def canonical_payload_text(payload: Mapping[str, Any]) -> str:
    """Return the stable text representation embedded and returned by MCP."""

    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


class HashingEmbedder:
    """Small deterministic lexical embedder for tests and zero-cost demos.

    This proves vector persistence, tenant filtering, ranking, and audit
    semantics without an external model call. It is not represented as a
    production semantic embedding model.
    """

    model_id = HASH_EMBEDDING_MODEL
    dimensions = EMBEDDING_DIMENSIONS

    def embed(self, text: str) -> tuple[float, ...]:
        normalized = unicodedata.normalize("NFKC", text).casefold()
        tokens = _TOKEN_PATTERN.findall(normalized)
        if not tokens:
            raise ValueError("text must contain at least one searchable token")

        features: list[tuple[str, float]] = [(token, 1.0) for token in tokens]
        features.extend(
            (f"{left}\x1f{right}", 0.5)
            for left, right in zip(tokens, tokens[1:], strict=False)
        )

        vector = [0.0] * self.dimensions
        for feature, weight in features:
            digest = hashlib.blake2b(
                feature.encode("utf-8"),
                digest_size=16,
                person=b"continuum-v1",
            ).digest()
            index = int.from_bytes(digest[:8], "big") % self.dimensions
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[index] += sign * weight

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:  # pragma: no cover - defensive collision guard
            raise ValueError("embedding norm must be non-zero")
        return tuple(value / norm for value in vector)


def vector_literal(values: Sequence[float], *, dimensions: int) -> str:
    """Validate and encode a vector for an explicit CockroachDB VECTOR cast."""

    if len(values) != dimensions:
        raise ValueError(f"expected {dimensions} dimensions, got {len(values)}")
    encoded: list[str] = []
    for value in values:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("embedding values must be finite")
        encoded.append(format(number, ".9g"))
    return f"[{','.join(encoded)}]"


def _digest(value: Mapping[str, Any]) -> str:
    body = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


class MemoryRetrievalStore:
    """Persist embeddings and retrieve canonical memory within one scope."""

    def __init__(
        self,
        connect: ConnectionFactory,
        *,
        max_attempts: int = 4,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        transaction_options: dict[str, Any] = {"max_attempts": max_attempts}
        if sleep is not None:
            transaction_options["sleep"] = sleep
        self._transactions = CockroachMemoryStore(connect, **transaction_options)

    def index_memory(
        self,
        *,
        tenant_id: str,
        incident_id: str,
        memory_id: str,
        embedder: Embedder,
        now: datetime | None = None,
    ) -> str:
        """Embed an immutable canonical payload, then persist it transactionally."""

        if embedder.dimensions != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"embedder must produce {EMBEDDING_DIMENSIONS} dimensions"
            )

        def load_payload(connection: Any) -> Mapping[str, Any]:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT payload
                    FROM canonical_memories
                    WHERE
                        memory_id = %s
                        AND tenant_id = %s
                        AND incident_id = %s
                    """,
                    (memory_id, tenant_id, incident_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise MemoryNotFoundError(memory_id)
                return row[0]

        payload = self._transactions.run_transaction(load_payload)
        embedding = vector_literal(
            embedder.embed(canonical_payload_text(payload)),
            dimensions=EMBEDDING_DIMENSIONS,
        )
        embedded_at = now or datetime.now(timezone.utc)

        def persist_embedding(connection: Any) -> str:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE canonical_memories
                    SET
                        embedding = %s::VECTOR,
                        embedding_model = %s,
                        embedding_updated_at = %s
                    WHERE
                        memory_id = %s
                        AND tenant_id = %s
                        AND incident_id = %s
                    RETURNING memory_id::STRING
                    """,
                    (
                        embedding,
                        embedder.model_id,
                        embedded_at,
                        memory_id,
                        tenant_id,
                        incident_id,
                    ),
                )
                row = cursor.fetchone()
                if row is None:
                    raise MemoryNotFoundError(memory_id)
                return row[0]

        return self._transactions.run_transaction(persist_embedding)

    def search(
        self,
        *,
        tenant_id: str,
        incident_id: str,
        query: str,
        embedder: Embedder,
        limit: int = 5,
        min_similarity: float = 0.05,
    ) -> RetrievalResult:
        """Run scoped cosine search and persist returned/accepted evidence."""

        query = query.strip()
        if not query:
            raise ValueError("query must not be empty")
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        if not -1.0 <= min_similarity <= 1.0:
            raise ValueError("min_similarity must be between -1 and 1")
        if embedder.dimensions != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"embedder must produce {EMBEDDING_DIMENSIONS} dimensions"
            )

        query_vector = vector_literal(
            embedder.embed(query),
            dimensions=EMBEDDING_DIMENSIONS,
        )
        query_digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
        policy_digest = _digest(
            {
                "embedding_model": embedder.model_id,
                "incident_id": incident_id,
                "limit": limit,
                "min_similarity": min_similarity,
                "tenant_id": tenant_id,
                "version": RETRIEVAL_POLICY_VERSION,
            }
        )

        def operation(connection: Any) -> RetrievalResult:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        memory_id::STRING,
                        payload,
                        accepted_at,
                        1.0 - (embedding <=> %s::VECTOR) AS similarity
                    FROM canonical_memories
                    WHERE
                        tenant_id = %s
                        AND incident_id = %s
                        AND embedding IS NOT NULL
                        AND embedding_model = %s
                    ORDER BY embedding <=> %s::VECTOR
                    LIMIT %s
                    """,
                    (
                        query_vector,
                        tenant_id,
                        incident_id,
                        embedder.model_id,
                        query_vector,
                        limit,
                    ),
                )
                rows = cursor.fetchall()
                evaluated_ids = tuple(row[0] for row in rows)
                hits = tuple(
                    RetrievalHit(
                        memory_id=row[0],
                        payload=row[1],
                        accepted_at=row[2],
                        similarity=float(row[3]),
                    )
                    for row in rows
                    if float(row[3]) >= min_similarity
                )
                accepted_ids = [hit.memory_id for hit in hits]
                cursor.execute(
                    """
                    INSERT INTO retrieval_audit (
                        tenant_id,
                        incident_id,
                        query_digest,
                        embedding_model,
                        returned_memory_ids,
                        accepted_memory_ids,
                        policy_digest
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s::UUID[],
                        %s::UUID[],
                        %s
                    )
                    RETURNING retrieval_id::STRING
                    """,
                    (
                        tenant_id,
                        incident_id,
                        query_digest,
                        embedder.model_id,
                        list(evaluated_ids),
                        accepted_ids,
                        policy_digest,
                    ),
                )
                retrieval_id = cursor.fetchone()[0]
                return RetrievalResult(
                    retrieval_id=retrieval_id,
                    query_digest=query_digest,
                    policy_digest=policy_digest,
                    embedding_model=embedder.model_id,
                    evaluated_memory_ids=evaluated_ids,
                    hits=hits,
                )

        return self._transactions.run_transaction(operation)

    def fetch_memory(
        self,
        *,
        tenant_id: str,
        incident_id: str,
        memory_id: str,
    ) -> MemoryDocument:
        """Fetch one canonical memory without permitting caller-selected scope."""

        def operation(connection: Any) -> MemoryDocument:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        memory_id::STRING,
                        tenant_id::STRING,
                        incident_id::STRING,
                        sequence_no,
                        payload,
                        accepted_at,
                        embedding_model
                    FROM canonical_memories
                    WHERE
                        memory_id = %s
                        AND tenant_id = %s
                        AND incident_id = %s
                    """,
                    (memory_id, tenant_id, incident_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise MemoryNotFoundError(memory_id)
                return MemoryDocument(
                    memory_id=row[0],
                    tenant_id=row[1],
                    incident_id=row[2],
                    sequence_no=row[3],
                    payload=row[4],
                    accepted_at=row[5],
                    embedding_model=row[6],
                )

        return self._transactions.run_transaction(operation)
