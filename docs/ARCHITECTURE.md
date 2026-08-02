# Architecture and trust boundaries

This document is authoritative for component responsibility and trust
boundaries. Current implementation state belongs in
[PROJECT_STATUS.md](PROJECT_STATUS.md); implementation order belongs in
[ROADMAP.md](ROADMAP.md).

The outcome-learning extension adds an explicit episode boundary. See
[EPISODE_CONTRACT.md](EPISODE_CONTRACT.md) for the model/tool authority contract.

## Authority model

Continuum distinguishes observations from durable authority:

```text
untrusted source
    |
    v
candidate_memories
    |
    | deterministic policy evaluation
    v
promotion transaction
    +--> canonical_memories
    +--> candidate decision metadata
    |
    v
idempotent action claim
```

- **Candidate memory** is untrusted input. Its existence does not authorize
  retrieval or an external action.
- **Policy decision** is deterministic application logic. It explains whether a
  candidate is eligible for promotion.
- **CockroachDB transaction** is the durable authority boundary. It decides
  which concurrent attempt commits.
- **Canonical memory** is accepted state scoped to a tenant and incident.
- **Action claim** selects one database winner for an idempotency key. It is not
  proof that an external provider performed the effect.

## Implemented P2A boundary

The repository implements:

```text
Python policy kernel
    -> CockroachMemoryStore
    -> PostgreSQL wire protocol
    -> CockroachDB transaction
       - candidate row lock
       - policy decision
       - canonical insertion or rejection audit
       - serialization retry
    -> action_attempts unique-key claim
    -> accepted payload embedding
    -> tenant + incident prefix vector query
    -> retrieval_audit
    -> read-only MCP search/fetch
```

The test environment launches an ephemeral CockroachDB node, applies the
packaged versioned migrations, and exercises migration replay, drift detection,
DDL/history crash recovery, lease exclusion, promotion, rejection, concurrent
claims, vector persistence, retrieval audit, cross-tenant exclusion, and a
synthetic end-to-end database smoke path. The MCP protocol is tested with an
in-memory client/server transport. The same migration and synthetic vector path
was subsequently live-smoked on the participant CockroachDB Cloud cluster. The
repository MCP service is now deployed on AWS with five-minute Cognito caller
authentication, a server-owned caller-to-scope registry, exact-host
DNS-rebinding protection, and deterministic RLS-confined SQL identities.

## Live evidence boundary

Two cloud paths are deployed and live-smoked:

```text
authorized AWS direct invoke
    -> private Lambda evidence worker
       - read-only Managed MCP tool allowlist
       - input/output bounds
       - one Secrets Manager ARN
       - optional reserved concurrency 1 when the account quota can retain
         AWS's minimum unreserved concurrency; otherwise no reservation
       -> CockroachDB Cloud Managed MCP over HTTPS

remote MCP client
    -> valid TLS + five-minute Cognito token
   -> EC2/Nginx repository MCP
       - exact public Host/Origin allowlist
       - verified caller -> audited active tenant/incident binding
       - deterministic binding -> matching scope SQL identity
       - read-only search/fetch tools
       - deterministic NOBYPASSRLS SQL role without DDL/canonical writes
    -> CockroachDB SQL through one Elastic IP /32
```

The Lambda intentionally has no Function URL, API Gateway, VPC, or NAT Gateway.
It remains an operational evidence client. The separate EC2 endpoint is the
competition application boundary. The repository implementation now resolves
each verified caller through a versioned CockroachDB binding, selects only the
matching deterministic SQL identity, and relies on that identity's RLS policy
for the same scope. The control-plane SQL identity can read binding metadata but
is explicitly denied canonical memory. Live status remains evidence-bound in
`PROJECT_STATUS.md` until the deployment workflow proves this exact path.

The live-versus-planned boundary is:

