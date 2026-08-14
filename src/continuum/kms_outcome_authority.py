"""AWS KMS-backed outcome authority with offline public-key verification.

The provider verifier is the only principal that may call ``kms:Sign``.  The
episode store receives a short-lived, proposal-bound v2 handle and verifies it
from a checksum-addressed public keyring.  Promotion therefore has no KMS
network dependency and an action worker cannot mint its own successful memory.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import json
import re
import secrets
from typing import Any, Callable, Mapping, Sequence, TYPE_CHECKING

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from continuum.outcome_attestation import (
    DEFAULT_ATTESTATION_TTL,
    MAX_ATTESTATION_TTL,
    OUTCOME_ATTESTATION_BINDING_MISMATCH,
    OUTCOME_ATTESTATION_EXPIRED,
    OUTCOME_ATTESTATION_INVALID,
    OutcomeAttestationClaims,
    OutcomeAttestationError,
    ReceiptLookupProvider,
    _canonical_bytes,
    _decode,
    _encode,
    handle_digest,
)

if TYPE_CHECKING:
    from continuum.episode import ProviderOutcome


KMS_ATTESTATION_VERSION = "v2"
KMS_ATTESTATION_SCHEMA_VERSION = 2
KMS_SIGNING_ALGORITHM = "ECDSA_SHA_256"
KMS_KEY_SPEC = "ECC_NIST_P256"
KMS_KEY_USAGE = "SIGN_VERIFY"
KMS_RAW_MESSAGE_LIMIT = 4096
KEYRING_KIND = "continuum.kms-outcome-authority-keyring"
KEYRING_SCHEMA_VERSION = 1
GENESIS_DIGEST = "0" * 64
DEFAULT_CLOCK_SKEW = timedelta(seconds=30)


class VerificationKeyState(str, Enum):
    ACTIVE = "active"
    RETIRING = "retiring"
    REVOKED = "revoked"


def _sha256(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def _aware(value: datetime, field: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_time(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} is invalid") from exc
    return _aware(parsed, field)


def _public_key(public_key_der: bytes) -> ec.EllipticCurvePublicKey:
    try:
        key = serialization.load_der_public_key(public_key_der)
    except (TypeError, ValueError) as exc:
        raise ValueError("public key SPKI is invalid") from exc
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(
        key.curve, ec.SECP256R1
    ):
        raise ValueError("public key must be ECC_NIST_P256")
    return key


@dataclass(frozen=True, slots=True)
class PinnedVerificationKey:
    """One key/epoch authorization inside a versioned public keyring."""

    key_id: str
    key_arn_digest: str
    authority_epoch: int
    public_key_der: bytes
    state: VerificationKeyState
    signing_not_before: datetime
    signing_not_after: datetime | None = None
    verify_until: datetime | None = None

    def __post_init__(self) -> None:
        if re.fullmatch(r"[0-9a-f]{64}", self.key_id) is None:
            raise ValueError("key_id must be a SHA-256 digest")
        if re.fullmatch(r"[0-9a-f]{64}", self.key_arn_digest) is None:
            raise ValueError("key_arn_digest must be a SHA-256 digest")
        if self.authority_epoch < 1:
            raise ValueError("authority_epoch must be positive")
        _public_key(self.public_key_der)
        if _sha256(self.public_key_der) != self.key_id:
            raise ValueError("key_id does not match the public key")
        _aware(self.signing_not_before, "signing_not_before")
        if self.state is VerificationKeyState.ACTIVE:
            if self.signing_not_after is not None or self.verify_until is not None:
                raise ValueError("active keys cannot have retirement bounds")
        else:
            if self.signing_not_after is None or self.verify_until is None:
                raise ValueError("non-active keys require retirement bounds")
            ended = _aware(self.signing_not_after, "signing_not_after")
            verify_until = _aware(self.verify_until, "verify_until")
            if ended < self.signing_not_before or verify_until < ended:
                raise ValueError("key retirement window is invalid")

    def as_manifest_entry(self) -> dict[str, Any]:
        return {
            "algorithm": KMS_SIGNING_ALGORITHM,
            "authority_epoch": self.authority_epoch,
            "key_arn_digest": self.key_arn_digest,
            "key_id": self.key_id,
            "public_key_spki_b64": _encode(self.public_key_der),
            "signing_not_after": (
                self.signing_not_after.isoformat()
                if self.signing_not_after is not None
                else None
            ),
            "signing_not_before": self.signing_not_before.isoformat(),
            "state": self.state.value,
            "verify_until": (
                self.verify_until.isoformat() if self.verify_until is not None else None
            ),
        }


@dataclass(frozen=True, slots=True)
class PublicVerificationKeyring:
    version: int
    previous_manifest_sha256: str
    transition: str
    effective_at: datetime
    entries: tuple[PinnedVerificationKey, ...]
    manifest_sha256: str

    @classmethod
    def build(
        cls,
        *,
        version: int,
        previous_manifest_sha256: str,
        transition: str,
        effective_at: datetime,
        entries: Sequence[PinnedVerificationKey],
    ) -> PublicVerificationKeyring:
        payload = {
            "effective_at": _aware(effective_at, "effective_at").isoformat(),
            "entries": [entry.as_manifest_entry() for entry in entries],
            "kind": KEYRING_KIND,
            "previous_manifest_sha256": previous_manifest_sha256,
            "schema_version": KEYRING_SCHEMA_VERSION,
            "transition": transition,
            "version": version,
        }
        payload["manifest_sha256"] = _sha256(_canonical_bytes(payload))
        return cls.from_manifest(payload)

    @classmethod
    def from_manifest(
        cls, manifest: Mapping[str, Any]
    ) -> PublicVerificationKeyring:
        expected_fields = {
            "effective_at",
            "entries",
            "kind",
            "manifest_sha256",
            "previous_manifest_sha256",
            "schema_version",
            "transition",
            "version",
        }
        if set(manifest) != expected_fields:
            raise ValueError("keyring manifest fields are invalid")
        if (
            manifest.get("kind") != KEYRING_KIND
            or manifest.get("schema_version") != KEYRING_SCHEMA_VERSION
        ):
            raise ValueError("keyring manifest contract is invalid")
        try:
            version = int(manifest["version"])
        except (TypeError, ValueError) as exc:
            raise ValueError("keyring version is invalid") from exc
        if version < 1:
            raise ValueError("keyring version must be positive")
        previous = str(manifest["previous_manifest_sha256"])
        if re.fullmatch(r"[0-9a-f]{64}", previous) is None:
            raise ValueError("keyring predecessor digest is invalid")
        if version == 1 and previous != GENESIS_DIGEST:
            raise ValueError("keyring genesis predecessor is invalid")
        transition = str(manifest["transition"])
        if re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", transition) is None:
            raise ValueError("keyring transition is invalid")
        effective_at = _parse_time(manifest["effective_at"], "effective_at")
        raw_entries = manifest["entries"]
        if not isinstance(raw_entries, list) or not raw_entries:
            raise ValueError("keyring entries are invalid")
        entries: list[PinnedVerificationKey] = []
        expected_entry_fields = {
            "algorithm",
            "authority_epoch",
            "key_arn_digest",
            "key_id",
            "public_key_spki_b64",
            "signing_not_after",
            "signing_not_before",
            "state",
            "verify_until",
        }
        for raw in raw_entries:
            if not isinstance(raw, Mapping) or set(raw) != expected_entry_fields:
                raise ValueError("keyring entry fields are invalid")
            if raw["algorithm"] != KMS_SIGNING_ALGORITHM:
                raise ValueError("keyring algorithm is invalid")
            try:
                state = VerificationKeyState(str(raw["state"]))
                authority_epoch = int(raw["authority_epoch"])
                public_key_der = _decode(str(raw["public_key_spki_b64"]))
            except (TypeError, ValueError) as exc:
                raise ValueError("keyring entry is invalid") from exc
            entries.append(
                PinnedVerificationKey(
                    key_id=str(raw["key_id"]),
                    key_arn_digest=str(raw["key_arn_digest"]),
                    authority_epoch=authority_epoch,
                    public_key_der=public_key_der,
                    state=state,
                    signing_not_before=_parse_time(
                        raw["signing_not_before"], "signing_not_before"
                    ),
                    signing_not_after=(
                        _parse_time(raw["signing_not_after"], "signing_not_after")
                        if raw["signing_not_after"] is not None
                        else None
                    ),
                    verify_until=(
                        _parse_time(raw["verify_until"], "verify_until")
                        if raw["verify_until"] is not None
                        else None
                    ),
                )
            )
        identities = {(entry.key_id, entry.authority_epoch) for entry in entries}
        if len(identities) != len(entries):
            raise ValueError("keyring contains duplicate key epochs")
        if sum(entry.state is VerificationKeyState.ACTIVE for entry in entries) != 1:
            raise ValueError("keyring requires exactly one active key epoch")
        without_digest = dict(manifest)
        observed_digest = str(without_digest.pop("manifest_sha256"))
        expected_digest = _sha256(_canonical_bytes(without_digest))
        if observed_digest != expected_digest:
            raise ValueError("keyring manifest digest mismatch")
        return cls(
            version=version,
            previous_manifest_sha256=previous,
            transition=transition,
            effective_at=effective_at,
            entries=tuple(entries),
            manifest_sha256=observed_digest,
        )

    def as_manifest(self) -> dict[str, Any]:
        return {
            "effective_at": self.effective_at.isoformat(),
            "entries": [entry.as_manifest_entry() for entry in self.entries],
            "kind": KEYRING_KIND,
            "manifest_sha256": self.manifest_sha256,
            "previous_manifest_sha256": self.previous_manifest_sha256,
            "schema_version": KEYRING_SCHEMA_VERSION,
            "transition": self.transition,
            "version": self.version,
        }

    def find(self, key_id: str, authority_epoch: int) -> PinnedVerificationKey:
        for entry in self.entries:
            if entry.key_id == key_id and entry.authority_epoch == authority_epoch:
                return entry
        raise OutcomeAttestationError(
            OUTCOME_ATTESTATION_INVALID,
            "handle key epoch is not in the pinned keyring",
        )


class KmsProviderOutcomeAttestationSigner:
    """Issue v2 handles with an asymmetric KMS key; never expose private bytes."""

    def __init__(
        self,
        kms_client: Any,
        *,
        key_arn: str,
        authority_epoch: int,
        issuer: str = "continuum-provider-verifier-kms-v2",
        clock: Callable[[], datetime] | None = None,
        nonce_factory: Callable[[], bytes] | None = None,
        public_key_response: Mapping[str, Any] | None = None,
    ) -> None:
        if not isinstance(key_arn, str) or not key_arn or len(key_arn) > 2048:
            raise ValueError("KMS key ARN is invalid")
        if authority_epoch < 1:
            raise ValueError("authority_epoch must be positive")
        if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", issuer) is None:
            raise ValueError("outcome attestation issuer is invalid")
        response = public_key_response or kms_client.get_public_key(KeyId=key_arn)
        public_key_der = response.get("PublicKey")
        if not isinstance(public_key_der, (bytes, bytearray)):
            raise ValueError("KMS public key response is invalid")
        if (
            response.get("KeySpec") != KMS_KEY_SPEC
            or response.get("KeyUsage") != KMS_KEY_USAGE
            or KMS_SIGNING_ALGORITHM not in response.get("SigningAlgorithms", [])
        ):
            raise ValueError("KMS key contract is incompatible")
        self.public_key_der = bytes(public_key_der)
        _public_key(self.public_key_der)
        self.key_id = _sha256(self.public_key_der)
        self.key_arn_digest = _sha256(key_arn)
        self.key_arn = key_arn
        self.authority_epoch = authority_epoch
        self.issuer = issuer
        self._kms = kms_client
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._nonce_factory = nonce_factory or (lambda: secrets.token_bytes(32))
        self.sign_count = 0

    def verification_key(
        self,
        *,
        state: VerificationKeyState,
        signing_not_before: datetime,
        signing_not_after: datetime | None = None,
        verify_until: datetime | None = None,
    ) -> PinnedVerificationKey:
        return PinnedVerificationKey(
            key_id=self.key_id,
            key_arn_digest=self.key_arn_digest,
            authority_epoch=self.authority_epoch,
            public_key_der=self.public_key_der,
            state=state,
            signing_not_before=signing_not_before,
            signing_not_after=signing_not_after,
            verify_until=verify_until,
        )

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
        if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", policy_version) is None:
            raise ValueError("attestation policy_version is invalid")
        if ttl.total_seconds() <= 0 or ttl > MAX_ATTESTATION_TTL:
            raise ValueError("attestation ttl must be between 1 second and 15 minutes")
        issued = _aware(issued_at or self._clock(), "issued_at")
        expires = issued + ttl
        nonce_bytes = self._nonce_factory()
        if not isinstance(nonce_bytes, bytes) or len(nonce_bytes) < 32:
            raise ValueError("attestation nonce source is invalid")
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
            nonce=_sha256(nonce_bytes),
            issued_at=issued,
            expires_at=expires,
            algorithm=KMS_SIGNING_ALGORITHM,
            authority_epoch=self.authority_epoch,
            key_arn_digest=self.key_arn_digest,
            schema_version=KMS_ATTESTATION_SCHEMA_VERSION,
        )
        body = _canonical_bytes(claims.as_payload())
        if len(body) > KMS_RAW_MESSAGE_LIMIT:
            raise ValueError("attestation payload exceeds KMS RAW message limit")
        response = self._kms.sign(
            KeyId=self.key_arn,
            Message=body,
            MessageType="RAW",
            SigningAlgorithm=KMS_SIGNING_ALGORITHM,
        )
        signature = response.get("Signature")
        if (
            not isinstance(signature, (bytes, bytearray))
            or not signature
            or response.get("SigningAlgorithm") != KMS_SIGNING_ALGORITHM
            or response.get("KeyId") != self.key_arn
        ):
            raise RuntimeError("KMS Sign response contract failed")
        self.sign_count += 1
        return f"{KMS_ATTESTATION_VERSION}.{_encode(body)}.{_encode(bytes(signature))}"

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


class PinnedPublicKeyringVerifier:
    """Verify KMS signatures locally without AWS credentials or network I/O."""

    def __init__(
        self,
        keyring: PublicVerificationKeyring | Mapping[str, Any],
        *,
        issuer: str = "continuum-provider-verifier-kms-v2",
        clock: Callable[[], datetime] | None = None,
        clock_skew: timedelta = DEFAULT_CLOCK_SKEW,
    ) -> None:
        self.keyring = (
            keyring
            if isinstance(keyring, PublicVerificationKeyring)
            else PublicVerificationKeyring.from_manifest(keyring)
        )
        if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", issuer) is None:
            raise ValueError("outcome attestation issuer is invalid")
        if clock_skew < timedelta(0) or clock_skew > timedelta(minutes=2):
            raise ValueError("clock skew bound is invalid")
        self.issuer = issuer
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._clock_skew = clock_skew

    def verify(self, handle: str) -> OutcomeAttestationClaims:
        handle_digest(handle)
        parts = handle.split(".")
        if len(parts) != 3 or parts[0] != KMS_ATTESTATION_VERSION:
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_INVALID,
                "handle version is invalid",
            )
        body = _decode(parts[1])
        signature = _decode(parts[2])
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_INVALID,
                "handle payload is invalid",
            ) from exc
        expected_fields = {
            "algorithm",
            "authority_epoch",
            "expires_at",
            "idempotency_key",
            "issued_at",
            "issuer",
            "key_arn_digest",
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
        if (
            not isinstance(payload, Mapping)
            or set(payload) != expected_fields
            or payload.get("schema_version") != KMS_ATTESTATION_SCHEMA_VERSION
            or payload.get("algorithm") != KMS_SIGNING_ALGORITHM
            or _canonical_bytes(payload) != body
        ):
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_INVALID,
                "handle schema or fields are invalid",
            )
        try:
            authority_epoch = int(payload["authority_epoch"])
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
                issued_at=_parse_time(payload["issued_at"], "issued_at"),
                expires_at=_parse_time(payload["expires_at"], "expires_at"),
                algorithm=str(payload["algorithm"]),
                authority_epoch=authority_epoch,
                key_arn_digest=str(payload["key_arn_digest"]),
                schema_version=KMS_ATTESTATION_SCHEMA_VERSION,
            )
        except (TypeError, ValueError) as exc:
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_INVALID,
                "handle claims are invalid",
            ) from exc
        if (
            claims.issuer != self.issuer
            or claims.status != "succeeded"
            or claims.algorithm != KMS_SIGNING_ALGORITHM
            or claims.authority_epoch is None
            or claims.authority_epoch < 1
            or re.fullmatch(r"[0-9a-f]{64}", claims.key_id) is None
            or re.fullmatch(r"[0-9a-f]{64}", claims.key_arn_digest or "") is None
            or re.fullmatch(r"[0-9a-f]{64}", claims.receipt_digest) is None
            or re.fullmatch(r"[0-9a-f]{64}", claims.nonce) is None
            or claims.expires_at <= claims.issued_at
            or claims.expires_at - claims.issued_at > MAX_ATTESTATION_TTL
        ):
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_INVALID,
                "handle claim constraints are invalid",
            )
        entry = self.keyring.find(claims.key_id, claims.authority_epoch)
        if entry.key_arn_digest != claims.key_arn_digest:
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_INVALID,
                "handle KMS key binding is invalid",
            )
        if entry.state is VerificationKeyState.REVOKED:
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_INVALID,
                "handle key epoch is revoked",
            )
        try:
            _public_key(entry.public_key_der).verify(
                signature,
                body,
                ec.ECDSA(hashes.SHA256()),
            )
        except InvalidSignature as exc:
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_INVALID,
                "handle signature is invalid",
            ) from exc
        now = _aware(self._clock(), "clock")
        if claims.issued_at > now + self._clock_skew:
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_INVALID,
                "handle issue time is in the future",
            )
        if claims.expires_at < now:
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_EXPIRED,
                "handle has expired",
            )
        if claims.issued_at < entry.signing_not_before:
            raise OutcomeAttestationError(
                OUTCOME_ATTESTATION_INVALID,
                "handle predates key epoch activation",
            )
        if entry.state is VerificationKeyState.RETIRING:
            assert entry.signing_not_after is not None
            assert entry.verify_until is not None
            if claims.issued_at > entry.signing_not_after or now > entry.verify_until:
                raise OutcomeAttestationError(
                    OUTCOME_ATTESTATION_INVALID,
                    "handle falls outside the retiring-key overlap",
                )
        return claims
