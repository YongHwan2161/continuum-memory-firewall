"""Read-only MCP surface for canonical Continuum memory."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Callable, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, Field

from continuum.identity import (
    CallerIdentity,
    CognitoTokenVerifier,
    IdentityVerificationError,
    ScopeRegistry,
    TokenVerifier,
    bind_caller,
    current_caller,
)
from continuum.retrieval import (
    BedrockTitanEmbedder,
    Embedder,
    MemoryNotFoundError,
    MemoryRetrievalStore,
    canonical_payload_text,
)
from continuum.store import PsycopgConnectionPool, database_url_user
from continuum.tenant_control import DatabaseTenantControlPlane


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
    caller_scopes_json: str
    oidc_issuer: str
    oidc_required_scope: str
    bedrock_region: str
    control_plane_database_url: str = ""
    scope_database_urls_json: str = ""
    public_base_url: str = DEFAULT_PUBLIC_BASE_URL
    host: str = "127.0.0.1"
    port: int = 8000

    @classmethod
    def from_env(cls) -> "MCPSettings":
        required = {
            "database_url": os.environ.get("CONTINUUM_DATABASE_URL", ""),
            "caller_scopes_json": os.environ.get(
                "CONTINUUM_CALLER_SCOPES_JSON", ""
            ),
            "oidc_issuer": os.environ.get("CONTINUUM_OIDC_ISSUER", ""),
            "oidc_required_scope": os.environ.get(
                "CONTINUUM_OIDC_REQUIRED_SCOPE", ""
            ),
            "bedrock_region": os.environ.get("CONTINUUM_BEDROCK_REGION", ""),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            environment_names = {
                "database_url": "CONTINUUM_DATABASE_URL",
                "caller_scopes_json": "CONTINUUM_CALLER_SCOPES_JSON",
                "oidc_issuer": "CONTINUUM_OIDC_ISSUER",
                "oidc_required_scope": "CONTINUUM_OIDC_REQUIRED_SCOPE",
                "bedrock_region": "CONTINUUM_BEDROCK_REGION",
            }
            names = ", ".join(environment_names[name] for name in missing)
            raise RuntimeError(f"missing required environment variables: {names}")

        public_base_url = os.environ.get(
            "CONTINUUM_PUBLIC_BASE_URL",
            DEFAULT_PUBLIC_BASE_URL,
        )
        _validate_public_base_url(public_base_url)
        _validate_database_transport(required["database_url"])
        ScopeRegistry.from_json(required["caller_scopes_json"])
        control_plane_database_url = os.environ.get(
            "CONTINUUM_CONTROL_PLANE_DATABASE_URL", ""
        )
        scope_database_urls_json = os.environ.get(
            "CONTINUUM_SCOPE_DATABASE_URLS_JSON", ""
        )
        if bool(control_plane_database_url) != bool(scope_database_urls_json):
            raise RuntimeError(
                "tenant control-plane URL and scope database URLs must be configured together"
            )
        if control_plane_database_url:
            _validate_database_transport(control_plane_database_url)
            ScopeStoreRegistry.validate_json(scope_database_urls_json)

        port_text = os.environ.get("PORT", os.environ.get("CONTINUUM_MCP_PORT", "8000"))
        try:
            port = int(port_text)
        except ValueError as exc:
            raise RuntimeError("MCP port must be an integer") from exc
        if not 1 <= port <= 65535:
            raise RuntimeError("MCP port must be between 1 and 65535")

        return cls(
            database_url=required["database_url"],
            caller_scopes_json=required["caller_scopes_json"],
            oidc_issuer=required["oidc_issuer"],
            oidc_required_scope=required["oidc_required_scope"],
            bedrock_region=required["bedrock_region"],
            control_plane_database_url=control_plane_database_url,
            scope_database_urls_json=scope_database_urls_json,
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


class ScopeStoreRegistry:
    """Select only a database URL whose login matches the audited SQL role."""

    def __init__(
        self,
        stores: dict[str, MemoryRetrievalStore],
        pools: tuple[PsycopgConnectionPool, ...] = (),
    ) -> None:
        if not stores:
            raise ValueError("at least one scope database store is required")
        self._stores = dict(stores)
        self._pools = pools

    @staticmethod
    def _parse_config(value: str) -> dict[str, str]:
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "CONTINUUM_SCOPE_DATABASE_URLS_JSON must be valid JSON"
            ) from exc
        if not isinstance(payload, dict) or not payload:
            raise RuntimeError(
                "CONTINUUM_SCOPE_DATABASE_URLS_JSON must be a non-empty object"
            )
        config: dict[str, str] = {}
        for sql_role, database_url in payload.items():
            if not isinstance(sql_role, str) or not sql_role.startswith(
                "continuum_scope_"
            ):
                raise RuntimeError("scope database URL keys must be scope SQL roles")
            if not isinstance(database_url, str) or not database_url:
                raise RuntimeError("scope database URLs must be non-empty strings")
            _validate_database_transport(database_url)
            if database_url_user(database_url) != sql_role:
                raise RuntimeError("scope database URL login does not match its SQL role")
            config[sql_role] = database_url
        return config

    @classmethod
    def validate_json(cls, value: str) -> None:
        cls._parse_config(value)

    @classmethod
    def from_json(cls, value: str) -> "ScopeStoreRegistry":
        stores: dict[str, MemoryRetrievalStore] = {}
        pools: list[PsycopgConnectionPool] = []
        for sql_role, database_url in cls._parse_config(value).items():
            pool = PsycopgConnectionPool(database_url)
            pools.append(pool)
            stores[sql_role] = MemoryRetrievalStore(pool)
        return cls(stores, tuple(pools))

    def store_for(self, identity: CallerIdentity) -> MemoryRetrievalStore:
        if identity.sql_role is None:
            raise IdentityVerificationError("audited SQL role is required")
        try:
            return self._stores[identity.sql_role]
        except KeyError as exc:
            raise IdentityVerificationError(
                "no database connection is registered for the audited SQL role"
            ) from exc


class ContinuumKnowledgeService:
    """Resolve the authenticated caller before every read-only MCP tool call."""

    def __init__(
        self,
        store: MemoryRetrievalStore | None = None,
        *,
        embedder: Embedder,
        public_base_url: str,
        identity_provider: Callable[[], CallerIdentity] = current_caller,
        store_provider: Callable[[CallerIdentity], MemoryRetrievalStore] | None = None,
    ) -> None:
        _validate_public_base_url(public_base_url)
        if (store is None) == (store_provider is None):
            raise ValueError("configure exactly one retrieval store source")
        self._store = store
        self._store_provider = store_provider
        self._embedder = embedder
        self._public_base_url = public_base_url
        self._identity_provider = identity_provider

    def _store_for(self, identity: CallerIdentity) -> MemoryRetrievalStore:
        if self._store_provider is not None:
            return self._store_provider(identity)
        assert self._store is not None
        return self._store

    def search(self, query: str) -> SearchOutput:
        identity = self._identity_provider()
        result = self._store_for(identity).search(
            tenant_id=identity.tenant_id,
            incident_id=identity.incident_id,
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
        identity = self._identity_provider()
        document = self._store_for(identity).fetch_memory(
            tenant_id=identity.tenant_id,
            incident_id=identity.incident_id,
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
            "Search only accepted canonical memory in the authenticated caller's "
            "server-owned tenant and incident scope. Call search before fetch. "
            "Search results have "
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


class OIDCAuthMiddleware:
    """Verify a short-lived token and bind its caller for one ASGI request."""

    def __init__(self, app: Any, *, verifier: TokenVerifier) -> None:
        self._app = app
        self._verifier = verifier

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope.get("path") == "/healthz":
            await self._app(scope, receive, send)
            return

        authorization = [
            value
            for name, value in scope.get("headers", [])
            if name.lower() == b"authorization"
        ]
        identity: CallerIdentity | None = None
        if len(authorization) == 1 and authorization[0].startswith(b"Bearer "):
            try:
                supplied = authorization[0][len(b"Bearer ") :].decode(
                    "ascii", errors="strict"
                )
                identity = self._verifier.verify(supplied)
            except (UnicodeDecodeError, IdentityVerificationError):
                identity = None
        if identity is None:
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

        with bind_caller(identity):
            await self._app(scope, receive, send)


def _healthz_handler(authorization_mode: str):
    async def healthz(_request: Any):
        from starlette.responses import JSONResponse

        return JSONResponse(
            {
                "ok": True,
                "service": "continuum-memory-firewall",
                "authorization_mode": authorization_mode,
                "database_connections": "bounded-pools-1-4",
            },
            headers={
                "Cache-Control": "no-store",
                "Access-Control-Allow-Origin": (
                    "https://yonghwan2161.github.io"
                ),
                "Vary": "Origin",
            },
        )

    return healthz


def create_authenticated_app(
    server: Any,
    *,
    verifier: TokenVerifier,
    authorization_mode: str = "static-registry",
):
    """Create the public ASGI boundary with health and OIDC authentication."""

    from starlette.routing import Route

    app = server.streamable_http_app()
    app.routes.append(
        Route(
            "/healthz",
            _healthz_handler(authorization_mode),
            methods=["GET"],
        )
    )
    return OIDCAuthMiddleware(app, verifier=verifier)


def _service_and_scope_resolver(settings: MCPSettings):
    embedder = BedrockTitanEmbedder(region=settings.bedrock_region)
    if settings.control_plane_database_url:
        resolver = DatabaseTenantControlPlane(
            PsycopgConnectionPool(settings.control_plane_database_url)
        )
        stores = ScopeStoreRegistry.from_json(settings.scope_database_urls_json)
        service = ContinuumKnowledgeService(
            embedder=embedder,
            public_base_url=settings.public_base_url,
            store_provider=stores.store_for,
        )
        return service, resolver, "audited-tenant-control-plane"
    service = ContinuumKnowledgeService(
        MemoryRetrievalStore(PsycopgConnectionPool(settings.database_url)),
        embedder=embedder,
        public_base_url=settings.public_base_url,
    )
    return (
        service,
        ScopeRegistry.from_json(settings.caller_scopes_json),
        "static-registry",
    )


def build_server_from_settings(settings: MCPSettings):
    service, _resolver, _mode = _service_and_scope_resolver(settings)
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
    service, resolver, mode = _service_and_scope_resolver(settings)
    server = create_mcp_server(
        service,
        host=settings.host,
        port=settings.port,
        website_url=settings.public_base_url,
    )
    verifier = CognitoTokenVerifier(
        issuer=settings.oidc_issuer,
        required_scope=settings.oidc_required_scope,
        registry=resolver,
    )
    return create_authenticated_app(
        server,
        verifier=verifier,
        authorization_mode=mode,
    )


def main() -> None:
    import uvicorn

    settings = MCPSettings.from_env()
    service, resolver, mode = _service_and_scope_resolver(settings)
    app = create_authenticated_app(
        create_mcp_server(
            service,
            host=settings.host,
            port=settings.port,
            website_url=settings.public_base_url,
        ),
        verifier=CognitoTokenVerifier(
            issuer=settings.oidc_issuer,
            required_scope=settings.oidc_required_scope,
            registry=resolver,
        ),
        authorization_mode=mode,
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
