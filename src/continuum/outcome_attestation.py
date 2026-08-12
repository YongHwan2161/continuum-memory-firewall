"""Short-lived provider-origin authority for canonical outcome promotion.

An action worker may carry a provider result, but it cannot manufacture the
authority that turns that result into future model-visible memory.  A verifier
that owns this authority issues a signed, proposal-bound handle only after a
provider receipt lookup.  The episode store verifies and consumes the handle in
the same transaction as the first outcome and canonical-memory insert.
"""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
import secrets
from typing import Any, Callable, Mapping, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from continuum.episode import ProviderOutcome


ATTESTATION_VERSION = "v1"
DEFAULT_ATTESTATION_TTL = timedelta(minutes=5)
MAX_ATTESTATION_TTL = timedelta(minutes=15)
MAX_HANDLE_BYTES = 8 * 1024
OUTCOME_ATTESTATION_REQUIRED = "OUTCOME_ATTESTATION_REQUIRED"
OUTCOME_ATTESTATION_INVALID = "OUTCOME_ATTESTATION_INVALID"
OUTCOME_ATTESTATION_EXPIRED = "OUTCOME_ATTESTATION_EXPIRED"
OUTCOME_ATTESTATION_BINDING_MISMATCH = "OUTCOME_ATTESTATION_BINDING_MISMATCH"
OUTCOME_ATTESTATION_REPLAY_CONFLICT = "OUTCOME_ATTESTATION_REPLAY_CONFLICT"


