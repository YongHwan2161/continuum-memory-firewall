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

**Completed 2026-08-02 for the bounded synthetic adapter:** migrations 29–30,
the transactional outbox worker, and participant-cluster crash injection now
cover before-send, idempotent after-send, before-ack, and non-idempotent
after-send uncertainty. The first three converge with zero duplicate effects;
the last terminates as `ambiguous` without blind resend or memory promotion.
A real provider capability contract remains P3 production follow-up.

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

**Completed P0 on 2026-08-10 — real CI closed-loop recovery:** reviewed source
produced 54 unique GitHub workflow/artifact receipts across six calibrated
fault families. Continuum and stateless recovered 12/12; raw-RAG recovered
11/12 and falsely promoted its one failed recurrence. Exact-head, provider,
artifact, public projection, no-mutation, and cleanup gates are bound into the
public judge and v18 release evidence. See
[CI_RECOVERY_BENCHMARK.md](CI_RECOVERY_BENCHMARK.md).

**Next P0 — sealed adaptive CI diagnosis:** the current explicit diagnostics
make the stateless arm perfect, so adding more source-defined repair families
would repeat safety evidence without proving the causal value of memory. The
next benchmark should preregister disposable repository variants whose first
red log is deliberately non-identifying. Each arm receives the same tool and
time budget and must choose provider-backed diagnostic probes before proposing
a patch. Hidden variant labels open only after all arms finish. Primary metrics
are verified recovery within budget, unnecessary diagnostic calls and cost,
recurrence MTTR, false promotion, and cleanup residual. The hard product claim
is admitted only if Continuum improves the paired recovery/cost frontier over
stateless while preserving false promotion 0. This is the shortest path from
“safe memory” to “memory supplies otherwise unavailable information.”

**Current:** the 540-observation synthetic ablation and the real-provider
guardian are separate evidence layers. In five serial, main-only OIDC workflow
clusters, the guardian repeated the same 36 incident definitions for 180 paired
executions. Continuum produced 180/180 verified outcomes versus raw-RAG 150/180
(+16.667 points; hierarchical workflow-cluster bootstrap 95% interval +10.0 to
+24.444), with zero unsafe proposals, poison exposure, citation adoption,
leakage, false promotion, duplicate effect, or cleanup residual. All five
clusters favored Continuum. Because the same definitions recur, the
180-execution exact p-value is descriptive rather than an independent-case
claim. The 99.53-second public video, Devpost submission, release-envelope v12,
five-state crash-reconciled release receipt, exact-head episode drill-down,
single-run guardian, and time-distributed aggregate are the judge-facing proof
surface. The remaining evidence priority is signed judge-path burn-in through
the submission and judging windows.

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

### In progress — preregistered blind generalization

The largest remaining evidence risk is no longer missing security controls or
missing repetition. It is evaluator coupling: the same 36 hand-designed case
definitions are visible to the implementation and recur across time. The source
now implements a fully automated evaluation firewall:

- seal a checksum-addressed challenge manifest in S3 before any candidate run;
- generate new provider-state families and paraphrases with an independent
  Bedrock job, keeping expected labels inaccessible to the candidate runtime;
- run raw-RAG and Continuum against the same sealed holdout and score them only
  after both arms finish;
- bind the manifest timestamp, generator/evaluator versions, workflow SHA,
  artifact digest, and result to the immutable release envelope; and
- fail closed if source, labels, or scoring policy change after preregistration.

The second real adapter is an encrypted, disposable S3 object provider with the
same idempotency, receipt lookup, reconciliation-timeout, and cleanup contract
as the GitHub draft adapter. Live metrics and release-envelope v13 remain HOLD
until the source merges and the main-only production environment workflow
passes. Adding more controls to the old GitHub-only case family does not precede
that gate.

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
