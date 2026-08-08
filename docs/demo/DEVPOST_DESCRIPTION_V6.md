# Continuum Memory Firewall

## A failed action must never become the next agent's memory

Long-running agents need memory, but raw-RAG can retrieve stale, poisoned, or
conflicting history and then append a failed action as if it were truth.
Continuum makes memory promotion an outcome transaction:

1. a verified caller resolves to a server-owned tenant scope;
2. that scope resolves to a least-privileged CockroachDB SQL identity;
3. RLS enforces the same scope on every durable row;
4. Bedrock may call only action-specific, parameter-free proposal tools; and
5. only a verified external-provider receipt can become canonical memory.

## New: real effects replicated across time

We ran the same 36 synthetic release incidents through raw-RAG and Continuum in
five separate, serial, main-only OIDC workflows: 180 pairs and 360 observations.
The inputs are non-sensitive, but the external effects are real: Bedrock creates
typed proposals, CockroachDB stores outcomes and canonical promotions, and
GitHub draft releases and assets are created, inspected, reconciled, or deleted
through the production API.

- **Continuum:** 180/180 verified outcomes, 0 unsafe proposals, 0 unsafe memory
  exposures, 0 unsafe citation adoptions, 0 false promotions, 0 duplicate
  effects, 0 cleanup residuals, and 0 cross-scope leaks.
- **raw-RAG:** 150/180 verified outcomes, 30 unsafe proposals, 112 unsafe memory
  exposures, 37 unsafe citation adoptions, and 30 failed outcomes promoted as
  memory.
- **Temporal consistency:** Continuum beat raw-RAG in 5/5 batches. Aggregate
  lift was +16.67 percentage points; hierarchical workflow-cluster bootstrap
  95% interval +10.0 to +24.44 points.
- **Receipt integrity:** all 330 successful outcomes had non-null, unique
  provider receipt fingerprints; all disposable effects were removed.

The same 36 incident definitions recur in five time clusters, so we do not
pretend these are 180 independent designs. The 180-execution exact p-value is
descriptive only; the cluster-aware interval and five-batch direction
consistency are the primary evidence.

The one-click judge page fetches the aggregate workflow/artifact and all five
source workflow/artifact receipts, then checks source SHA, population checksum,
run attempts, digests, time spacing, safety, cleanup, and immutable release
asset. No judge credential is required.

## Why CockroachDB and AWS are essential

CockroachDB is not a passive vector store. It is the memory authority:

- caller scope and SQL identity are auditable control-plane bindings;
- RLS makes cross-tenant memory invisible even for a perfect semantic match;
- canonical promotion and outcome evidence are transactional;
- a prefixed vector index is naturally selected at 10k and 50k 512-dimensional
  rows; and
- bounded pools retain zero leakage and one durable action owner under 50-agent
  pressure.

AWS supplies the keyless deployment and orchestration plane: main-only GitHub
OIDC, Secrets Manager, fixed-egress EC2, Bedrock Titan embeddings, Nova tool
calling, S3 evidence transport, CloudFormation, and a USD 20 judging-window
Budget alert.

## One immutable proof unit

`hackathon-v12` binds the application evidence, 50k vector benchmark, 50-agent
pressure report, 540-observation three-arm ablation, 180-case episode explorer,
single-run guardian, five time-distributed guardian receipts, their 180-pair
aggregate, RLS checksum, key-rotation receipt, Devpost receipt, workflow
artifact digests, and public judge evidence. The release
transaction is durable-draft-first, author-signed once through Sigstore, made
immutable, automatically reconciled after crashes, and materialized through
Pages.

## Judge links

- 99-second real-provider video: https://youtu.be/OEPYF7cVpbs
- Product proof: https://yonghwan2161.github.io/continuum-memory-firewall/
- One-click verifier: https://yonghwan2161.github.io/continuum-memory-firewall/verify.html
- Real-provider paired explorer: https://yonghwan2161.github.io/continuum-memory-firewall/release-guardian.html
- Five-batch time explorer: https://yonghwan2161.github.io/continuum-memory-firewall/release-guardian-replication.html
- Source: https://github.com/YongHwan2161/continuum-memory-firewall
