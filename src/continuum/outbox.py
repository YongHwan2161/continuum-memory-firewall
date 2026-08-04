"""Transactional outbox and crash reconciliation for bounded agent actions.

The database transaction ends before the provider call.  A durable
``dispatching`` marker records that an effect may have crossed the boundary.
After a crash, an idempotent provider may be queried or called again with the
same key; a provider without that contract is never called blindly and the
episode becomes explicitly ``ambiguous``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import hashlib
import json
from typing import Any, Callable, Mapping, Protocol
from uuid import NAMESPACE_URL, uuid4, uuid5

from continuum.episode import (
    AgentRunStatus,
    EpisodeStore,
    InMemoryEpisodeStore,
    OutcomePromotionResult,
    OutcomeStatus,
    ProviderOutcome,
    canonical_json_bytes,
    validate_outcome,
)
from continuum.store import CockroachMemoryStore, ConnectionFactory


MAX_PROVIDER_LENGTH = 128
MAX_IDEMPOTENCY_KEY_LENGTH = 256
DEFAULT_LEASE_SECONDS = 30


class OutboxStatus(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    DISPATCHING = "dispatching"
    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"
    AMBIGUOUS = "ambiguous"


class CrashPoint(StrEnum):
    BEFORE_SEND = "before_send"
    AFTER_SEND = "after_send"
    BEFORE_ACK = "before_ack"


class InjectedCrash(RuntimeError):
    """Raised only by deterministic fault-injection tests and live proof."""

    def __init__(self, point: CrashPoint) -> None:
        super().__init__(f"injected crash at {point.value}")
        self.point = point


@dataclass(frozen=True, slots=True)
class ProviderCapabilityManifest:
    """Immutable provider guarantees captured with each outbox dispatch."""

    supports_idempotency: bool
    receipt_lookup: bool
    reconciliation_timeout: timedelta

    def __post_init__(self) -> None:
        seconds = self.reconciliation_timeout.total_seconds()
        if seconds < 0 or seconds > 3600 or not seconds.is_integer():
            raise ValueError(
                "reconciliation_timeout must be whole seconds between 0 and 3600"
            )
        if not self.receipt_lookup and seconds != 0:
            raise ValueError("reconciliation_timeout requires receipt_lookup")

    @property
    def reconciliation_timeout_seconds(self) -> int:
        return int(self.reconciliation_timeout.total_seconds())

    def as_evidence(self) -> Mapping[str, Any]:
        return {
            "supports_idempotency": self.supports_idempotency,
            "receipt_lookup": self.receipt_lookup,
            "reconciliation_timeout_seconds": self.reconciliation_timeout_seconds,
            "schema_version": 1,
        }


@dataclass(frozen=True, slots=True)
class OutboxItem:
    outbox_id: str
    proposal_id: str
    run_id: str
    tenant_id: str
    incident_id: str
    provider: str
    idempotency_key: str
    action_payload: Mapping[str, Any]
    provider_capabilities: ProviderCapabilityManifest
    status: OutboxStatus
    attempt_count: int
    next_attempt_at: datetime
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    dispatch_started_at: datetime | None = None
    provider_outcome_status: OutcomeStatus | None = None
    provider_observed_at: datetime | None = None
    provider_verified_at: datetime | None = None
    provider_receipt_id: str | None = None
    receipt_digest: str | None = None
    response_evidence: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class DispatchResult:
    item: OutboxItem
    promotion: OutcomePromotionResult | None = None


class ActionProvider(Protocol):
    name: str
    capabilities: ProviderCapabilityManifest

    def send(
        self,
        *,
        action_payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> ProviderOutcome: ...

    def lookup(self, *, idempotency_key: str) -> ProviderOutcome | None: ...


class OutboxStore(Protocol):
    def enqueue_proposal(
        self,
        *,
        proposal_id: str,
        provider: str,
        provider_capabilities: ProviderCapabilityManifest,
        now: datetime | None = None,
    ) -> OutboxItem: ...

    def lease_next(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> OutboxItem | None: ...

    def begin_dispatch(
        self,
        *,
        outbox_id: str,
        worker_id: str,
        now: datetime,
    ) -> OutboxItem: ...

    def store_sent(
        self,
        *,
        outbox_id: str,
        outcome: ProviderOutcome,
        now: datetime,
    ) -> OutboxItem: ...

    def mark_acknowledged(
        self,
        *,
        outbox_id: str,
        now: datetime,
    ) -> OutboxItem: ...

    def mark_ambiguous(
        self,
        *,
        outbox_id: str,
        evidence: Mapping[str, Any],
        error_code: str,
        now: datetime,
    ) -> OutboxItem: ...

    def requeue_expired(self, *, outbox_id: str, now: datetime) -> OutboxItem: ...

    def get(self, outbox_id: str) -> OutboxItem: ...


def _validate_timestamp(value: datetime, name: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


def _validate_worker(worker_id: str) -> str:
    worker = worker_id.strip()
    if not worker or len(worker) > 256 or any(character.isspace() for character in worker):
        raise ValueError("worker_id must be a bounded non-whitespace identifier")
    return worker


def _validate_provider(provider: str) -> str:
    value = provider.strip()
    if (
        not value
        or len(value) > MAX_PROVIDER_LENGTH
        or any(character.isspace() for character in value)
    ):
        raise ValueError("provider must be a bounded non-whitespace identifier")
    return value


def outbox_idempotency_key(*, provider: str, proposal_id: str) -> str:
    provider = _validate_provider(provider)
    return str(
        uuid5(
            NAMESPACE_URL,
            f"continuum:provider-dispatch:v1:{provider}:{proposal_id}",
        )
    )


def _proposal_payload(action_key: str, action_type: str, parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = {
        "action_key": action_key,
        "action_type": action_type,
        "parameters": parameters,
        "schema_version": 1,
    }
    if len(canonical_json_bytes(payload)) > 16 * 1024:
        raise ValueError("outbox action payload exceeds 16 KiB")
    return payload


def _item_from_row(row: Any) -> OutboxItem:
    evidence = row[23]
    return OutboxItem(
        outbox_id=str(row[0]),
        proposal_id=str(row[1]),
        run_id=str(row[2]),
        tenant_id=str(row[3]),
        incident_id=str(row[4]),
        provider=row[5],
        idempotency_key=row[6],
        action_payload=row[7],
        provider_capabilities=ProviderCapabilityManifest(
            supports_idempotency=bool(row[8]),
            receipt_lookup=bool(row[9]),
            reconciliation_timeout=timedelta(seconds=int(row[10])),
        ),
        status=OutboxStatus(row[11]),
        attempt_count=int(row[12]),
        next_attempt_at=row[13],
        lease_owner=row[14],
        lease_expires_at=row[15],
        dispatch_started_at=row[16],
        provider_outcome_status=(
            None if row[18] is None else OutcomeStatus(row[18])
        ),
        provider_observed_at=row[19],
        provider_verified_at=row[20],
        provider_receipt_id=row[21],
        receipt_digest=row[22],
        response_evidence=evidence,
    )


OUTBOX_SELECT = """
    SELECT
        outbox_id::STRING,
        proposal_id::STRING,
        run_id::STRING,
        tenant_id::STRING,
        incident_id::STRING,
        provider,
        idempotency_key,
        action_payload,
        provider_supports_idempotency,
        provider_receipt_lookup,
        provider_reconciliation_timeout_seconds,
        status,
        attempt_count,
        next_attempt_at,
        lease_owner,
        lease_expires_at,
        dispatch_started_at,
        sent_at,
        provider_outcome_status,
        provider_observed_at,
        provider_verified_at,
        provider_receipt_id,
        receipt_digest,
        response_evidence
    FROM action_outbox
