"""Load one scoped runtime secret into a rootless systemd environment file."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
from typing import Mapping


REQUIRED_FIELDS = (
    "database_url",
    "bearer_token",
    "tenant_id",
    "incident_id",
    "public_base_url",
)


def _quote_environment_value(value: str) -> str:
    if "\x00" in value or "\n" in value or "\r" in value:
        raise ValueError("runtime secret values must be single-line strings")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _parse_secret(value: str) -> dict[str, str]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError("runtime secret must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("runtime secret must be a JSON object")
    parsed: dict[str, str] = {}
    for field in REQUIRED_FIELDS:
        item = payload.get(field)
        if not isinstance(item, str) or not item:
            raise RuntimeError(f"runtime secret field {field!r} is required")
        parsed[field] = item
    if len(parsed["bearer_token"]) < 32:
        raise RuntimeError("runtime bearer token must be at least 32 characters")
    return parsed


def _render_environment(payload: Mapping[str, str]) -> str:
    names = {
        "database_url": "CONTINUUM_DATABASE_URL",
        "bearer_token": "CONTINUUM_MCP_BEARER_TOKEN",
        "tenant_id": "CONTINUUM_TENANT_ID",
        "incident_id": "CONTINUUM_INCIDENT_ID",
        "public_base_url": "CONTINUUM_PUBLIC_BASE_URL",
    }
    return "".join(
        f"{names[field]}={_quote_environment_value(payload[field])}\n"
        for field in REQUIRED_FIELDS
    )


def load_secret(*, secret_arn: str, region: str) -> dict[str, str]:
    result = subprocess.run(
        [
            "aws",
            "secretsmanager",
            "get-secret-value",
            "--secret-id",
            secret_arn,
            "--region",
            region,
            "--query",
            "SecretString",
            "--output",
            "text",
            "--no-cli-pager",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return _parse_secret(result.stdout)


def write_environment(path: Path, payload: Mapping[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(_render_environment(payload))
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--secret-arn", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = load_secret(secret_arn=args.secret_arn, region=args.region)
    write_environment(args.output, payload)


if __name__ == "__main__":
    main()
