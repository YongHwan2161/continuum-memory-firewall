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

**Completed P0 on 2026-08-11 — sealed adaptive CI diagnosis:** exact-head run
`31400622882` generated and write-once sealed a fresh challenge/label commitment
before candidate execution, then bound 84 unique GitHub workflow/artifact
receipts. All three arms recovered 12/12. Continuum used six diagnostic child
workflows versus twelve for stateless and skipped all six registered recurrence
probes; paired exact `p=0.03125`, canonical precision 1.0, false promotion 0,
repository mutation 0, and cleanup residual 0. The earlier 116-child run
`31398666306` remains the immutable fail-closed predecessor at `p=0.0625`; no
threshold or label was changed. The admitted result is exact-fingerprint
information value. It does not claim semantic transfer, higher recovery, or
lower token cost. See
[ADAPTIVE_DIAGNOSIS_BENCHMARK.md](ADAPTIVE_DIAGNOSIS_BENCHMARK.md).

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

### Next fundamental P0 — preregistered counterfactual transfer firewall

The largest remaining evidence risk is now exact-key coupling. The adaptive
benchmark correctly proves that an exact provider-verified fingerprint can
replace a repeated probe, but a judge can still characterize that behavior as
a safe cache lookup rather than generalizable agentic memory. The next automated
evaluation must therefore test causal transfer without exposing an answer key:

- preregister positive-transfer and near-neighbor negative-transfer variants in
  which repository layout, tool version, wording, and environment fingerprint
  change while the latent causal fault either remains or deliberately changes;
- expose only signed causal evidence features and server-issued citation
  handles, never the expected action or transfer label;
- require Continuum to choose among reuse, bounded probe, and fail-closed
  abstention, while stateless and raw-RAG receive identical provider tools;
- score verified recovery, probes saved, calibrated abstention, and recovery
  latency, with **false transfer fixed at zero as the hard gate**; and
- seal challenge/labels before candidates, cluster-bootstrap over generated
  environment families, and bind every disposable GitHub receipt and result to
  the next immutable release.

This P0 has higher judging value than adding another security control or scaling
the exact-fingerprint population: it directly distinguishes durable causal
memory from retrieval-by-key, strengthening Agentic Memory Design, Technical
Implementation, and Real-World Impact with one falsifiable experiment.

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
