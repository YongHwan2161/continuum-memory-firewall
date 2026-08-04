"""AWS Lambda sandbox provider adapter with durable receipt lookup."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from typing import Any, Mapping, Protocol

from continuum.episode import OutcomeStatus, ProviderOutcome, validate_outcome
from continuum.outbox import (
    MAX_IDEMPOTENCY_KEY_LENGTH,
    ProviderCapabilityManifest,
    _validate_provider,
)


class LambdaRuntime(Protocol):
    def invoke(self, **kwargs: Any) -> Mapping[str, Any]: ...


class AwsLambdaSandboxProvider:
    """Invoke the project-owned non-production effect sandbox."""

    def __init__(
        self,
        *,
        function_name: str,
        region: str,
        name: str = "continuum-aws-sandbox-v1",
        runtime: LambdaRuntime | None = None,
        reconciliation_timeout: timedelta = timedelta(seconds=30),
    ) -> None:
        if not function_name.strip() or len(function_name) > 140:
            raise ValueError("function_name must be bounded")
        if runtime is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover - optional boundary
                raise RuntimeError("install boto3 to use the AWS sandbox provider") from exc
            runtime = boto3.client("lambda", region_name=region)
        self.name = _validate_provider(name)
        self.function_name = function_name.strip()
        self._runtime = runtime
        self.capabilities = ProviderCapabilityManifest(
            supports_idempotency=True,
            receipt_lookup=True,
            reconciliation_timeout=reconciliation_timeout,
        )

    def send(
        self,
        *,
        action_payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> ProviderOutcome:
        if len(idempotency_key) > MAX_IDEMPOTENCY_KEY_LENGTH:
            raise ValueError("idempotency key is too long")
        response = self._invoke(
            {
                "operation": "send",
                "provider": self.name,
                "idempotency_key": idempotency_key,
                "action_payload": dict(action_payload),
            }
        )
        outcome = self._outcome(response.get("outcome"))
        if outcome is None:
            raise RuntimeError("sandbox provider send returned no outcome")
        return outcome

    def lookup(self, *, idempotency_key: str) -> ProviderOutcome | None:
        if len(idempotency_key) > MAX_IDEMPOTENCY_KEY_LENGTH:
            raise ValueError("idempotency key is too long")
        response = self._invoke(
            {
                "operation": "lookup",
                "provider": self.name,
                "idempotency_key": idempotency_key,
            }
        )
        return self._outcome(response.get("outcome"))

    def _invoke(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            response = self._runtime.invoke(
                FunctionName=self.function_name,
                InvocationType="RequestResponse",
                Payload=json.dumps(
                    payload,
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8"),
            )
            if response.get("FunctionError"):
                raise RuntimeError("sandbox provider function returned an error")
            stream = response.get("Payload")
            raw = stream.read() if hasattr(stream, "read") else stream
            if not isinstance(raw, (bytes, bytearray)):
                raise RuntimeError("sandbox provider response payload is invalid")
            value = json.loads(raw)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError("sandbox provider invocation failed") from exc
        if not isinstance(value, Mapping) or value.get("schema_version") != 1:
            raise RuntimeError("sandbox provider response contract is invalid")
        return value

    def _outcome(self, value: object) -> ProviderOutcome | None:
        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise RuntimeError("sandbox provider outcome is invalid")
        try:
            status = OutcomeStatus(str(value["status"]))
            observed_at = datetime.fromisoformat(str(value["observed_at"]))
            verified_raw = value.get("verified_at")
            verified_at = (
                None
                if verified_raw is None
                else datetime.fromisoformat(str(verified_raw))
            )
            evidence = value["evidence"]
            if not isinstance(evidence, Mapping):
                raise ValueError("evidence is not an object")
            outcome = ProviderOutcome(
                provider=str(value["provider"]),
                status=status,
                provider_receipt_id=value.get("provider_receipt_id"),
                evidence=dict(evidence),
                observed_at=observed_at,
                verified_at=verified_at,
            )
            if outcome.provider != self.name:
                raise ValueError("provider name mismatch")
            validate_outcome(outcome)
            return outcome
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("sandbox provider outcome contract is invalid") from exc
