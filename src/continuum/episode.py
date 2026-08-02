"""Durable episode contract for model-assisted, outcome-gated agent runs.

The model may retrieve memory and propose an action.  It never executes an
external effect or promotes memory.  Those authority transitions live behind
separate database and provider-verification boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
from typing import Any, Callable, Mapping, Protocol, Sequence
from uuid import uuid4

from continuum.store import CockroachMemoryStore, ConnectionFactory


MAX_INPUT_BYTES = 32 * 1024
MAX_ACTION_BYTES = 16 * 1024
MAX_CITATIONS = 20


class AgentArm(StrEnum):
    STATELESS = "stateless"
    RAW_RAG = "raw_rag"
    CONTINUUM = "continuum"


class AgentRunStatus(StrEnum):
    STARTED = "started"
    PROPOSED = "proposed"
    ENQUEUED = "enqueued"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    AMBIGUOUS = "ambiguous"


class RiskClass(StrEnum):
    READ_ONLY = "read_only"
    REVERSIBLE = "reversible"
    DESTRUCTIVE = "destructive"


class OutcomeStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class RetrievedCitation:
    memory_id: str
    rank: int
    payload: Mapping[str, Any]
    similarity: float | None = None
    retrieval_id: str | None = None


@dataclass(frozen=True, slots=True)
class PersistedCitation:
    citation_id: str
    memory_id: str
    rank: int


@dataclass(frozen=True, slots=True)
class ProposedAction:
    action_key: str
    action_type: str
    parameters: Mapping[str, Any]
    rationale: str
    citation_memory_ids: tuple[str, ...]
    risk_class: RiskClass


@dataclass(frozen=True, slots=True)
class AgentRun:
    run_id: str
    tenant_id: str
    incident_id: str
    arm: AgentArm
    model_id: str
    request_digest: str
    status: AgentRunStatus


class EpisodeStore(Protocol):
    def start_run(
        self,
        *,
        tenant_id: str,
        incident_id: str,
        arm: AgentArm,
        model_id: str,
        input_payload: Mapping[str, Any],
        now: datetime | None = None,
    ) -> AgentRun: ...

    def record_citations(
        self,
        *,
        run: AgentRun,
        citations: Sequence[RetrievedCitation],
    ) -> tuple[PersistedCitation, ...]: ...

    def record_proposal(
        self,
        *,
        run: AgentRun,
        proposal: ProposedAction,
        now: datetime | None = None,
    ) -> str: ...

    def finish_without_action(
        self,
        *,
        run: AgentRun,
        final_text: str,
        now: datetime | None = None,
    ) -> None: ...


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("episode payload must be JSON serializable") from exc
    return encoded


def payload_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _validate_run_input(model_id: str, payload: Mapping[str, Any]) -> str:
    if not model_id.strip() or len(model_id) > 256:
        raise ValueError("model_id must be between 1 and 256 characters")
    encoded = canonical_json_bytes(payload)
    if len(encoded) > MAX_INPUT_BYTES:
        raise ValueError("agent input exceeds 32 KiB")
    return hashlib.sha256(encoded).hexdigest()


def validate_citations(
    citations: Sequence[RetrievedCitation],
) -> tuple[RetrievedCitation, ...]:
    durable = tuple(citations)
    if len(durable) > MAX_CITATIONS:
        raise ValueError("an agent run may cite at most 20 memories")
    memory_ids: set[str] = set()
    ranks: set[int] = set()
    for citation in durable:
        if not citation.memory_id:
            raise ValueError("citation memory_id is required")
        if citation.memory_id in memory_ids:
            raise ValueError("citation memory_ids must be unique")
        if citation.rank < 1 or citation.rank in ranks:
            raise ValueError("citation ranks must be unique positive integers")
        if citation.similarity is not None and not -1.0 <= citation.similarity <= 1.0:
            raise ValueError("citation similarity must be between -1 and 1")
        canonical_json_bytes(citation.payload)
        memory_ids.add(citation.memory_id)
        ranks.add(citation.rank)
    return durable


def validate_proposal(proposal: ProposedAction) -> ProposedAction:
    if not proposal.action_key.strip() or len(proposal.action_key) > 256:
        raise ValueError("action_key must be between 1 and 256 characters")
    if not proposal.action_type.strip() or len(proposal.action_type) > 128:
        raise ValueError("action_type must be between 1 and 128 characters")
    if not proposal.rationale.strip() or len(proposal.rationale) > 4_096:
        raise ValueError("rationale must be between 1 and 4096 characters")
    if len(set(proposal.citation_memory_ids)) != len(proposal.citation_memory_ids):
        raise ValueError("proposal citation memory_ids must be unique")
    if len(proposal.citation_memory_ids) > MAX_CITATIONS:
        raise ValueError("proposal may reference at most 20 citations")
    if len(canonical_json_bytes(proposal.parameters)) > MAX_ACTION_BYTES:
        raise ValueError("action parameters exceed 16 KiB")
    return proposal


class CockroachEpisodeStore:
    """Persist episode facts under CockroachDB SERIALIZABLE transactions."""

    def __init__(
        self,
        connect: ConnectionFactory,
        *,
        max_attempts: int = 4,
    ) -> None:
        self._transactions = CockroachMemoryStore(
            connect,
            max_attempts=max_attempts,
        )

    def start_run(
        self,
        *,
        tenant_id: str,
        incident_id: str,
        arm: AgentArm,
        model_id: str,
        input_payload: Mapping[str, Any],
        now: datetime | None = None,
    ) -> AgentRun:
        request_digest = _validate_run_input(model_id, input_payload)
        started_at = now or datetime.now(timezone.utc)

        def operation(connection: Any) -> AgentRun:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO agent_runs (
                        tenant_id,
                        incident_id,
                        arm,
                        model_id,
                        request_digest,
                        input_payload,
                        status,
                        started_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s::JSONB, 'started', %s)
                    RETURNING run_id::STRING
                    """,
                    (
                        tenant_id,
                        incident_id,
                        arm.value,
                        model_id,
                        request_digest,
                        json.dumps(input_payload, ensure_ascii=False),
                        started_at,
                    ),
                )
                run_id = cursor.fetchone()[0]
                return AgentRun(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    incident_id=incident_id,
                    arm=arm,
                    model_id=model_id,
                    request_digest=request_digest,
                    status=AgentRunStatus.STARTED,
                )

        return self._transactions.run_transaction(operation)

    def record_citations(
        self,
        *,
        run: AgentRun,
        citations: Sequence[RetrievedCitation],
    ) -> tuple[PersistedCitation, ...]:
        durable = validate_citations(citations)
        if run.arm is AgentArm.STATELESS and durable:
            raise ValueError("stateless runs cannot persist retrieved citations")

        def operation(connection: Any) -> tuple[PersistedCitation, ...]:
            persisted: list[PersistedCitation] = []
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT status
                    FROM agent_runs
                    WHERE run_id = %s AND tenant_id = %s AND incident_id = %s
                    FOR UPDATE
                    """,
                    (run.run_id, run.tenant_id, run.incident_id),
                )
                row = cursor.fetchone()
                if row is None or row[0] != AgentRunStatus.STARTED.value:
                    raise RuntimeError("agent run is not open for citations")
                for citation in durable:
                    cursor.execute(
                        """
                        INSERT INTO retrieved_citations (
                            run_id,
                            tenant_id,
                            incident_id,
                            memory_id,
                            rank,
                            similarity,
                            retrieval_id,
                            payload_digest,
                            cited_payload
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::JSONB)
                        RETURNING citation_id::STRING
                        """,
                        (
                            run.run_id,
                            run.tenant_id,
                            run.incident_id,
                            citation.memory_id,
                            citation.rank,
                            citation.similarity,
                            citation.retrieval_id,
                            payload_digest(citation.payload),
                            json.dumps(citation.payload, ensure_ascii=False),
                        ),
                    )
                    persisted.append(
                        PersistedCitation(
                            citation_id=cursor.fetchone()[0],
                            memory_id=citation.memory_id,
                            rank=citation.rank,
                        )
                    )
            return tuple(persisted)

        return self._transactions.run_transaction(operation)

    def record_proposal(
        self,
        *,
        run: AgentRun,
        proposal: ProposedAction,
        now: datetime | None = None,
    ) -> str:
        validate_proposal(proposal)
        proposed_at = now or datetime.now(timezone.utc)

        def operation(connection: Any) -> str:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT status
                    FROM agent_runs
                    WHERE run_id = %s AND tenant_id = %s AND incident_id = %s
                    FOR UPDATE
                    """,
                    (run.run_id, run.tenant_id, run.incident_id),
                )
                row = cursor.fetchone()
                if row is None or row[0] != AgentRunStatus.STARTED.value:
                    raise RuntimeError("agent run is not open for a proposal")
                citation_ids: list[str] = []
                for memory_id in proposal.citation_memory_ids:
                    cursor.execute(
                        """
                        SELECT citation_id::STRING
                        FROM retrieved_citations
                        WHERE run_id = %s AND memory_id = %s
                            AND tenant_id = %s AND incident_id = %s
                        """,
                        (
                            run.run_id,
                            memory_id,
                            run.tenant_id,
                            run.incident_id,
                        ),
                    )
                    citation_row = cursor.fetchone()
                    if citation_row is None:
                        raise ValueError("proposal references an uncited memory")
                    citation_ids.append(citation_row[0])
                cursor.execute(
                    """
                    INSERT INTO proposed_actions (
                        run_id,
                        tenant_id,
                        incident_id,
                        action_key,
                        action_type,
                        parameters,
                        rationale,
                        citation_ids,
                        risk_class,
                        status,
                        created_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s::JSONB, %s,
                        %s::UUID[], %s, 'proposed', %s
                    )
                    RETURNING proposal_id::STRING
                    """,
                    (
                        run.run_id,
                        run.tenant_id,
                        run.incident_id,
                        proposal.action_key,
                        proposal.action_type,
                        json.dumps(proposal.parameters, ensure_ascii=False),
                        proposal.rationale,
                        citation_ids,
                        proposal.risk_class.value,
                        proposed_at,
                    ),
                )
                proposal_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'proposed'
                    WHERE run_id = %s AND status = 'started'
                    """,
                    (run.run_id,),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("agent run proposal transition failed")
                return proposal_id

        return self._transactions.run_transaction(operation)

    def finish_without_action(
        self,
        *,
        run: AgentRun,
        final_text: str,
        now: datetime | None = None,
    ) -> None:
        completed_at = now or datetime.now(timezone.utc)
        if len(final_text) > 16_384:
            raise ValueError("final_text exceeds 16 KiB")

        def operation(connection: Any) -> None:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'failed', final_text = %s, completed_at = %s
                    WHERE run_id = %s AND tenant_id = %s AND incident_id = %s
                        AND status = 'started'
                    """,
                    (
                        final_text,
                        completed_at,
                        run.run_id,
                        run.tenant_id,
                        run.incident_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("agent run terminal transition failed")

        self._transactions.run_transaction(operation)


class InMemoryEpisodeStore:
    """Test/evaluation implementation with the same state-transition contract."""

    def __init__(self, *, id_factory: Callable[[], str] | None = None) -> None:
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self.runs: dict[str, AgentRun] = {}
        self.inputs: dict[str, Mapping[str, Any]] = {}
        self.citations: dict[str, list[tuple[PersistedCitation, RetrievedCitation]]] = {}
        self.proposals: dict[str, tuple[str, ProposedAction]] = {}
        self.final_text: dict[str, str] = {}

    def start_run(
        self,
        *,
        tenant_id: str,
        incident_id: str,
        arm: AgentArm,
        model_id: str,
        input_payload: Mapping[str, Any],
        now: datetime | None = None,
    ) -> AgentRun:
        del now
        digest = _validate_run_input(model_id, input_payload)
        run = AgentRun(
            run_id=self._id_factory(),
            tenant_id=tenant_id,
            incident_id=incident_id,
            arm=arm,
            model_id=model_id,
            request_digest=digest,
            status=AgentRunStatus.STARTED,
        )
        self.runs[run.run_id] = run
        self.inputs[run.run_id] = dict(input_payload)
        self.citations[run.run_id] = []
        return run

    def record_citations(
        self,
        *,
        run: AgentRun,
        citations: Sequence[RetrievedCitation],
    ) -> tuple[PersistedCitation, ...]:
        durable = validate_citations(citations)
        if run.arm is AgentArm.STATELESS and durable:
            raise ValueError("stateless runs cannot persist retrieved citations")
        if self.runs[run.run_id].status is not AgentRunStatus.STARTED:
            raise RuntimeError("agent run is not open for citations")
        persisted = tuple(
            PersistedCitation(self._id_factory(), item.memory_id, item.rank)
            for item in durable
        )
        self.citations[run.run_id].extend(zip(persisted, durable, strict=True))
        return persisted

    def record_proposal(
        self,
        *,
        run: AgentRun,
        proposal: ProposedAction,
        now: datetime | None = None,
    ) -> str:
        del now
        validate_proposal(proposal)
        if self.runs[run.run_id].status is not AgentRunStatus.STARTED:
            raise RuntimeError("agent run is not open for a proposal")
        cited = {item.memory_id for item, _ in self.citations[run.run_id]}
        if not set(proposal.citation_memory_ids).issubset(cited):
            raise ValueError("proposal references an uncited memory")
        proposal_id = self._id_factory()
        self.proposals[proposal_id] = (run.run_id, proposal)
        self.runs[run.run_id] = replace(run, status=AgentRunStatus.PROPOSED)
        return proposal_id

    def finish_without_action(
        self,
        *,
        run: AgentRun,
        final_text: str,
        now: datetime | None = None,
    ) -> None:
        del now
        if self.runs[run.run_id].status is not AgentRunStatus.STARTED:
            raise RuntimeError("agent run terminal transition failed")
        self.runs[run.run_id] = replace(run, status=AgentRunStatus.FAILED)
        self.final_text[run.run_id] = final_text
