import unittest

from continuum.identity import IdentityVerificationError
from continuum.scope_roles import scope_role_name
from continuum.tenant_control import (
    DatabaseTenantControlPlane,
    database_url_with_login,
)


TENANT = "11111111-1111-4111-8111-111111111111"
INCIDENT = "22222222-2222-4222-8222-222222222222"


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, _sql, _params):
        return FakeResult(self.row)


class TenantControlPlaneTests(unittest.TestCase):
    def test_active_binding_resolves_audited_sql_identity(self):
        role = scope_role_name(TENANT, INCIDENT)
        resolver = DatabaseTenantControlPlane(
            lambda: FakeConnection((TENANT, INCIDENT, role, 4, "active"))
        )
        identity = resolver.resolve("client-a")
        self.assertEqual(identity.sql_role, role)
        self.assertEqual(identity.binding_version, 4)

    def test_disabled_or_role_mismatched_binding_fails_closed(self):
        for row in (
            (TENANT, INCIDENT, scope_role_name(TENANT, INCIDENT), 5, "disabled"),
            (TENANT, INCIDENT, "continuum_scope_wrong", 5, "active"),
            None,
        ):
            with self.subTest(row=row):
                resolver = DatabaseTenantControlPlane(lambda row=row: FakeConnection(row))
                with self.assertRaises(IdentityVerificationError):
                    resolver.resolve("client-a")

    def test_database_login_replacement_percent_encodes_credentials(self):
        result = database_url_with_login(
            "postgresql://old@db.example.test:26257/continuum?sslmode=verify-full",
            user="scope_role",
            password="a/b:c@d",
        )
        self.assertIn("scope_role:a%2Fb%3Ac%40d@db.example.test", result)
        self.assertNotIn("old@", result)


if __name__ == "__main__":
    unittest.main()
