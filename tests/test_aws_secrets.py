from __future__ import annotations

import unittest

from continuum.aws_secrets import get_secret_string_with_backoff


class AccessDenied(Exception):
    def __init__(self) -> None:
        super().__init__("access denied")
        self.response = {"Error": {"Code": "AccessDeniedException"}}


class FakeSecretsClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get_secret_value(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class SecretBackoffTests(unittest.TestCase):
    def test_access_denied_is_retried_without_exposing_the_value(self):
        client = FakeSecretsClient(
            [AccessDenied(), AccessDenied(), {"SecretString": "private-value"}]
        )
        sleeps = []

        value = get_secret_string_with_backoff(
            client,
            "secret-name",
            attempts=3,
            delay_seconds=0.25,
            sleep=sleeps.append,
        )

        self.assertEqual(value, "private-value")
        self.assertEqual(sleeps, [0.25, 0.25])
        self.assertEqual(
            client.calls,
            [{"SecretId": "secret-name"}] * 3,
        )

    def test_non_propagation_error_fails_without_retry(self):
        client = FakeSecretsClient([RuntimeError("network failure")])
        sleeps = []

        with self.assertRaisesRegex(RuntimeError, "network failure"):
            get_secret_string_with_backoff(client, "secret-name", sleep=sleeps.append)

        self.assertEqual(sleeps, [])

    def test_bounds_and_secret_shape_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "bounds"):
            get_secret_string_with_backoff(FakeSecretsClient([]), "x", attempts=0)
        with self.assertRaisesRegex(RuntimeError, "SecretString"):
            get_secret_string_with_backoff(
                FakeSecretsClient([{"SecretString": ""}]),
                "x",
            )


if __name__ == "__main__":
    unittest.main()
