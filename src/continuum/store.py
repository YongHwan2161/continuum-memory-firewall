"""CockroachDB transaction boundary for canonical memory and action claims.

The policy kernel remains pure.  This module makes its decision durable under
CockroachDB's default SERIALIZABLE isolation and retries whole transactions on
SQLSTATE 40001.  External side effects are deliberately outside the
transaction; ``claim_action`` prevents duplicate claims but does not pretend to
make an arbitrary external API exactly-once.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import json
import time
from typing import Any, Protocol, TypeVar

from continuum.memory import (
    ActionClass,
    DecisionCode,
    MemoryCandidate,
    MemoryPolicy,
    SourceKind,
    evaluate_candidate,
)


class Connection(Protocol):
    def __enter__(self) -> "Connection": ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...

    def transaction(self) -> Any: ...

    def cursor(self) -> Any: ...


ConnectionFactory = Callable[[], Connection]
T = TypeVar("T")


class CandidateNotFoundError(LookupError):
    """Raised when a promotion references an unknown candidate."""


class IncidentNotFoundError(LookupError):
    """Raised when an action claim references an unknown incident."""


class TransactionRetryExhaustedError(RuntimeError):
    """Raised after all SERIALIZABLE transaction retry attempts are consumed."""


class ActionClaimCode(StrEnum):
    CLAIMED = "CLAIMED"
    DUPLICATE = "DUPLICATE"
    CROSS_TENANT = "CROSS_TENANT"
    STALE_HEAD = "STALE_HEAD"


@dataclass(frozen=True, slots=True)
class PromotionResult:
    candidate_id: str
    decision_code: DecisionCode
    event_hash: str | None = None
    sequence_no: int | None = None
    memory_id: str | None = None
    replayed: bool = False

    @property
    def accepted(self) -> bool:
        return self.decision_code is DecisionCode.ACCEPTED


@dataclass(frozen=True, slots=True)
class ActionClaimResult:
    code: ActionClaimCode
    attempt_id: str | None = None
    owner_worker_id: str | None = None

    @property
    def claimed(self) -> bool:
        return self.code is ActionClaimCode.CLAIMED


def _is_retryable(exc: Exception) -> bool:
    return getattr(exc, "sqlstate", None) == "40001"


class CockroachMemoryStore:
    """Persist policy decisions and idempotent action claims in CockroachDB."""

    def __init__(
        self,
        connect: ConnectionFactory,
        *,
        max_attempts: int = 4,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._connect = connect
        self._max_attempts = max_attempts
        self._sleep = sleep

    def run_transaction(self, operation: Callable[[Connection], T]) -> T:
        """Execute one database-only operation with full serialization retries."""

        last_error: Exception | None = None
        for attempt in range(self._max_attempts):
            try:
                with self._connect() as connection:
                    with connection.transaction():
                        return operation(connection)
            except Exception as exc:
                if not _is_retryable(exc):
                    raise
                last_error = exc
                if attempt + 1 < self._max_attempts:
                    self._sleep(0.01 * (2**attempt))

        raise TransactionRetryExhaustedError(
            f"transaction failed after {self._max_attempts} attempts"
        ) from last_error

    # Kept for compatibility with the P1 tests and any early adopters.
    _run_transaction = run_transaction

    def promote_candidate(
        self,
        candidate_id: str,
        *,
        now: datetime,
    ) -> PromotionResult:
        """Evaluate and durably promote or reject one candidate.

        Repeated calls are idempotent: an already-decided candidate returns the
        original durable result without adding another canonical memory.
        """

        def operation(connection: Connection) -> PromotionResult:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        c.candidate_id::STRING,
                        c.tenant_id::STRING,
                        c.incident_id::STRING,
                        c.parent_hash,
                        c.source_kind,
                        c.action_class,
                        c.payload,
                        c.created_at,
                        c.expires_at,
                        c.human_approved,
                        c.decision_code,
                        i.tenant_id::STRING,
                        i.current_head
                    FROM memory_candidates AS c
                    JOIN incidents AS i ON i.incident_id = c.incident_id
                    WHERE c.candidate_id = %s
                    FOR UPDATE
                    """,
                    (candidate_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise CandidateNotFoundError(candidate_id)

                (
                    durable_candidate_id,
                    candidate_tenant_id,
                    incident_id,
                    parent_hash,
                    source_kind,
                    action_class,
                    payload,
                    created_at,
                    expires_at,
                    human_approved,
                    prior_decision,
                    incident_tenant_id,
                    current_head,
                ) = row

                if prior_decision is not None:
                    return self._load_prior_result(
                        cursor,
                        durable_candidate_id,
                        DecisionCode(prior_decision),
                    )

                candidate = MemoryCandidate(
                    candidate_id=durable_candidate_id,
                    tenant_id=candidate_tenant_id,
                    incident_id=incident_id,
                    parent_hash=parent_hash,
                    source_kind=SourceKind(source_kind),
                    action_class=ActionClass(action_class),
                    payload=payload,
                    created_at=created_at,
                    expires_at=expires_at,
                    human_approved=human_approved,
                )
                policy = MemoryPolicy(
                    tenant_id=incident_tenant_id,
                    incident_id=incident_id,
                    current_head=current_head,
                )
                decision = evaluate_candidate(candidate, policy, now=now)

                if not decision.accepted:
                    cursor.execute(
                        """
                        UPDATE memory_candidates
                        SET decision_code = %s, decided_at = %s
                        WHERE candidate_id = %s AND decision_code IS NULL
                        """,
                        (decision.code.value, now, durable_candidate_id),
                    )
                    return PromotionResult(
                        candidate_id=durable_candidate_id,
                        decision_code=decision.code,
                    )

                assert decision.event is not None
                cursor.execute(
                    """
                    UPDATE incidents
                    SET
                        current_sequence = current_sequence + 1,
                        current_head = %s,
                        updated_at = %s
                    WHERE
                        incident_id = %s
                        AND tenant_id = %s
                        AND current_head = %s
                    RETURNING current_sequence
                    """,
                    (
                        decision.event.event_hash,
                        now,
                        incident_id,
                        incident_tenant_id,
                        parent_hash,
                    ),
                )
                sequence_row = cursor.fetchone()
                if sequence_row is None:
                    raise RuntimeError("incident head changed inside locked transaction")
                sequence_no = sequence_row[0]

                cursor.execute(
                    """
                    INSERT INTO canonical_memories (
                        tenant_id,
                        incident_id,
                        sequence_no,
                        parent_hash,
                        event_hash,
                        source_candidate_id,
                        payload,
                        accepted_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s::JSONB, %s)
                    RETURNING memory_id::STRING
                    """,
                    (
                        candidate_tenant_id,
                        incident_id,
                        sequence_no,
                        parent_hash,
                        decision.event.event_hash,
                        durable_candidate_id,
                        json.dumps(payload, separators=(",", ":"), sort_keys=True),
                        now,
                    ),
                )
                memory_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    UPDATE memory_candidates
                    SET decision_code = %s, decided_at = %s
                    WHERE candidate_id = %s AND decision_code IS NULL
                    """,
                    (DecisionCode.ACCEPTED.value, now, durable_candidate_id),
                )
                return PromotionResult(
                    candidate_id=durable_candidate_id,
                    decision_code=DecisionCode.ACCEPTED,
                    event_hash=decision.event.event_hash,
                    sequence_no=sequence_no,
                    memory_id=memory_id,
                )

        return self.run_transaction(operation)

    @staticmethod
    def _load_prior_result(
        cursor: Any,
        candidate_id: str,
        decision_code: DecisionCode,
    ) -> PromotionResult:
        if decision_code is not DecisionCode.ACCEPTED:
            return PromotionResult(
                candidate_id=candidate_id,
                decision_code=decision_code,
                replayed=True,
            )
        cursor.execute(
            """
            SELECT memory_id::STRING, event_hash, sequence_no
            FROM canonical_memories
            WHERE source_candidate_id = %s
            """,
            (candidate_id,),
        )
        canonical = cursor.fetchone()
        if canonical is None:
            raise RuntimeError("accepted candidate has no canonical memory")
        memory_id, event_hash, sequence_no = canonical
        return PromotionResult(
            candidate_id=candidate_id,
            decision_code=decision_code,
            event_hash=event_hash,
            sequence_no=sequence_no,
            memory_id=memory_id,
            replayed=True,
        )

    def claim_action(
        self,
        *,
        tenant_id: str,
        incident_id: str,
        expected_head: str,
        action_key: str,
        action_payload: dict[str, Any],
        worker_id: str,
    ) -> ActionClaimResult:
        """Claim an action key once for a specific incident head."""

        def operation(connection: Connection) -> ActionClaimResult:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT tenant_id::STRING, current_head
                    FROM incidents
                    WHERE incident_id = %s
                    FOR UPDATE
                    """,
                    (incident_id,),
                )
                incident = cursor.fetchone()
                if incident is None:
                    raise IncidentNotFoundError(incident_id)
                durable_tenant_id, durable_head = incident
                if durable_tenant_id != tenant_id:
                    return ActionClaimResult(ActionClaimCode.CROSS_TENANT)
                if durable_head != expected_head:
                    return ActionClaimResult(ActionClaimCode.STALE_HEAD)

                cursor.execute(
                    """
                    INSERT INTO action_attempts (
                        tenant_id,
                        incident_id,
                        expected_head,
                        action_key,
                        action_payload,
                        worker_id,
                        status
                    )
                    VALUES (%s, %s, %s, %s, %s::JSONB, %s, 'approved')
                    ON CONFLICT (incident_id, expected_head, action_key)
                    DO NOTHING
                    RETURNING attempt_id::STRING
                    """,
                    (
                        tenant_id,
                        incident_id,
                        expected_head,
                        action_key,
                        json.dumps(
                            action_payload,
                            separators=(",", ":"),
                            sort_keys=True,
                        ),
                        worker_id,
                    ),
                )
                claimed = cursor.fetchone()
                if claimed is not None:
                    return ActionClaimResult(
                        ActionClaimCode.CLAIMED,
                        attempt_id=claimed[0],
                        owner_worker_id=worker_id,
                    )

                cursor.execute(
                    """
                    SELECT attempt_id::STRING, worker_id
                    FROM action_attempts
                    WHERE
                        incident_id = %s
                        AND expected_head = %s
                        AND action_key = %s
                    """,
                    (incident_id, expected_head, action_key),
                )
                existing = cursor.fetchone()
                if existing is None:
                    raise RuntimeError("conflicting action claim was not found")
                return ActionClaimResult(
                    ActionClaimCode.DUPLICATE,
                    attempt_id=existing[0],
                    owner_worker_id=existing[1],
                )

        return self.run_transaction(operation)


def psycopg_connection_factory(database_url: str) -> ConnectionFactory:
    """Create the optional psycopg connection factory for P1 integration."""

    if not database_url:
        raise ValueError("database_url must not be empty")
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - exercised by install boundary
        raise RuntimeError(
            "install the CockroachDB extra: pip install '.[cockroach]'"
        ) from exc

    return lambda: psycopg.connect(database_url)
