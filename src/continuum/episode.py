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
import re
from typing import Any, Callable, Mapping, Protocol, Sequence
from uuid import NAMESPACE_URL, uuid4, uuid5

from continuum.memory import (
    ActionClass,
    MemoryCandidate,
    MemoryPolicy,
    SourceKind,
    evaluate_candidate,
)
from continuum.outcome_attestation import (
    OUTCOME_ATTESTATION_BINDING_MISMATCH,
    OUTCOME_ATTESTATION_EXPIRED,
    OUTCOME_ATTESTATION_INVALID,
    OUTCOME_ATTESTATION_REQUIRED,
    OUTCOME_ATTESTATION_REPLAY_CONFLICT,
    OutcomeAttestationClaims,
    OutcomeAttestationError,
    OutcomeAttestationVerifier,
    handle_digest as outcome_attestation_digest,
    nonce_digest as outcome_attestation_nonce_digest,
)
from continuum.store import CockroachMemoryStore, ConnectionFactory


MAX_INPUT_BYTES = 32 * 1024
MAX_ACTION_BYTES = 16 * 1024
MAX_CITATIONS = 20
CANONICAL_OUTCOME_FACT_KEYS = frozenset(
    {
        "causal_evidence_sha256",
        "causal_signature",
        "environment_fingerprint",
        "environment_profile_id",
        "family",
        "patch_id",
        "provider_conclusion",
        "provider_receipt_sha256",
        "summary",
        "transfer_contract",
    }
)


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


@dataclass(frozen=True, slots=True)
class ProviderOutcome:
    provider: str
    status: OutcomeStatus
    evidence: Mapping[str, Any]
    observed_at: datetime
    provider_receipt_id: str | None = None
    verified_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class OutcomePromotionResult:
    outcome_id: str
    status: OutcomeStatus
    receipt_digest: str | None
    memory_id: str | None = None
    event_hash: str | None = None
    replayed: bool = False
    attestation_digest: str | None = None


OUTCOME_REPLAY_CONFLICT = "OUTCOME_REPLAY_CONFLICT"
OUTCOME_RECONCILIATION_GENESIS_HASH = "0" * 64


@dataclass(frozen=True, slots=True)
class OutcomeReplayIdentity:
    provider: str
    status: OutcomeStatus
    provider_receipt_id: str | None
    receipt_digest: str | None


@dataclass(frozen=True, slots=True)
class OutcomeReconciliationEntry:
    reconciliation_id: str
    proposal_id: str
    outcome_id: str
    run_id: str
    tenant_id: str
    incident_id: str
    decision: str
    incoming: OutcomeReplayIdentity
    durable: OutcomeReplayIdentity
    error_code: str | None
    sequence_no: int
    previous_entry_hash: str
    entry_hash: str
    recorded_at: datetime


class OutcomeReplayConflictError(RuntimeError):
    """A proposal already owns a different durable provider outcome."""

    code = OUTCOME_REPLAY_CONFLICT

    def __init__(self, entry: OutcomeReconciliationEntry) -> None:
        self.entry = entry
        self.reconciliation_id = entry.reconciliation_id
        self.proposal_id = entry.proposal_id
        self.outcome_id = entry.outcome_id
        super().__init__(
            f"{self.code}: proposal {entry.proposal_id} already has outcome "
            f"{entry.outcome_id}; reconciliation {entry.reconciliation_id}"
        )


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

    def approve_proposal(
        self,
        *,
        proposal_id: str,
        actor: str,
        reason: str,
        human_approved: bool = False,
        now: datetime | None = None,
    ) -> None: ...

    def record_outcome_and_promote(
        self,
        *,
        proposal_id: str,
        outcome: ProviderOutcome,
        outcome_attestation: str | None = None,
    ) -> OutcomePromotionResult: ...


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


def validate_outcome(outcome: ProviderOutcome) -> str | None:
    if (
        not outcome.provider.strip()
        or len(outcome.provider) > 128
        or any(character.isspace() for character in outcome.provider)
    ):
        raise ValueError("provider must be a bounded non-whitespace identifier")
    if outcome.observed_at.tzinfo is None:
        raise ValueError("outcome observed_at must be timezone-aware")
    if len(canonical_json_bytes(outcome.evidence)) > MAX_ACTION_BYTES:
        raise ValueError("outcome evidence exceeds 16 KiB")
    if outcome.status is OutcomeStatus.SUCCEEDED:
        if not outcome.provider_receipt_id or len(outcome.provider_receipt_id) > 512:
            raise ValueError("successful outcome requires a provider receipt")
        if outcome.verified_at is None or outcome.verified_at.tzinfo is None:
            raise ValueError("successful outcome requires verified_at")
        if outcome.verified_at < outcome.observed_at:
            raise ValueError("verified_at cannot precede observed_at")
        return payload_digest(
            {
                "evidence": outcome.evidence,
                "provider": outcome.provider,
                "provider_receipt_id": outcome.provider_receipt_id,
                "status": outcome.status.value,
            }
        )
    if outcome.verified_at is not None:
        raise ValueError("failed or ambiguous outcomes cannot be verified")
    return None


