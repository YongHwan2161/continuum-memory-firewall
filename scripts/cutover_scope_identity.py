"""Cut the runtime secret over to a generated, RLS-confined SQL login."""

from __future__ import annotations

import argparse
from collections.abc import Callable
import json
import secrets
import time
from urllib.parse import quote, urlsplit, urlunsplit

from continuum.migrate import Migrator
from continuum.scope_roles import (
    configure_scope_read_policies,
    provision_scope_role,
    scope_role_name,
    verify_scope_role,
)
from continuum.store import (
    database_url_user,
    pin_database_tls_root,
    psycopg_connection_factory,
)
from continuum.tenant_control import (
    CONTROL_PLANE_USER,
    DatabaseTenantControlPlane,
    bind_caller_scope,
    provision_control_plane_role,
    verify_control_plane_role,
)


def _secret_payload(
    client: object,
    secret_id: str,
    *,
    attempts: int = 12,
    delay_seconds: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
) -> object:
    """Read a secret after bounded IAM propagation without printing its value."""

    if attempts < 1 or delay_seconds < 0:
        raise ValueError("secret access retry bounds are invalid")
    for attempt in range(1, attempts + 1):
        try:
            value = client.get_secret_value(SecretId=secret_id)["SecretString"]
            break
        except Exception as error:
            response = getattr(error, "response", {})
            code = response.get("Error", {}).get("Code")
            if code != "AccessDeniedException" or attempt == attempts:
                raise
            sleep(delay_seconds)
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


def _verify_role_options_empty(
    connect: Callable[[], object],
    usernames: tuple[str, ...],
) -> bool:
    """Fail closed unless every bootstrap identity has no elevated options."""

    if not usernames or any(not username for username in usernames):
        raise ValueError("role option verification requires named identities")
    placeholders = ", ".join("%s" for _ in usernames)
    with connect() as connection:
        rows = connection.execute(
            "SELECT username, options FROM [SHOW ROLES] "
            f"WHERE username IN ({placeholders})",
            usernames,
        ).fetchall()
    observed = {str(row[0]): tuple(row[1] or ()) for row in rows}
    if set(observed) != set(usernames):
        raise RuntimeError("bootstrap role option evidence is incomplete")
    if any(observed.values()):
        raise RuntimeError("bootstrap role options are still elevated")
    return True


def main() -> None:
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - deployment dependency
        raise RuntimeError("boto3 is required for the live cutover") from exc

    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-secret-id", required=True)
    parser.add_argument("--migrator-secret-id", required=True)
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--bedrock-region", default="ap-northeast-2")
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
    caller_id, scope = next(iter(caller_scopes.items()))
    if not isinstance(caller_id, str) or not caller_id:
        raise RuntimeError("caller id must be a non-empty string")
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
    runtime_secret_updated = False
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
        runtime_secret_updated = True
        password = ""
    if runtime_payload.get("bedrock_region") != args.bedrock_region:
        runtime_payload["bedrock_region"] = args.bedrock_region
        runtime_secret_updated = True
    control_plane_url = runtime_payload.get("control_plane_database_url")
    control_plane_reused = (
        isinstance(control_plane_url, str)
        and database_url_user(control_plane_url) == CONTROL_PLANE_USER
    )
    control_plane_bootstrap_options_revoked = False
    if control_plane_reused:
        control_plane_url = pin_database_tls_root(control_plane_url, args.ca_cert)
    else:
        control_plane_password = secrets.token_urlsafe(48)
        control_plane_provisioned = provision_control_plane_role(
            migrator_url,
            password=control_plane_password,
            revoke_bootstrap_user=database_url_user(migrator_url),
        )
        control_plane_bootstrap_options_revoked = control_plane_provisioned[
            "bootstrap_options_revoked"
        ]
        control_plane_url = _replace_login(
            migrator_url,
            user=CONTROL_PLANE_USER,
            password=control_plane_password,
        )
        control_plane_password = ""
        runtime_secret_updated = True
    binding = bind_caller_scope(
        migrator_url,
        caller_id=caller_id,
        tenant_id=tenant_id,
        incident_id=incident_id,
        actor="github-oidc-deployer",
        reason="authenticated MCP tenant-control-plane cutover",
    )
    scope_database_urls = runtime_payload.get("scope_database_urls")
    if not isinstance(scope_database_urls, dict):
        scope_database_urls = {}
    if scope_database_urls.get(expected_role) != runtime_url:
        scope_database_urls[expected_role] = runtime_url
        runtime_secret_updated = True
    if runtime_payload.get("control_plane_database_url") != control_plane_url:
        runtime_payload["control_plane_database_url"] = control_plane_url
        runtime_secret_updated = True
    if runtime_payload.get("scope_database_urls") != scope_database_urls:
        runtime_payload["scope_database_urls"] = scope_database_urls
        runtime_secret_updated = True
    configure_scope_read_policies(
        migrator_url,
        tenant_id=tenant_id,
        incident_id=incident_id,
    )
    verified = verify_scope_role(
        runtime_url,
        tenant_id=tenant_id,
        incident_id=incident_id,
        forbidden_memory_id=args.forbidden_memory_id,
    )
    control_verified = verify_control_plane_role(control_plane_url)
    control_plane_bootstrap_options_revoked = _verify_role_options_empty(
        psycopg_connection_factory(migrator_url),
        (database_url_user(migrator_url), CONTROL_PLANE_USER),
    )
    resolved = DatabaseTenantControlPlane(
        psycopg_connection_factory(control_plane_url)
    ).resolve(caller_id)
    if resolved.sql_role != expected_role or resolved.binding_version != binding[
        "binding_version"
    ]:
        raise RuntimeError("audited tenant binding did not resolve to the scope role")
    if runtime_secret_updated:
        secrets_client.put_secret_value(
            SecretId=args.runtime_secret_id,
            SecretString=json.dumps(
                runtime_payload,
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
    runtime_url = ""
    control_plane_url = ""
    print(
        json.dumps(
            {
                "ok": True,
                "migration": migration.as_dict(),
                "scope_role": expected_role,
                "identity_reused": identity_reused,
                "bedrock_region": args.bedrock_region,
                "runtime_secret_updated": runtime_secret_updated,
                "tenant_control_plane_active": True,
                "control_plane_identity_reused": control_plane_reused,
                "control_plane_memory_denied": control_verified[
                    "canonical_memory_denied"
                ],
                "control_plane_bootstrap_options_revoked": (
                    control_plane_bootstrap_options_revoked
                ),
                "binding_version": binding["binding_version"],
                "binding_event": binding["event_type"],
                "legacy_runtime_privileges_revoked": True,
                "visible_rows": verified["visible_rows"],
                "visible_incidents": verified["visible_incidents"],
                "visible_audits": verified["visible_audits"],
                "all_visible_rows_in_scope": verified[
                    "all_visible_rows_in_scope"
                ],
                "all_visible_incidents_in_scope": verified[
                    "all_visible_incidents_in_scope"
                ],
                "all_visible_audits_in_scope": verified[
                    "all_visible_audits_in_scope"
                ],
                "forbidden_memory_visible": verified["forbidden_memory_visible"],
                "negative_checks": verified["denied"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
