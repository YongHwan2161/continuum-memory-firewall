"""Provision one non-bypass CockroachDB identity per authorized caller scope."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from typing import Any
from uuid import UUID

from continuum.store import psycopg_connection_factory


LEGACY_RUNTIME_ROLE = "continuum_runtime_role"


def scope_role_name(tenant_id: str, incident_id: str) -> str:
    UUID(tenant_id)
    UUID(incident_id)
    digest = hashlib.sha256(
        f"{tenant_id}\x00{incident_id}".encode("ascii")
    ).hexdigest()[:16]
    return f"continuum_scope_{digest}"


def _password_statement(user: str, password: str):
    from psycopg import sql

    return sql.SQL("ALTER USER {} WITH PASSWORD {}").format(
        sql.Identifier(user),
        sql.Literal(password),
    )


def configure_scope_read_policies(
    migrator_database_url: str,
    *,
    tenant_id: str,
    incident_id: str,
) -> dict[str, Any]:
    """Give an existing scope login FK-safe and RETURNING-safe reads."""

    role_name = scope_role_name(tenant_id, incident_id)
    suffix = role_name.removeprefix("continuum_scope_")
    incident_policy = f"continuum_incident_select_{suffix}"
    audit_policy = f"continuum_audit_select_{suffix}"
    connect = psycopg_connection_factory(migrator_database_url)
    from psycopg import sql

    with connect() as connection:
        connection.execute(
            sql.SQL("GRANT SELECT ON TABLE public.incidents TO {}").format(
                sql.Identifier(role_name)
            )
        )
        connection.execute("ALTER TABLE public.incidents ENABLE ROW LEVEL SECURITY")
        connection.execute(
            sql.SQL("DROP POLICY IF EXISTS {} ON public.incidents").format(
                sql.Identifier(incident_policy)
            )
        )
        connection.execute(
            sql.SQL(
                "CREATE POLICY {} ON public.incidents "
                "FOR SELECT TO {} USING "
                "(tenant_id = {}::UUID AND incident_id = {}::UUID)"
            ).format(
                sql.Identifier(incident_policy),
                sql.Identifier(role_name),
                sql.Literal(tenant_id),
                sql.Literal(incident_id),
            )
        )
        connection.execute(
            sql.SQL("GRANT SELECT ON TABLE public.retrieval_audit TO {}").format(
                sql.Identifier(role_name)
            )
        )
        connection.execute(
            sql.SQL("DROP POLICY IF EXISTS {} ON public.retrieval_audit").format(
                sql.Identifier(audit_policy)
            )
        )
        connection.execute(
            sql.SQL(
                "CREATE POLICY {} ON public.retrieval_audit "
                "FOR SELECT TO {} USING "
                "(tenant_id = {}::UUID AND incident_id = {}::UUID)"
            ).format(
                sql.Identifier(audit_policy),
                sql.Identifier(role_name),
                sql.Literal(tenant_id),
                sql.Literal(incident_id),
            )
        )
    return {
        "scope_role": role_name,
        "policies": [incident_policy, audit_policy],
    }


def provision_scope_role(
    migrator_database_url: str,
    *,
    tenant_id: str,
    incident_id: str,
    password: str,
) -> dict[str, Any]:
    """Create a login whose SQL visibility is hard-bound by RLS policy."""

    if len(password) < 32:
        raise ValueError("scope SQL password must be at least 32 characters")
    role_name = scope_role_name(tenant_id, incident_id)
    suffix = role_name.removeprefix("continuum_scope_")
    canonical_policy = f"continuum_canonical_select_{suffix}"
    audit_policy = f"continuum_audit_insert_{suffix}"
    connect = psycopg_connection_factory(migrator_database_url)
    from psycopg import sql

    with connect() as connection:
        database_name, current_user = connection.execute(
            "SELECT current_database(), current_user"
        ).fetchone()
        connection.execute(
            sql.SQL("CREATE USER IF NOT EXISTS {}").format(sql.Identifier(role_name))
        )
        connection.execute(
            sql.SQL("ALTER ROLE {} WITH NOBYPASSRLS").format(
                sql.Identifier(role_name)
            )
        )
        connection.execute(_password_statement(role_name, password))
        connection.execute(
            sql.SQL("ALTER ROLE {} SET row_security = on").format(
                sql.Identifier(role_name)
            )
        )
        connection.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(database_name),
                sql.Identifier(role_name),
            )
        )
        connection.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                sql.Identifier(role_name)
            )
        )
        connection.execute(
            sql.SQL("GRANT SELECT ON TABLE public.canonical_memories TO {}").format(
                sql.Identifier(role_name)
            )
        )
        connection.execute(
            sql.SQL("GRANT INSERT ON TABLE public.retrieval_audit TO {}").format(
                sql.Identifier(role_name)
            )
        )

        # The legacy process-wide role must not retain a table-wide read path.
        connection.execute(
            sql.SQL("CREATE ROLE IF NOT EXISTS {} NOLOGIN").format(
                sql.Identifier(LEGACY_RUNTIME_ROLE)
            )
        )
        connection.execute(
            sql.SQL(
                "REVOKE ALL ON TABLE public.incidents, public.canonical_memories, "
                "public.retrieval_audit FROM {}"
            ).format(sql.Identifier(LEGACY_RUNTIME_ROLE))
        )
        connection.execute(
            "ALTER TABLE public.canonical_memories ENABLE ROW LEVEL SECURITY"
        )
        connection.execute(
            "ALTER TABLE public.retrieval_audit ENABLE ROW LEVEL SECURITY"
        )
        connection.execute(
            sql.SQL("DROP POLICY IF EXISTS {} ON public.canonical_memories").format(
                sql.Identifier(canonical_policy)
            )
        )
        connection.execute(
            sql.SQL(
                "CREATE POLICY {} ON public.canonical_memories "
                "FOR SELECT TO {} USING (tenant_id = {}::UUID AND incident_id = {}::UUID)"
            ).format(
                sql.Identifier(canonical_policy),
                sql.Identifier(role_name),
                sql.Literal(tenant_id),
                sql.Literal(incident_id),
            )
        )
        connection.execute(
            sql.SQL("DROP POLICY IF EXISTS {} ON public.retrieval_audit").format(
                sql.Identifier(audit_policy)
            )
        )
        connection.execute(
            sql.SQL(
                "CREATE POLICY {} ON public.retrieval_audit "
                "FOR INSERT TO {} WITH CHECK "
                "(tenant_id = {}::UUID AND incident_id = {}::UUID)"
            ).format(
                sql.Identifier(audit_policy),
                sql.Identifier(role_name),
                sql.Literal(tenant_id),
                sql.Literal(incident_id),
            )
        )

    read_policies = configure_scope_read_policies(
        migrator_database_url,
        tenant_id=tenant_id,
        incident_id=incident_id,
    )["policies"]
    return {
        "ok": True,
        "database": database_name,
        "migration_owner": current_user,
        "scope_role": role_name,
        "tenant_id": tenant_id,
        "incident_id": incident_id,
        "legacy_runtime_privileges_revoked": True,
        "policies": [canonical_policy, audit_policy, *read_policies],
    }


def verify_scope_role(
    runtime_database_url: str,
    *,
    tenant_id: str,
    incident_id: str,
    forbidden_memory_id: str | None = None,
) -> dict[str, Any]:
    """Prove that unscoped SQL is still confined by database policy."""

    expected_user = scope_role_name(tenant_id, incident_id)
    connect = psycopg_connection_factory(runtime_database_url)
    with connect() as connection:
        current_user = connection.execute("SELECT current_user").fetchone()[0]
        if current_user != expected_user:
            raise RuntimeError("runtime connection does not use the expected scope role")
        visible_count, all_rows_in_scope = connection.execute(
            """
            SELECT
                count(*),
                coalesce(bool_and(tenant_id = %s AND incident_id = %s), true)
            FROM canonical_memories
            """,
            (tenant_id, incident_id),
        ).fetchone()
        forbidden_visible = False
        if forbidden_memory_id:
            forbidden_visible = (
                connection.execute(
                    "SELECT 1 FROM canonical_memories WHERE memory_id = %s",
                    (forbidden_memory_id,),
                ).fetchone()
                is not None
            )
        if not all_rows_in_scope or forbidden_visible:
            raise RuntimeError("database row isolation failed")
        visible_incidents, all_incidents_in_scope = connection.execute(
            """
            SELECT
                count(*),
                coalesce(bool_and(tenant_id = %s AND incident_id = %s), true)
            FROM incidents
            """,
            (tenant_id, incident_id),
        ).fetchone()
        if not all_incidents_in_scope:
            raise RuntimeError("incident row isolation failed")
        visible_audits, all_audits_in_scope = connection.execute(
            """
            SELECT
                count(*),
                coalesce(bool_and(tenant_id = %s AND incident_id = %s), true)
            FROM retrieval_audit
            """,
            (tenant_id, incident_id),
        ).fetchone()
        if not all_audits_in_scope:
            raise RuntimeError("retrieval audit row isolation failed")

    denied: list[str] = []
    negative_checks: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "row_security_off",
            ("SET row_security = off", "SELECT count(*) FROM canonical_memories"),
        ),
        (
            "canonical_update",
            ("UPDATE canonical_memories SET payload = payload WHERE false",),
        ),
    )
    for name, statements in negative_checks:
        with connect() as connection:
            try:
                for statement in statements:
                    connection.execute(statement)
            except Exception as exc:
                connection.rollback()
                if getattr(exc, "sqlstate", None) != "42501":
                    raise
                denied.append(name)
            else:
                connection.rollback()
                raise RuntimeError(f"scope-role negative check unexpectedly passed: {name}")

    return {
        "ok": True,
        "current_user": current_user,
        "visible_rows": visible_count,
        "visible_incidents": visible_incidents,
        "visible_audits": visible_audits,
        "all_visible_rows_in_scope": bool(all_rows_in_scope),
        "all_visible_incidents_in_scope": bool(all_incidents_in_scope),
        "all_visible_audits_in_scope": bool(all_audits_in_scope),
        "forbidden_memory_visible": forbidden_visible,
        "denied": denied,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--forbidden-memory-id")
    args = parser.parse_args()
    required = {
        "database_url": os.environ.get("CONTINUUM_DATABASE_URL", ""),
        "tenant_id": os.environ.get("CONTINUUM_TENANT_ID", ""),
        "incident_id": os.environ.get("CONTINUUM_INCIDENT_ID", ""),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        parser.error("missing required process environment: " + ", ".join(missing))
    if args.verify:
        result = verify_scope_role(
            required["database_url"],
            tenant_id=required["tenant_id"],
            incident_id=required["incident_id"],
            forbidden_memory_id=args.forbidden_memory_id,
        )
    else:
        password = os.environ.get("CONTINUUM_SCOPE_PASSWORD", "")
        if not password:
            parser.error("CONTINUUM_SCOPE_PASSWORD is required for provisioning")
        result = provision_scope_role(
            required["database_url"],
            tenant_id=required["tenant_id"],
            incident_id=required["incident_id"],
            password=password,
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
