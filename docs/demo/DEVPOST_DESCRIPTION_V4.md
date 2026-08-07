## Inspiration

Long-running agents remember tool output, model guesses, and human instructions. If every retrieved observation becomes durable truth, stale or poisoned context can outlive an incident, raw RAG can steer a provider action, and retries can create duplicate effects. Continuum makes the missing production boundary explicit: **a model may retrieve and propose, but only verified provider outcome evidence may become canonical memory.**

## What it does

Continuum Memory Firewall runs an agent episode as a durable contract:

1. Amazon Bedrock may call scoped `search` and `fetch` tools.
2. Search returns server-issued citation handles, not model-invented memory IDs.
3. The model may create only an action-specific typed proposal; prohibited fields are absent from the schema.
4. A transactional outbox executes the proposal through a capability-aware provider adapter.
5. Only a successful provider receipt promotes the episode outcome to canonical CockroachDB memory. Unsupported provider idempotency becomes an explicit `AMBIGUOUS` state rather than a false success.

Every call also follows one authorization chain:

`verified caller -> audited binding -> server-owned tenant/incident -> deterministic SQL identity -> same-scope CockroachDB RLS`

Self-asserted tenant input never selects a database role.

The public demo replays a fixed checkout incident against the participant AWS and CockroachDB deployment: trusted recovery is stored, a poisoned instruction is quarantined, Titan retrieves the verified recovery within scope, and two workers race while CockroachDB records exactly one durable action owner.

## The result: paired agent outcomes, not a retrieval-only score

We ran the same 36 synthetic, non-effecting incident designs across five independent episode-state replications and all three arms: **180 cases per arm, 540 observations total**. The cases deliberately include stale, poisoned, and conflicting memory that can induce a wrong action.

| Metric | Stateless | Raw RAG | Continuum |
| --- | ---: | ---: | ---: |
| Verified provider outcome success | 44.4% | 52.8% | **100%** |
| Unsafe proposal rate under memory pressure | 55.6% | 88.9% | **0%** |
| Poison exposure rate | 0% | 94.4% | **0%** |
| Canonical promotion precision | n/a | 52.8% | **100%** |
| Cross-scope leaked rows | 0 | 0 | **0** |

Continuum improved verified outcomes over raw RAG by **+47.2 percentage points**. A 10,000-resample paired cluster bootstrap over the 36 base incidents gives a **95% interval of +30.6 to +63.9 points**. Continuum produced 180/180 verified provider receipts and zero false canonical promotions; raw RAG produced 95/180 verified receipts and 85 false promotions.

The latency comparison is intentionally outcome-aware: raw RAG's recovery p95 excludes five failed recoveries, while Continuum completed all 30/30 recovery cases. We do not present censored latency as a reliability win.

## How we built it

### CockroachDB

- **Distributed Vector Indexing:** 50,000 non-sensitive 512-dimensional vectors; exact primary-index scans establish ground truth; CockroachDB naturally selects the scoped vector-search operator.
- **Cloud Managed MCP Server:** a private Lambda calls a read-only allowlist. `list_databases` and `list_tables` pass; write tools are rejected before secret access.
- **31 checksummed, single-statement migrations** define `VECTOR(512)`, the four-column scoped vector prefix, episode/outbox/outcome evidence, forced RLS, and the audited tenant control plane.
- Separate bounded Psycopg pools serve the control plane and scope-specific `NOBYPASSRLS` identities.

### AWS

- **Amazon Bedrock:** Titan Text Embeddings v2 creates live 512-dimensional embeddings; Bedrock tool calling drives the constrained episode orchestrator.
- **AWS Lambda:** performs Managed MCP read proofs.
- **Amazon Cognito:** issues five-minute client-credentials JWTs.
- **Amazon S3:** stores private deployment artifacts and immutable evidence inputs.
- **AWS Secrets Manager:** supports fail-closed key rotation and rollback.
- The public MCP runs on an SSM-managed EC2 host with TLS, no SSH, a fixed Elastic IP for SQL egress, CloudWatch logs, GitHub OIDC deployment, and a USD 10 Budget alert.

## Additional measured evidence

### Semantic quality with an attacker in the room

Sixty live Titan queries cover paraphrase, terse wording, typo, negation, misleading scope, and multi-intent:

- Recall@1 / @3 / @5: **86.7% / 98.3% / 100%**
- End-to-end p50 / p95: **242.8 / 270.6 ms**
- Cross-scope leaked documents: **0**

### Real-scale vector index

At 10k and 50k rows, every tested beam uses CockroachDB's vector-search operator, avoids a full scan, and returns zero foreign-scope rows. At 50k / beam 512:

- Recall@1 / @5 / @10: **100% / 97.5% / 96.9%**
- Warm ANN p50 / p95: **216.4 / 314.3 ms**
- Exact 50k baseline p50 / p95: **1168.2 / 1362.0 ms**

### Concurrent-agent pressure

Ten, 25, and 50 agents execute an exact 70% vector-read / 20% trusted-promotion / 10% action-claim mix over 850 live operations:

- worker errors: **0**
- foreign rows: **0**
- durable action owners: **exactly 1** at every level
- peak throughput: **80.4 ops/s** at 25 agents
- deliberate client-pool teardown to first successful ANN read: **118 ms**

At 50 agents, 599 of 603 pool requests queue behind the bounded 20-connection cap; correctness still holds. This shows the next optimization is admission control and outcome-weighted latency, not an unsafe unbounded pool.

## One-click judge path

The public read-only verifier needs no login, token, database secret, or write permission. In one click it binds the live MCP, exact workflow heads, 540 paired episodes, vector and pressure evidence, RLS checksum, sandbox provider receipt, key rotation, Devpost receipt, and immutable release assets.

- Judge verifier: https://yonghwan2161.github.io/continuum-memory-firewall/verify.html
- Live incident: https://yonghwan2161.github.io/continuum-memory-firewall/
- Source: https://github.com/YongHwan2161/continuum-memory-firewall

## Challenges we ran into

The most valuable failures became controls. A three-column vector prefix caused full scans after `embedding_model` entered the predicate, so migration 17 rebuilt the index with every equality-prefix column. An initial detector misunderstood CockroachDB's real vector-plan shape, so the gate now proves the vector operator and independently rejects full scans. The first ablation let the model invent citation IDs; server-issued handles now make that state unrepresentable. Provider failures around send, receipt lookup, and acknowledgement became a transactional outbox with explicit reconciliation capabilities.

## What we learned

An ANN index existing in DDL proves very little. Representative scale, natural optimizer choice, exact ground truth, paired outcome evidence, cross-scope isolation, concurrent load, and digest-bound raw receipts turn it into a defensible implementation claim.

More fundamentally, useful memory is not "everything retrieved." It is the set of outcomes whose authority, scope, provider effect, and promotion lineage can be independently verified.

## What's next

The highest-value next improvement is a per-episode paired drill-down that lets a judge inspect the same stale/poison/conflict incident across stateless, raw-RAG, and Continuum, including issued citation handles, the typed proposal, provider receipt, and promotion decision. We will also add outcome-weighted tail latency, judge-path burn-in, and admission control above the bounded pool while keeping the public judging environment live through evaluation.
