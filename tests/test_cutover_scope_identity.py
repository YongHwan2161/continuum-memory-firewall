from __future__ import annotations

import unittest

from scripts.cutover_scope_identity import (
    _secret_payload,
    _verify_role_creation_denied,
)


class SecretPropagationTests(unittest.TestCase):
    def test_access_denied_is_retried_without_exposing_the_value(self) -> None:
        class Denied(Exception):
            response = {"Error": {"Code": "AccessDeniedException"}}

        class Client:
            calls = 0

            def get_secret_value(self, **_kwargs):
                self.calls += 1
                if self.calls < 3:
                    raise Denied()
                return {"SecretString": '{"database_url":"redacted"}'}

        sleeps = []
        payload = _secret_payload(Client(), "secret", sleep=sleeps.append)
        self.assertEqual(payload, {"database_url": "redacted"})
        self.assertEqual(sleeps, [5.0, 5.0])

    def test_non_propagation_error_fails_immediately(self) -> None:
        class BrokenClient:
            def get_secret_value(self, **_kwargs):
                raise RuntimeError("network failure")

        with self.assertRaisesRegex(RuntimeError, "network failure"):
            _secret_payload(BrokenClient(), "secret", sleep=lambda _value: None)


class RoleCapabilityVerificationTests(unittest.TestCase):
    class Connection:
        def __init__(self, error=None):
            self.error = error
            self.executed = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, statement):
            self.executed.append(statement)
            if self.error is not None:
                raise self.error

        def rollback(self):
            return None

    def test_role_and_user_creation_are_both_denied(self) -> None:
        class Denied(Exception):
            sqlstate = "42501"

        connections = []

        def connect():
            connection = self.Connection(Denied())
            connections.append(connection)
            return connection

        self.assertTrue(_verify_role_creation_denied(connect))
        self.assertEqual(len(connections), 2)

    def test_unexpected_creation_capability_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "can still create"):
            _verify_role_creation_denied(lambda: self.Connection())

    def test_non_privilege_error_is_not_hidden(self) -> None:
        class Fatal(Exception):
            sqlstate = "08006"

        with self.assertRaises(Fatal):
            _verify_role_creation_denied(lambda: self.Connection(Fatal()))


if __name__ == "__main__":
    unittest.main()