def outcome_replay_identity(
    outcome: ProviderOutcome,
    receipt_digest: str | None,
) -> OutcomeReplayIdentity:
    return OutcomeReplayIdentity(
        provider=outcome.provider,
        status=outcome.status,
        provider_receipt_id=outcome.provider_receipt_id,
        receipt_digest=receipt_digest,
    )


def validate_outcome_attestation_binding(
    claims: OutcomeAttestationClaims,
    *,
    proposal_id: str,
    outcome: ProviderOutcome,
    receipt_digest: str,
    expected_idempotency_key: str | None = None,
) -> None:
    expected = {
        "proposal_id": proposal_id,
        "provider": outcome.provider,
        "provider_receipt_id": str(outcome.provider_receipt_id),
        "receipt_digest": receipt_digest,
        "status": outcome.status.value,
    }
    observed = {
        "proposal_id": claims.proposal_id,
        "provider": claims.provider,
        "provider_receipt_id": claims.provider_receipt_id,
        "receipt_digest": claims.receipt_digest,
        "status": claims.status,
    }
    if expected != observed or (
        expected_idempotency_key is not None
        and claims.idempotency_key != expected_idempotency_key
    ):
        raise OutcomeAttestationError(
            OUTCOME_ATTESTATION_BINDING_MISMATCH,
            "handle does not match proposal, provider, idempotency, or receipt",
        )


def build_outcome_reconciliation_entry(
    *,
    reconciliation_id: str,
    proposal_id: str,
    outcome_id: str,
    run_id: str,
    tenant_id: str,
    incident_id: str,
    decision: str,
    incoming: OutcomeReplayIdentity,
    durable: OutcomeReplayIdentity,
    sequence_no: int,
    previous_entry_hash: str,
    recorded_at: datetime,
) -> OutcomeReconciliationEntry:
    if decision not in {"accepted", "exact_replay", "conflict"}:
        raise ValueError("invalid outcome reconciliation decision")
    if sequence_no < 1:
        raise ValueError("outcome reconciliation sequence must be positive")
    if len(previous_entry_hash) != 64:
        raise ValueError("outcome reconciliation predecessor must be SHA-256")
    if recorded_at.tzinfo is None:
        raise ValueError("outcome reconciliation time must be timezone-aware")
    identities_match = incoming == durable
    if decision == "conflict" and identities_match:
        raise ValueError("conflict reconciliation requires different identities")
    if decision != "conflict" and not identities_match:
        raise ValueError("accepted reconciliation requires matching identities")
    error_code = OUTCOME_REPLAY_CONFLICT if decision == "conflict" else None
    entry_hash = payload_digest(
        {
            "decision": decision,
            "durable": {
                "provider": durable.provider,
                "provider_receipt_id": durable.provider_receipt_id,
                "receipt_digest": durable.receipt_digest,
                "status": durable.status.value,
            },
            "error_code": error_code,
            "incident_id": incident_id,
            "incoming": {
                "provider": incoming.provider,
                "provider_receipt_id": incoming.provider_receipt_id,
                "receipt_digest": incoming.receipt_digest,
                "status": incoming.status.value,
            },
            "outcome_id": outcome_id,
            "previous_entry_hash": previous_entry_hash,
            "proposal_id": proposal_id,
            "reconciliation_id": reconciliation_id,
            "recorded_at": recorded_at.isoformat(),
            "run_id": run_id,
            "sequence_no": sequence_no,
            "tenant_id": tenant_id,
        }
    )
    return OutcomeReconciliationEntry(
        reconciliation_id=reconciliation_id,
        proposal_id=proposal_id,
        outcome_id=outcome_id,
        run_id=run_id,
        tenant_id=tenant_id,
        incident_id=incident_id,
        decision=decision,
        incoming=incoming,
        durable=durable,
        error_code=error_code,
        sequence_no=sequence_no,
        previous_entry_hash=previous_entry_hash,
        entry_hash=entry_hash,
        recorded_at=recorded_at,
    )


