"""Cost-bounded AWS Lambda client for CockroachDB Cloud Managed MCP."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import json
import os
import time
from typing import Any, Awaitable, Callable, Mapping
from urllib.parse import urlsplit


DEFAULT_MANAGED_MCP_URL = "https://cockroachlabs.cloud/mcp"
MAX_REQUEST_BYTES = 16 * 1024
MAX_RESULT_BYTES = 256 * 1024
SECRET_CACHE_SECONDS = 300

# The managed service also offers write tools. This worker intentionally exposes
# only the documented inspection/query subset and has no public Function URL.
READ_ONLY_TOOLS = frozenset(
    {
        "list_clusters",
        "get_cluster",
        "list_databases",
        "list_tables",
        "get_table_schema",
        "select_query",
        "explain_query",
        "show_running_queries",
    }
)


class RequestValidationError(ValueError):
    """Raised before credentials or the remote service are accessed."""


class ManagedMCPError(RuntimeError):
    """Raised when the managed MCP call cannot produce a safe result."""


@dataclass(frozen=True, slots=True)
class AWSMCPSettings:
    secret_arn: str
    cluster_id: str
    endpoint: str = DEFAULT_MANAGED_MCP_URL
    request_timeout_seconds: float = 20.0

    @classmethod
    def from_env(cls) -> "AWSMCPSettings":
        secret_arn = os.environ.get(
            "CONTINUUM_COCKROACH_MCP_SECRET_ARN", ""
        ).strip()
        cluster_id = os.environ.get(
            "CONTINUUM_COCKROACH_CLUSTER_ID", ""
        ).strip()
        missing = []
        if not secret_arn:
            missing.append("CONTINUUM_COCKROACH_MCP_SECRET_ARN")
        if not cluster_id:
            missing.append("CONTINUUM_COCKROACH_CLUSTER_ID")
        if missing:
            raise RuntimeError(
                "missing required environment variables: " + ", ".join(missing)
            )

        endpoint = os.environ.get(
            "CONTINUUM_COCKROACH_MCP_URL",
            DEFAULT_MANAGED_MCP_URL,
        )
        _validate_managed_mcp_url(endpoint)
        if len(cluster_id) > 256 or any(
            character.isspace() for character in cluster_id
        ):
            raise RuntimeError("CONTINUUM_COCKROACH_CLUSTER_ID is invalid")

        return cls(
            secret_arn=secret_arn,
            cluster_id=cluster_id,
            endpoint=endpoint,
        )


def _validate_managed_mcp_url(value: str) -> None:
    """Prevent a configuration error from forwarding a bearer token elsewhere."""

    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or parts.hostname != "cockroachlabs.cloud"
        or parts.port is not None
        or parts.username is not None
        or parts.password is not None
        or parts.path.rstrip("/") != "/mcp"
        or parts.query
        or parts.fragment
    ):
        raise RuntimeError(
            "CONTINUUM_COCKROACH_MCP_URL must be "
            "https://cockroachlabs.cloud/mcp"
        )


def _parse_api_key(secret_string: str) -> str:
    """Accept a plain API key or a JSON object containing ``api_key``."""

    value = secret_string.strip()
    if not value:
        raise ManagedMCPError("the CockroachDB MCP secret is empty")
    if value.startswith("{"):
        try:
            document = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ManagedMCPError(
                "the CockroachDB MCP secret is not valid JSON"
            ) from exc
        if not isinstance(document, dict):
            raise ManagedMCPError(
                "the CockroachDB MCP secret JSON must be an object"
            )
        value = document.get("api_key", "")
        if not isinstance(value, str):
            raise ManagedMCPError(
                "the CockroachDB MCP secret api_key must be a string"
            )
        value = value.strip()
    if not value or any(character.isspace() for character in value):
        raise ManagedMCPError("the CockroachDB MCP API key is invalid")
    return value


_secret_cache: dict[str, tuple[float, str]] = {}


def _load_api_key(secret_arn: str) -> str:
    cached = _secret_cache.get(secret_arn)
    now = time.monotonic()
    if cached is not None and now - cached[0] < SECRET_CACHE_SECONDS:
        return cached[1]

    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - Lambda runtime boundary
        raise ManagedMCPError("boto3 is unavailable") from exc

    response = boto3.client("secretsmanager").get_secret_value(
        SecretId=secret_arn
    )
    secret_string = response.get("SecretString")
    if not isinstance(secret_string, str):
        raise ManagedMCPError("the CockroachDB MCP secret must be text")
    api_key = _parse_api_key(secret_string)
    _secret_cache[secret_arn] = (now, api_key)
    return api_key


async def _call_managed_mcp(
    settings: AWSMCPSettings,
    api_key: str,
    tool: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    try:
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
    except ImportError as exc:  # pragma: no cover - package boundary
        raise ManagedMCPError("the MCP Lambda dependencies are unavailable") from exc

    headers = {
        "Authorization": f"Bearer {api_key}",
        "mcp-cluster-id": settings.cluster_id,
    }
    timeout = httpx.Timeout(settings.request_timeout_seconds)
    try:
        async with httpx.AsyncClient(
            headers=headers,
            timeout=timeout,
            follow_redirects=False,
        ) as http_client:
            async with streamable_http_client(
                settings.endpoint,
                http_client=http_client,
                terminate_on_close=False,
            ) as (read_stream, write_stream, _):
                async with ClientSession(
                    read_stream,
                    write_stream,
                    read_timeout_seconds=timedelta(
                        seconds=settings.request_timeout_seconds
                    ),
                ) as session:
                    await session.initialize()
                    advertised = {
                        item.name for item in (await session.list_tools()).tools
                    }
                    if tool not in advertised:
                        raise ManagedMCPError(
                            "the requested read-only tool is not advertised"
                        )
                    result = await session.call_tool(tool, arguments)
    except ManagedMCPError:
        raise
    except Exception as exc:
        # Do not return the provider exception: it may contain request details.
        raise ManagedMCPError("the managed MCP request failed") from exc

    if result.isError:
        raise ManagedMCPError("the managed MCP tool returned an error")
    payload = result.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
        exclude={"meta"},
    )
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_RESULT_BYTES:
        raise ManagedMCPError("the managed MCP result exceeds the response limit")
    return payload


SecretLoader = Callable[[str], str]
ToolCaller = Callable[
    [AWSMCPSettings, str, str, dict[str, Any]],
    Awaitable[dict[str, Any]],
]


def _validate_event(event: object) -> tuple[str, dict[str, Any]]:
    if not isinstance(event, Mapping):
        raise RequestValidationError("event must be an object")
    try:
        encoded = json.dumps(event, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise RequestValidationError("event must be JSON serializable") from exc
    if len(encoded.encode("utf-8")) > MAX_REQUEST_BYTES:
        raise RequestValidationError("event exceeds the 16 KiB request limit")

    tool = event.get("tool")
    if not isinstance(tool, str) or tool not in READ_ONLY_TOOLS:
        raise RequestValidationError("tool is not in the read-only allowlist")
    arguments = event.get("arguments", {})
    if not isinstance(arguments, dict):
        raise RequestValidationError("arguments must be an object")
    return tool, arguments


async def dispatch(
    event: object,
    *,
    settings: AWSMCPSettings | None = None,
    secret_loader: SecretLoader = _load_api_key,
    tool_caller: ToolCaller = _call_managed_mcp,
) -> dict[str, Any]:
    """Validate first, then resolve the secret and call the managed service."""

    tool, arguments = _validate_event(event)
    active_settings = settings or AWSMCPSettings.from_env()
    api_key = secret_loader(active_settings.secret_arn)
    result = await tool_caller(
        active_settings,
        api_key,
        tool,
        arguments,
    )
    return {"ok": True, "tool": tool, "result": result}


def handler(event: object, context: object) -> dict[str, Any]:
    """Lambda direct-invocation entry point; intentionally not an HTTP API."""

    request_id = getattr(context, "aws_request_id", None)
    try:
        response = asyncio.run(dispatch(event))
    except RequestValidationError as exc:
        response = {
            "ok": False,
            "error": {"code": "INVALID_REQUEST", "message": str(exc)},
        }
    except (ManagedMCPError, RuntimeError):
        response = {
            "ok": False,
            "error": {
                "code": "UPSTREAM_FAILURE",
                "message": "managed MCP request could not be completed",
            },
        }
    if request_id:
        response["request_id"] = request_id
    return response
