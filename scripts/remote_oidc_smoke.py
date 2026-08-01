"""Acquire a five-minute Cognito token and run a redacted remote MCP smoke."""

from __future__ import annotations

import argparse
import base64
import json
import ssl
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import boto3


def _request(request: Request) -> tuple[int, dict[str, str], bytes]:
    try:
        with urlopen(request, context=ssl.create_default_context(), timeout=30) as response:
            return response.status, dict(response.headers.items()), response.read()
    except HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-secret-id", required=True)
    parser.add_argument("--mcp-url", required=True)
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--query", default="How do we recover from migration checksum drift?")
    parser.add_argument("--forbidden-memory-id")
    args = parser.parse_args()

    client = boto3.client("secretsmanager", region_name=args.region)
    secret = json.loads(
        client.get_secret_value(SecretId=args.client_secret_id)["SecretString"]
    )
    credentials = base64.b64encode(
        f"{secret['client_id']}:{secret['client_secret']}".encode("utf-8")
    ).decode("ascii")
    body = urlencode(
        {
            "grant_type": "client_credentials",
            "scope": secret["scope"],
        }
    ).encode("ascii")
    token_status, _, token_body = _request(
        Request(
            secret["token_endpoint"],
            data=body,
            method="POST",
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
    )
    credentials = ""
    if token_status != 200:
        raise RuntimeError(f"Cognito token request failed with HTTP {token_status}")
    token_payload = json.loads(token_body)
    token = token_payload["access_token"]
    expires_in = int(token_payload["expires_in"])
    if expires_in > 300:
        raise RuntimeError("Cognito token lifetime exceeds five minutes")

    unauth_status, _, _ = _request(
        Request(
            args.mcp_url,
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
    )
    if unauth_status != 401:
        raise RuntimeError("unauthenticated MCP request was not rejected")

    session_id: str | None = None

    def rpc(payload: dict[str, object]) -> tuple[int, dict[str, object] | None]:
        nonlocal session_id
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if session_id:
            headers["Mcp-Session-Id"] = session_id
            headers["MCP-Protocol-Version"] = "2025-11-25"
        status, response_headers, response_body = _request(
            Request(
                args.mcp_url,
                data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                method="POST",
                headers=headers,
            )
        )
        for name, value in response_headers.items():
            if name.lower() == "mcp-session-id":
                session_id = value
        decoded = json.loads(response_body) if response_body else None
        return status, decoded

    initialize_status, initialize = rpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "continuum-release-smoke", "version": "1"},
            },
        }
    )
    if initialize_status != 200 or initialize is None:
        raise RuntimeError("MCP initialization failed")
    rpc({"jsonrpc": "2.0", "method": "notifications/initialized"})
    tools_status, tools = rpc(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    )
    if tools_status != 200 or tools is None:
        raise RuntimeError("MCP tools/list failed")
    tool_names = [item["name"] for item in tools["result"]["tools"]]
    if tool_names != ["search", "fetch"]:
        raise RuntimeError("unexpected public MCP tools")
    search_status, search = rpc(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "search", "arguments": {"query": args.query}},
        }
    )
    if search_status != 200 or search is None:
        raise RuntimeError("MCP search failed")
    hits = search["result"]["structuredContent"]["results"]
    if not hits:
        raise RuntimeError("semantic search returned no result")
    fetch_status, fetched = rpc(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "fetch", "arguments": {"id": hits[0]["id"]}},
        }
    )
    fetch_ok = (
        fetch_status == 200
        and fetched is not None
        and not fetched["result"].get("isError", False)
    )
    if not fetch_ok:
        raise RuntimeError("MCP fetch failed")

    forbidden_denied = None
    if args.forbidden_memory_id:
        _, forbidden = rpc(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "fetch",
                    "arguments": {"id": args.forbidden_memory_id},
                },
            }
        )
        forbidden_denied = bool(forbidden and forbidden["result"].get("isError"))
        if not forbidden_denied:
            raise RuntimeError("cross-scope MCP fetch was not denied")

    token = ""
    print(
        json.dumps(
            {
                "ok": True,
                "token_lifetime_seconds": expires_in,
                "unauthenticated_status": unauth_status,
                "protocol": initialize["result"]["protocolVersion"],
                "tools": tool_names,
                "semantic_search_hits": len(hits),
                "fetch_ok": fetch_ok,
                "cross_scope_fetch_denied": forbidden_denied,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