def canonical_outcome_facts(outcome: ProviderOutcome) -> Mapping[str, str]:
    """Return the bounded provider facts eligible for canonical retrieval.

    Outcome evidence remains the durable verification record.  Only this
    explicit projection may cross into future model-visible memory, which
    prevents an arbitrary provider payload from becoming prompt authority.
    """

    raw = outcome.evidence.get("canonical_memory")
    if raw is None:
        return {}
    if outcome.status is not OutcomeStatus.SUCCEEDED:
        raise ValueError("only successful outcomes may expose canonical facts")
    if not isinstance(raw, Mapping) or set(raw) - CANONICAL_OUTCOME_FACT_KEYS:
        raise ValueError("canonical outcome facts do not match the allowlist")
    required = {
        "environment_fingerprint",
        "patch_id",
        "provider_conclusion",
        "provider_receipt_sha256",
        "summary",
    }
    if not required.issubset(raw):
        raise ValueError("canonical outcome facts are incomplete")
    facts: dict[str, str] = {}
    for key, value in raw.items():
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > (2_048 if key == "summary" else 512)
            or any(character in value for character in "\r\n\x00")
        ):
            raise ValueError("canonical outcome facts must be bounded strings")
        facts[str(key)] = value.strip()
    if facts["provider_conclusion"] != "success":
        raise ValueError("canonical outcome facts require provider success")
    for key in (
        "provider_receipt_sha256",
        "causal_evidence_sha256",
        "causal_signature",
    ):
        if key in facts and re.fullmatch(r"[0-9a-f]{64}", facts[key]) is None:
            raise ValueError(f"canonical outcome {key} must be SHA-256")
    if "transfer_contract" in facts and "causal_signature" not in facts:
        raise ValueError("transfer facts require a causal signature")
    return facts


def outcome_candidate_id(proposal_id: str, receipt_digest: str) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"continuum:verified-outcome:v1:{proposal_id}:{receipt_digest}",
        )
    )


