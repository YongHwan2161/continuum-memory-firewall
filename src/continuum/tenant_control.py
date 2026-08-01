"""Audited caller-to-scope control plane with separated SQL authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import quote, urlsplit, urlunsplit

from continuum.identity import CallerIdentity, IdentityVerificationError
from continuum.scope_roles import scope_role_name
from continuum.store import psycopg_connection_factory


CONTROL_PLANE_ROLE = "continuum_control_plane_role"
CONTROL_PLANE_USER = "continuum_control_plane"


@dataclass(frozen=True, slots=True)
class TenantBinding:
    caller_id: str
    tenant_id: str
    incident_id: str
    sql_role: str
    binding_version: int
    status: str

    def identity(self) -> CallerIdentity:
        return CallerIdentity(
            caller_id=self.caller_id,
            tenant_id=self.tenant_id,
            incident_id=self.incident_id,
            sql_role=self.sql_role,
            binding_version=self.binding_version,
        )


def database_url_with_login(database_url: str, *, user: str, password: str) -> str:
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


class DatabaseTenantControlPlane:
    """Resolve only active, versioned bindings owned by the database."""

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect

    def resolve(self, caller_id: str) -> CallerIdentity:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT tenant_id::STRING, incident_id::STRING, sql_role,
                       binding_version, status
                FROM tenant_scope_bindings
                WHERE caller_id = %s
                """,
                (caller_id,),
            ).fetchone()
        if row is None or row[4] != "active":
            raise IdentityVerificationError("caller is not authorized")
        tenant_id, incident_id, sql_role, version, status = row
        expected_role = scope_role_name(tenant_id, incident_id)
        if sql_role != expected_role or int(version) < 1:
            raise IdentityVerificationError("caller binding is invalid")
        return TenantBinding(
            caller_id=caller_id,
            tenant_id=tenant_id,
            incident_id=incident_id,
            sql_role=sql_role,
            binding_version=int(version),
            status=status,
        ).identity()


def _required_text(name: str, value: str, *, maximum: int = 500) -> str:
    if not value or len(value) > maximum or any(ch in value for ch in "\r\n\x00"):
        raise ValueError(f"{name} must be a bounded single-line value")
    return value


