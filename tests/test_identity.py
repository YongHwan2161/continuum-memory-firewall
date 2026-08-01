import json
import importlib.util
import time
import unittest

from continuum.identity import (
    CallerIdentity,
    CognitoTokenVerifier,
    IdentityVerificationError,
    ScopeRegistry,
    bind_caller,
    current_caller,
)


class ScopeRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = ScopeRegistry.from_json(
            json.dumps(
                {
                    "client-a": {
                        "tenant_id": "tenant-a",
                        "incident_id": "incident-a",
                    }
                }
            )
        )

    def test_resolves_only_server_registered_caller(self):
        self.assertEqual(
            self.registry.resolve("client-a"),
            CallerIdentity("client-a", "tenant-a", "incident-a"),
        )
        with self.assertRaises(IdentityVerificationError):
            self.registry.resolve("client-b")

    def test_context_is_request_bounded(self):
        with self.assertRaises(IdentityVerificationError):
            current_caller()
        with bind_caller(CallerIdentity("client-a", "tenant-a", "incident-a")):
            self.assertEqual(current_caller().tenant_id, "tenant-a")
        with self.assertRaises(IdentityVerificationError):
            current_caller()

    @unittest.skipUnless(importlib.util.find_spec("jwt"), "install the MCP extra")
    def test_claim_policy_requires_access_scope_and_short_lifetime(self):
        now = int(time.time())
        verifier = CognitoTokenVerifier(
            issuer="https://issuer.example.test/pool",
            required_scope="continuum/memory.read",
            registry=self.registry,
            clock=lambda: now,
        )
        identity = verifier._identity_from_claims(
            {
                "client_id": "client-a",
                "iat": now,
                "exp": now + 300,
                "scope": "continuum/memory.read",
                "token_use": "access",
            }
        )
        self.assertEqual(identity.incident_id, "incident-a")

        with self.assertRaisesRegex(IdentityVerificationError, "lifetime"):
            verifier._identity_from_claims(
                {
                    "client_id": "client-a",
                    "iat": now,
                    "exp": now + 3600,
                    "scope": "continuum/memory.read",
                    "token_use": "access",
                }
            )
        with self.assertRaisesRegex(IdentityVerificationError, "scope"):
            verifier._identity_from_claims(
                {
                    "client_id": "client-a",
                    "iat": now,
                    "exp": now + 300,
                    "scope": "other/scope",
                    "token_use": "access",
                }
            )


if __name__ == "__main__":
    unittest.main()
