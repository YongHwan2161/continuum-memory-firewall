## Inspiration

The hardest production failure is not “the workflow failed.” It is “the provider effect may already have happened, but the acknowledgement did not.” Rebuilding or signing again can split source, assets, identity, and public proof into different histories. Continuum Memory Firewall treats release recovery with the same rule it applies to agent memory: **provider outcome evidence, not a retry assumption, decides what becomes canonical.**

## The 30-second difference

A release crashes after signing:

1. the immutable GitHub Release, target SHA, asset digests, and original author attestation remain unchanged;
2. the coordinator looks up that exact provider identity and resumes a hash-chained receipt;
3. recovery creates **zero additional author signatures**;
4. the terminal public receipt records the successful coordinator workflow run ID, artifact ID, artifact digest, source SHA, and receipt digest;
5. the one-click judge fetches GitHub's public run and artifact APIs and verifies them directly.

Unknown external effects become an explicit `AMBIGUOUS` hold. They never trigger a blind resend or a false PASS.

## What it does

Continuum runs each agent episode as a durable, scoped contract:

1. Amazon Bedrock may call scoped `search` and `fetch` tools.
2. Search returns server-issued citation handles, so the model cannot invent memory IDs.
3. The model may create only action-specific typed proposals; prohibited fields do not exist in the schema.
4. A transactional outbox executes through a capability-aware provider adapter.
5. Only a successful provider receipt promotes the outcome to canonical CockroachDB memory.

Every call follows one authorization chain:

`verified caller -> audited binding -> server-owned scope -> deterministic SQL identity -> same-scope CockroachDB RLS`

Self-asserted tenant input never selects a database role.

## Measured outcome evidence

The same 36 adversarial incident designs were run across five independent episode-state seeds and all three arms: **180 cases per arm, 540 observations total**.

| Metric | Stateless | Raw RAG | Continuum |
| --- | ---: | ---: | ---: |
| Verified provider outcome success | 44.4% | 52.8% | **100%** |
| Unsafe proposal rate under memory pressure | 55.6% | 88.9% | **0%** |
| Poison exposure rate | 0% | 94.4% | **0%** |
| Canonical promotion precision | n/a | 52.8% | **100%** |
| Cross-scope leaked rows | 0 | 0 | **0** |

Continuum improves verified outcomes over raw RAG by **+47.2 percentage points**; the 10,000-resample paired cluster-bootstrap 95% interval is **+30.6 to +63.9 points**.

## Crash proof, not crash promises

Property-based state-machine tests permute every coordinator crash boundary and assert monotonic state, stable identity, one author attestation, asset cardinality, and fail-closed ambiguity.

A disposable GitHub Release provider matrix then injects real failures after draft creation, asset upload, duplicate upload, receipt upload, and deletion-before-ack. It recovers every case, proves duplicate asset cardinality remains one, deletes the exact draft and tag, publishes zero releases, and generates zero attestations.

## CockroachDB + AWS implementation

- **CockroachDB:** 50,000 non-sensitive 512-dimensional vectors, natural vector-search plan selection, exact ground truth, forced RLS, scoped `NOBYPASSRLS` identities, 31 checksummed migrations, and bounded pools.
- **AWS:** Bedrock Titan embeddings and tool calling, Cognito five-minute JWTs, Lambda Managed MCP proof, Secrets Manager key rotation, S3 private artifacts, CloudWatch, SSM-managed EC2 with fixed SQL egress, GitHub OIDC deployment, and a USD 10 Budget alert.
- **Supply-chain evidence:** an immutable release, one author Sigstore provenance, GitHub platform attestation, release coordinator receipt, and direct public workflow/artifact binding.
- **CI runtime:** checkout, setup-python, and upload-artifact are Node 24 releases pinned by reviewed immutable commit SHAs.

## Real-scale evidence

At 50k rows and beam 512, CockroachDB reaches **96.9% Recall@10**, with warm ANN p50/p95 of **216.4/314.3 ms**, versus an exact 50k baseline of **1168.2/1362.0 ms**. Every tested beam uses the vector-search operator and returns zero foreign-scope rows.

At 50 concurrent agents, a bounded 20-connection cap preserves zero worker errors, zero leaked rows, and exactly one durable action owner. This deliberately measures backpressure instead of hiding it with an unsafe unbounded pool.

## One-click judge path

The public verifier requires no login, secret, or write permission. It binds the live MCP, exact workflow heads, 540 paired observations, per-episode drill-down, vector and pressure receipts, RLS checksum, sandbox provider proof, immutable release assets, Devpost receipt, and the coordinator workflow artifact.

- Judge: https://yonghwan2161.github.io/continuum-memory-firewall/verify.html
- Live incident: https://yonghwan2161.github.io/continuum-memory-firewall/
- Source: https://github.com/YongHwan2161/continuum-memory-firewall

## What we learned

Exactly-once is not a retry count. It is a bounded claim about stable provider identity, durable receipts, explicit capability manifests, reconciliation, and visible ambiguity. Likewise, an ANN index in DDL is not proof; representative scale, natural optimizer choice, exact ground truth, isolation, pressure, and digest-bound receipts make it defensible.

The deeper principle is shared by agent memory and release automation: **similarity or intent may propose what to do, but verified outcomes earn authority and immutable evidence preserves it across failure.**
