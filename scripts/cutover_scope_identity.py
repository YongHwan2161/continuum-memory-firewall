"""Cut the runtime secret over to a generated, RLS-confined SQL login."""

from __future__ import annotations

import argparse
import json
import secrets
from urllib.parse import quote, urlsplit, urlunsplit

import boto3

from continuum.migrate import Migrator
from continuum.scope_roles import (
    provision_scope_role,
    scope_role_name,
    verify_scope_role,
)
from continuum.store import (
    database_url_user,
    pin_database_tls_root,
    psycopg_connection_factory,
)


def _secret_payload(client: object, secret_id: str) -> object:
    value = client.get_secret_value(SecretId=secret_id)["SecretString"]
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _database_url(payload: object) -> str:
    if isinstance(payload, str) and payload:
        return payload
    if isinstance(payload, dict):
        value = payload.get("database_url")
        if isinstance(value, str) and value:
            return value
    raise RuntimeError("database secret does not contain database_url")


def _replace_login(database_url: str, *, user: str, password: str) -> str:
    parts = urlsplit(database_url)
    if not parts.hostname:
        raise RuntimeError("database URL has no hostname")
    host = parts.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = f"{quote(user, safe='')}:{quote(password, safe='')}@{host}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, ""))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-secret-id", required=True)
    parser.add_argument("--migrator-secret-id", required=True)
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument(
        "--ca-cert",
        default="/opt/continuum/cockroach-ca.crt",
    )
    parser.add_argument("--forbidden-memory-id")
    args = parser.parse_args()

    secrets_client = boto3.client("secretsmanager", region_name=args.region)
    runtime_payload = _secret_payload(secrets_client, args.runtime_secret_id)
    if not isinstance(runtime_payload, dict):
        raise RuntimeError("runtime secret must be a JSON object")
    caller_scopes = runtime_payload.get("caller_scopes")
    if not isinstance(caller_scopes, dict) or len(caller_scopes) != 1:
        raise RuntimeError("cutover requires exactly one registered demo caller")
    scope = next(iter(caller_scopes.values()))
    if not isinstance(scope, dict):
        raise RuntimeError("caller scope must be an object")
    tenant_id = scope.get("tenant_id")
    incident_id = scope.get("incident_id")
    if not isinstance(tenant_id, str) or not isinstance(incident_id, str):
        raise RuntimeError("caller scope is incomplete")

    migrator_url = pin_database_tls_root(
        _database_url(_secret_payload(secrets_client, args.migrator_secret_id)),
        args.ca_cert,
    )
    migration = Migrator(psycopg_connection_factory(migrator_url)).migrate()
    runtime_url = pin_database_tls_root(
        _database_url(runtime_payload),
        args.ca_cert,
    )
    expected_role = scope_role_name(tenant_id, incident_id)
    identity_reused = database_url_user(runtime_url) == expected_role
    if not identity_reused:
        password = secrets.token_urlsafe(48)
        provisioned = provision_scope_role(
            migrator_url,
            tenant_id=tenant_id,
            incident_id=incident_id,
            password=password,
        )
        runtime_url = _replace_login(
            runtime_url,
            user=provisioned["scope_role"],
            password=password,
        )
        runtime_payload["database_url"] = runtime_url
        secrets_client.put_secret_value(
            SecretId=args.runtime_secret_id,
            SecretString=json.dumps(
                runtime_payload,
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
        password = ""
    verified = verify_scope_role(
        runtime_url,
        tenant_id=tenant_id,
        incident_id=incident_id,
        forbidden_memory_id=args.forbidden_memory_id,
    )
    runtime_url = ""
    print(
        json.dumps(
            {
                "ok": True,
                "migration": migration.as_dict(),
                "scope_role": expected_role,
                "identity_reused": identity_reused,
                "legacy_runtime_privileges_revoked": True,
                "visible_rows": verified["visible_rows"],
                "all_visible_rows_in_scope": verified[
                    "all_visible_rows_in_scope"
                ],
                "forbidden_memory_visible": verified["forbidden_memory_visible"],
                "negative_checks": verified["denied"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