class CockroachEpisodeStore:
    """Persist episode facts under CockroachDB SERIALIZABLE transactions."""

    def __init__(
        self,
        connect: ConnectionFactory,
        *,
        attestation_verifier: OutcomeAttestationVerifier | None = None,
        max_attempts: int = 4,
    ) -> None:
        self._attestation_verifier = attestation_verifier
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

    def approve_proposal(
        self,
        *,
        proposal_id: str,
        actor: str,
        reason: str,
        human_approved: bool = False,
        now: datetime | None = None,
    ) -> None:
        actor = actor.strip()
        reason = reason.strip()
        if not actor or len(actor) > 256 or not reason or len(reason) > 2_048:
            raise ValueError("approval actor and reason are required and bounded")
        decided_at = now or datetime.now(timezone.utc)
        evidence = {
            "actor": actor,
            "human_approved": human_approved,
            "policy_version": "continuum-proposal-approval-v1",
            "reason": reason,
        }

        def operation(connection: Any) -> None:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT risk_class, status
                    FROM proposed_actions
                    WHERE proposal_id = %s
                    FOR UPDATE
                    """,
                    (proposal_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise LookupError(proposal_id)
                risk_class, status = row
                if status == "approved":
                    return
                if status != "proposed":
                    raise RuntimeError("proposal is not open for approval")
                if risk_class == RiskClass.DESTRUCTIVE.value and not human_approved:
                    raise ValueError("destructive proposal requires human approval")
                cursor.execute(
                    """
                    UPDATE proposed_actions
                    SET
                        status = 'approved',
                        decided_at = %s,
                        approval_evidence = %s::JSONB
                    WHERE proposal_id = %s AND status = 'proposed'
                    """,
                    (
                        decided_at,
                        json.dumps(evidence, ensure_ascii=False),
                        proposal_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("proposal approval transition failed")

        self._transactions.run_transaction(operation)

    def record_outcome_and_promote(
        self,
        *,
        proposal_id: str,
        outcome: ProviderOutcome,
        outcome_attestation: str | None = None,
    ) -> OutcomePromotionResult:
        receipt_digest = validate_outcome(outcome)
        attestation_claims = None
        attestation_digest = None
        attestation_nonce_digest = None
        if outcome.status is OutcomeStatus.SUCCEEDED:
            if outcome_attestation is None or self._attestation_verifier is None:
                raise OutcomeAttestationError(
                    OUTCOME_ATTESTATION_REQUIRED,
                    "successful outcome promotion requires a verifier-issued handle",
                )
            attestation_claims = self._attestation_verifier.verify(
                outcome_attestation
            )
            attestation_digest = outcome_attestation_digest(outcome_attestation)
            attestation_nonce_digest = outcome_attestation_nonce_digest(
                attestation_claims.nonce
            )
        elif outcome_attestation is not None:
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_INVALID,
                "failed or ambiguous outcomes cannot consume a success handle",
            )
        incoming_identity = outcome_replay_identity(outcome, receipt_digest)
        reconciliation_id = str(uuid4())
        reconciliation_time = datetime.now(timezone.utc)

        def operation(
            connection: Any,
        ) -> OutcomePromotionResult | OutcomeReconciliationEntry:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        p.run_id::STRING,
                        p.tenant_id::STRING,
                        p.incident_id::STRING,
                        p.action_key,
                        p.action_type,
                        p.parameters,
                        p.rationale,
                        p.citation_ids,
                        p.status,
                        p.approval_evidence,
                        r.arm,
                        i.current_head
                    FROM proposed_actions AS p
                    JOIN agent_runs AS r ON
                        r.run_id = p.run_id
                        AND r.tenant_id = p.tenant_id
                        AND r.incident_id = p.incident_id
                    JOIN incidents AS i ON
                        i.tenant_id = p.tenant_id
                        AND i.incident_id = p.incident_id
                    WHERE p.proposal_id = %s
                    FOR UPDATE
                    """,
                    (proposal_id,),
                )
                proposal_row = cursor.fetchone()
                if proposal_row is None:
                    raise LookupError(proposal_id)
                (
                    run_id,
                    tenant_id,
                    incident_id,
                    action_key,
                    action_type,
                    parameters,
                    rationale,
                    citation_ids,
                    proposal_status,
                    approval_evidence,
                    arm,
                    current_head,
                ) = proposal_row
                if proposal_status not in {"approved", "enqueued"}:
                    raise RuntimeError("provider outcome requires an approved proposal")
                if not isinstance(approval_evidence, Mapping):
                    raise RuntimeError("provider outcome requires approval evidence")

                expected_idempotency_key = None
                cursor.execute(
                    """
                    SELECT provider, idempotency_key
                    FROM action_outbox
                    WHERE proposal_id = %s
                    """,
                    (proposal_id,),
                )
                outbox_identity = cursor.fetchone()
                if outbox_identity is not None:
                    if str(outbox_identity[0]) != outcome.provider:
                        raise OutcomeAttestationError(
                            OUTCOME_ATTESTATION_BINDING_MISMATCH,
                            "outcome provider does not match the durable outbox",
                        )
                    expected_idempotency_key = str(outbox_identity[1])
                if attestation_claims is not None:
                    assert receipt_digest is not None
                    validate_outcome_attestation_binding(
                        attestation_claims,
                        proposal_id=proposal_id,
                        outcome=outcome,
                        receipt_digest=receipt_digest,
                        expected_idempotency_key=expected_idempotency_key,
                    )

                def append_reconciliation(
                    *,
                    decision: str,
                    durable: OutcomeReplayIdentity,
                    outcome_id: str,
                ) -> OutcomeReconciliationEntry:
                    cursor.execute(
                        """
                        SELECT sequence_no, entry_hash
                        FROM outcome_reconciliation_journal
                        WHERE proposal_id = %s
                        ORDER BY sequence_no DESC
                        LIMIT 1
                        """,
                        (proposal_id,),
                    )
                    previous = cursor.fetchone()
                    sequence_no = int(previous[0]) + 1 if previous else 1
                    previous_hash = (
                        str(previous[1])
                        if previous
                        else OUTCOME_RECONCILIATION_GENESIS_HASH
                    )
                    entry = build_outcome_reconciliation_entry(
                        reconciliation_id=reconciliation_id,
                        proposal_id=proposal_id,
                        outcome_id=outcome_id,
                        run_id=run_id,
                        tenant_id=tenant_id,
                        incident_id=incident_id,
                        decision=decision,
                        incoming=incoming_identity,
                        durable=durable,
                        sequence_no=sequence_no,
                        previous_entry_hash=previous_hash,
                        recorded_at=reconciliation_time,
                    )
                    cursor.execute(
                        """
                        INSERT INTO outcome_reconciliation_journal (
                            reconciliation_id,
                            proposal_id,
                            outcome_id,
                            run_id,
                            tenant_id,
                            incident_id,
                            decision,
                            incoming_provider,
                            incoming_status,
                            incoming_provider_receipt_id,
                            incoming_receipt_digest,
                            durable_provider,
                            durable_status,
                            durable_provider_receipt_id,
                            durable_receipt_digest,
                            error_code,
                            sequence_no,
                            previous_entry_hash,
                            entry_hash,
                            recorded_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        """,
                        (
                            entry.reconciliation_id,
                            entry.proposal_id,
                            entry.outcome_id,
                            entry.run_id,
                            entry.tenant_id,
                            entry.incident_id,
                            entry.decision,
                            entry.incoming.provider,
                            entry.incoming.status.value,
                            entry.incoming.provider_receipt_id,
                            entry.incoming.receipt_digest,
                            entry.durable.provider,
                            entry.durable.status.value,
                            entry.durable.provider_receipt_id,
                            entry.durable.receipt_digest,
                            entry.error_code,
                            entry.sequence_no,
                            entry.previous_entry_hash,
                            entry.entry_hash,
                            entry.recorded_at,
                        ),
                    )
                    return entry

                cursor.execute(
                    """
                    SELECT
                        outcome_id::STRING,
                        provider,
                        status,
                        provider_receipt_id,
                        receipt_digest
                    FROM outcome_evidence
                    WHERE proposal_id = %s
                    """,
                    (proposal_id,),
                )
                prior = cursor.fetchone()
                if prior is not None:
                    (
                        prior_outcome_id,
                        prior_provider,
                        prior_status,
                        prior_receipt_id,
                        prior_digest,
                    ) = prior
                    durable_identity = OutcomeReplayIdentity(
                        provider=str(prior_provider),
                        status=OutcomeStatus(prior_status),
                        provider_receipt_id=prior_receipt_id,
                        receipt_digest=prior_digest,
                    )
                    prior_attestation_digest = None
                    if prior_status == OutcomeStatus.SUCCEEDED.value:
                        cursor.execute(
                            """
                            SELECT handle_digest
                            FROM provider_outcome_attestations
                            WHERE proposal_id = %s
                                AND consumed_outcome_id = %s
                            """,
                            (proposal_id, prior_outcome_id),
                        )
                        attestation_row = cursor.fetchone()
                        if attestation_row is None:
                            raise RuntimeError(
                                "successful outcome is missing its consumed attestation"
                            )
                        prior_attestation_digest = str(attestation_row[0])
                    if incoming_identity != durable_identity:
                        if (
                            attestation_claims is not None
                            and attestation_claims.expires_at < reconciliation_time
                        ):
                            raise OutcomeAttestationError(
                                OUTCOME_ATTESTATION_EXPIRED,
                                "unconsumed conflicting handle has expired",
                            )
                        return append_reconciliation(
                            decision="conflict",
                            durable=durable_identity,
                            outcome_id=prior_outcome_id,
                        )
                    if (
                        prior_status == OutcomeStatus.SUCCEEDED.value
                        and attestation_digest != prior_attestation_digest
                    ):
                        raise OutcomeAttestationError(
                            OUTCOME_ATTESTATION_REPLAY_CONFLICT,
                            "exact outcome replay used a different handle",
                        )
                    memory_id = None
                    event_hash = None
                    if prior_status == OutcomeStatus.SUCCEEDED.value and prior_digest:
                        candidate_id = outcome_candidate_id(proposal_id, prior_digest)
                        cursor.execute(
                            """
                            SELECT memory_id::STRING, event_hash
                            FROM canonical_memories
                            WHERE source_candidate_id = %s
                            """,
                            (candidate_id,),
                        )
                        memory_row = cursor.fetchone()
                        if memory_row is None:
                            raise RuntimeError(
                                "successful outcome is missing canonical memory"
                            )
                        memory_id, event_hash = memory_row
                    append_reconciliation(
                        decision="exact_replay",
                        durable=durable_identity,
                        outcome_id=prior_outcome_id,
                    )
                    return OutcomePromotionResult(
                        outcome_id=prior_outcome_id,
                        status=OutcomeStatus(prior_status),
                        receipt_digest=prior_digest,
                        memory_id=memory_id,
                        event_hash=event_hash,
                        replayed=True,
                        attestation_digest=prior_attestation_digest,
                    )

                if attestation_claims is not None:
                    if attestation_claims.issued_at > reconciliation_time:
                        raise OutcomeAttestationError(
                            OUTCOME_ATTESTATION_INVALID,
                            "handle was issued in the future",
                        )
                    if attestation_claims.expires_at < reconciliation_time:
                        raise OutcomeAttestationError(
                            OUTCOME_ATTESTATION_EXPIRED,
                            "unconsumed handle has expired",
                        )
                    cursor.execute(
                        """
                        SELECT proposal_id::STRING, consumed_outcome_id::STRING
                        FROM provider_outcome_attestations
                        WHERE handle_digest = %s OR nonce_digest = %s
                        """,
                        (attestation_digest, attestation_nonce_digest),
                    )
                    consumed = cursor.fetchone()
                    if consumed is not None:
                        raise OutcomeAttestationError(
                            OUTCOME_ATTESTATION_REPLAY_CONFLICT,
                            "handle or nonce was already consumed by another outcome",
                        )

                cursor.execute(
                    """
                    INSERT INTO outcome_evidence (
                        run_id,
                        proposal_id,
                        tenant_id,
                        incident_id,
                        provider,
                        status,
                        provider_receipt_id,
                        receipt_digest,
                        evidence,
                        observed_at,
                        verified_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::JSONB, %s, %s
                    )
                    RETURNING outcome_id::STRING
                    """,
                    (
                        run_id,
                        proposal_id,
                        tenant_id,
                        incident_id,
                        outcome.provider,
                        outcome.status.value,
                        outcome.provider_receipt_id,
                        receipt_digest,
                        json.dumps(outcome.evidence, ensure_ascii=False),
                        outcome.observed_at,
                        outcome.verified_at,
                    ),
                )
                outcome_id = cursor.fetchone()[0]

                if attestation_claims is not None:
                    cursor.execute(
                        """
                        INSERT INTO provider_outcome_attestations (
                            handle_digest,
                            nonce_digest,
                            proposal_id,
                            run_id,
                            tenant_id,
                            incident_id,
                            provider,
                            idempotency_key,
                            status,
                            provider_receipt_id,
                            receipt_digest,
                            policy_version,
                            issuer,
                            key_id,
                            issued_at,
                            expires_at,
                            consumed_at,
                            consumed_outcome_id
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, 'succeeded',
                            %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        """,
                        (
                            attestation_digest,
                            attestation_nonce_digest,
                            proposal_id,
                            run_id,
                            tenant_id,
                            incident_id,
                            attestation_claims.provider,
                            attestation_claims.idempotency_key,
                            attestation_claims.provider_receipt_id,
                            attestation_claims.receipt_digest,
                            attestation_claims.policy_version,
                            attestation_claims.issuer,
                            attestation_claims.key_id,
                            attestation_claims.issued_at,
                            attestation_claims.expires_at,
                            reconciliation_time,
                            outcome_id,
                        ),
                    )

                terminal_time = outcome.verified_at or outcome.observed_at
                if outcome.status is not OutcomeStatus.SUCCEEDED:
                    cursor.execute(
                        """
                        UPDATE agent_runs
                        SET status = %s, completed_at = %s
                        WHERE run_id = %s AND status IN ('proposed', 'enqueued')
                        """,
                        (outcome.status.value, terminal_time, run_id),
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError("agent run outcome transition failed")
                    append_reconciliation(
                        decision="accepted",
                        durable=incoming_identity,
                        outcome_id=outcome_id,
                    )
                    return OutcomePromotionResult(
                        outcome_id=outcome_id,
                        status=outcome.status,
                        receipt_digest=receipt_digest,
                    )

                assert receipt_digest is not None
                assert outcome.verified_at is not None
                candidate_id = outcome_candidate_id(proposal_id, receipt_digest)
                payload = {
                    "action_key": action_key,
                    "action_type": action_type,
                    "arm": arm,
                    "citation_ids": [str(item) for item in citation_ids],
                    "episode_run_id": run_id,
                    "outcome_status": outcome.status.value,
                    "parameters": parameters,
                    "proposal_id": proposal_id,
                    "provider": outcome.provider,
                    "provider_receipt_id": outcome.provider_receipt_id,
                    "rationale": rationale,
                    "receipt_digest": receipt_digest,
                    "type": "verified_outcome_episode_v1",
                    "verified_at": outcome.verified_at.isoformat(),
                }
                payload.update(canonical_outcome_facts(outcome))
                candidate = MemoryCandidate(
                    candidate_id=candidate_id,
                    tenant_id=tenant_id,
                    incident_id=incident_id,
                    parent_hash=current_head,
                    source_kind=SourceKind.TOOL,
                    action_class=ActionClass.OBSERVE,
                    payload=payload,
                    human_approved=True,
                    created_at=outcome.verified_at,
                )
                decision = evaluate_candidate(
                    candidate,
                    MemoryPolicy(
                        tenant_id=tenant_id,
                        incident_id=incident_id,
                        current_head=current_head,
                    ),
                    now=outcome.verified_at,
                )
                if not decision.accepted or decision.event is None:
                    raise RuntimeError("verified outcome failed memory policy")
                event = decision.event

                cursor.execute(
                    """
                    INSERT INTO memory_candidates (
                        candidate_id,
                        tenant_id,
                        incident_id,
                        parent_hash,
                        source_kind,
                        action_class,
                        payload,
                        human_approved,
                        created_at,
                        decision_code,
                        decided_at
                    )
                    VALUES (
                        %s, %s, %s, %s, 'tool', 'observe', %s::JSONB,
                        true, %s, 'ACCEPTED', %s
                    )
                    """,
                    (
                        candidate_id,
                        tenant_id,
                        incident_id,
                        current_head,
                        json.dumps(payload, ensure_ascii=False),
                        outcome.verified_at,
                        outcome.verified_at,
                    ),
                )
                cursor.execute(
                    """
                    UPDATE incidents
                    SET
                        current_sequence = current_sequence + 1,
                        current_head = %s,
                        updated_at = %s
                    WHERE tenant_id = %s AND incident_id = %s
                        AND current_head = %s
                    RETURNING current_sequence
                    """,
                    (
                        event.event_hash,
                        outcome.verified_at,
                        tenant_id,
                        incident_id,
                        current_head,
                    ),
                )
                sequence_row = cursor.fetchone()
                if sequence_row is None:
                    raise RuntimeError("incident head changed during outcome promotion")
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
                        tenant_id,
                        incident_id,
                        sequence_no,
                        current_head,
                        event.event_hash,
                        candidate_id,
                        json.dumps(payload, ensure_ascii=False),
                        outcome.verified_at,
                    ),
                )
                memory_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'succeeded', completed_at = %s
                    WHERE run_id = %s AND status IN ('proposed', 'enqueued')
                    """,
                    (outcome.verified_at, run_id),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("agent run success transition failed")
                append_reconciliation(
                    decision="accepted",
                    durable=incoming_identity,
                    outcome_id=outcome_id,
                )
                return OutcomePromotionResult(
                    outcome_id=outcome_id,
                    status=outcome.status,
                    receipt_digest=receipt_digest,
                    memory_id=memory_id,
                    event_hash=event.event_hash,
                    attestation_digest=attestation_digest,
                )

        result = self._transactions.run_transaction(operation)
        if isinstance(result, OutcomeReconciliationEntry):
            raise OutcomeReplayConflictError(result)
        return result


class InMemoryEpisodeStore:
    """Test/evaluation implementation with the same state-transition contract."""

    def __init__(
        self,
        *,
        attestation_verifier: OutcomeAttestationVerifier | None = None,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._attestation_verifier = attestation_verifier
        self.runs: dict[str, AgentRun] = {}
        self.inputs: dict[str, Mapping[str, Any]] = {}
        self.citations: dict[str, list[tuple[PersistedCitation, RetrievedCitation]]] = {}
        self.proposals: dict[str, tuple[str, ProposedAction]] = {}
        self.final_text: dict[str, str] = {}
        self.approvals: dict[str, Mapping[str, Any]] = {}
        self.outcomes: dict[str, OutcomePromotionResult] = {}
        self.outcome_identities: dict[str, OutcomeReplayIdentity] = {}
        self.reconciliation_journal: list[OutcomeReconciliationEntry] = []
        self.canonical_outcomes: dict[str, Mapping[str, Any]] = {}
        self._provider_receipts: set[tuple[str, str]] = set()
        self.consumed_attestations: dict[str, Mapping[str, Any]] = {}

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

    def approve_proposal(
        self,
        *,
        proposal_id: str,
        actor: str,
        reason: str,
        human_approved: bool = False,
        now: datetime | None = None,
    ) -> None:
        del now
        if proposal_id not in self.proposals:
            raise LookupError(proposal_id)
        _, proposal = self.proposals[proposal_id]
        if proposal.risk_class is RiskClass.DESTRUCTIVE and not human_approved:
            raise ValueError("destructive proposal requires human approval")
        if not actor.strip() or not reason.strip():
            raise ValueError("approval actor and reason are required and bounded")
        self.approvals.setdefault(
            proposal_id,
            {
                "actor": actor.strip(),
                "human_approved": human_approved,
                "reason": reason.strip(),
            },
        )

    def record_outcome_and_promote(
        self,
        *,
        proposal_id: str,
        outcome: ProviderOutcome,
        outcome_attestation: str | None = None,
    ) -> OutcomePromotionResult:
        digest = validate_outcome(outcome)
        claims = None
        attestation_digest = None
        if outcome.status is OutcomeStatus.SUCCEEDED:
            if outcome_attestation is None or self._attestation_verifier is None:
                raise OutcomeAttestationError(
                    OUTCOME_ATTESTATION_REQUIRED,
                    "successful outcome promotion requires a verifier-issued handle",
                )
            claims = self._attestation_verifier.verify(outcome_attestation)
            attestation_digest = outcome_attestation_digest(outcome_attestation)
            assert digest is not None
            validate_outcome_attestation_binding(
                claims,
                proposal_id=proposal_id,
                outcome=outcome,
                receipt_digest=digest,
            )
        elif outcome_attestation is not None:
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_INVALID,
                "failed or ambiguous outcomes cannot consume a success handle",
            )
        incoming_identity = outcome_replay_identity(outcome, digest)
        prior = self.outcomes.get(proposal_id)
        if prior is not None:
            durable_identity = self.outcome_identities[proposal_id]
            decision = (
                "exact_replay"
                if incoming_identity == durable_identity
                else "conflict"
            )
            if decision == "conflict":
                if claims is not None and claims.expires_at < self._clock():
                    raise OutcomeAttestationError(
                        OUTCOME_ATTESTATION_EXPIRED,
                        "unconsumed conflicting handle has expired",
                    )
            if (
                decision == "exact_replay"
                and
                prior.status is OutcomeStatus.SUCCEEDED
                and prior.attestation_digest != attestation_digest
            ):
                raise OutcomeAttestationError(
                    OUTCOME_ATTESTATION_REPLAY_CONFLICT,
                    "exact outcome replay used a different handle",
                )
            entry = self._append_outcome_reconciliation(
                proposal_id=proposal_id,
                outcome_id=prior.outcome_id,
                decision=decision,
                incoming=incoming_identity,
                durable=durable_identity,
            )
            if decision == "conflict":
                raise OutcomeReplayConflictError(entry)
            return replace(prior, replayed=True)
        if proposal_id not in self.approvals:
            raise RuntimeError("provider outcome requires an approved proposal")
        run_id, proposal = self.proposals[proposal_id]
        run = self.runs[run_id]
        if claims is not None:
            now = self._clock()
            if claims.issued_at > now:
                raise OutcomeAttestationError(
                    OUTCOME_ATTESTATION_INVALID,
                    "handle was issued in the future",
                )
            if claims.expires_at < now:
                raise OutcomeAttestationError(
                    OUTCOME_ATTESTATION_EXPIRED,
                    "unconsumed handle has expired",
                )
            nonce_hash = outcome_attestation_nonce_digest(claims.nonce)
            for consumed in self.consumed_attestations.values():
                if consumed["nonce_digest"] == nonce_hash:
                    raise OutcomeAttestationError(
                        OUTCOME_ATTESTATION_REPLAY_CONFLICT,
                        "handle nonce was already consumed",
                    )
        if outcome.provider_receipt_id:
            provider_key = (outcome.provider, outcome.provider_receipt_id)
            if provider_key in self._provider_receipts:
                raise RuntimeError("provider receipt was already consumed")
            self._provider_receipts.add(provider_key)
        outcome_id = self._id_factory()
        memory_id = None
        event_hash = None
        if outcome.status is OutcomeStatus.SUCCEEDED:
            assert digest is not None
            candidate_id = outcome_candidate_id(proposal_id, digest)
            memory_id = self._id_factory()
            event_hash = payload_digest(
                {
                    "candidate_id": candidate_id,
                    "proposal_id": proposal_id,
                    "receipt_digest": digest,
                }
            )
            self.canonical_outcomes[memory_id] = {
                "action_key": proposal.action_key,
                "action_type": proposal.action_type,
                "parameters": dict(proposal.parameters),
                "proposal_id": proposal_id,
                "provider": outcome.provider,
                "provider_receipt_id": outcome.provider_receipt_id,
                "receipt_digest": digest,
                "status": outcome.status.value,
                **canonical_outcome_facts(outcome),
            }
        result = OutcomePromotionResult(
            outcome_id=outcome_id,
            status=outcome.status,
            receipt_digest=digest,
            memory_id=memory_id,
            event_hash=event_hash,
            attestation_digest=attestation_digest,
        )
        self.outcomes[proposal_id] = result
        self.outcome_identities[proposal_id] = incoming_identity
        self.runs[run_id] = replace(
            run,
            status=AgentRunStatus(outcome.status.value),
        )
        if claims is not None:
            assert attestation_digest is not None
            self.consumed_attestations[attestation_digest] = {
                "nonce_digest": outcome_attestation_nonce_digest(claims.nonce),
                "outcome_id": outcome_id,
                "proposal_id": proposal_id,
                "receipt_digest": digest,
            }
        self._append_outcome_reconciliation(
            proposal_id=proposal_id,
            outcome_id=outcome_id,
            decision="accepted",
            incoming=incoming_identity,
            durable=incoming_identity,
        )
        return result

    def _append_outcome_reconciliation(
        self,
        *,
        proposal_id: str,
        outcome_id: str,
        decision: str,
        incoming: OutcomeReplayIdentity,
        durable: OutcomeReplayIdentity,
    ) -> OutcomeReconciliationEntry:
        run_id, _proposal = self.proposals[proposal_id]
        run = self.runs[run_id]
        prior = [
            item
            for item in self.reconciliation_journal
            if item.proposal_id == proposal_id
        ]
        previous = prior[-1] if prior else None
        entry = build_outcome_reconciliation_entry(
            reconciliation_id=self._id_factory(),
            proposal_id=proposal_id,
            outcome_id=outcome_id,
            run_id=run_id,
            tenant_id=run.tenant_id,
            incident_id=run.incident_id,
            decision=decision,
            incoming=incoming,
            durable=durable,
            sequence_no=(previous.sequence_no + 1 if previous else 1),
            previous_entry_hash=(
                previous.entry_hash
                if previous
                else OUTCOME_RECONCILIATION_GENESIS_HASH
            ),
            recorded_at=datetime.now(timezone.utc),
        )
        self.reconciliation_journal.append(entry)
        return entry
