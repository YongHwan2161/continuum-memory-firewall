"""Load one scoped runtime secret into a rootless systemd environment file."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
from typing import Mapping


REQUIRED_STRING_FIELDS = (
    "database_url",
    "oidc_issuer",
    "oidc_required_scope",
    "bedrock_region",
    "public_base_url",
)
CALLER_SCOPES_FIELD = "caller_scopes"
CONTROL_PLANE_DATABASE_URL_FIELD = "control_plane_database_url"
SCOPE_DATABASE_URLS_FIELD = "scope_database_urls"


def _quote_environment_value(value: str) -> str:
    if "\x00" in value or "\n" in value or "\r" in value:
        raise ValueError("runtime secret values must be single-line strings")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _parse_secret(value: str) -> dict[str, object]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError("runtime secret must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("runtime secret must be a JSON object")
    parsed: dict[str, object] = {}
    for field in REQUIRED_STRING_FIELDS:
        item = payload.get(field)
        if not isinstance(item, str) or not item:
            raise RuntimeError(f"runtime secret field {field!r} is required")
        parsed[field] = item
    caller_scopes = payload.get(CALLER_SCOPES_FIELD)
    if not isinstance(caller_scopes, dict) or not caller_scopes:
        raise RuntimeError("runtime secret caller_scopes must be a non-empty object")
    parsed[CALLER_SCOPES_FIELD] = caller_scopes
    control_plane_url = payload.get(CONTROL_PLANE_DATABASE_URL_FIELD)
    scope_database_urls = payload.get(SCOPE_DATABASE_URLS_FIELD)
    if (control_plane_url is None) != (scope_database_urls is None):
        raise RuntimeError(
            "runtime secret control-plane fields must be configured together"
        )
    if control_plane_url is not None:
        if not isinstance(control_plane_url, str) or not control_plane_url:
            raise RuntimeError("runtime secret control-plane URL must be a string")
        if not isinstance(scope_database_urls, dict) or not scope_database_urls:
            raise RuntimeError(
                "runtime secret scope database URLs must be a non-empty object"
            )
        if not all(
            isinstance(role, str)
            and role
            and isinstance(url, str)
            and url
            for role, url in scope_database_urls.items()
        ):
            raise RuntimeError("runtime secret scope database URL entries are invalid")
        parsed[CONTROL_PLANE_DATABASE_URL_FIELD] = control_plane_url
        parsed[SCOPE_DATABASE_URLS_FIELD] = scope_database_urls
    return parsed


def _render_environment(payload: Mapping[str, object]) -> str:
    names = {
        "database_url": "CONTINUUM_DATABASE_URL",
        "oidc_issuer": "CONTINUUM_OIDC_ISSUER",
        "oidc_required_scope": "CONTINUUM_OIDC_REQUIRED_SCOPE",
        "bedrock_region": "CONTINUUM_BEDROCK_REGION",
        "public_base_url": "CONTINUUM_PUBLIC_BASE_URL",
        "caller_scopes": "CONTINUUM_CALLER_SCOPES_JSON",
        "control_plane_database_url": "CONTINUUM_CONTROL_PLANE_DATABASE_URL",
        "scope_database_urls": "CONTINUUM_SCOPE_DATABASE_URLS_JSON",
    }
    values = {
        field: str(payload[field]) for field in REQUIRED_STRING_FIELDS
    }
    values[CALLER_SCOPES_FIELD] = json.dumps(
        payload[CALLER_SCOPES_FIELD],
        separators=(",", ":"),
        sort_keys=True,
    )
    fields = [*REQUIRED_STRING_FIELDS, CALLER_SCOPES_FIELD]
    if CONTROL_PLANE_DATABASE_URL_FIELD in payload:
        values[CONTROL_PLANE_DATABASE_URL_FIELD] = str(
            payload[CONTROL_PLANE_DATABASE_URL_FIELD]
        )
        values[SCOPE_DATABASE_URLS_FIELD] = json.dumps(
            payload[SCOPE_DATABASE_URLS_FIELD],
            separators=(",", ":"),
            sort_keys=True,
        )
        fields.extend(
            (CONTROL_PLANE_DATABASE_URL_FIELD, SCOPE_DATABASE_URLS_FIELD)
        )
    return "".join(
        f"{names[field]}={_quote_environment_value(values[field])}\n"
        for field in fields
    )


def load_secret(*, secret_arn: str, region: str) -> dict[str, object]:
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


def write_environment(path: Path, payload: Mapping[str, object]) -> None:
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
