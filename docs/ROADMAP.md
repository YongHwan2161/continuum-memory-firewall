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

### Completed P0 — preregistered counterfactual transfer firewall

Exact-head run `31439117749` completed on 2026-08-11. Across six disjoint-
environment counterfactual pairs, Continuum achieved 12/12 recovery, 6/6
provider-attested same-cause transfer without a diagnostic, 6/6 near-neighbour
rejection, and zero false promotion. raw-RAG recovered 6/12 and falsely
transferred and promoted all six near neighbours. All 84 provider receipts have
unique workflow, artifact, and digest identities; the challenge and labels were
sealed before the first candidate call. See
[TRANSFER_FIREWALL_BENCHMARK.md](TRANSFER_FIREWALL_BENCHMARK.md).

### Completed fundamental P0 — online CockroachDB memory-lineage closure

Recovery run `31506117708` completed the previously missing real seam. A
successful GitHub Actions source receipt became canonical CockroachDB memory,
was embedded by Titan v2, and was retrieved through the caller's non-bypass RLS
role. The same-cause target selected that exact memory with zero diagnostics;
the near-neighbour target rejected it and used exactly one current diagnostic.
Both exact proposals were durable before action, both later provider outcomes
succeeded, and both became the next canonical memories. Cross-scope visibility,
repository mutation, cleanup residuals, and false transfer remained zero.

The candidate run `31503686643` intentionally remains failed after its
evaluator crashed following the two external actions. The successful cross-head
reconciler had `actions: read`, no provider-dispatch capability, and reports
provider action reexecution count zero. The public projection removes
server-owned tenant and incident identifiers while retaining candidate and
reconciler SHAs, Actions artifact digests, memory/retrieval/proposal/outcome
IDs, the RLS checksum, and the bounded one-pair/two-case claim. See
[ONLINE_MEMORY_LINEAGE.md](ONLINE_MEMORY_LINEAGE.md).

### Completed fundamental P0 — outcome-receipt CAS and durable reconciliation journal

The live crash exposed the next narrow architectural seam. The CockroachDB
`record_outcome_and_promote` replay path returns an existing proposal outcome,
but does not first compare the incoming provider, receipt ID, status, and
receipt digest to the stored row. The workflow currently prevents mismatched
replay by validating the exact failed-run artifact; that invariant should not
depend only on orchestration code.

Implement one database transaction that:

- inserts the first provider outcome under a proposal-scoped receipt identity;
- returns the existing outcome only when every replay identity field matches;
- records a typed conflict and refuses promotion when any replay field differs;
- persists reconciliation attempt, source head, artifact digest, decision, and
  terminal reason in an append-only journal; and
- proves exact replay, conflicting replay, crash-before-commit, and
  crash-after-commit behavior with CockroachDB integration/property tests.

Migrations 32 and 33, proposal-scoped compare-and-set, typed
`OUTCOME_REPLAY_CONFLICT`, and the append-only reconciliation hash chain are
implemented and live-verified on the participant cluster. Exact replay returns
the one durable outcome; a different real S3 receipt commits a conflict journal
entry before the typed error reaches the caller. See
[the live proof](evidence/2026-08-12-outcome-replay-cas-live.md).

### Completed fundamental P0 — provider-origin outcome attestation admission

Migrations 34 and 35, the server-issued handle contract, atomic CockroachDB
consumption, and RLS are implemented. The handle binds proposal, provider,
idempotency key, provider receipt and digest, success status, verifier policy,
issuer, key ID, nonce, issue time, and expiry. The outbox worker can mint it
only after a fresh adapter receipt lookup; callers cannot construct a bare
successful `ProviderOutcome` and reach promotion.

Participant-cluster run `31650943912` performed seven real S3
`HeadObject`/`GetObject` lookups. One five-minute handle produced exactly one
outcome, one attestation consumption, and one canonical promotion in one
transaction. Missing, forged, expired, cross-proposal, cross-provider, and
receipt-mismatched handles produced typed failures and zero negative outcome
rows. Exact replay remained idempotent, conflicting replay remained journaled,
the raw handle was not persisted, and the NOBYPASSRLS scope role could read its
one row but could not insert an attestation row (`SQLSTATE 42501`). See
[the live receipt](evidence/2026-08-13-provider-outcome-attestation-live.md).

### Next fundamental P0 — durable verifier key custody and rotation continuity

The protocol is closed, but the live proof intentionally used one
process-scoped HMAC authority. The next authority seam is operational custody:

- issue handles with a versioned AWS KMS asymmetric signing key held by a
  verifier-only role after provider lookup;
- let promotion verify signatures locally from a pinned public-key keyring so
  the database transaction has no network dependency and workers have no sign
  permission;
- bind key ARN/version and verifier policy to the persisted digest receipt;
- prove dual-key overlap, rotation, rollback, expiry, verifier restart, and
  exact committed replay without re-signing; and
- add a negative IAM proof that the action worker cannot call `kms:Sign`.

This is higher leverage than another benchmark because it turns the proven
admission protocol into a durable production authority boundary. A second real
adapter should follow under the same key contract rather than create a second
ad hoc signer.

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
