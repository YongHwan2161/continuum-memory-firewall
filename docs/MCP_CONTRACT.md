# MCP contract

This document is the single source of truth for the repository MCP tool schema,
scope, transport, and deployment boundary. Current implementation evidence and
non-claims belong in [PROJECT_STATUS.md](PROJECT_STATUS.md).

## Server shape

The server is a tool-only MCP application built with the official Python MCP
SDK. It runs Streamable HTTP at `/mcp`, emits JSON responses, and exposes exactly
two read-only tools:

| Tool | Input | Output |
|---|---|---|
| `search` | `query`: non-empty string, maximum 2,000 characters | `results[]` containing `id`, `title`, and absolute HTTPS `url` |
| `fetch` | `id`: canonical memory identifier returned by `search` | `id`, `title`, canonical JSON `text`, absolute HTTPS `url`, and metadata |

Both tools declare read-only, non-destructive, idempotent, closed-world
annotations. Protocol tests assert the advertised schemas and verify both
`structuredContent` and its JSON text fallback.

## Authorization and scope

Tenant and incident identifiers are process configuration, never tool inputs.
Every database read and write includes both identifiers, and composite database
constraints preserve their relationship. Rejected candidates are not queried by
the retrieval store and are not exposed by MCP.

The competition deployment wraps this fixed scope in a server-side bearer
boundary. That is sufficient to deny unauthenticated access and demonstrate
cross-scope exclusion for one synthetic scenario. It is not a substitute for
production caller authentication. A multi-user deployment must add short-lived
OAuth/JWT identity and derive permitted scope from authenticated claims rather
than one process-wide scope.

## Runtime configuration

Required variables:

- `CONTINUUM_DATABASE_URL`
- `CONTINUUM_TENANT_ID`
- `CONTINUUM_INCIDENT_ID`
- `CONTINUUM_MCP_BEARER_TOKEN` — at least 32 random characters

Optional variables:

- `CONTINUUM_PUBLIC_BASE_URL` — absolute HTTPS base for citable memory links
- `CONTINUUM_MCP_HOST` — defaults to `0.0.0.0` when loaded from the environment
- `CONTINUUM_MCP_PORT` or platform-provided `PORT` — defaults to `8000`

Remote database URLs fail closed unless `sslmode=verify-full` is present.
Credentials must be injected through the deployment platform's secret mechanism
and must not appear in source, browser code, command history, or logs.
FastMCP DNS-rebinding protection stays enabled; the server accepts only the
configured public HTTPS host and origin.

## Embedding boundary

`HashingEmbedder` is deterministic, local, and zero-cost. It exists to prove:

- embedding persistence with model identity;
- CockroachDB `VECTOR(512)` cosine ranking;
- mandatory tenant and incident prefix filters;
- accepted-result thresholds and durable retrieval evidence.

It is lexical test/demo machinery, not a semantic-quality claim. The managed
cloud slice must replace it with a bounded semantic embedder and a measured
retrieval evaluation while retaining explicit model versioning.

## Deployment acceptance gate

A production or competition deployment is not complete until:

1. `/mcp` is available at stable public HTTPS;
2. authentication is enforced server-side;
3. a remote client can list and call both tools;
4. a negative-scope test proves cross-tenant denial;
5. database TLS, secrets, timeouts, pooling, logs, and budget controls are
   verified;
6. citation URLs resolve to durable reviewer-visible content.

The 2026-08-01 competition deployment closes gates 1–4 and verifies database
TLS, secret injection, bounded HTTP handling, budget alerts, and fixed SQL
egress. Production pooling and durable reviewer-visible live-memory pages remain
separate hardening work rather than implied by that deployment.
