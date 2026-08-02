from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from continuum.migrate import (
    MigrationDefinitionError,
    MigrationDriftError,
    MigrationError,
    Migrator,
    canonical_migration_bytes,
    discover_migrations,
    validate_database_transport,
)


class MigrationDefinitionTests(unittest.TestCase):
    def test_repository_migrations_are_contiguous_and_single_statement(self) -> None:
        migrations = discover_migrations()

        self.assertEqual(
            [migration.version for migration in migrations],
            list(range(1, 26)),
        )
        self.assertTrue(
            all(len(migration.checksum) == 64 for migration in migrations)
        )

    def test_version_gap_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "0001_first.sql").write_text(
                "CREATE TABLE one (id INT PRIMARY KEY);",
                encoding="utf-8",
            )
            (root / "0003_third.sql").write_text(
                "CREATE TABLE three (id INT PRIMARY KEY);",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                MigrationDefinitionError,
                "contiguous",
            ):
                discover_migrations(root)

    def test_multiple_statements_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "0001_bad.sql").write_text(
                "CREATE TABLE one (id INT PRIMARY KEY);"
                "CREATE TABLE two (id INT PRIMARY KEY);",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                MigrationDefinitionError,
                "exactly one",
            ):
                discover_migrations(root)

    def test_checksum_is_stable_across_checkout_line_endings(self) -> None:
        sql_lf = b"-- migration\nCREATE TABLE stable (id INT PRIMARY KEY);\n"
        sql_crlf = sql_lf.replace(b"\n", b"\r\n")

        self.assertEqual(
            canonical_migration_bytes(sql_lf),
            sql_crlf,
        )
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            Path(left, "0001_stable.sql").write_bytes(sql_lf)
            Path(right, "0001_stable.sql").write_bytes(sql_crlf)

            self.assertEqual(
                discover_migrations(Path(left))[0].checksum,
                discover_migrations(Path(right))[0].checksum,
            )


class MigrationBoundaryTests(unittest.TestCase):
    def test_remote_database_requires_verify_full(self) -> None:
        with self.assertRaisesRegex(MigrationError, "sslmode=verify-full"):
            validate_database_transport(
                "postgresql://user@example.cockroachlabs.cloud/defaultdb"
                "?sslmode=require"
            )

    def test_local_database_may_be_insecure(self) -> None:
        validate_database_transport(
            "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"
        )

    def test_checksum_drift_is_rejected_before_sql_execution(self) -> None:
        migrations = discover_migrations()
        migrator = Migrator(
            lambda: None,
            migrations=migrations,
        )
        changed = replace(migrations[0], checksum="0" * 64)

        with self.assertRaisesRegex(MigrationDriftError, "checksum drift"):
            migrator._validate_records(
                {changed.version: (changed.name, changed.checksum)},
                record_kind="intent",
            )

    def test_non_contiguous_history_is_rejected(self) -> None:
        migrator = Migrator(lambda: None, migrations=discover_migrations())

        with self.assertRaisesRegex(MigrationDriftError, "contiguous prefix"):
            migrator._validate_progress(
                {2: ("create_memory_candidates", "x")},
                {},
            )

    def test_only_next_migration_may_have_an_intent(self) -> None:
        migrator = Migrator(lambda: None, migrations=discover_migrations())

        with self.assertRaisesRegex(MigrationDriftError, "next version"):
            migrator._validate_progress(
                {1: ("create_incidents", "x")},
                {3: ("index_memory_candidates", "y")},
            )


if __name__ == "__main__":
    unittest.main()
