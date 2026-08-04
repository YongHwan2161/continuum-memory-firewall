from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
import unittest

from continuum.aws_sandbox_provider import AwsLambdaSandboxProvider
from continuum.episode import OutcomeStatus


NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


class FakeLambda:
    def __init__(self) -> None:
        self.calls = []

    def invoke(self, **kwargs):
        request = json.loads(kwargs["Payload"])
        self.calls.append(request)
        outcome = None
        if request["operation"] == "send":
            outcome = {
                "provider": request["provider"],
                "status": "succeeded",
                "provider_receipt_id": "sandbox-receipt-1",
                "evidence": {
                    "effect_count": 1,
                    "sandbox": True,
                    "schema_version": 1,
                },
                "observed_at": NOW.isoformat(),
                "verified_at": NOW.isoformat(),
            }
        return {
            "Payload": BytesIO(
                json.dumps({"schema_version": 1, "outcome": outcome}).encode()
            )
        }


class AwsLambdaSandboxProviderTests(unittest.TestCase):
    def test_send_and_lookup_use_bounded_lambda_contract(self) -> None:
        runtime = FakeLambda()
        provider = AwsLambdaSandboxProvider(
            function_name="continuum-sandbox-provider",
            region="ap-southeast-1",
            runtime=runtime,
        )

        outcome = provider.send(
            action_payload={"action_type": "inspect_service"},
            idempotency_key="sandbox-key-1",
        )
        missing = provider.lookup(idempotency_key="missing-key")

        self.assertEqual(outcome.status, OutcomeStatus.SUCCEEDED)
        self.assertEqual(outcome.provider_receipt_id, "sandbox-receipt-1")
        self.assertIsNone(missing)
        self.assertTrue(provider.capabilities.supports_idempotency)
        self.assertTrue(provider.capabilities.receipt_lookup)
        self.assertEqual(
            provider.capabilities.reconciliation_timeout.total_seconds(), 30
        )
        self.assertEqual(
            [call["operation"] for call in runtime.calls], ["send", "lookup"]
        )

    def test_function_error_is_value_free(self) -> None:
        class ErrorLambda:
            def invoke(self, **kwargs):
                return {
                    "FunctionError": "Unhandled",
                    "Payload": BytesIO(b'{"secret":"must-not-surface"}'),
                }

        provider = AwsLambdaSandboxProvider(
            function_name="continuum-sandbox-provider",
            region="ap-southeast-1",
            runtime=ErrorLambda(),
        )
        with self.assertRaisesRegex(
            RuntimeError, "sandbox provider function returned an error"
        ) as raised:
            provider.lookup(idempotency_key="sandbox-key-2")
        self.assertNotIn("must-not-surface", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
