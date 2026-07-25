# Roadmap

This document is the single source of truth for implementation order and
milestone acceptance criteria. Current completion state belongs in
[PROJECT_STATUS.md](PROJECT_STATUS.md).

## Priority 1 — P2 cloud-backed retrieval vertical slice

**Goal:** replace the largest current non-claim with a small, end-to-end,
reviewable CockroachDB Cloud demonstration.

Implement:

1. provision a cost-capped CockroachDB Cloud database and least-privilege
   application identity;
2. add secure configuration validation, connection pooling, timeouts, and
   application identity metadata;
3. ingest canonical-memory embeddings into `VECTOR(512)`;
4. implement tenant-scoped vector retrieval through a minimal Managed MCP tool;
5. record retrieval audit rows and expose evidence in the reviewer console;
6. capture a repeatable deployment check and query-plan evidence in CI or a
   separately documented smoke test.

Exit criteria:

- one submitted candidate can be promoted, embedded, retrieved, and audited
  against the live database;
- the MCP tool cannot read another tenant's memory;
- secrets do not enter source control, logs, or browser code;
- a fresh reviewer can reproduce the flow from documented commands;
- the cloud resource has an explicit budget/usage guardrail and teardown plan.

**Why this is first:** it directly demonstrates CockroachDB as the system of
record and vector retrieval engine, removes the most material gap in the current
demo, and creates better competition evidence than adding a second cloud
provider before the primary database path is real.

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
- enforce tenant integrity in the database with composite keys and/or row-level
  controls rather than relying only on application predicates;
- separate content identity from commit time in audit hashing, then add
  tamper-evident chain anchoring if the threat model requires it;
- distinguish invalid/unserializable payloads from oversized payloads;
- constrain decision and lifecycle states in DDL;
- add retry jitter, deadlines, metrics, connection pooling, TLS validation, and
  `application_name`;
- verify downloaded CI binaries by checksum or use a pinned trusted image;
- add formatting, lint, type, dependency, secret, and static-security checks;
- expand contention, fault-injection, and worker-termination tests.
