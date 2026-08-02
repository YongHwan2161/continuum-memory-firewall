# Semantic retrieval evaluation

The competition suite contains 60 labeled queries over 10 allowed memories and
10 semantically similar denied-scope lures. Each allowed memory has one query
in every variant class:

- `paraphrase`
- `terse`
- `typo`
- `negation`
- `misleading-scope`
- `multi-intent`

The suite reports Recall@1, Recall@3, Recall@5, returned cross-scope documents,
and nearest-rank p50/p95/max end-to-end latency. Local evaluation additionally
reports how often an unscoped global top-three ranking would contain a foreign
document. That collision metric is not leakage; it demonstrates that the denied
documents are meaningful adversarial lures and that scope enforcement matters.

The live runner measures the complete `MemoryRetrievalStore.search` operation:
Bedrock Titan Text Embeddings v2 invocation, CockroachDB vector query, and
retrieval-audit insert. It uses the RLS-confined runtime SQL identity and fails
the competition gate when Recall@3 is below 0.75 or any denied memory is
returned.

```bash
PYTHONPATH=src python -m continuum.evaluation \
  --dataset evals/adversarial-semantic-retrieval-v2.json \
  --provider titan --region ap-northeast-2 --k 3 --ks 1,3,5
```

The deterministic hashing baseline is suitable for CI mechanics, not as a
semantic-model claim. On the committed suite it currently produces Recall@1
0.65, Recall@3 0.8667, Recall@5 0.9333, zero returned leakage, and 48/60 global
top-three collision opportunities. Live Titan and CockroachDB measurements must
be recorded separately with their exact workflow head.

The live report also records a read-only `EXPLAIN (REDACT)` digest and
`SHOW INDEXES` metadata for the scoped vector query. It fails closed unless the
visible `canonical_memories_model_embedding_idx` declares the tenant, incident,
embedding model, and embedding columns in that order. The raw plan is never
emitted because even a redacted plan is unnecessary public surface; reviewers
receive its SHA-256, line count, expected-index signal, and full-scan signal
instead.

## Outcome-learning three-arm ablation

`continuum.ablation` defines 36 non-sensitive synthetic recurrences across six
incident families and six variants: explicit seed, paraphrase, similar meaning,
poison pressure, stale pressure, and later recurrence. The exact same ordered
case IDs are run through:

1. `stateless`: Nova receives no memory tools;
2. `raw_rag`: Nova retrieves append-all model episodes plus untrusted/stale
   injections from an isolated baseline scope;
3. `continuum`: Nova retrieves only provider-verified canonical outcomes.

All memory-enabled calls use the same Titan embedding model, CockroachDB vector
query, top-k limit, model, action allowlist, and synthetic provider verifier.
The first tool call is forced to a scope-free `search_memory`; a cold start may
propose without citations only after that search returns no rows. Later
proposals must cite returned memory. Tool exposure follows the phase machine in
`EPISODE_CONTRACT.md`, so Nova cannot fetch before search, search repeatedly, or
continue retrieval after a fetch.

The primary metric is provider-receipt success rate, not model text agreement.
The denominator is all 36 eligible cases in every arm. The report also includes
Wilson 95% intervals, p50/p95 end-to-end latency, tool calls, failed and
ambiguous outcomes, canonical promotions, false promotions, and cross-scope
leaks. It also reports stable orchestration failure-code counts and actual
model-turn/tool-call progress for rejected cases, rather than representing all
rejections as zero work. The release gate requires 36 observations in each
arm, zero promotion of failed/ambiguous outcomes, and zero cross-scope leakage.
It does not require a preselected lift; any measured lift or regression is
reported as observed.

The provider is explicitly non-effecting and synthetic. It issues deterministic
idempotent receipts only when the proposal action and target match the labeled
case. This supports causal product comparison without claiming a production
remediation API. The live workflow retains the full 108-observation JSON as a
private GitHub Actions artifact and emits only redacted aggregate evidence.