```mermaid
flowchart LR
  reviewer["Reviewer / authorized AWS operator"]

  subgraph live["Live deployed and verified"]
    lambda["Private AWS Lambda<br/>read-only allowlist"]
    secret["AWS Secrets Manager<br/>one API key"]
    managed["CockroachDB Cloud<br/>Managed MCP"]
    basic["CockroachDB Basic<br/>migrated schema + live vector smoke"]
    repoMcp["OIDC-authenticated repository MCP<br/>search / fetch"]
    runtimeSecret["Runtime secret<br/>caller registry, no static bearer"]
    eip["AWS Elastic IP<br/>only SQL allowlist /32"]
    budget["AWS Budget + 7-day logs<br/>private S3 package"]
    lambda --> secret
    lambda --> managed
    managed --> basic
    repoMcp --> runtimeSecret
    repoMcp --> eip --> basic
    budget -. guardrails .-> lambda
    budget -. guardrails .-> repoMcp
  end

  subgraph local["Repository and CI evidence"]
    policy["Promotion policy"]
    store["Transaction + vector retrieval"]
    policy --> store
  end

  subgraph implemented["Implemented; live status evidence-bound"]
    auth["Audited tenant control plane<br/>bind / rebind / disable"]
  end

  subgraph planned["Planned"]
    outbox["Outbox delivery + reconciliation"]
  end

  reviewer -->|"AWS direct invoke"| lambda
  reviewer -->|"HTTPS + 5-minute JWT"| repoMcp
  store --> repoMcp
  auth --> repoMcp
  auth -. "future delivery authority" .-> outbox
```

The private AWS worker, its minimum-IAM role, its one-secret boundary, the
Managed MCP connection, two read calls, application schema, Titan semantic
query execution, short-lived identity-derived scope, and database RLS are live.
The audited tenant-control-plane lifecycle is implemented; outbox delivery and
reconciliation remain planned.
The current SQL allowlist contains only the AWS Elastic IP `/32`.

## Component ownership

| Component | Owns | Must not own |
|---|---|---|
| Policy kernel | eligibility rules and deterministic decision reason | transaction outcome or external side effects |
| Store transaction | row locking, persistence, replay, conflict retry | changing policy meaning |
| Migration runner | ordered single-statement DDL, durable intent, checksums, renewable lease, schema validation, explicit adoption | hiding drift, guessing a partial legacy schema, or claiming DDL/history atomicity |
| CockroachDB | durable accepted state, uniqueness, audit, concurrent winner | interpreting untrusted prose |
| Repository MCP boundary | authenticated, least-privilege `search`/`fetch` contract | database credentials or caller-selected tenant scope |
| Database pools | bounded, lazy TLS connection reuse per control/scope identity | sharing a connection across SQL identities or exposing connection strings in metrics |
| CockroachDB Managed MCP | managed operational database tools for the competition agent | replacing application retrieval authorization |
| Private AWS evidence worker | bounded direct invocation of a hard-coded read-only Managed MCP subset | public query access, row-level tenant authorization, or arbitrary Managed MCP writes |
| Retrieval service | tenant filter, embedding query, retrieval audit | promotion of untrusted candidates |
| Outbox worker | delivery attempts, leases, acknowledgement, reconciliation | rewriting canonical memory |
| Reviewer console | understandable evidence and scenario control | secret material or unverified production claims |

## Required trust controls

1. Tenant and incident scope must be checked in both application queries and
   database constraints/authorization.
2. Candidate payloads must be treated as data, never as executable instruction.
3. Promotion and audit persistence must commit atomically.
4. Source identity and action idempotency must be unique at the durable layer.
5. Serialization failures must retry the entire transaction.
6. External calls must happen outside the promotion transaction through an
   outbox-style delivery boundary.
7. Secrets must remain server-side and be injected through an approved secret
   channel.
8. Any bearer or short-lived-token destination must be pinned to the official HTTPS host; a
   configurable endpoint must not become a credential-exfiltration path.
9. Managed MCP write tools must be denied before the worker reads its secret.
10. Applied migration bytes are immutable; checksum drift and uncertain schema
    states must fail closed.
11. Runtime authorization must be tested through the exact runtime identity with
    negative DDL/write operations; reviewing direct grants alone is insufficient
    because inherited roles can restore authority.
12. Verified caller identity must select a server-owned scope and a matching
    database role; tool arguments and self-asserted tenant claims cannot choose
    authorization scope.

## Failure semantics

- A policy rejection is a durable, auditable outcome.
- A serialization conflict is retriable and must not leak a partial result.
- A repeated source event returns the prior canonical result.
- A repeated action key returns a duplicate claim, not a second database winner.
- A network timeout after an external send is ambiguous until acknowledged or
  reconciled; it must not be described as exactly-once delivery.

Detailed transaction mechanics are in
[TRANSACTION_MODEL.md](TRANSACTION_MODEL.md).
