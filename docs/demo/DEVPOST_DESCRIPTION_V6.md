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

## New: real external effects, paired end to end

We ran the same 36 synthetic release incidents through raw-RAG and Continuum,
72 observations total. The inputs are non-sensitive, but the external effects
are real: GitHub draft releases and assets are created, inspected, reconciled,
quarantined, or deleted through the production GitHub Releases API.

- **Continuum:** 36/36 verified outcomes, 0 unsafe proposals, 0 unsafe memory
  exposures, 0 false promotions, 0 duplicate effects, and 0 cleanup residuals.
- **raw-RAG:** 31/36 verified outcomes, 5 unsafe proposals, 23 unsafe memory
  exposures, and 5 failed outcomes promoted as memory.
- **Paired lift:** +13.89 percentage points; bootstrap 95% interval +2.78 to
  +25.0 points. The 36-pair exact p-value is 0.0625, so we present this as
  high-value real-provider validation, not as an overstated standalone p < .05
  result.

The one-click judge page checks the successful workflow and artifact APIs, raw
report and public-projection digests, immutable release asset, exact population,
provider capability manifest, and zero-residual cleanup. A paired drill-down
shows the proposal, provider receipt fingerprint, promotion decision, and
latency for both arms.

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

`hackathon-v11` binds the application evidence, 50k vector benchmark, 50-agent
pressure report, 540-observation three-arm ablation, 180-case episode explorer,
real-provider guardian raw report, RLS checksum, key-rotation receipt, Devpost
receipt, workflow artifact digests, and public judge evidence. The release
transaction is durable-draft-first, author-signed once through Sigstore, made
immutable, automatically reconciled after crashes, and materialized through
Pages.

## Judge links

- Product proof: https://yonghwan2161.github.io/continuum-memory-firewall/
- One-click verifier: https://yonghwan2161.github.io/continuum-memory-firewall/verify.html
- Real-provider paired explorer: https://yonghwan2161.github.io/continuum-memory-firewall/release-guardian.html
- Source: https://github.com/YongHwan2161/continuum-memory-firewall
