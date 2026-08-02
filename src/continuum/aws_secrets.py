"""Bounded AWS Secrets Manager reads for newly granted runtime roles."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import time
from typing import Any, Protocol


class SecretsManagerClient(Protocol):
    def get_secret_value(self, **kwargs: Any) -> Mapping[str, Any]: ...


def get_secret_string_with_backoff(
    client: SecretsManagerClient,
    secret_id: str,
    *,
    attempts: int = 24,
    delay_seconds: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Read one secret after bounded IAM propagation without logging its value."""

    if attempts < 1 or delay_seconds < 0:
        raise ValueError("secret access retry bounds are invalid")
    for attempt in range(1, attempts + 1):
        try:
            response = client.get_secret_value(SecretId=secret_id)
            value = response.get("SecretString")
            if not isinstance(value, str) or not value:
                raise RuntimeError("secret has no non-empty SecretString")
            return value
        except Exception as error:
            response = getattr(error, "response", {})
            code = response.get("Error", {}).get("Code")
            if code != "AccessDeniedException" or attempt == attempts:
                raise
            sleep(delay_seconds)
    raise AssertionError("bounded secret retry loop did not terminate")
