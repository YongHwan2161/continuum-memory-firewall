"""Deterministic acceptance boundary for persistent agent memory.

This policy module intentionally performs no model calls and no database writes.
It turns a candidate and an explicit policy into a stable decision and, on
acceptance, an immutable event hash.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
from typing import Any, Mapping


class SourceKind(StrEnum):
    HUMAN = "human"
    TOOL = "tool"
    MODEL = "model"
    EXTERNAL = "external"


class ActionClass(StrEnum):
    OBSERVE = "observe"
    RECOMMEND = "recommend"
    DESTRUCTIVE = "destructive"


class DecisionCode(StrEnum):
    ACCEPTED = "ACCEPTED"
    CROSS_TENANT = "CROSS_TENANT"
    CROSS_INCIDENT = "CROSS_INCIDENT"
    STALE_PARENT = "STALE_PARENT"
    EXPIRED = "EXPIRED"
    UNTRUSTED_SOURCE = "UNTRUSTED_SOURCE"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    INVALID_TIME = "INVALID_TIME"


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    candidate_id: str
    tenant_id: str
    incident_id: str
    parent_hash: str
    source_kind: SourceKind
    action_class: ActionClass
    payload: Mapping[str, Any]
    created_at: datetime
    expires_at: datetime | None = None
    human_approved: bool = False


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    tenant_id: str
    incident_id: str
    current_head: str
    trusted_sources: frozenset[SourceKind] = frozenset(
        {SourceKind.HUMAN, SourceKind.TOOL}
    )
    max_payload_bytes: int = 16_384
    destructive_requires_human: bool = True


@dataclass(frozen=True, slots=True)
class MemoryEvent:
    candidate_id: str
    tenant_id: str
    incident_id: str
    parent_hash: str
    event_hash: str
    payload: Mapping[str, Any]
    accepted_at: datetime


@dataclass(frozen=True, slots=True)
class Decision:
    code: DecisionCode
    event: MemoryEvent | None = None

    @property
    def accepted(self) -> bool:
        return self.code is DecisionCode.ACCEPTED


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    """Return stable UTF-8 JSON bytes for the bounded policy data model.

    This is deterministic JSON for the testable policy kernel. It is not yet
    presented as a complete RFC 8785 implementation.
    """

    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _event_hash(candidate: MemoryCandidate, accepted_at: datetime) -> str:
    envelope = {
        "accepted_at": _utc(accepted_at).isoformat(),
        "candidate_id": candidate.candidate_id,
        "incident_id": candidate.incident_id,
        "parent_hash": candidate.parent_hash,
        "payload": candidate.payload,
        "tenant_id": candidate.tenant_id,
    }
    return hashlib.sha256(b"continuum-memory-event-v1\x00" + _canonical_bytes(envelope)).hexdigest()


def evaluate_candidate(
    candidate: MemoryCandidate,
    policy: MemoryPolicy,
    *,
    now: datetime,
) -> Decision:
    """Evaluate a candidate without side effects.

    Validation order is part of the public contract: scope, lineage, time,
    provenance, approval, then resource limits.
    """

    try:
        current_time = _utc(now)
        created_at = _utc(candidate.created_at)
        expires_at = _utc(candidate.expires_at) if candidate.expires_at else None
    except ValueError:
        return Decision(DecisionCode.INVALID_TIME)

    if candidate.tenant_id != policy.tenant_id:
        return Decision(DecisionCode.CROSS_TENANT)
    if candidate.incident_id != policy.incident_id:
        return Decision(DecisionCode.CROSS_INCIDENT)
    if candidate.parent_hash != policy.current_head:
        return Decision(DecisionCode.STALE_PARENT)
    if created_at > current_time or (expires_at is not None and expires_at <= current_time):
        return Decision(DecisionCode.EXPIRED)
    if candidate.source_kind not in policy.trusted_sources:
        return Decision(DecisionCode.UNTRUSTED_SOURCE)
    if (
        policy.destructive_requires_human
        and candidate.action_class is ActionClass.DESTRUCTIVE
        and not candidate.human_approved
    ):
        return Decision(DecisionCode.HUMAN_APPROVAL_REQUIRED)

    try:
        payload_size = len(_canonical_bytes(candidate.payload))
    except (TypeError, ValueError):
        return Decision(DecisionCode.PAYLOAD_TOO_LARGE)
    if payload_size > policy.max_payload_bytes:
        return Decision(DecisionCode.PAYLOAD_TOO_LARGE)

    event = MemoryEvent(
        candidate_id=candidate.candidate_id,
        tenant_id=candidate.tenant_id,
        incident_id=candidate.incident_id,
        parent_hash=candidate.parent_hash,
        event_hash=_event_hash(candidate, current_time),
        payload=candidate.payload,
        accepted_at=current_time,
    )
    return Decision(DecisionCode.ACCEPTED, event)
