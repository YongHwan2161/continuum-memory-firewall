import importlib.util
import json
import os
from unittest import IsolatedAsyncioTestCase, TestCase, skipUnless
from unittest.mock import patch


MCP_AVAILABLE = (
    importlib.util.find_spec("mcp") is not None
    and importlib.util.find_spec("pydantic") is not None
)


@skipUnless(MCP_AVAILABLE, "install the MCP extra to run protocol tests")
class MCPProtocolTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from continuum.mcp_server import FetchOutput, SearchOutput, SearchResult

        class FakeKnowledgeService:
            def search(self, query):
                return SearchOutput(
                    results=[
                        SearchResult(
                            id="memory-1",
                            title=f"Accepted memory for {query}",
                            url="https://example.test/memory-1",
                        )
                    ]
                )

            def fetch(self, memory_id):
                return FetchOutput(
                    id=memory_id,
                    title="Checkout incident",
                    text='{"service":"checkout"}',
                    url=f"https://example.test/{memory_id}",
                    metadata={"sequence_no": 1},
                )

        from continuum.mcp_server import create_mcp_server

        self.server = create_mcp_server(
            FakeKnowledgeService(),
            website_url="https://example.test/",
        )

    async def test_lists_only_read_only_search_and_fetch_tools(self):
        from mcp.shared.memory import create_connected_server_and_client_session

        async with create_connected_server_and_client_session(
            self.server
        ) as session:
            tools = (await session.list_tools()).tools

        self.assertEqual([tool.name for tool in tools], ["search", "fetch"])
        for tool in tools:
            self.assertTrue(tool.annotations.readOnlyHint)
            self.assertFalse(tool.annotations.destructiveHint)
            self.assertTrue(tool.annotations.idempotentHint)
            self.assertFalse(tool.annotations.openWorldHint)
            self.assertIsNotNone(tool.outputSchema)

    def test_transport_security_allows_only_the_configured_public_host(self):
        settings = self.server.settings.transport_security

        self.assertTrue(settings.enable_dns_rebinding_protection)
        self.assertEqual(settings.allowed_hosts, ["example.test"])
        self.assertEqual(settings.allowed_origins, ["https://example.test"])
        self.assertNotIn("*", settings.allowed_hosts)

    async def test_search_returns_structured_content_and_json_text_fallback(self):
        from mcp.shared.memory import create_connected_server_and_client_session
        from mcp.types import TextContent

        async with create_connected_server_and_client_session(
            self.server
        ) as session:
            result = await session.call_tool(
                "search",
                {"query": "checkout timeout"},
            )

        self.assertFalse(result.isError)
        self.assertEqual(result.structuredContent["results"][0]["id"], "memory-1")
        self.assertEqual(len(result.content), 1)
        self.assertIsInstance(result.content[0], TextContent)
        self.assertEqual(json.loads(result.content[0].text), result.structuredContent)

    async def test_fetch_returns_complete_citable_document(self):
        from mcp.shared.memory import create_connected_server_and_client_session

        async with create_connected_server_and_client_session(
            self.server
        ) as session:
            result = await session.call_tool("fetch", {"id": "memory-1"})

        self.assertFalse(result.isError)
        self.assertEqual(result.structuredContent["id"], "memory-1")
        self.assertEqual(
            result.structuredContent["url"],
            "https://example.test/memory-1",
        )
        self.assertEqual(result.structuredContent["metadata"]["sequence_no"], 1)


