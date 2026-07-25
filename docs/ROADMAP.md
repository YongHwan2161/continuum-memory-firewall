# Roadmap

This document is the single source of truth for implementation order and
milestone acceptance criteria. Current completion state belongs in
[PROJECT_STATUS.md](PROJECT_STATUS.md).

## Priority 1 — P2B managed-cloud competition slice

**Goal:** convert the implemented local P2A retrieval/MCP contract into a
competition-eligible, managed-cloud demonstration.

Implement:

1. run the guarded CockroachDB Basic and AWS account procedure in
   [CLOUD_DEPLOYMENT_RUNBOOK.md](CLOUD_DEPLOYMENT_RUNBOOK.md), then capture one
   successful and one denied Managed MCP Lambda invocation;
2. provision the live database with a least-privilege application identity,
   replace bootstrap-only DDL with versioned migrations, and capture vector
   query-plan evidence;
3. deploy the repository MCP server behind authenticated stable HTTPS and add a
   reproducible remote smoke test;
4. replace deterministic demo embeddings with a bounded semantic embedder and
   add connection pooling, deadlines, and application identity metadata;
5. expose promotion, retrieval, audit, and negative-scope evidence in the
   reviewer console;
6. capture a repeatable deployment check and query-plan evidence in CI or a
   separately documented smoke test.

Exit criteria:

- one submitted candidate can be promoted, semantically embedded, retrieved,
  and audited
  against the live database;
- remote MCP authentication binds a caller to allowed scope and cannot read
  another tenant's memory;
- secrets do not enter source control, logs, or browser code;
- a fresh reviewer can reproduce the flow from documented commands;
- the implementation demonstrably uses two qualifying CockroachDB tools and at
  least one AWS service;
- the cloud resource has an explicit budget/usage guardrail and teardown plan.

**Why this is first:** P2A already proves the application contract locally.
The repository now contains the cost-bounded Managed MCP/AWS deployment path,
so P2B's shortest remaining gate is live participant-owned evidence. That closes
the competition's decisive proof gap before broader product features.

## Priority 2 — P3 reliable external-action delivery

**Goal:** extend database idempotency into an operationally reliable side-effect
workflow without claiming impossible exactly-once network delivery.

Implement:

- transactional outbox creation in the same transaction as the authoritative
  state change;
- leased worker claims with attempt count, lease expiry, next-attempt time, and
  bounded exponential backoff with jitter;
- provider idempotency keys where the destination supports them;
- response digest, acknowledgement time, terminal failure, and reconciliation
  state;
- crash tests covering failure before send, after send, and before
  acknowledgement persistence.

Exit criteria:

- a worker crash cannot permanently strand an action;
- retries do not create duplicate provider effects when provider idempotency is
  available;
- ambiguous outcomes are visible and reconcilable rather than reported as
  successful;
- incident-level concurrency no longer becomes an avoidable action-claim
  hotspot.

## Priority 3 — P4 evaluation and submission evidence

**Goal:** turn the implementation into a judge-friendly, measurable submission.

Implement:

- poisoning and stale-memory scenario corpus;
- policy precision/recall, duplicate-prevention, retrieval relevance, and
  recovery-latency measurements;
- architecture diagram that distinguishes implemented and planned components;
- cloud-backed demo flow and short failure/retry scenario;
- concise Devpost narrative, screenshots, and demo video.

Exit criteria:

- every material claim links to code, test output, deployment evidence, or a
  measured result;
- the demo finishes within the target presentation time and includes one
  negative/security path;
- the checklist in
  [DEVPOST_CHECKLIST.md](DEVPOST_CHECKLIST.md) contains no unresolved required
  item.

## Cross-cutting engineering backlog

The following items should be pulled into the milestone they block:

- persist policy/evaluator version, candidate digest, and structured decision
  evidence with each audit event;
- add database-native authorization or separate per-tenant identities for
  defense beyond the implemented composite keys and application predicates;
- separate content identity from commit time in audit hashing, then add
  tamper-evident chain anchoring if the threat model requires it;
- distinguish invalid/unserializable payloads from oversized payloads;
- add retry jitter, deadlines, metrics, connection pooling, TLS validation, and
  `application_name`;
- verify downloaded CI binaries by checksum or use a pinned trusted image;
- add formatting, lint, type, dependency, secret, and static-security checks;
- expand contention, fault-injection, and worker-termination tests.
