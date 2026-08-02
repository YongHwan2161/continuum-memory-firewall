from __future__ import annotations

import unittest

from scripts.cutover_scope_identity import _secret_payload, _verify_role_options_empty


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


class RoleOptionVerificationTests(unittest.TestCase):
    class Result:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

    class Connection:
        def __init__(self, rows):
            self.rows = rows

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, _statement, _params):
            return RoleOptionVerificationTests.Result(self.rows)

    def test_empty_options_are_required_for_both_identities(self) -> None:
        rows = [("continuum_migrator", []), ("continuum_control", [])]
        connect = lambda: self.Connection(rows)
        self.assertTrue(
            _verify_role_options_empty(
                connect,
                ("continuum_migrator", "continuum_control"),
            )
        )

    def test_elevated_or_missing_role_fails_closed(self) -> None:
        elevated = lambda: self.Connection(
            [("continuum_migrator", ["CREATEROLE"]), ("continuum_control", [])]
        )
        with self.assertRaisesRegex(RuntimeError, "still elevated"):
            _verify_role_options_empty(
                elevated,
                ("continuum_migrator", "continuum_control"),
            )
        missing = lambda: self.Connection([("continuum_migrator", [])])
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            _verify_role_options_empty(
                missing,
                ("continuum_migrator", "continuum_control"),
            )


if __name__ == "__main__":
    unittest.main()