@skipUnless(
    importlib.util.find_spec("pydantic") is not None,
    "pydantic is required for MCP settings tests",
)
class MCPSettingsTests(TestCase):
    def test_remote_database_requires_verify_full_tls(self):
        from continuum.mcp_server import MCPSettings

        environment = {
            "CONTINUUM_DATABASE_URL": (
                "postgresql://user@example.cockroachlabs.cloud:26257/defaultdb"
                "?sslmode=require"
            ),
            "CONTINUUM_CALLER_SCOPES_JSON": json.dumps(
                {"client": {"tenant_id": "tenant", "incident_id": "incident"}}
            ),
            "CONTINUUM_OIDC_ISSUER": "https://issuer.example.test/pool",
            "CONTINUUM_OIDC_REQUIRED_SCOPE": "continuum/memory.read",
            "CONTINUUM_BEDROCK_REGION": "ap-southeast-1",
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(RuntimeError, "sslmode=verify-full"):
                MCPSettings.from_env()

    def test_local_database_and_public_https_url_are_accepted(self):
        from continuum.mcp_server import MCPSettings

        environment = {
            "CONTINUUM_DATABASE_URL": (
                "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"
            ),
            "CONTINUUM_CALLER_SCOPES_JSON": json.dumps(
                {"client": {"tenant_id": "tenant", "incident_id": "incident"}}
            ),
            "CONTINUUM_OIDC_ISSUER": "https://issuer.example.test/pool",
            "CONTINUUM_OIDC_REQUIRED_SCOPE": "continuum/memory.read",
            "CONTINUUM_BEDROCK_REGION": "ap-southeast-1",
            "CONTINUUM_PUBLIC_BASE_URL": "https://example.test/memories",
            "CONTINUUM_MCP_PORT": "9000",
        }
        with patch.dict(os.environ, environment, clear=True):
            settings = MCPSettings.from_env()

        self.assertEqual(settings.port, 9000)
        self.assertEqual(settings.host, "0.0.0.0")

    def test_audited_control_plane_requires_matching_scope_login(self):
        from continuum.mcp_server import MCPSettings

        environment = {
            "CONTINUUM_DATABASE_URL": (
                "postgresql://legacy@127.0.0.1:26257/defaultdb?sslmode=disable"
            ),
            "CONTINUUM_CALLER_SCOPES_JSON": json.dumps(
                {"client-a": {"tenant_id": "tenant-a", "incident_id": "incident-a"}}
            ),
            "CONTINUUM_OIDC_ISSUER": "https://issuer.example.test/pool",
            "CONTINUUM_OIDC_REQUIRED_SCOPE": "continuum/memory.read",
            "CONTINUUM_BEDROCK_REGION": "ap-northeast-2",
            "CONTINUUM_CONTROL_PLANE_DATABASE_URL": (
                "postgresql://continuum_control_plane@127.0.0.1:26257/defaultdb"
                "?sslmode=disable"
            ),
            "CONTINUUM_SCOPE_DATABASE_URLS_JSON": json.dumps(
                {
                    "continuum_scope_abc": (
                        "postgresql://continuum_scope_abc@127.0.0.1:26257/defaultdb"
                        "?sslmode=disable"
                    )
                }
            ),
        }
        with patch.dict(os.environ, environment, clear=True):
            settings = MCPSettings.from_env()
        self.assertTrue(settings.control_plane_database_url)

        environment["CONTINUUM_SCOPE_DATABASE_URLS_JSON"] = json.dumps(
            {
                "continuum_scope_abc": (
                    "postgresql://different@127.0.0.1:26257/defaultdb"
                    "?sslmode=disable"
                )
            }
        )
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(RuntimeError, "login does not match"):
                MCPSettings.from_env()


@skipUnless(MCP_AVAILABLE, "install the MCP extra to run HTTP boundary tests")
class BearerAuthTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from continuum.identity import CallerIdentity, IdentityVerificationError
        from continuum.mcp_server import OIDCAuthMiddleware

        async def accepted(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 204,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b""})

        class FakeVerifier:
            def verify(self, token):
                if token != "valid-token":
                    raise IdentityVerificationError("invalid")
                return CallerIdentity("client", "tenant", "incident")

        self.token = "valid-token"
        self.app = OIDCAuthMiddleware(accepted, verifier=FakeVerifier())

    async def request(self, path="/mcp", authorization=None):
        headers = []
        if authorization is not None:
            headers.append((b"authorization", authorization.encode("utf-8")))
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        await self.app(
            {"type": "http", "method": "POST", "path": path, "headers": headers},
            receive,
            send,
        )
        return messages

    async def test_missing_and_wrong_tokens_fail_closed(self):
        for value in (None, "Basic abc", "Bearer wrong"):
            with self.subTest(value=value):
                messages = await self.request(authorization=value)
                self.assertEqual(messages[0]["status"], 401)
                self.assertIn(
                    (b"cache-control", b"no-store"),
                    messages[0]["headers"],
                )

    async def test_correct_token_reaches_mcp(self):
        messages = await self.request(authorization=f"Bearer {self.token}")
        self.assertEqual(messages[0]["status"], 204)

    async def test_health_is_available_without_credentials(self):
        messages = await self.request(path="/healthz")
        self.assertEqual(messages[0]["status"], 204)

if __name__ == "__main__":
    import unittest

    unittest.main()
