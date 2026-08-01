"""Short-lived caller identity and fail-closed scope binding.

The HTTP bearer proves a caller identity.  Scope is never accepted from an MCP
tool argument or token-controlled tenant claim; it is resolved from the
server-owned registry after the Cognito signature and lifetime are verified.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import json
import time
from typing import Any, Iterator, Mapping, Protocol
from urllib.parse import urlsplit


class IdentityVerificationError(RuntimeError):
    """Raised without exposing token details when identity verification fails."""


@dataclass(frozen=True, slots=True)
class CallerIdentity:
    caller_id: str
    tenant_id: str
    incident_id: str


class TokenVerifier(Protocol):
    def verify(self, token: str) -> CallerIdentity: ...


_CURRENT_CALLER: ContextVar[CallerIdentity | None] = ContextVar(
    "continuum_current_caller",
    default=None,
)


def current_caller() -> CallerIdentity:
    identity = _CURRENT_CALLER.get()
    if identity is None:
        raise IdentityVerificationError("authenticated caller context is required")
    return identity


@contextmanager
def bind_caller(identity: CallerIdentity) -> Iterator[None]:
    token = _CURRENT_CALLER.set(identity)
    try:
        yield
    finally:
        _CURRENT_CALLER.reset(token)


class ScopeRegistry:
    """Server-owned mapping from an authenticated client to one database scope."""

    def __init__(self, scopes: Mapping[str, CallerIdentity]) -> None:
        if not scopes:
            raise ValueError("at least one caller scope is required")
        self._scopes = dict(scopes)

    @classmethod
    def from_json(cls, value: str) -> "ScopeRegistry":
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            raise RuntimeError("CONTINUUM_CALLER_SCOPES_JSON must be valid JSON") from exc
        if not isinstance(payload, dict) or not payload:
            raise RuntimeError("CONTINUUM_CALLER_SCOPES_JSON must be a non-empty object")

        scopes: dict[str, CallerIdentity] = {}
        for caller_id, raw_scope in payload.items():
            if not isinstance(caller_id, str) or not caller_id:
                raise RuntimeError("caller ids must be non-empty strings")
            if not isinstance(raw_scope, dict):
                raise RuntimeError("each caller scope must be an object")
            tenant_id = raw_scope.get("tenant_id")
            incident_id = raw_scope.get("incident_id")
            if not isinstance(tenant_id, str) or not tenant_id:
                raise RuntimeError("caller tenant_id must be a non-empty string")
            if not isinstance(incident_id, str) or not incident_id:
                raise RuntimeError("caller incident_id must be a non-empty string")
            scopes[caller_id] = CallerIdentity(
                caller_id=caller_id,
                tenant_id=tenant_id,
                incident_id=incident_id,
            )
        return cls(scopes)

    @property
    def caller_ids(self) -> frozenset[str]:
        return frozenset(self._scopes)

    def resolve(self, caller_id: str) -> CallerIdentity:
        try:
            return self._scopes[caller_id]
        except KeyError as exc:
            raise IdentityVerificationError("caller is not authorized") from exc


class CognitoTokenVerifier:
    """Verify Cognito RS256 access tokens and bind them to server-owned scope."""

    def __init__(
        self,
        *,
        issuer: str,
        required_scope: str,
        registry: ScopeRegistry,
        max_token_lifetime_seconds: int = 600,
        clock: Any = time.time,
    ) -> None:
        parts = urlsplit(issuer)
        if parts.scheme != "https" or not parts.netloc or parts.query or parts.fragment:
            raise ValueError("OIDC issuer must be an absolute HTTPS URL")
        if not required_scope or any(character.isspace() for character in required_scope):
            raise ValueError("required OAuth scope must be one non-empty token")
        if not 300 <= max_token_lifetime_seconds <= 900:
            raise ValueError("maximum token lifetime must be between 5 and 15 minutes")

        try:
            import jwt
        except ImportError as exc:  # pragma: no cover - optional package boundary
            raise RuntimeError("install the MCP extra: pip install '.[mcp]'") from exc

        self._jwt = jwt
        self._issuer = issuer.rstrip("/")
        self._required_scope = required_scope
        self._registry = registry
        self._maximum_lifetime = max_token_lifetime_seconds
        self._clock = clock
        self._jwks = jwt.PyJWKClient(
            f"{self._issuer}/.well-known/jwks.json",
            cache_jwk_set=True,
            lifespan=300,
            cache_keys=True,
            max_cached_keys=8,
        )

    def verify(self, token: str) -> CallerIdentity:
        if not token or len(token) > 16_384:
            raise IdentityVerificationError("access token is invalid")
        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token)
            claims = self._jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                options={
                    "verify_aud": False,
                    "require": ["client_id", "exp", "iat", "iss", "token_use"],
                },
                leeway=30,
            )
            return self._identity_from_claims(claims)
        except IdentityVerificationError:
            raise
        except Exception as exc:
            raise IdentityVerificationError("access token is invalid") from exc

    def _identity_from_claims(self, claims: Mapping[str, Any]) -> CallerIdentity:
        if claims.get("token_use") != "access":
            raise IdentityVerificationError("an access token is required")
        caller_id = claims.get("client_id")
        if not isinstance(caller_id, str):
            raise IdentityVerificationError("client identity is missing")

        issued_at = claims.get("iat")
        expires_at = claims.get("exp")
        if not isinstance(issued_at, (int, float)) or not isinstance(
            expires_at, (int, float)
        ):
            raise IdentityVerificationError("token lifetime is invalid")
        lifetime = float(expires_at) - float(issued_at)
        now = float(self._clock())
        if lifetime < 1 or lifetime > self._maximum_lifetime:
            raise IdentityVerificationError("token lifetime exceeds policy")
        if float(issued_at) > now + 30 or float(expires_at) <= now - 30:
            raise IdentityVerificationError("token is outside its validity window")

        raw_scopes = claims.get("scope", "")
        if not isinstance(raw_scopes, str):
            raise IdentityVerificationError("token scope is invalid")
        if self._required_scope not in raw_scopes.split():
            raise IdentityVerificationError("required scope is missing")
        return self._registry.resolve(caller_id)
