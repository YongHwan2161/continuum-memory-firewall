import importlib.util
import unittest
from unittest.mock import MagicMock, patch

from continuum.sql_roles import (
    OWNED_TABLES,
    _password_statement,
    verify_runtime_role,
)


PSYCOPG_AVAILABLE = importlib.util.find_spec("psycopg") is not None


class SqlRoleProvisioningTests(unittest.TestCase):
    def test_every_application_and_migration_table_has_an_owner_target(self):
        self.assertEqual(
            set(OWNED_TABLES),
            {
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
            },
        )

    @unittest.skipUnless(PSYCOPG_AVAILABLE, "install the CockroachDB extra")
    def test_password_is_a_quoted_literal_not_identifier_text(self):
        statement = _password_statement("runtime-user", "p'assword")
        rendered = statement.as_string(None)
        self.assertIn('"runtime-user"', rendered)
        self.assertIn("'p''assword'", rendered)

    def test_negative_privilege_checks_always_rollback(self):
        initial = MagicMock()

        def initial_execute(statement):
            cursor = MagicMock()
            if "current_user" in statement:
                cursor.fetchone.return_value = ("continuum_runtime",)
            else:
                cursor.fetchone.return_value = (1,)
            return cursor

        initial.execute.side_effect = initial_execute

        class PrivilegeDenied(Exception):
            sqlstate = "42501"

        denied_connections = [MagicMock(), MagicMock()]
        for connection in denied_connections:
            connection.execute.side_effect = PrivilegeDenied()

        contexts = []
        for connection in [initial, *denied_connections]:
            context = MagicMock()
            context.__enter__.return_value = connection
            contexts.append(context)
        connect = MagicMock(side_effect=contexts)

        with patch(
            "continuum.sql_roles.psycopg_connection_factory",
            return_value=connect,
        ):
            result = verify_runtime_role("postgresql://example.test/continuum")

        self.assertEqual(result["current_user"], "continuum_runtime")
        self.assertEqual(result["denied"], ["schema_create", "canonical_update"])
        for connection in denied_connections:
            connection.rollback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
