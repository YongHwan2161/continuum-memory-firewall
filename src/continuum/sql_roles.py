"""Provision and verify separated CockroachDB migration/runtime identities."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from continuum.migrate import Migrator, psycopg_connection_factory


MIGRATOR_ROLE = "continuum_migrator_role"
MIGRATOR_USER = "continuum_migrator"
RUNTIME_ROLE = "continuum_runtime_role"
RUNTIME_USER = "continuum_runtime"

OWNED_TABLES = (
    "continuum_schema_migrations",
    "continuum_migration_lock",
    "continuum_migration_intents",
    "incidents",
    "memory_candidates",
    "canonical_memories",
    "action_attempts",
    "retrieval_audit",
    "tenant_scope_bindings",
    "tenant_scope_binding_audit",
)


def _password_statement(user: str, password: str):
    from psycopg import sql

    return sql.SQL("ALTER USER {} WITH PASSWORD {}").format(
        sql.Identifier(user),
        sql.Literal(password),
    )


def provision_sql_roles(
    database_url: str,
    *,
    migrator_password: str,
    runtime_password: str,
    bootstrap_user: str | None = None,
    revoke_bootstrap_admin: bool = False,
) -> dict[str, Any]:
    if min(len(migrator_password), len(runtime_password)) < 24:
        raise ValueError("generated SQL passwords must be at least 24 characters")
    connect = psycopg_connection_factory(database_url)
    from psycopg import sql

    with connect() as connection:
        database_name, current_user = connection.execute(
            "SELECT current_database(), current_user"
        ).fetchone()
        if bootstrap_user is not None and current_user != bootstrap_user:
            raise RuntimeError("connected SQL identity does not match bootstrap user")

        for role in (MIGRATOR_ROLE, RUNTIME_ROLE):
            connection.execute(
                sql.SQL("CREATE ROLE IF NOT EXISTS {} NOLOGIN").format(
                    sql.Identifier(role)
                )
            )
        for user in (MIGRATOR_USER, RUNTIME_USER):
            connection.execute(
                sql.SQL("CREATE USER IF NOT EXISTS {}").format(sql.Identifier(user))
            )
            connection.execute(
                sql.SQL("REVOKE admin FROM {}").format(sql.Identifier(user))
            )

        connection.execute(_password_statement(MIGRATOR_USER, migrator_password))
        connection.execute(_password_statement(RUNTIME_USER, runtime_password))
        connection.execute(
            sql.SQL("GRANT {} TO {}").format(
                sql.Identifier(MIGRATOR_ROLE),
                sql.Identifier(MIGRATOR_USER),
            )
        )
        connection.execute(
            sql.SQL("GRANT {} TO {}").format(
                sql.Identifier(RUNTIME_ROLE),
                sql.Identifier(RUNTIME_USER),
            )
        )

        connection.execute(
            sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
                sql.Identifier(database_name),
                sql.Identifier(MIGRATOR_ROLE),
            )
        )
        connection.execute(
            sql.SQL("ALTER SCHEMA public OWNER TO {}").format(
                sql.Identifier(MIGRATOR_ROLE)
            )
        )
        for table in OWNED_TABLES:
            connection.execute(
                sql.SQL("ALTER TABLE public.{} OWNER TO {}").format(
                    sql.Identifier(table),
                    sql.Identifier(MIGRATOR_ROLE),
                )
            )

        connection.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(
                sql.Identifier(database_name),
                sql.Identifier(MIGRATOR_ROLE),
                sql.Identifier(RUNTIME_ROLE),
            )
        )
        connection.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}, {}").format(
                sql.Identifier(MIGRATOR_ROLE),
                sql.Identifier(RUNTIME_ROLE),
            )
        )
        connection.execute(
            sql.SQL("REVOKE CREATE ON DATABASE {} FROM public").format(
                sql.Identifier(database_name)
            )
        )
        connection.execute("REVOKE CREATE ON SCHEMA public FROM public")
        connection.execute(
            sql.SQL("GRANT CREATE ON DATABASE {} TO {}").format(
                sql.Identifier(database_name),
                sql.Identifier(MIGRATOR_ROLE),
            )
        )
        connection.execute(
            sql.SQL("GRANT CREATE ON SCHEMA public TO {}").format(
                sql.Identifier(MIGRATOR_ROLE)
            )
        )
        connection.execute(
            sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}").format(
                sql.Identifier(RUNTIME_ROLE)
            )
        )
        connection.execute(
            sql.SQL(
                "GRANT SELECT ON TABLE public.incidents, "
                "public.canonical_memories TO {}"
            ).format(sql.Identifier(RUNTIME_ROLE))
        )
        connection.execute(
            sql.SQL("GRANT INSERT ON TABLE public.retrieval_audit TO {}").format(
                sql.Identifier(RUNTIME_ROLE)
            )
        )

        if revoke_bootstrap_admin:
            connection.execute(
                sql.SQL("REVOKE admin FROM {}").format(
                    sql.Identifier(current_user)
                )
            )

    return {
        "ok": True,
        "database": database_name,
        "migrator_user": MIGRATOR_USER,
        "runtime_user": RUNTIME_USER,
        "bootstrap_admin_revoked": revoke_bootstrap_admin,
    }


def verify_runtime_role(database_url: str) -> dict[str, Any]:
    connect = psycopg_connection_factory(database_url)
    with connect() as connection:
        current_user = connection.execute("SELECT current_user").fetchone()[0]
        connection.execute("SELECT count(*) FROM canonical_memories").fetchone()

    denied = []
    checks = (
        (
            "schema_create",
            "CREATE TABLE continuum_runtime_must_not_create (id INT PRIMARY KEY)",
        ),
        (
            "canonical_update",
            "UPDATE canonical_memories SET payload = payload WHERE false",
        ),
    )
    for name, statement in checks:
        with connect() as connection:
            try:
                connection.execute(statement)
            except Exception as exc:  # provider exception type varies by driver
                connection.rollback()
                if getattr(exc, "sqlstate", None) != "42501":
                    raise
                denied.append(name)
            else:
                connection.rollback()
                raise RuntimeError(
                    f"runtime privilege negative test unexpectedly passed: {name}"
                )
    return {"ok": True, "current_user": current_user, "denied": denied}


def verify_migrator_role(database_url: str) -> dict[str, Any]:
    report = Migrator(psycopg_connection_factory(database_url)).migrate()
    return {"ok": True, "migration": report.as_dict()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revoke-bootstrap-admin", action="store_true")
    args = parser.parse_args()
    required = {
        "database_url": os.environ.get("CONTINUUM_DATABASE_URL", ""),
        "migrator_password": os.environ.get("CONTINUUM_MIGRATOR_PASSWORD", ""),
        "runtime_password": os.environ.get("CONTINUUM_RUNTIME_PASSWORD", ""),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        parser.error("missing required process environment: " + ", ".join(missing))
    result = provision_sql_roles(
        required["database_url"],
        migrator_password=required["migrator_password"],
        runtime_password=required["runtime_password"],
        bootstrap_user=os.environ.get("CONTINUUM_BOOTSTRAP_USER") or None,
        revoke_bootstrap_admin=args.revoke_bootstrap_admin,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
