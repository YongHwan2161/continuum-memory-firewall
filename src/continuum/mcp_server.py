"""Read-only MCP surface for canonical Continuum memory."""

from __future__ import annotations

from dataclasses import dataclass
import hmac
import json
import os
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, Field

from continuum.retrieval import (
    HashingEmbedder,
    MemoryNotFoundError,
    MemoryRetrievalStore,
    canonical_payload_text,
)
from continuum.store import psycopg_connection_factory


DEFAULT_PUBLIC_BASE_URL = (
    "https://continuum-memory-firewall.ant713800.chatgpt.site/"
)


class SearchResult(BaseModel):
    id: str
    title: str
    url: str


class SearchOutput(BaseModel):
    results: list[SearchResult]


class FetchOutput(BaseModel):
    id: str
    title: str
    text: str
    url: str
    metadata: dict[str, Any] | None = None


class KnowledgeService(Protocol):
    def search(self, query: str) -> SearchOutput: ...

    def fetch(self, memory_id: str) -> FetchOutput: ...


@dataclass(frozen=True, slots=True)
class MCPSettings:
    database_url: str
    tenant_id: str
    incident_id: str
    bearer_token: str
    public_base_url: str = DEFAULT_PUBLIC_BASE_URL
    host: str = "127.0.0.1"
    port: int = 8000

    @classmethod
    def from_env(cls) -> "MCPSettings":
        required = {
            "database_url": os.environ.get("CONTINUUM_DATABASE_URL", ""),
            "tenant_id": os.environ.get("CONTINUUM_TENANT_ID", ""),
            "incident_id": os.environ.get("CONTINUUM_INCIDENT_ID", ""),
            "bearer_token": os.environ.get("CONTINUUM_MCP_BEARER_TOKEN", ""),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            environment_names = {
                "database_url": "CONTINUUM_DATABASE_URL",
                "tenant_id": "CONTINUUM_TENANT_ID",
                "incident_id": "CONTINUUM_INCIDENT_ID",
                "bearer_token": "CONTINUUM_MCP_BEARER_TOKEN",
            }
            names = ", ".join(environment_names[name] for name in missing)
            raise RuntimeError(f"missing required environment variables: {names}")

        public_base_url = os.environ.get(
            "CONTINUUM_PUBLIC_BASE_URL",
            DEFAULT_PUBLIC_BASE_URL,
        )
        _validate_public_base_url(public_base_url)
        _validate_database_transport(required["database_url"])

        port_text = os.environ.get("PORT", os.environ.get("CONTINUUM_MCP_PORT", "8000"))
        try:
            port = int(port_text)
        except ValueError as exc:
            raise RuntimeError("MCP port must be an integer") from exc
        if not 1 <= port <= 65535:
            raise RuntimeError("MCP port must be between 1 and 65535")

        return cls(
            database_url=required["database_url"],
            tenant_id=required["tenant_id"],
            incident_id=required["incident_id"],
            bearer_token=required["bearer_token"],
            public_base_url=public_base_url,
            host=os.environ.get("CONTINUUM_MCP_HOST", "0.0.0.0"),
            port=port,
        )


def _validate_public_base_url(value: str) -> None:
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.netloc:
        raise RuntimeError("CONTINUUM_PUBLIC_BASE_URL must be an absolute HTTPS URL")


def _validate_database_transport(database_url: str) -> None:
    """Reject cleartext remote database configuration at the process boundary."""

    parts = urlsplit(database_url)
    hostname = parts.hostname or ""
    local = hostname in {"127.0.0.1", "localhost", "::1"}
    query = dict(parse_qsl(parts.query))
    if not local and query.get("sslmode") != "verify-full":
        raise RuntimeError(
            "remote CONTINUUM_DATABASE_URL must set sslmode=verify-full"
        )


def _memory_url(base_url: str, memory_id: str) -> str:
    parts = urlsplit(base_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["memory"] = memory_id
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path or "/", urlencode(query), "")
    )


def _memory_title(payload: dict[str, Any], memory_id: str) -> str:
    for field in ("title", "summary", "service", "kind"):
        value = payload.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()[:160]
    return f"Canonical memory {memory_id[:8]}"


class ContinuumKnowledgeService:
    """Bind a fixed tenant and incident scope to the read-only MCP tools."""

    def __init__(
        self,
        store: MemoryRetrievalStore,
        *,
        tenant_id: str,
        incident_id: str,
        public_base_url: str,
    ) -> None:
        _validate_public_base_url(public_base_url)
        self._store = store
        self._tenant_id = tenant_id
        self._incident_id = incident_id
        self._public_base_url = public_base_url
        self._embedder = HashingEmbedder()

    def search(self, query: str) -> SearchOutput:
        result = self._store.search(
            tenant_id=self._tenant_id,
            incident_id=self._incident_id,
            query=query,
            embedder=self._embedder,
        )
        return SearchOutput(
            results=[
                SearchResult(
                    id=hit.memory_id,
                    title=_memory_title(dict(hit.payload), hit.memory_id),
                    url=_memory_url(self._public_base_url, hit.memory_id),
                )
                for hit in result.hits
            ]
        )

    def fetch(self, memory_id: str) -> FetchOutput:
        document = self._store.fetch_memory(
            tenant_id=self._tenant_id,
            incident_id=self._incident_id,
            memory_id=memory_id,
        )
        payload = dict(document.payload)
        return FetchOutput(
            id=document.memory_id,
            title=_memory_title(payload, document.memory_id),
            text=canonical_payload_text(payload),
            url=_memory_url(self._public_base_url, document.memory_id),
            metadata={
                "accepted_at": document.accepted_at.isoformat(),
                "embedding_model": document.embedding_model,
                "sequence_no": document.sequence_no,
            },
        )


