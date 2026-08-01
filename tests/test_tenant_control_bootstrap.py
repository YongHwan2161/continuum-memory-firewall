import unittest
from unittest.mock import patch

from continuum.tenant_control import provision_control_plane_role


try:
    import psycopg  # noqa: F401
except ImportError:
    PSYCOPG_AVAILABLE = False
else:
    PSYCOPG_AVAILABLE = True


class Result:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row


class RecordingConnection:
    def __init__(self, statements):
        self.statements = statements

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, statement, _params=None):
        rendered = (
            statement.as_string(None)
            if hasattr(statement, "as_string")
            else str(statement)
        )
        self.statements.append(rendered)
        if "current_database(), current_user" in rendered:
            return Result(("defaultdb", "continuum_migrator"))
        if rendered == "SELECT current_user":
            return Result(("continuum_migrator",))
        return Result()


@unittest.skipUnless(PSYCOPG_AVAILABLE, "psycopg is not installed")
class ControlPlaneBootstrapTests(unittest.TestCase):
    def test_least_privilege_bootstrap_does_not_require_admin_option(self):
        statements = []

        def factory(_url):
            return lambda: RecordingConnection(statements)

        with patch("continuum.tenant_control.psycopg_connection_factory", factory):
            report = provision_control_plane_role(
                "postgresql://unused",
                revoke_bootstrap_user="continuum_migrator",
            )

        self.assertTrue(report["bootstrap_options_revoked"])
        self.assertFalse(report["fresh_identity_verified"])
        self.assertFalse(any("REVOKE admin" in item for item in statements))
        self.assertTrue(
            any(
                'ALTER USER "continuum_migrator" WITH '
                "NOCREATEROLE NOCREATELOGIN" in item
                for item in statements
            )
        )


if __name__ == "__main__":
    unittest.main()