class OutcomeAttestationError(RuntimeError):
    """Fail-closed outcome-attestation admission error."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class OutcomeAttestationClaims:
    proposal_id: str
    provider: str
    idempotency_key: str
    provider_receipt_id: str
    receipt_digest: str
    status: str
    policy_version: str
    issuer: str
    key_id: str
    nonce: str
    issued_at: datetime
    expires_at: datetime

    def as_payload(self) -> dict[str, Any]:
        return {
            "expires_at": self.expires_at.isoformat(),
            "idempotency_key": self.idempotency_key,
            "issued_at": self.issued_at.isoformat(),
            "issuer": self.issuer,
            "key_id": self.key_id,
            "nonce": self.nonce,
            "policy_version": self.policy_version,
            "proposal_id": self.proposal_id,
            "provider": self.provider,
            "provider_receipt_id": self.provider_receipt_id,
            "receipt_digest": self.receipt_digest,
            "schema_version": 1,
            "status": self.status,
        }


class OutcomeAttestationVerifier(Protocol):
    def verify(self, handle: str) -> OutcomeAttestationClaims: ...


class ReceiptLookupProvider(Protocol):
    name: str

    def lookup(self, *, idempotency_key: str) -> ProviderOutcome | None: ...


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _encode(value: bytes) -> str:
    return urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        decoded = urlsafe_b64decode((value + padding).encode("ascii"))
    except Exception as exc:
        raise OutcomeAttestationError(
            OUTCOME_ATTESTATION_INVALID,
            "handle encoding is invalid",
        ) from exc
    # Base64 permits alternate text representations when unused trailing bits
    # are non-zero.  Reject those aliases so the signed handle has exactly one
    # wire representation and a one-character mutation cannot remain valid.
    if _encode(decoded) != value:
        raise OutcomeAttestationError(
            OUTCOME_ATTESTATION_INVALID,
            "handle encoding is not canonical",
        )
    return decoded


def handle_digest(handle: str) -> str:
    if not isinstance(handle, str) or not handle:
        raise OutcomeAttestationError(
            OUTCOME_ATTESTATION_INVALID,
            "handle is absent or oversized",
        )
    try:
        encoded = handle.encode("ascii", errors="strict")
    except UnicodeEncodeError as exc:
        raise OutcomeAttestationError(
            OUTCOME_ATTESTATION_INVALID,
            "handle encoding is invalid",
        ) from exc
    if len(encoded) > MAX_HANDLE_BYTES:
        raise OutcomeAttestationError(
            OUTCOME_ATTESTATION_INVALID,
            "handle is absent or oversized",
        )
    return hashlib.sha256(encoded).hexdigest()


def nonce_digest(nonce: str) -> str:
    return hashlib.sha256(nonce.encode("ascii", errors="strict")).hexdigest()


class ProviderOutcomeAttestationAuthority:
    """Issue and verify signed handles; callers without the key cannot mint one."""

    def __init__(
        self,
        signing_key: bytes,
        *,
        issuer: str = "continuum-provider-verifier-v1",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise ValueError("outcome attestation signing key must be at least 32 bytes")
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", issuer):
            raise ValueError("outcome attestation issuer is invalid")
        self._key = bytes(signing_key)
        self.issuer = issuer
        self.key_id = hashlib.sha256(self._key).hexdigest()[:16]
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @classmethod
    def ephemeral(
        cls,
        *,
        issuer: str = "continuum-provider-verifier-v1",
        clock: Callable[[], datetime] | None = None,
    ) -> ProviderOutcomeAttestationAuthority:
        return cls(secrets.token_bytes(32), issuer=issuer, clock=clock)

    def issue(
        self,
        *,
        proposal_id: str,
        idempotency_key: str,
        outcome: ProviderOutcome,
        policy_version: str,
        issued_at: datetime | None = None,
        ttl: timedelta = DEFAULT_ATTESTATION_TTL,
    ) -> str:
        # Imported lazily to keep the episode contract and authority separable.
        from continuum.episode import OutcomeStatus, validate_outcome

        receipt_digest = validate_outcome(outcome)
        if outcome.status is not OutcomeStatus.SUCCEEDED or receipt_digest is None:
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_INVALID,
                "only a provider-verified success can be attested",
            )
        if not proposal_id or len(proposal_id) > 128:
            raise ValueError("attestation proposal_id is invalid")
        if not idempotency_key or len(idempotency_key) > 256:
            raise ValueError("attestation idempotency_key is invalid")
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", policy_version):
            raise ValueError("attestation policy_version is invalid")
        seconds = ttl.total_seconds()
        if seconds <= 0 or ttl > MAX_ATTESTATION_TTL:
            raise ValueError("attestation ttl must be between 1 second and 15 minutes")
        issued = issued_at or self._clock()
        if issued.tzinfo is None:
            raise ValueError("attestation issued_at must be timezone-aware")
        expires = issued + ttl
        stable_identity = _canonical_bytes(
            {
                "idempotency_key": idempotency_key,
                "issued_at": issued.isoformat(),
                "policy_version": policy_version,
                "proposal_id": proposal_id,
                "provider": outcome.provider,
                "provider_receipt_id": outcome.provider_receipt_id,
                "receipt_digest": receipt_digest,
            }
        )
        nonce = hmac.new(
            self._key,
            b"continuum:outcome-attestation:nonce:v1\x00" + stable_identity,
            hashlib.sha256,
        ).hexdigest()
        claims = OutcomeAttestationClaims(
            proposal_id=proposal_id,
            provider=outcome.provider,
            idempotency_key=idempotency_key,
            provider_receipt_id=str(outcome.provider_receipt_id),
            receipt_digest=receipt_digest,
            status=outcome.status.value,
            policy_version=policy_version,
            issuer=self.issuer,
            key_id=self.key_id,
            nonce=nonce,
            issued_at=issued,
            expires_at=expires,
        )
        body = _canonical_bytes(claims.as_payload())
        signature = hmac.new(self._key, body, hashlib.sha256).digest()
        return f"{ATTESTATION_VERSION}.{_encode(body)}.{_encode(signature)}"

    def verify_and_issue(
        self,
        *,
        proposal_id: str,
        idempotency_key: str,
        provider: ReceiptLookupProvider,
        policy_version: str,
        issued_at: datetime | None = None,
        ttl: timedelta = DEFAULT_ATTESTATION_TTL,
    ) -> tuple[ProviderOutcome, str]:
        """Perform the provider lookup before issuing the promotion capability."""

        outcome = provider.lookup(idempotency_key=idempotency_key)
        if outcome is None:
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_INVALID,
                "provider lookup returned no durable receipt",
            )
        if outcome.provider != provider.name:
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_BINDING_MISMATCH,
                "provider lookup identity does not match the adapter",
            )
        return outcome, self.issue(
            proposal_id=proposal_id,
            idempotency_key=idempotency_key,
            outcome=outcome,
            policy_version=policy_version,
            issued_at=issued_at,
            ttl=ttl,
        )

    def verify(self, handle: str) -> OutcomeAttestationClaims:
        handle_digest(handle)
        parts = handle.split(".")
        if len(parts) != 3 or parts[0] != ATTESTATION_VERSION:
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_INVALID,
                "handle version is invalid",
            )
        body = _decode(parts[1])
        signature = _decode(parts[2])
        expected = hmac.new(self._key, body, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_INVALID,
                "handle signature is invalid",
            )
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_INVALID,
                "handle payload is invalid",
            ) from exc
        if not isinstance(payload, Mapping) or payload.get("schema_version") != 1:
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_INVALID,
                "handle schema is invalid",
            )
        expected_fields = {
            "expires_at",
            "idempotency_key",
            "issued_at",
            "issuer",
            "key_id",
            "nonce",
            "policy_version",
            "proposal_id",
            "provider",
            "provider_receipt_id",
            "receipt_digest",
            "schema_version",
            "status",
        }
        if set(payload) != expected_fields:
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_INVALID,
                "handle fields are invalid",
            )
        try:
            claims = OutcomeAttestationClaims(
                proposal_id=str(payload["proposal_id"]),
                provider=str(payload["provider"]),
                idempotency_key=str(payload["idempotency_key"]),
                provider_receipt_id=str(payload["provider_receipt_id"]),
                receipt_digest=str(payload["receipt_digest"]),
                status=str(payload["status"]),
                policy_version=str(payload["policy_version"]),
                issuer=str(payload["issuer"]),
                key_id=str(payload["key_id"]),
                nonce=str(payload["nonce"]),
                issued_at=datetime.fromisoformat(str(payload["issued_at"])),
                expires_at=datetime.fromisoformat(str(payload["expires_at"])),
            )
        except (TypeError, ValueError) as exc:
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_INVALID,
                "handle claims are invalid",
            ) from exc
        if (
            claims.issuer != self.issuer
            or claims.key_id != self.key_id
            or claims.status != "succeeded"
            or claims.issued_at.tzinfo is None
            or claims.expires_at.tzinfo is None
            or claims.expires_at <= claims.issued_at
            or claims.expires_at - claims.issued_at > MAX_ATTESTATION_TTL
            or re.fullmatch(r"[0-9a-f]{64}", claims.receipt_digest) is None
            or re.fullmatch(r"[0-9a-f]{64}", claims.nonce) is None
        ):
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_INVALID,
                "handle claim constraints are invalid",
            )
        return claims