def bind_caller_scope(
    migrator_database_url: str,
    *,
    caller_id: str,
    tenant_id: str,
    incident_id: str,
    actor: str,
    reason: str,
) -> dict[str, Any]:
    caller_id = _required_text("caller_id", caller_id, maximum=256)
    actor = _required_text("actor", actor, maximum=256)
    reason = _required_text("reason", reason)
    sql_role = scope_role_name(tenant_id, incident_id)
    connect = psycopg_connection_factory(migrator_database_url)
    with connect() as connection:
        prior = connection.execute(
            """
            SELECT tenant_id::STRING, incident_id::STRING, sql_role,
                   binding_version, status
            FROM tenant_scope_bindings
            WHERE caller_id = %s
            FOR UPDATE
            """,
            (caller_id,),
        ).fetchone()
        if prior and prior[:3] == (tenant_id, incident_id, sql_role) and prior[4] == "active":
            return {
                "ok": True,
                "changed": False,
                "caller_id": caller_id,
                "sql_role": sql_role,
                "binding_version": int(prior[3]),
                "event_type": "unchanged",
            }
        version = 1 if prior is None else int(prior[3]) + 1
        event_type = "bound" if prior is None else "rebound"
        connection.execute(
            """
            INSERT INTO tenant_scope_bindings (
                caller_id, tenant_id, incident_id, sql_role, binding_version,
                status, created_by, reason, updated_at
            ) VALUES (%s, %s, %s, %s, %s, 'active', %s, %s, now())
            ON CONFLICT (caller_id) DO UPDATE SET
                tenant_id = excluded.tenant_id,
                incident_id = excluded.incident_id,
                sql_role = excluded.sql_role,
                binding_version = excluded.binding_version,
                status = excluded.status,
                updated_at = excluded.updated_at,
                created_by = excluded.created_by,
                reason = excluded.reason
            """,
            (caller_id, tenant_id, incident_id, sql_role, version, actor, reason),
        )
        connection.execute(
            """
            INSERT INTO tenant_scope_binding_audit (
                caller_id, tenant_id, incident_id, sql_role, binding_version,
                event_type, actor, reason
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                caller_id,
                tenant_id,
                incident_id,
                sql_role,
                version,
                event_type,
                actor,
                reason,
            ),
        )
    return {
        "ok": True,
        "changed": True,
        "caller_id": caller_id,
        "sql_role": sql_role,
        "binding_version": version,
        "event_type": event_type,
    }


def disable_caller(
    migrator_database_url: str,
    *,
    caller_id: str,
    actor: str,
    reason: str,
) -> dict[str, Any]:
    caller_id = _required_text("caller_id", caller_id, maximum=256)
    actor = _required_text("actor", actor, maximum=256)
    reason = _required_text("reason", reason)
    connect = psycopg_connection_factory(migrator_database_url)
    with connect() as connection:
        prior = connection.execute(
            """
            SELECT tenant_id::STRING, incident_id::STRING, sql_role,
                   binding_version, status
            FROM tenant_scope_bindings
            WHERE caller_id = %s
            FOR UPDATE
            """,
            (caller_id,),
        ).fetchone()
        if prior is None:
            raise ValueError("caller binding does not exist")
        if prior[4] == "disabled":
            return {"ok": True, "changed": False, "binding_version": int(prior[3])}
        version = int(prior[3]) + 1
        connection.execute(
            """
            UPDATE tenant_scope_bindings
            SET status = 'disabled', binding_version = %s,
                updated_at = now(), created_by = %s, reason = %s
            WHERE caller_id = %s
            """,
            (version, actor, reason, caller_id),
        )
        connection.execute(
            """
            INSERT INTO tenant_scope_binding_audit (
                caller_id, tenant_id, incident_id, sql_role, binding_version,
                event_type, actor, reason
            ) VALUES (%s, %s, %s, %s, %s, 'disabled', %s, %s)
            """,
            (caller_id, prior[0], prior[1], prior[2], version, actor, reason),
        )
    return {"ok": True, "changed": True, "binding_version": version}


def provision_control_plane_role(
    migrator_database_url: str,
    *,
    password: str | None = None,
    revoke_bootstrap_user: str | None = None,
) -> dict[str, Any]:
    if password is not None and len(password) < 32:
        raise ValueError("control-plane SQL password must be at least 32 characters")
    connect = psycopg_connection_factory(migrator_database_url)
    from psycopg import sql

    try:
        with connect() as connection:
            database_name, current_user = connection.execute(
                "SELECT current_database(), current_user"
            ).fetchone()
            if (
                revoke_bootstrap_user is not None
                and current_user != revoke_bootstrap_user
            ):
                raise RuntimeError("control-plane bootstrap SQL identity mismatch")
            connection.execute(
                sql.SQL("CREATE ROLE IF NOT EXISTS {} NOLOGIN").format(
                    sql.Identifier(CONTROL_PLANE_ROLE)
                )
            )
            connection.execute(
                sql.SQL("CREATE USER IF NOT EXISTS {}").format(
                    sql.Identifier(CONTROL_PLANE_USER)
                )
            )
            # The bootstrap identity intentionally has CREATEROLE/CREATELOGIN,
            # not ADMIN OPTION on the built-in admin role. A defensive REVOKE
            # here would therefore widen the bootstrap requirement. A fresh
            # login is negatively verified below before it can be published.
            connection.execute(
                sql.SQL("ALTER ROLE {} WITH NOBYPASSRLS").format(
                    sql.Identifier(CONTROL_PLANE_USER)
                )
            )
            if password is not None:
                connection.execute(
                    sql.SQL("ALTER USER {} WITH PASSWORD {}").format(
                        sql.Identifier(CONTROL_PLANE_USER),
                        sql.Literal(password),
                    )
                )
            connection.execute(
                sql.SQL("GRANT {} TO {}").format(
                    sql.Identifier(CONTROL_PLANE_ROLE),
                    sql.Identifier(CONTROL_PLANE_USER),
                )
            )
            connection.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(database_name),
                    sql.Identifier(CONTROL_PLANE_ROLE),
                )
            )
            connection.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                    sql.Identifier(CONTROL_PLANE_ROLE)
                )
            )
            connection.execute(
                sql.SQL(
                    "GRANT SELECT ON TABLE public.tenant_scope_bindings, "
                    "public.tenant_scope_binding_audit TO {}"
                ).format(sql.Identifier(CONTROL_PLANE_ROLE))
            )
            connection.execute(
                sql.SQL(
                    "REVOKE ALL ON TABLE public.incidents, public.memory_candidates, "
                    "public.canonical_memories, public.action_attempts, "
                    "public.retrieval_audit FROM {}"
                ).format(sql.Identifier(CONTROL_PLANE_ROLE))
            )
        fresh_identity_verified = False
        if password is not None:
            control_plane_url = database_url_with_login(
                migrator_database_url,
                user=CONTROL_PLANE_USER,
                password=password,
            )
            fresh_identity_verified = verify_control_plane_role(
                control_plane_url
            )["canonical_memory_denied"]
    finally:
        if revoke_bootstrap_user is not None:
            _revoke_bootstrap_role_options(connect, revoke_bootstrap_user)
    return {
        "ok": True,
        "database": database_name,
        "user": CONTROL_PLANE_USER,
        "fresh_identity_verified": fresh_identity_verified,
        "bootstrap_options_revoked": revoke_bootstrap_user is not None,
    }


def _revoke_bootstrap_role_options(
    connect: Callable[[], Any], expected_user: str
) -> None:
    """Remove the one-time role/login creation options, even after failure."""

    expected_user = _required_text("bootstrap user", expected_user, maximum=128)
    from psycopg import sql

    with connect() as connection:
        current_user = connection.execute("SELECT current_user").fetchone()[0]
        if current_user != expected_user:
            raise RuntimeError("refusing to revoke options from an unexpected SQL user")
        connection.execute(
            sql.SQL("ALTER USER {} WITH NOCREATEROLE NOCREATELOGIN").format(
                sql.Identifier(expected_user)
            )
        )


def verify_control_plane_role(database_url: str) -> dict[str, Any]:
    connect = psycopg_connection_factory(database_url)
    with connect() as connection:
        current_user = connection.execute("SELECT current_user").fetchone()[0]
        if current_user != CONTROL_PLANE_USER:
            raise RuntimeError("control-plane connection uses the wrong SQL identity")
        binding_count = connection.execute(
            "SELECT count(*) FROM tenant_scope_bindings"
        ).fetchone()[0]
    with connect() as connection:
        try:
            connection.execute("SELECT count(*) FROM canonical_memories").fetchone()
        except Exception as exc:
            connection.rollback()
            if getattr(exc, "sqlstate", None) != "42501":
                raise
        else:
            raise RuntimeError("control-plane identity can read canonical memory")
    return {
        "ok": True,
        "current_user": current_user,
        "binding_count": binding_count,
        "canonical_memory_denied": True,
    }
