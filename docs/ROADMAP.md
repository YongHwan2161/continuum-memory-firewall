# Roadmap

This document is the single source of truth for implementation order and
milestone acceptance criteria. Current completion state belongs in
[PROJECT_STATUS.md](PROJECT_STATUS.md).

## Priority 1 — P2B managed-cloud competition slice

**Goal:** convert the implemented local P2A retrieval/MCP contract into a
competition-eligible, managed-cloud demonstration.

Implement:

1. **Completed 2026-07-31:** run the guarded CockroachDB Basic and AWS account procedure in
   [CLOUD_DEPLOYMENT_RUNBOOK.md](CLOUD_DEPLOYMENT_RUNBOOK.md), then capture one
   successful and one denied Managed MCP Lambda invocation; two successful read
   tools and one pre-secret write denial are now recorded;
2. **Live-data and least-privilege path completed 2026-08-01:** run the implemented versioned
   migrator and synthetic smoke path against the participant database; all
   fifteen migrations and the scoped vector flow passed; deterministic
   per-scope SQL roles plus RLS on canonical memory, incidents, and retrieval
   audit enforce the caller boundary; the allowlist contains only the AWS
   Elastic IP `/32`. Bounded per-identity pooling and redacted query-plan/index
   evidence were added and live-verified on 2026-08-02;
3. **Authenticated remote MCP completed 2026-08-01:** the repository server is
   deployed behind valid TLS and five-minute Cognito client-credentials
   authentication; deterministic, hash-verified SSM deployment and a remote
   allowed/denied-scope smoke passed;
4. **Expanded 2026-08-02:** Bedrock Titan Text Embeddings v2 now runs a
   60-query, six-variant Recall@1/3/5, leakage, and p50/p95 evaluation;
5. **Completed 2026-08-02:** expose exact-head evaluation, authorization,
   pooling, RLS, and vector-index evidence in the one-click read-only judge
   console;
6. **Completed 2026-08-02:** capture repeatable redacted natural-plan and index
   metadata evidence in integration CI and the live AWS/Cockroach smoke.

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
The cost-bounded Managed MCP/AWS path now has participant-owned live evidence.
P2B's authenticated application, short-lived caller identity, database-backed
tenant control plane, RLS, semantic retrieval, pooling, and least-privilege SQL
gates are now closed. The project is submitted. The highest-value remaining
competition work is judge-path polish and representative-scale ANN evidence;
the tiny evaluation corpus correctly records that the cost-based optimizer did
not select the vector index, without overstating a production-scale speedup.

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
- generalize the implemented database-native authorization and deterministic
  per-scope identities into an auditable tenant-control-plane lifecycle;
- separate content identity from commit time in audit hashing, then add
  tamper-evident chain anchoring if the threat model requires it;
- distinguish invalid/unserializable payloads from oversized payloads;
- add retry jitter, deadlines, metrics, connection pooling, TLS validation, and
  `application_name`;
- verify downloaded CI binaries by checksum or use a pinned trusted image;
- add formatting, lint, type, dependency, secret, and static-security checks;
- expand contention, fault-injection, and worker-termination tests.
