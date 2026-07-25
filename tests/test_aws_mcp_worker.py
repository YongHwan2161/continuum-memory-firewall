from __future__ import annotations

import asyncio
import json
import os
import unittest
from unittest.mock import patch

from continuum.aws_mcp_worker import (
    AWSMCPSettings,
    DEFAULT_MANAGED_MCP_URL,
    ManagedMCPError,
    RequestValidationError,
    _parse_api_key,
    _validate_event,
    dispatch,
)


class AWSMCPSettingsTests(unittest.TestCase):
    def test_settings_require_secret_and_cluster(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                RuntimeError,
                "CONTINUUM_COCKROACH_MCP_SECRET_ARN",
            ):
                AWSMCPSettings.from_env()

    def test_settings_reject_token_exfiltration_endpoint(self) -> None:
        environment = {
            "CONTINUUM_COCKROACH_MCP_SECRET_ARN": "arn:example",
            "CONTINUUM_COCKROACH_CLUSTER_ID": "cluster-id",
            "CONTINUUM_COCKROACH_MCP_URL": "https://attacker.invalid/mcp",
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(RuntimeError, "cockroachlabs.cloud"):
                AWSMCPSettings.from_env()

    def test_settings_accept_official_endpoint(self) -> None:
        environment = {
            "CONTINUUM_COCKROACH_MCP_SECRET_ARN": "arn:example",
            "CONTINUUM_COCKROACH_CLUSTER_ID": "cluster-id",
        }
        with patch.dict(os.environ, environment, clear=True):
            settings = AWSMCPSettings.from_env()
        self.assertEqual(settings.endpoint, DEFAULT_MANAGED_MCP_URL)


class SecretParsingTests(unittest.TestCase):
    def test_plain_and_json_api_keys_are_supported(self) -> None:
        self.assertEqual(_parse_api_key("key-value"), "key-value")
        self.assertEqual(
            _parse_api_key(json.dumps({"api_key": "key-value"})),
            "key-value",
        )

    def test_empty_or_malformed_secret_is_rejected(self) -> None:
        for value in ("", " ", '{"api_key": ""}', '{"api_key": 2}', "{bad"):
            with self.subTest(value=value):
                with self.assertRaises(ManagedMCPError):
                    _parse_api_key(value)


class RequestBoundaryTests(unittest.TestCase):
    def test_write_tool_is_rejected_before_secret_lookup(self) -> None:
        secret_called = False

        def load_secret(_: str) -> str:
            nonlocal secret_called
            secret_called = True
            return "secret"

        settings = AWSMCPSettings("arn:example", "cluster-id")
        with self.assertRaises(RequestValidationError):
            asyncio.run(
                dispatch(
                    {"tool": "insert_rows", "arguments": {}},
                    settings=settings,
                    secret_loader=load_secret,
                )
            )
        self.assertFalse(secret_called)

    def test_non_object_arguments_are_rejected(self) -> None:
        with self.assertRaisesRegex(RequestValidationError, "arguments"):
            _validate_event({"tool": "list_tables", "arguments": []})

    def test_large_request_is_rejected(self) -> None:
        with self.assertRaisesRegex(RequestValidationError, "16 KiB"):
            _validate_event(
                {
                    "tool": "select_query",
                    "arguments": {"query": "x" * (17 * 1024)},
                }
            )

    def test_dispatch_passes_only_validated_read_tool(self) -> None:
        captured: dict[str, object] = {}

        async def call_tool(settings, api_key, tool, arguments):
            captured.update(
                {
                    "settings": settings,
                    "api_key": api_key,
                    "tool": tool,
                    "arguments": arguments,
                }
            )
            return {"structuredContent": {"databases": ["defaultdb"]}}

        settings = AWSMCPSettings("arn:example", "cluster-id")
        response = asyncio.run(
            dispatch(
                {"tool": "list_databases", "arguments": {}},
                settings=settings,
                secret_loader=lambda _: "secret-value",
                tool_caller=call_tool,
            )
        )

        self.assertTrue(response["ok"])
        self.assertEqual(captured["api_key"], "secret-value")
        self.assertEqual(captured["tool"], "list_databases")
        self.assertEqual(captured["arguments"], {})


if __name__ == "__main__":
    unittest.main()