"""


class CockroachOutboxStore:
    """CockroachDB implementation of the outbox state machine."""

    def __init__(
        self,
        connect: ConnectionFactory,
        *,
        max_attempts: int = 4,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {"max_attempts": max_attempts}
        if sleep is not None:
            kwargs["sleep"] = sleep
        self._transactions = CockroachMemoryStore(connect, **kwargs)

    def enqueue_proposal(
        self,
        *,
        proposal_id: str,
        provider: str,
        provider_capabilities: ProviderCapabilityManifest,
        now: datetime | None = None,
    ) -> OutboxItem:
        provider = _validate_provider(provider)
        created_at = now or datetime.now(timezone.utc)
        _validate_timestamp(created_at, "enqueue time")
        idempotency_key = outbox_idempotency_key(
            provider=provider,
            proposal_id=proposal_id,
        )

        def operation(connection: Any) -> OutboxItem:
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
                        p.status,
                        p.approval_evidence,
                        r.status
                    FROM proposed_actions AS p
                    JOIN agent_runs AS r ON
                        r.run_id = p.run_id
                        AND r.tenant_id = p.tenant_id
                        AND r.incident_id = p.incident_id
                    WHERE p.proposal_id = %s
                    FOR UPDATE
                    """,
                    (proposal_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise LookupError(proposal_id)
                (
                    run_id,
                    tenant_id,
                    incident_id,
                    action_key,
                    action_type,
                    parameters,
                    proposal_status,
                    approval_evidence,
                    run_status,
                ) = row
                if not isinstance(approval_evidence, Mapping):
                    raise RuntimeError("outbox enqueue requires approval evidence")
                action_payload = _proposal_payload(action_key, action_type, parameters)
                if proposal_status == "enqueued":
                    cursor.execute(
                        OUTBOX_SELECT + " WHERE proposal_id = %s",
                        (proposal_id,),
                    )
                    existing = cursor.fetchone()
                    if existing is None:
                        raise RuntimeError("enqueued proposal is missing its outbox row")
                    item = _item_from_row(existing)
                    if (
                        item.provider != provider
                        or item.idempotency_key != idempotency_key
                        or item.provider_capabilities != provider_capabilities
                        or item.action_payload != action_payload
                    ):
                        raise RuntimeError("outbox replay does not match durable dispatch")
                    return item
                if proposal_status != "approved" or run_status != "proposed":
                    raise RuntimeError("only an approved proposal may be enqueued")

                cursor.execute(
                    """
                    INSERT INTO action_outbox (
                        proposal_id,
                        run_id,
                        tenant_id,
                        incident_id,
                        provider,
                        idempotency_key,
                        action_payload,
                        provider_supports_idempotency,
                        provider_receipt_lookup,
                        provider_reconciliation_timeout_seconds,
                        status,
                        next_attempt_at,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s::JSONB, %s, %s, %s,
                        'pending', %s, %s, %s
                    )
                    RETURNING outbox_id::STRING
                    """,
                    (
                        proposal_id,
                        run_id,
                        tenant_id,
                        incident_id,
                        provider,
                        idempotency_key,
                        json.dumps(action_payload, ensure_ascii=False),
                        provider_capabilities.supports_idempotency,
                        provider_capabilities.receipt_lookup,
                        provider_capabilities.reconciliation_timeout_seconds,
                        created_at,
                        created_at,
                        created_at,
                    ),
                )
                outbox_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    UPDATE proposed_actions
                    SET status = 'enqueued'
                    WHERE proposal_id = %s AND status = 'approved'
                    """,
                    (proposal_id,),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("proposal enqueue transition failed")
                cursor.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'enqueued'
                    WHERE run_id = %s AND status = 'proposed'
                    """,
                    (run_id,),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("agent run enqueue transition failed")
                cursor.execute(OUTBOX_SELECT + " WHERE outbox_id = %s", (outbox_id,))
                return _item_from_row(cursor.fetchone())

        return self._transactions.run_transaction(operation)

    def lease_next(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> OutboxItem | None:
        worker_id = _validate_worker(worker_id)
        _validate_timestamp(now, "lease time")
        if not 1 <= lease_seconds <= 300:
            raise ValueError("lease_seconds must be between 1 and 300")
        expires_at = now + timedelta(seconds=lease_seconds)

        def operation(connection: Any) -> OutboxItem | None:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT outbox_id::STRING
                    FROM action_outbox
                    WHERE
                        (status = 'pending' AND next_attempt_at <= %s)
                        OR (status = 'leased' AND lease_expires_at <= %s)
                    ORDER BY next_attempt_at, created_at, outbox_id
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """,
                    (now, now),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                outbox_id = row[0]
                cursor.execute(
                    """
                    UPDATE action_outbox
                    SET
                        status = 'leased',
                        attempt_count = attempt_count + 1,
                        lease_owner = %s,
                        lease_expires_at = %s,
                        updated_at = %s
                    WHERE outbox_id = %s
                    """,
                    (worker_id, expires_at, now, outbox_id),
                )
                cursor.execute(OUTBOX_SELECT + " WHERE outbox_id = %s", (outbox_id,))
                return _item_from_row(cursor.fetchone())

        return self._transactions.run_transaction(operation)

    def begin_dispatch(
        self,
        *,
        outbox_id: str,
        worker_id: str,
        now: datetime,
    ) -> OutboxItem:
        worker_id = _validate_worker(worker_id)
        _validate_timestamp(now, "dispatch time")

        def operation(connection: Any) -> OutboxItem:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE action_outbox
                    SET status = 'dispatching', dispatch_started_at = %s, updated_at = %s
                    WHERE outbox_id = %s AND status = 'leased'
                        AND lease_owner = %s AND lease_expires_at >= %s
                    """,
                    (now, now, outbox_id, worker_id, now),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("outbox lease is absent or expired")
                cursor.execute(OUTBOX_SELECT + " WHERE outbox_id = %s", (outbox_id,))
                return _item_from_row(cursor.fetchone())

        return self._transactions.run_transaction(operation)

    def store_sent(
        self,
        *,
        outbox_id: str,
        outcome: ProviderOutcome,
        now: datetime,
    ) -> OutboxItem:
        _validate_timestamp(now, "sent time")
        receipt_digest = validate_outcome(outcome)

        def operation(connection: Any) -> OutboxItem:
            with connection.cursor() as cursor:
                cursor.execute(OUTBOX_SELECT + " WHERE outbox_id = %s FOR UPDATE", (outbox_id,))
                row = cursor.fetchone()
                if row is None:
                    raise LookupError(outbox_id)
                item = _item_from_row(row)
                if item.provider != outcome.provider:
                    raise RuntimeError("provider outcome does not match outbox provider")
                if item.status is OutboxStatus.SENT:
                    if (
                        item.provider_outcome_status is not outcome.status
                        or item.provider_observed_at != outcome.observed_at
                        or item.provider_verified_at != outcome.verified_at
                        or item.provider_receipt_id != outcome.provider_receipt_id
                        or item.receipt_digest != receipt_digest
                        or item.response_evidence != outcome.evidence
                    ):
                        raise RuntimeError("sent outcome replay does not match durable receipt")
                    return item
                if item.status is not OutboxStatus.DISPATCHING:
                    raise RuntimeError("only a dispatching outbox row may store a response")
                cursor.execute(
                    """
                    UPDATE action_outbox
                    SET
                        status = 'sent',
                        sent_at = %s,
                        provider_outcome_status = %s,
                        provider_observed_at = %s,
                        provider_verified_at = %s,
                        provider_receipt_id = %s,
                        receipt_digest = %s,
                        response_evidence = %s::JSONB,
                        updated_at = %s
                    WHERE outbox_id = %s AND status = 'dispatching'
                    """,
                    (
                        now,
                        outcome.status.value,
                        outcome.observed_at,
                        outcome.verified_at,
                        outcome.provider_receipt_id,
                        receipt_digest,
                        json.dumps(outcome.evidence, ensure_ascii=False),
                        now,
                        outbox_id,
                    ),
                )
                cursor.execute(OUTBOX_SELECT + " WHERE outbox_id = %s", (outbox_id,))
                return _item_from_row(cursor.fetchone())

        return self._transactions.run_transaction(operation)

    def mark_acknowledged(
        self,
        *,
        outbox_id: str,
        now: datetime,
    ) -> OutboxItem:
        _validate_timestamp(now, "acknowledgement time")

        def operation(connection: Any) -> OutboxItem:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE action_outbox
                    SET
                        status = 'acknowledged',
                        acknowledged_at = %s,
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        updated_at = %s
                    WHERE outbox_id = %s AND status = 'sent'
                    """,
                    (now, now, outbox_id),
                )
                if cursor.rowcount == 0:
                    cursor.execute(OUTBOX_SELECT + " WHERE outbox_id = %s", (outbox_id,))
                    row = cursor.fetchone()
                    if row is None:
                        raise LookupError(outbox_id)
                    item = _item_from_row(row)
                    if item.status is not OutboxStatus.ACKNOWLEDGED:
                        raise RuntimeError("outbox response is not ready to acknowledge")
                    return item
                cursor.execute(OUTBOX_SELECT + " WHERE outbox_id = %s", (outbox_id,))
                return _item_from_row(cursor.fetchone())

        return self._transactions.run_transaction(operation)

    def mark_ambiguous(
        self,
        *,
        outbox_id: str,
        evidence: Mapping[str, Any],
        error_code: str,
        now: datetime,
    ) -> OutboxItem:
        _validate_timestamp(now, "ambiguity time")
        if not error_code or len(error_code) > 128:
            raise ValueError("error_code must be bounded")
        if len(canonical_json_bytes(evidence)) > 16 * 1024:
            raise ValueError("ambiguity evidence exceeds 16 KiB")

        def operation(connection: Any) -> OutboxItem:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE action_outbox
                    SET
                        status = 'ambiguous',
                        provider_outcome_status = 'ambiguous',
                        response_evidence = %s::JSONB,
                        last_error_code = %s,
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        updated_at = %s
                    WHERE outbox_id = %s AND status = 'dispatching'
                    """,
                    (json.dumps(evidence, ensure_ascii=False), error_code, now, outbox_id),
                )
                if cursor.rowcount == 0:
                    cursor.execute(OUTBOX_SELECT + " WHERE outbox_id = %s", (outbox_id,))
                    row = cursor.fetchone()
                    if row is None:
                        raise LookupError(outbox_id)
                    item = _item_from_row(row)
                    if item.status is not OutboxStatus.AMBIGUOUS:
                        raise RuntimeError("outbox row cannot transition to ambiguous")
                    return item
                cursor.execute(OUTBOX_SELECT + " WHERE outbox_id = %s", (outbox_id,))
                return _item_from_row(cursor.fetchone())

        return self._transactions.run_transaction(operation)

    def requeue_expired(self, *, outbox_id: str, now: datetime) -> OutboxItem:
        _validate_timestamp(now, "requeue time")

        def operation(connection: Any) -> OutboxItem:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE action_outbox
                    SET
                        status = 'pending',
                        next_attempt_at = %s,
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        updated_at = %s
                    WHERE outbox_id = %s AND status = 'leased'
                        AND lease_expires_at <= %s
                    """,
                    (now, now, outbox_id, now),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("outbox lease has not expired")
                cursor.execute(OUTBOX_SELECT + " WHERE outbox_id = %s", (outbox_id,))
                return _item_from_row(cursor.fetchone())

        return self._transactions.run_transaction(operation)

    def get(self, outbox_id: str) -> OutboxItem:
        def operation(connection: Any) -> OutboxItem:
            with connection.cursor() as cursor:
                cursor.execute(OUTBOX_SELECT + " WHERE outbox_id = %s", (outbox_id,))
                row = cursor.fetchone()
                if row is None:
                    raise LookupError(outbox_id)
                return _item_from_row(row)

        return self._transactions.run_transaction(operation)


class InMemoryOutboxStore:
    """Deterministic state-machine double used for crash-injection tests."""

    def __init__(self, episodes: InMemoryEpisodeStore) -> None:
        self.episodes = episodes
        self.items: dict[str, OutboxItem] = {}
        self.by_proposal: dict[str, str] = {}

    def enqueue_proposal(
        self,
        *,
        proposal_id: str,
        provider: str,
        provider_capabilities: ProviderCapabilityManifest,
        now: datetime | None = None,
    ) -> OutboxItem:
        provider = _validate_provider(provider)
        created_at = now or datetime.now(timezone.utc)
        prior_id = self.by_proposal.get(proposal_id)
        if prior_id is not None:
            prior = self.items[prior_id]
            if (
                prior.provider != provider
                or prior.provider_capabilities != provider_capabilities
            ):
                raise RuntimeError("outbox replay does not match durable dispatch")
            return prior
        if proposal_id not in self.episodes.proposals:
            raise LookupError(proposal_id)
        if proposal_id not in self.episodes.approvals:
            raise RuntimeError("outbox enqueue requires approval evidence")
        run_id, proposal = self.episodes.proposals[proposal_id]
        run = self.episodes.runs[run_id]
        if run.status is not AgentRunStatus.PROPOSED:
            raise RuntimeError("only an approved proposal may be enqueued")
        payload = _proposal_payload(
            proposal.action_key,
            proposal.action_type,
            proposal.parameters,
        )
        outbox_id = str(uuid4())
        item = OutboxItem(
            outbox_id=outbox_id,
            proposal_id=proposal_id,
            run_id=run_id,
            tenant_id=run.tenant_id,
            incident_id=run.incident_id,
            provider=provider,
            idempotency_key=outbox_idempotency_key(
                provider=provider,
                proposal_id=proposal_id,
            ),
            action_payload=payload,
            provider_capabilities=provider_capabilities,
            status=OutboxStatus.PENDING,
            attempt_count=0,
            next_attempt_at=created_at,
        )
        self.items[outbox_id] = item
        self.by_proposal[proposal_id] = outbox_id
        self.episodes.runs[run_id] = replace(run, status=AgentRunStatus.ENQUEUED)
        return item

    def lease_next(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> OutboxItem | None:
        worker_id = _validate_worker(worker_id)
        eligible = [
            item
            for item in self.items.values()
            if (
                item.status is OutboxStatus.PENDING
                and item.next_attempt_at <= now
            )
            or (
                item.status is OutboxStatus.LEASED
                and item.lease_expires_at is not None
                and item.lease_expires_at <= now
            )
        ]
        if not eligible:
            return None
        item = min(eligible, key=lambda row: (row.next_attempt_at, row.outbox_id))
        item = replace(
            item,
            status=OutboxStatus.LEASED,
            attempt_count=item.attempt_count + 1,
            lease_owner=worker_id,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
        )
        self.items[item.outbox_id] = item
        return item

    def begin_dispatch(self, *, outbox_id: str, worker_id: str, now: datetime) -> OutboxItem:
        item = self.get(outbox_id)
        if (
            item.status is not OutboxStatus.LEASED
            or item.lease_owner != worker_id
            or item.lease_expires_at is None
            or item.lease_expires_at < now
        ):
            raise RuntimeError("outbox lease is absent or expired")
        item = replace(
            item,
            status=OutboxStatus.DISPATCHING,
            dispatch_started_at=now,
        )
        self.items[outbox_id] = item
        return item

    def store_sent(self, *, outbox_id: str, outcome: ProviderOutcome, now: datetime) -> OutboxItem:
        del now
        digest = validate_outcome(outcome)
        item = self.get(outbox_id)
        if item.provider != outcome.provider:
            raise RuntimeError("provider outcome does not match outbox provider")
        if item.status is OutboxStatus.SENT:
            if (
                item.provider_outcome_status is not outcome.status
                or item.provider_observed_at != outcome.observed_at
                or item.provider_verified_at != outcome.verified_at
                or item.provider_receipt_id != outcome.provider_receipt_id
                or item.receipt_digest != digest
                or item.response_evidence != outcome.evidence
            ):
                raise RuntimeError("sent outcome replay does not match durable receipt")
            return item
        if item.status is not OutboxStatus.DISPATCHING:
            raise RuntimeError("only a dispatching outbox row may store a response")
        item = replace(
            item,
            status=OutboxStatus.SENT,
            provider_outcome_status=outcome.status,
            provider_observed_at=outcome.observed_at,
            provider_verified_at=outcome.verified_at,
            provider_receipt_id=outcome.provider_receipt_id,
            receipt_digest=digest,
            response_evidence=dict(outcome.evidence),
        )
        self.items[outbox_id] = item
        return item

    def mark_acknowledged(self, *, outbox_id: str, now: datetime) -> OutboxItem:
        del now
        item = self.get(outbox_id)
        if item.status is OutboxStatus.ACKNOWLEDGED:
            return item
        if item.status is not OutboxStatus.SENT:
            raise RuntimeError("outbox response is not ready to acknowledge")
        item = replace(
            item,
            status=OutboxStatus.ACKNOWLEDGED,
            lease_owner=None,
            lease_expires_at=None,
        )
        self.items[outbox_id] = item
        return item

    def mark_ambiguous(
        self,
        *,
        outbox_id: str,
        evidence: Mapping[str, Any],
        error_code: str,
        now: datetime,
    ) -> OutboxItem:
        del error_code, now
        item = self.get(outbox_id)
        if item.status is OutboxStatus.AMBIGUOUS:
            return item
        if item.status is not OutboxStatus.DISPATCHING:
            raise RuntimeError("outbox row cannot transition to ambiguous")
        item = replace(
            item,
            status=OutboxStatus.AMBIGUOUS,
            provider_outcome_status=OutcomeStatus.AMBIGUOUS,
            response_evidence=dict(evidence),
            lease_owner=None,
            lease_expires_at=None,
        )
        self.items[outbox_id] = item
        return item

    def requeue_expired(self, *, outbox_id: str, now: datetime) -> OutboxItem:
        item = self.get(outbox_id)
        if (
            item.status is not OutboxStatus.LEASED
            or item.lease_expires_at is None
            or item.lease_expires_at > now
        ):
            raise RuntimeError("outbox lease has not expired")
        item = replace(
            item,
            status=OutboxStatus.PENDING,
            next_attempt_at=now,
            lease_owner=None,
            lease_expires_at=None,
        )
        self.items[outbox_id] = item
        return item

    def get(self, outbox_id: str) -> OutboxItem:
        try:
            return self.items[outbox_id]
        except KeyError as exc:
            raise LookupError(outbox_id) from exc


class TransactionalOutboxWorker:
    """Drive one durable action without claiming impossible generic exactly-once."""

    def __init__(
        self,
        *,
        outbox: OutboxStore,
        episodes: EpisodeStore,
        provider: ActionProvider,
        worker_id: str,
    ) -> None:
        self.outbox = outbox
        self.episodes = episodes
        self.provider = provider
        self.worker_id = _validate_worker(worker_id)
        _validate_provider(provider.name)

    def process_one(
        self,
        *,
        now: datetime,
        crash_at: CrashPoint | None = None,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> DispatchResult | None:
        item = self.outbox.lease_next(
            worker_id=self.worker_id,
            now=now,
            lease_seconds=lease_seconds,
        )
        if item is None:
            return None
        self._require_provider(item)
        if crash_at is CrashPoint.BEFORE_SEND:
            raise InjectedCrash(crash_at)
        item = self.outbox.begin_dispatch(
            outbox_id=item.outbox_id,
            worker_id=self.worker_id,
            now=now,
        )
        outcome = self.provider.send(
            action_payload=item.action_payload,
            idempotency_key=item.idempotency_key,
        )
        if crash_at is CrashPoint.AFTER_SEND:
            raise InjectedCrash(crash_at)
        item = self.outbox.store_sent(
            outbox_id=item.outbox_id,
            outcome=outcome,
            now=now,
        )
        if crash_at is CrashPoint.BEFORE_ACK:
            raise InjectedCrash(crash_at)
        return self._ack(item, outcome=outcome, now=now)

    def reconcile(self, *, outbox_id: str, now: datetime) -> DispatchResult:
        item = self.outbox.get(outbox_id)
        self._require_provider(item)
        if item.status is OutboxStatus.LEASED:
            item = self.outbox.requeue_expired(outbox_id=outbox_id, now=now)
            return DispatchResult(item=item)
        if item.status is OutboxStatus.DISPATCHING:
            capabilities = item.provider_capabilities
            outcome = None
            if capabilities.receipt_lookup:
                outcome = self.provider.lookup(idempotency_key=item.idempotency_key)
                if outcome is None:
                    if item.dispatch_started_at is None:
                        raise RuntimeError(
                            "dispatching outbox row has no dispatch_started_at"
                        )
                    reconcile_after = (
                        item.dispatch_started_at
                        + capabilities.reconciliation_timeout
                    )
                    if now < reconcile_after:
                        return DispatchResult(item=item)
            if outcome is None and capabilities.supports_idempotency:
                outcome = self.provider.send(
                    action_payload=item.action_payload,
                    idempotency_key=item.idempotency_key,
                )
            if outcome is None:
                evidence = {
                    "provider_capabilities": capabilities.as_evidence(),
                    "reason_code": "PROVIDER_EFFECT_UNKNOWN_AFTER_RECONCILIATION_TIMEOUT",
                    "schema_version": 1,
                }
                ambiguous = ProviderOutcome(
                    provider=item.provider,
                    status=OutcomeStatus.AMBIGUOUS,
                    evidence=evidence,
                    observed_at=now,
                )
                promotion = self.episodes.record_outcome_and_promote(
                    proposal_id=item.proposal_id,
                    outcome=ambiguous,
                )
                item = self.outbox.mark_ambiguous(
                    outbox_id=outbox_id,
                    evidence=evidence,
                    error_code="RECONCILIATION_TIMEOUT",
                    now=now,
                )
                return DispatchResult(item=item, promotion=promotion)
            item = self.outbox.store_sent(
                outbox_id=outbox_id,
                outcome=outcome,
                now=now,
            )
            return self._ack(item, outcome=outcome, now=now)
        if item.status is OutboxStatus.SENT:
            outcome = ProviderOutcome(
                provider=item.provider,
                status=item.provider_outcome_status or OutcomeStatus.FAILED,
                provider_receipt_id=item.provider_receipt_id,
                evidence=item.response_evidence or {},
                observed_at=item.provider_observed_at or now,
                verified_at=item.provider_verified_at,
            )
            return self._ack(item, outcome=outcome, now=now)
        return DispatchResult(item=item)

    def _ack(
        self,
        item: OutboxItem,
        *,
        outcome: ProviderOutcome,
        now: datetime,
    ) -> DispatchResult:
        promotion = self.episodes.record_outcome_and_promote(
            proposal_id=item.proposal_id,
            outcome=outcome,
        )
        acknowledged = self.outbox.mark_acknowledged(
            outbox_id=item.outbox_id,
            now=now,
        )
        return DispatchResult(item=acknowledged, promotion=promotion)

    def _require_provider(self, item: OutboxItem) -> None:
        if item.provider != self.provider.name:
            raise RuntimeError("worker provider does not match durable outbox provider")
        if item.provider_capabilities != self.provider.capabilities:
            raise RuntimeError(
                "worker provider capabilities do not match durable outbox manifest"
            )


class InMemoryEffectProvider:
    """Non-effecting provider double that counts logical external effects."""

    def __init__(
        self,
        *,
        name: str = "continuum-fault-provider-v1",
        supports_idempotency: bool,
        receipt_lookup: bool | None = None,
        reconciliation_timeout: timedelta = timedelta(0),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.name = _validate_provider(name)
        if receipt_lookup is None:
            receipt_lookup = supports_idempotency
        self.capabilities = ProviderCapabilityManifest(
            supports_idempotency=supports_idempotency,
            receipt_lookup=receipt_lookup,
            reconciliation_timeout=reconciliation_timeout,
        )
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._receipts: dict[str, ProviderOutcome] = {}
        self.effect_count: dict[str, int] = {}

    def send(
        self,
        *,
        action_payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> ProviderOutcome:
        if len(idempotency_key) > MAX_IDEMPOTENCY_KEY_LENGTH:
            raise ValueError("idempotency key is too long")
        if self.capabilities.supports_idempotency and idempotency_key in self._receipts:
            return self._receipts[idempotency_key]
        count = self.effect_count.get(idempotency_key, 0) + 1
        self.effect_count[idempotency_key] = count
        observed_at = self._clock()
        digest = hashlib.sha256(canonical_json_bytes(action_payload)).hexdigest()
        outcome = ProviderOutcome(
            provider=self.name,
            status=OutcomeStatus.SUCCEEDED,
            provider_receipt_id=f"fault-proof-{idempotency_key}-{count}",
            evidence={
                "action_payload_sha256": digest,
                "effect_count": count,
                "non_effecting": True,
                "schema_version": 1,
            },
            observed_at=observed_at,
            verified_at=observed_at,
        )
        if (
            self.capabilities.supports_idempotency
            or self.capabilities.receipt_lookup
        ):
            self._receipts[idempotency_key] = outcome
        return outcome

    def lookup(self, *, idempotency_key: str) -> ProviderOutcome | None:
        if not self.capabilities.receipt_lookup:
            return None
        return self._receipts.get(idempotency_key)
