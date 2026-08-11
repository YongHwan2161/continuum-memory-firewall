"""Versioned, drift-detecting CockroachDB schema migrations."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from threading import Event, Thread
import time
from typing import Any, Callable, Iterator, Sequence
from urllib.parse import parse_qsl, urlsplit
from uuid import uuid4


MIGRATION_FILE_PATTERN = re.compile(
    r"^(?P<version>[0-9]{4})_(?P<name>[a-z0-9_]+)\.sql$"
)
SERIALIZATION_FAILURE = "40001"
UNCERTAIN_SCHEMA_CHANGE = "XXA00"
DEFAULT_LEASE_SECONDS = 300
DEFAULT_MAX_ATTEMPTS = 4

EXPECTED_COLUMNS = {
    "incidents": {
        "incident_id",
        "tenant_id",
        "service_name",
        "status",
        "current_sequence",
        "current_head",
        "opened_at",
        "updated_at",
    },
    "memory_candidates": {
        "candidate_id",
        "tenant_id",
        "incident_id",
        "parent_hash",
        "source_kind",
        "action_class",
        "payload",
        "human_approved",
        "created_at",
        "expires_at",
        "decision_code",
        "decided_at",
    },
    "canonical_memories": {
        "memory_id",
        "tenant_id",
        "incident_id",
        "sequence_no",
        "parent_hash",
        "event_hash",
        "source_candidate_id",
        "payload",
        "embedding",
        "embedding_model",
        "embedding_updated_at",
        "accepted_at",
    },
    "action_attempts": {
        "attempt_id",
        "tenant_id",
        "incident_id",
        "expected_head",
        "action_key",
        "action_payload",
        "worker_id",
        "status",
        "rejection_code",
        "created_at",
    },
    "retrieval_audit": {
        "retrieval_id",
        "tenant_id",
        "incident_id",
        "query_digest",
        "embedding_model",
        "returned_memory_ids",
        "accepted_memory_ids",
        "policy_digest",
        "created_at",
    },
    "tenant_scope_bindings": {
        "caller_id",
        "tenant_id",
        "incident_id",
        "sql_role",
        "binding_version",
        "status",
        "created_at",
        "updated_at",
        "created_by",
        "reason",
    },
    "tenant_scope_binding_audit": {
        "audit_id",
        "caller_id",
        "tenant_id",
        "incident_id",
        "sql_role",
        "binding_version",
        "event_type",
        "actor",
        "reason",
        "recorded_at",
    },
    "agent_runs": {
        "run_id",
        "tenant_id",
        "incident_id",
        "arm",
        "model_id",
        "request_digest",
        "input_payload",
        "status",
        "final_text",
        "started_at",
        "completed_at",
    },
    "retrieved_citations": {
        "citation_id",
        "run_id",
        "tenant_id",
        "incident_id",
        "memory_id",
        "rank",
        "similarity",
        "retrieval_id",
        "payload_digest",
        "cited_payload",
        "created_at",
    },
    "proposed_actions": {
        "proposal_id",
        "run_id",
        "tenant_id",
        "incident_id",
        "action_key",
        "action_type",
        "parameters",
        "rationale",
        "citation_ids",
        "risk_class",
        "status",
        "created_at",
        "decided_at",
        "approval_evidence",
    },
    "outcome_evidence": {
        "outcome_id",
        "run_id",
        "proposal_id",
        "tenant_id",
        "incident_id",
        "provider",
        "status",
        "provider_receipt_id",
        "receipt_digest",
        "evidence",
        "observed_at",
        "verified_at",
    },
    "action_outbox": {
        "outbox_id",
        "proposal_id",
        "run_id",
        "tenant_id",
        "incident_id",
        "provider",
        "idempotency_key",
        "action_payload",
        "provider_supports_idempotency",
        "provider_receipt_lookup",
        "provider_reconciliation_timeout_seconds",
        "status",
        "attempt_count",
        "next_attempt_at",
        "lease_owner",
        "lease_expires_at",
        "dispatch_started_at",
        "sent_at",
        "acknowledged_at",
        "provider_outcome_status",
        "provider_observed_at",
        "provider_verified_at",
        "provider_receipt_id",
        "receipt_digest",
        "response_evidence",
        "last_error_code",
        "created_at",
        "updated_at",
    },
    "outcome_reconciliation_journal": {
        "reconciliation_id",
        "proposal_id",
        "outcome_id",
        "run_id",
        "tenant_id",
        "incident_id",
        "decision",
        "incoming_provider",
        "incoming_status",
        "incoming_provider_receipt_id",
        "incoming_receipt_digest",
        "durable_provider",
        "durable_status",
        "durable_provider_receipt_id",
        "durable_receipt_digest",
        "error_code",
        "sequence_no",
        "previous_entry_hash",
        "entry_hash",
        "recorded_at",
    },
}
EXPECTED_INDEXES = {
    "memory_candidates_incident_created_idx",
    "canonical_memories_model_embedding_idx",
    "retrieval_audit_incident_created_idx",
    "tenant_scope_bindings_scope_idx",
    "tenant_scope_binding_audit_caller_idx",
    "agent_runs_scope_started_idx",
    "retrieved_citations_scope_run_idx",
    "proposed_actions_scope_run_idx",
    "outcome_evidence_scope_run_idx",
    "canonical_memories_scope_memory_idx",
    "outcome_evidence_provider_receipt_idx",
    "action_outbox_ready_idx",
    "action_outbox_scope_run_idx",
    "outcome_reconciliation_scope_proposal_idx",
}
EXPECTED_SCOPE_FOREIGN_KEYS = {
    "memory_candidates",
    "canonical_memories",
    "action_attempts",
    "retrieval_audit",
    "tenant_scope_bindings",
    "agent_runs",
    "retrieved_citations",
    "proposed_actions",
    "outcome_evidence",
    "action_outbox",
    "outcome_reconciliation_journal",
}
SAFE_UPDATES_OFF_MIGRATIONS = {"create_model_scoped_vector_index"}


class MigrationError(RuntimeError):
    """Base class for migration failures."""


class MigrationDefinitionError(MigrationError):
    """Raised when the local ordered migration set is invalid."""


class MigrationDriftError(MigrationError):
    """Raised when an applied migration no longer matches its file."""


class MigrationLockError(MigrationError):
    """Raised when another migration owner holds the logical lease."""


class MigrationAdoptionError(MigrationError):
    """Raised when an unmanaged schema needs explicit validated adoption."""


class SchemaValidationError(MigrationError):
    """Raised when the database does not match the expected application schema."""


class MigrationStateUncertainError(MigrationError):
    """Raised when CockroachDB reports a partially applied schema change."""


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    checksum: str
    sql: str
    path: Path


@dataclass(frozen=True, slots=True)
class MigrationReport:
    applied: tuple[int, ...]
    adopted: tuple[int, ...]
    current_version: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "applied": list(self.applied),
            "adopted": list(self.adopted),
            "current_version": self.current_version,
        }


ConnectionFactory = Callable[[], Any]
Sleep = Callable[[float], None]


def default_migrations_dir() -> Path:
    return Path(__file__).with_name("migrations")


def _statement_count(sql: str) -> int:
    without_line_comments = re.sub(r"--[^\n]*", "", sql)
    if "/*" in without_line_comments or "*/" in without_line_comments:
        raise MigrationDefinitionError("block comments are not allowed")
    return len(
        [part for part in without_line_comments.split(";") if part.strip()]
    )


def canonical_migration_bytes(raw: bytes) -> bytes:
    """Normalize SQL newlines to the historical CRLF migration format."""

    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return normalized.replace(b"\n", b"\r\n")


def discover_migrations(directory: Path | None = None) -> tuple[Migration, ...]:
    root = directory or default_migrations_dir()
    if not root.is_dir():
        raise MigrationDefinitionError(f"migration directory not found: {root}")

    migrations: list[Migration] = []
    for path in sorted(root.glob("*.sql")):
        match = MIGRATION_FILE_PATTERN.fullmatch(path.name)
        if match is None:
            raise MigrationDefinitionError(
                f"invalid migration filename: {path.name}"
            )
        raw = canonical_migration_bytes(path.read_bytes())
        sql = raw.decode("utf-8")
        if _statement_count(sql) != 1:
            raise MigrationDefinitionError(
                f"{path.name} must contain exactly one SQL statement"
            )
        migrations.append(
            Migration(
                version=int(match.group("version")),
                name=match.group("name"),
                checksum=hashlib.sha256(raw).hexdigest(),
                sql=sql,
                path=path,
            )
        )

    if not migrations:
        raise MigrationDefinitionError("no migration files found")
    versions = [migration.version for migration in migrations]
    expected = list(range(1, len(migrations) + 1))
    if versions != expected:
        raise MigrationDefinitionError(
            f"migration versions must be contiguous: expected {expected}, "
            f"found {versions}"
        )
    return tuple(migrations)


def validate_database_transport(database_url: str) -> None:
    parts = urlsplit(database_url)
    hostname = parts.hostname or ""
    if not hostname:
        raise MigrationError("CONTINUUM_DATABASE_URL must contain a hostname")
    local = hostname in {"127.0.0.1", "localhost", "::1"}
    query = dict(parse_qsl(parts.query))
    if not local and query.get("sslmode") != "verify-full":
        raise MigrationError(
            "remote CONTINUUM_DATABASE_URL must set sslmode=verify-full"
        )


def _sqlstate(error: BaseException) -> str | None:
    return getattr(error, "sqlstate", None)


class Migrator:
    """Apply single-statement online schema changes under a renewable lease."""

    def __init__(
        self,
        connection_factory: ConnectionFactory,
        *,
        migrations: Sequence[Migration] | None = None,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        sleep: Sleep = time.sleep,
    ) -> None:
        if lease_seconds < 30:
            raise ValueError("lease_seconds must be at least 30")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self._connect = connection_factory
        self._migrations = tuple(migrations or discover_migrations())
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts
        self._sleep = sleep

    def _autocommit_connection(self):
        connection = self._connect()
        connection.autocommit = True
        return connection

    def _bootstrap_metadata(self) -> None:
        statements = (
            """
            CREATE TABLE IF NOT EXISTS continuum_schema_migrations (
                version INT8 PRIMARY KEY,
                name STRING NOT NULL,
                checksum STRING NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS continuum_migration_lock (
                lock_id INT8 PRIMARY KEY CHECK (lock_id = 1),
                owner_id UUID,
                lease_expires_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS continuum_migration_intents (
                version INT8 PRIMARY KEY,
                name STRING NOT NULL,
                checksum STRING NOT NULL,
                started_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """,
            """
            INSERT INTO continuum_migration_lock (lock_id)
            VALUES (1)
            ON CONFLICT (lock_id) DO NOTHING
            """,
        )
        with self._autocommit_connection() as connection:
            for statement in statements:
                connection.execute(statement)

    def _renew(self, owner_id: str) -> None:
        with self._autocommit_connection() as connection:
            row = connection.execute(
                """
                UPDATE continuum_migration_lock
                SET
                    lease_expires_at =
                        now() + (%s * INTERVAL '1 second'),
                    updated_at = now()
                WHERE lock_id = 1 AND owner_id = %s
                RETURNING owner_id::STRING
                """,
                (self._lease_seconds, owner_id),
            ).fetchone()
        if row is None:
            raise MigrationLockError("migration lease was lost")

    @contextmanager
    def lease(self) -> Iterator[str]:
        self._bootstrap_metadata()
        owner_id = str(uuid4())
        with self._autocommit_connection() as connection:
            row = connection.execute(
                """
                UPDATE continuum_migration_lock
                SET
                    owner_id = %s,
                    lease_expires_at =
                        now() + (%s * INTERVAL '1 second'),
                    updated_at = now()
                WHERE
                    lock_id = 1
                    AND (
                        owner_id IS NULL
                        OR lease_expires_at <= now()
                        OR owner_id = %s
                    )
                RETURNING owner_id::STRING
                """,
                (owner_id, self._lease_seconds, owner_id),
            ).fetchone()
        if row is None:
            raise MigrationLockError(
                "another migrator holds the schema lease"
            )
        stop_heartbeat = Event()
        heartbeat_errors: list[BaseException] = []

        def heartbeat() -> None:
            while not stop_heartbeat.wait(self._lease_seconds / 3):
                try:
                    self._renew(owner_id)
                except BaseException as error:  # preserve for the owner thread
                    heartbeat_errors.append(error)
                    stop_heartbeat.set()

        heartbeat_thread = Thread(
            target=heartbeat,
            name="continuum-migration-lease",
            daemon=True,
        )
        heartbeat_thread.start()
        body_error: BaseException | None = None
        try:
            yield owner_id
            if heartbeat_errors:
                raise MigrationLockError(
                    "migration lease heartbeat failed"
                ) from heartbeat_errors[0]
        except BaseException as error:
            body_error = error
            raise
        finally:
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=2)
            try:
                with self._autocommit_connection() as connection:
                    connection.execute(
                        """
                        UPDATE continuum_migration_lock
                        SET
                            owner_id = NULL,
                            lease_expires_at = NULL,
                            updated_at = now()
                        WHERE lock_id = 1 AND owner_id = %s
                        """,
                        (owner_id,),
                    )
            except BaseException:
                if body_error is None:
                    raise

    def _load_applied(self) -> dict[int, tuple[str, str]]:
        with self._autocommit_connection() as connection:
            rows = connection.execute(
                """
                SELECT version, name, checksum
                FROM continuum_schema_migrations
                ORDER BY version
                """
            ).fetchall()
        return {int(row[0]): (row[1], row[2]) for row in rows}

    def _load_intents(self) -> dict[int, tuple[str, str]]:
        with self._autocommit_connection() as connection:
            rows = connection.execute(
                """
                SELECT version, name, checksum
                FROM continuum_migration_intents
                ORDER BY version
                """
            ).fetchall()
        return {int(row[0]): (row[1], row[2]) for row in rows}

    def _validate_records(
        self,
        records: dict[int, tuple[str, str]],
        *,
        record_kind: str,
    ) -> None:
        local = {migration.version: migration for migration in self._migrations}
        for version, (name, checksum) in records.items():
            migration = local.get(version)
            if migration is None:
                raise MigrationDriftError(
                    f"database contains unknown {record_kind} version {version}"
                )
            if migration.name != name or migration.checksum != checksum:
                raise MigrationDriftError(
                    f"migration {version:04d}_{migration.name} "
                    f"{record_kind} checksum drift"
                )

    def _validate_history(
        self,
        applied: dict[int, tuple[str, str]],
    ) -> None:
        self._validate_records(applied, record_kind="history")

    def _validate_progress(
        self,
        applied: dict[int, tuple[str, str]],
        intents: dict[int, tuple[str, str]],
    ) -> None:
        versions = sorted(applied)
        if versions != list(range(1, len(versions) + 1)):
            raise MigrationDriftError(
                "migration history must be a contiguous prefix"
            )
        if len(intents) > 1:
            raise MigrationDriftError(
                "multiple unfinished migration intents require inspection"
            )
        if intents and next(iter(intents)) != len(applied) + 1:
            raise MigrationDriftError(
                "unfinished migration intent is not the next version"
            )

    def _product_tables(self) -> set[str]:
        with self._autocommit_connection() as connection:
            rows = connection.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            ).fetchall()
        return {row[0] for row in rows} & set(EXPECTED_COLUMNS)

    def validate_schema(self) -> None:
        with self._autocommit_connection() as connection:
            columns = connection.execute(
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                """
            ).fetchall()
            indexes = connection.execute(
                """
                SELECT index_name
                FROM information_schema.statistics
                WHERE table_schema = 'public'
                """
            ).fetchall()
            foreign_key_columns = connection.execute(
                """
                SELECT
                    constraints.table_name,
                    key_columns.constraint_name,
                    key_columns.column_name,
                    key_columns.ordinal_position
                FROM information_schema.table_constraints AS constraints
                JOIN information_schema.key_column_usage AS key_columns
                    ON constraints.constraint_catalog =
                        key_columns.constraint_catalog
                    AND constraints.constraint_schema =
                        key_columns.constraint_schema
                    AND constraints.constraint_name =
                        key_columns.constraint_name
                    AND constraints.table_name = key_columns.table_name
                WHERE
                    constraints.table_schema = 'public'
                    AND constraints.constraint_type = 'FOREIGN KEY'
                ORDER BY
                    constraints.table_name,
                    key_columns.constraint_name,
                    key_columns.ordinal_position
                """
            ).fetchall()

        actual_columns: dict[str, set[str]] = {}
        for table_name, column_name in columns:
            actual_columns.setdefault(table_name, set()).add(column_name)
        problems = []
        for table_name, required in EXPECTED_COLUMNS.items():
            missing = required - actual_columns.get(table_name, set())
            if missing:
                problems.append(
                    f"{table_name} missing columns {sorted(missing)}"
                )
        actual_indexes = {row[0] for row in indexes}
        missing_indexes = EXPECTED_INDEXES - actual_indexes
        if missing_indexes:
            problems.append(f"missing indexes {sorted(missing_indexes)}")
        foreign_keys: dict[tuple[str, str], list[str]] = {}
        for table_name, constraint_name, column_name, _ in foreign_key_columns:
            foreign_keys.setdefault((table_name, constraint_name), []).append(
                column_name
            )
        scoped_tables = {
            table_name
            for (table_name, _), column_names in foreign_keys.items()
            if column_names[:2] == ["tenant_id", "incident_id"]
        }
        missing_scope_foreign_keys = EXPECTED_SCOPE_FOREIGN_KEYS - scoped_tables
        if missing_scope_foreign_keys:
            problems.append(
                "missing composite scope foreign keys "
                f"{sorted(missing_scope_foreign_keys)}"
            )
        if problems:
            raise SchemaValidationError("; ".join(problems))

    def _execute_migration(self, migration: Migration) -> None:
        for attempt in range(self._max_attempts):
            try:
                with self._autocommit_connection() as connection:
                    if migration.name in SAFE_UPDATES_OFF_MIGRATIONS:
                        connection.execute("SET sql_safe_updates = false")
                    connection.execute(migration.sql)
                return
            except Exception as error:
                state = _sqlstate(error)
                if state == UNCERTAIN_SCHEMA_CHANGE:
                    raise MigrationStateUncertainError(
                        f"{migration.path.name} may be partially applied; "
                        "inspect SHOW JOBS and schema state before retrying"
                    ) from error
                if state != SERIALIZATION_FAILURE:
                    raise
                if attempt + 1 == self._max_attempts:
                    raise MigrationError(
                        f"{migration.path.name} exhausted serialization retries"
                    ) from error
                self._sleep(min(0.05 * (2**attempt), 0.5))

    def _record(self, migration: Migration) -> None:
        with self._autocommit_connection() as connection:
            connection.execute(
                """
                INSERT INTO continuum_schema_migrations (
                    version, name, checksum
                )
                VALUES (%s, %s, %s)
                """,
                (migration.version, migration.name, migration.checksum),
            )

    def _start_intent(self, migration: Migration) -> None:
        with self._autocommit_connection() as connection:
            connection.execute(
                """
                INSERT INTO continuum_migration_intents (
                    version, name, checksum
                )
                VALUES (%s, %s, %s)
                ON CONFLICT (version) DO NOTHING
                """,
                (migration.version, migration.name, migration.checksum),
            )

    def _clear_intent(self, version: int) -> None:
        with self._autocommit_connection() as connection:
            connection.execute(
                """
                DELETE FROM continuum_migration_intents
                WHERE version = %s
                """,
                (version,),
            )

    def migrate(self, *, adopt_existing: bool = False) -> MigrationReport:
        applied_versions: list[int] = []
        adopted_versions: list[int] = []
        with self.lease() as owner_id:
            applied = self._load_applied()
            self._validate_history(applied)
            intents = self._load_intents()
            self._validate_records(intents, record_kind="intent")

            for version in set(applied) & set(intents):
                self._clear_intent(version)
                intents.pop(version)
            self._validate_progress(applied, intents)

            if not applied and not intents and self._product_tables():
                if not adopt_existing:
                    raise MigrationAdoptionError(
                        "unmanaged application tables exist; validate the "
                        "current P2 schema, then rerun with --adopt-existing"
                    )
                self.validate_schema()
                for migration in self._migrations:
                    self._renew(owner_id)
                    self._record(migration)
                    adopted_versions.append(migration.version)
                return MigrationReport(
                    applied=(),
                    adopted=tuple(adopted_versions),
                    current_version=self._migrations[-1].version,
                )

            for migration in self._migrations:
                if migration.version in applied:
                    continue
                self._renew(owner_id)
                if migration.version not in intents:
                    self._start_intent(migration)
                self._execute_migration(migration)
                self._renew(owner_id)
                self._record(migration)
                self._clear_intent(migration.version)
                applied_versions.append(migration.version)

            self.validate_schema()
            return MigrationReport(
                applied=tuple(applied_versions),
                adopted=(),
                current_version=self._migrations[-1].version,
            )


def psycopg_connection_factory(database_url: str) -> ConnectionFactory:
    validate_database_transport(database_url)

    def connect():
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - optional package boundary
            raise MigrationError(
                "install the CockroachDB extra: pip install '.[cockroach]'"
            ) from exc
        return psycopg.connect(
            database_url,
            application_name="continuum-migrator",
        )

    return connect


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply Continuum CockroachDB migrations."
    )
    parser.add_argument(
        "--adopt-existing",
        action="store_true",
        help="record a validated unmanaged P2 schema without replaying DDL",
    )
    parser.add_argument(
        "--migrations-dir",
        type=Path,
        help="override migration directory for controlled testing",
    )
    args = parser.parse_args()

    database_url = os.environ.get("CONTINUUM_DATABASE_URL", "")
    if not database_url:
        parser.error("CONTINUUM_DATABASE_URL is required")
    migrations = discover_migrations(args.migrations_dir)
    report = Migrator(
        psycopg_connection_factory(database_url),
        migrations=migrations,
    ).migrate(adopt_existing=args.adopt_existing)
    print(json.dumps(report.as_dict(), sort_keys=True))


if __name__ == "__main__":
    main()
