from __future__ import annotations

import unittest

from scripts.cutover_scope_identity import _secret_payload


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


if __name__ == "__main__":
    unittest.main()
