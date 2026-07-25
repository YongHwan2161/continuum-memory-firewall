# Architecture and trust boundaries

This document is authoritative for component responsibility and trust
boundaries. Current implementation state belongs in
[PROJECT_STATUS.md](PROJECT_STATUS.md); implementation order belongs in
[ROADMAP.md](ROADMAP.md).

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

The test environment launches an ephemeral CockroachDB node, applies
`db/schema.sql`, and exercises promotion, replay, rejection, and concurrent
claims plus vector persistence, retrieval audit, and cross-tenant exclusion. The
MCP protocol is tested with an in-memory client/server transport. This is
executable evidence, but not a managed-cloud or public MCP deployment.

## Target cloud boundary

The planned competition vertical slice is:

```text
Reviewer UI / agent
    -> authenticated repository MCP service
       -> promotion and retrieval service
          -> CockroachDB Cloud
             - candidate and canonical authority
             - vector storage and tenant-scoped retrieval
             - decision and retrieval audit
          -> transactional outbox
             -> optional AWS worker / model service
             -> provider acknowledgement and reconciliation
    -> CockroachDB Cloud Managed MCP
       -> operational database evidence for the agent/reviewer
```

This diagram is a target design. CockroachDB Cloud, Cloud Managed MCP, and AWS
are not implemented merely because they appear here. Vector query execution is
implemented only against the disposable integration environment.

## Component ownership

| Component | Owns | Must not own |
|---|---|---|
| Policy kernel | eligibility rules and deterministic decision reason | transaction outcome or external side effects |
| Store transaction | row locking, persistence, replay, conflict retry | changing policy meaning |
| CockroachDB | durable accepted state, uniqueness, audit, concurrent winner | interpreting untrusted prose |
| Repository MCP boundary | authenticated, least-privilege `search`/`fetch` contract | database credentials or caller-selected tenant scope |
| CockroachDB Managed MCP | managed operational database tools for the competition agent | replacing application retrieval authorization |
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

## Failure semantics

- A policy rejection is a durable, auditable outcome.
- A serialization conflict is retriable and must not leak a partial result.
- A repeated source event returns the prior canonical result.
- A repeated action key returns a duplicate claim, not a second database winner.
- A network timeout after an external send is ambiguous until acknowledged or
  reconciled; it must not be described as exactly-once delivery.

Detailed transaction mechanics are in
[TRANSACTION_MODEL.md](TRANSACTION_MODEL.md).