def create_mcp_server(
    service: KnowledgeService,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    website_url: str = DEFAULT_PUBLIC_BASE_URL,
):
    """Create the official FastMCP v1 read-only server."""

    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.server.transport_security import TransportSecuritySettings
        from mcp.types import ToolAnnotations
    except ImportError as exc:  # pragma: no cover - package boundary
        raise RuntimeError("install the MCP extra: pip install '.[mcp]'") from exc

    public_url = urlsplit(website_url)
    if public_url.scheme != "https" or not public_url.netloc:
        raise RuntimeError("website_url must be an absolute HTTPS URL")

    server = FastMCP(
        "continuum-memory-firewall",
        instructions=(
            "Search only accepted canonical memory in the configured synthetic "
            "tenant and incident. Call search before fetch. Search results have "
            "already passed the retrieval policy; candidate and rejected memory "
            "are never exposed by these tools."
        ),
        website_url=website_url,
        host=host,
        port=port,
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[public_url.netloc],
            allowed_origins=[f"{public_url.scheme}://{public_url.netloc}"],
        ),
    )
    read_only = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        openWorldHint=False,
        idempotentHint=True,
    )

    @server.tool(
        name="search",
        title="Search canonical memory",
        description=(
            "Use this when the user wants to find accepted memories relevant "
            "to a query in the configured tenant and incident."
        ),
        annotations=read_only,
    )
    def search(
        query: str = Field(
            min_length=1,
            max_length=2_000,
            description="Natural-language search query.",
        ),
    ) -> SearchOutput:
        return service.search(query)

    @server.tool(
        name="fetch",
        title="Fetch canonical memory",
        description=(
            "Use this when a prior search returned a memory id and the user "
            "needs the complete accepted memory with citation metadata."
        ),
        annotations=read_only,
    )
    def fetch(
        id: str = Field(
            min_length=1,
            max_length=128,
            description="Canonical memory id returned by search.",
        ),
    ) -> FetchOutput:
        try:
            return service.fetch(id)
        except MemoryNotFoundError as exc:
            raise ValueError(
                "canonical memory was not found in the configured scope"
            ) from exc

    return server


class BearerAuthMiddleware:
    """Fail closed before an unauthenticated request reaches MCP."""

    def __init__(self, app: Any, *, bearer_token: str) -> None:
        if len(bearer_token) < 32:
            raise RuntimeError("CONTINUUM_MCP_BEARER_TOKEN must be at least 32 characters")
        self._app = app
        self._bearer_token = bearer_token.encode("utf-8")

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope.get("path") == "/healthz":
            await self._app(scope, receive, send)
            return

        authorization = [
            value
            for name, value in scope.get("headers", [])
            if name.lower() == b"authorization"
        ]
        valid = False
        if len(authorization) == 1 and authorization[0].startswith(b"Bearer "):
            supplied = authorization[0][len(b"Bearer ") :]
            valid = hmac.compare_digest(supplied, self._bearer_token)
        if not valid:
            body = json.dumps(
                {"error": "unauthorized"},
                separators=(",", ":"),
            ).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                        (b"www-authenticate", b"Bearer"),
                        (b"cache-control", b"no-store"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        await self._app(scope, receive, send)


async def _healthz(_request: Any):
    from starlette.responses import JSONResponse

    return JSONResponse(
        {"ok": True, "service": "continuum-memory-firewall"},
        headers={"Cache-Control": "no-store"},
    )


def create_authenticated_app(server: Any, *, bearer_token: str):
    """Create the public ASGI boundary with health and bearer authentication."""

    from starlette.routing import Route

    app = server.streamable_http_app()
    app.routes.append(Route("/healthz", _healthz, methods=["GET"]))
    return BearerAuthMiddleware(app, bearer_token=bearer_token)


def build_server_from_settings(settings: MCPSettings):
    store = MemoryRetrievalStore(
        psycopg_connection_factory(settings.database_url)
    )
    service = ContinuumKnowledgeService(
        store,
        tenant_id=settings.tenant_id,
        incident_id=settings.incident_id,
        public_base_url=settings.public_base_url,
    )
    return create_mcp_server(
        service,
        host=settings.host,
        port=settings.port,
        website_url=settings.public_base_url,
    )


def build_server_from_env():
    return build_server_from_settings(MCPSettings.from_env())


def build_authenticated_app_from_env():
    settings = MCPSettings.from_env()
    server = build_server_from_settings(settings)
    return create_authenticated_app(server, bearer_token=settings.bearer_token)


def main() -> None:
    import uvicorn

    settings = MCPSettings.from_env()
    app = create_authenticated_app(
        build_server_from_settings(settings),
        bearer_token=settings.bearer_token,
    )
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        access_log=True,
        timeout_keep_alive=5,
        limit_concurrency=16,
    )


if __name__ == "__main__":
    main()
