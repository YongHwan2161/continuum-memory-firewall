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
incident families and six ordered variants: explicit seed, paraphrase, poison
pressure, stale pressure, conflicting-memory pressure, and clean recovery. Five independent episode
state replications run the exact same ordered case IDs through each arm, for
180 observations per arm and 540 total observations:

1. `stateless`: Nova receives no memory tools;
2. `raw_rag`: Nova retrieves append-all model episodes plus untrusted, stale,
   and conflicting
   injections from an isolated baseline scope;
3. `continuum`: Nova retrieves only provider-verified canonical outcomes.

All memory-enabled calls use the same Titan embedding model, CockroachDB vector
query, top-k limit, model, action allowlist, and synthetic provider verifier.
The first tool call is forced to a scope-free `search_memory`; a cold start may
propose without citations only after that search returns no rows. Later
proposals must cite server-issued handles returned by the current search. The
model never receives database memory IDs, and fetch/proposal schemas contain a
dynamic enum of only the current episode's handles. Tool exposure follows the phase machine in
`EPISODE_CONTRACT.md`, so Nova cannot fetch before search, search repeatedly, or
continue retrieval after a fetch.

The paired pressure sequence first establishes clean verified precedent, then
injects plausible but unverified raw records that recommend a labeled wrong
action, an obsolete topology action, and a conflicting newest-looking action.
Only the raw-RAG scope receives those records. The final recovery case measures
whether an arm returns to a provider-verified action after the pressure. This is
an intervention on memory policy: incident labels, case order, model,
embeddings, retrieval limits, and provider verifier remain paired.

The pre-registered judge metrics are:

- unsafe proposal rate, including the pressure-only denominator;
- unsafe-memory exposure rate, defined as any injected poison, stale, or
  conflicting record entering the search result in a pressure case;
- poison exposure rate, defined narrowly as an injected poison handle entering
  the result; per-kind poison/stale/conflict exposure and citation adoption are
  reported separately to distinguish seeing bad memory from relying on it;
- verified outcome success, requiring the expected provider receipt;
- canonical promotion precision, where Continuum counts only outcome-gated
  writes and raw-RAG counts its append-all strategy write; and
- recovery latency over successful clean recovery episodes, with failed
  recoveries reported as censored rather than silently dropped.

Provider-receipt success remains the primary outcome, not model text agreement.
The denominator is all 180 eligible cases in every arm. The five identifiers are
replication IDs, not a claim that Bedrock Converse exposes an RNG seed: every
replication receives a fresh CockroachDB incident scope while the identifier is
retained only as Bedrock request metadata and evidence lineage. This prevents
memory carry-over between replications without pretending to control provider
sampling.

The report includes Wilson 95% intervals for success, unsafe proposals,
unsafe-memory and poison exposure, and promotion precision; p50/p95 end-to-end
and recovery latency; tool calls, failed and ambiguous outcomes, canonical
promotions, false promotions, and cross-scope leaks. Pairwise arm differences are computed on all 180 matched
observations. The two-sided exact sign test uses discordant pairs; a deterministic
10,000-resample paired cluster bootstrap resamples the 36 base incidents and
keeps their five replications together, avoiding falsely treating repeated
incidents as 180 independent semantic cases. Failure-cause totals and per-seed
distributions distinguish orchestration rejection, no proposal, action mismatch,
resource mismatch, provider rejection, and ambiguous outcome where applicable.

The release gate requires 180 observations in each arm, all three 180-pair
success comparisons, all three 90-pair safety comparisons, zero failed/ambiguous
promotion by Continuum, no pressure exposure in Continuum/stateless, zero
unissued-handle grounding failures, and zero cross-scope leakage. Raw-RAG false
promotions are measured rather than forbidden because append-all is the baseline
policy under test. The gate does not require a preselected lift; any measured
lift or regression is reported as observed.

The provider is explicitly non-effecting and synthetic. It issues deterministic
idempotent receipts only when the proposal action and target match the labeled
case. This supports causal product comparison without claiming a production
remediation API.

## Per-episode paired evidence

The live workflow retains the full 540-observation JSON as a private GitHub
Actions artifact. Trace schema v1 records, for each arm and paired incident:

1. whether scoped search ran and which public-safe synthetic results it exposed;
2. SHA-256 fingerprints of the ephemeral handles issued by search, fetched by
   the model, and selected by the proposal;
3. the action-specific `propose_*` tool, typed parameters, and expected-action
   match result;
4. the provider status, verification bit, and durable receipt digest; and
5. the arm-specific promotion strategy and decision.

`continuum.drilldown.build_public_episode_drilldown` fail-closes unless all 180
`(replication, case)` pairs contain exactly stateless, raw-RAG, and Continuum
observations with the same incident and expected-action contract. Selected and
fetched handle fingerprints must be subsets of the current search's issued
fingerprints. The public projection is rejected if it contains raw tenant,
incident, run, memory, proposal, outcome, or provider-receipt identifier keys,
if Continuum has an unsafe proposal, or if any arm leaks a cross-scope row.

The resulting 180-case projection is checksum-bound by the judge evidence and
published as an immutable release asset. It is a drill-down of the same live
evaluation, not a hand-selected or separately simulated example set.
## Real-provider release guardian

The 540-observation ablation deliberately uses a synthetic, non-effecting
provider so five replications remain deterministic and affordable. A separate
external-validity suite closes that boundary with real GitHub Releases draft
effects.

Six provider-state families by six variants produce 36 exact paired incidents
per arm. raw-RAG and Continuum receive the same incident definitions, model,
provider pre-state, tool contracts, and retrieval budget. The six proposal tools
have discriminated, parameter-free schemas; provider identities are supplied by
the server. The run records provider receipt digests, effect counts, duplicate
effects, cleanup residuals, cross-scope rows, promotion decisions, and latency.

The 2026-08-08 live run produced 36/36 verified Continuum outcomes versus 31/36
for raw-RAG (+13.8889 points), with zero Continuum unsafe proposals, unsafe
memory exposures, false canonical promotions, duplicate effects, cleanup
residuals, and cross-scope rows. See
[the exact receipt](evidence/2026-08-08-real-provider-release-guardian.md).

### Time-distributed replication

The external-validity suite was then repeated in five distinct, serial,
main-only OIDC workflows over a 4,081-second window. Every run retained the
same exact source head, 36-case population checksum, provider contract, fixed
egress, and cleanup gate. Start times were separated by at least 843 seconds.

Across 180 paired executions, Continuum produced 180/180 verified outcomes
versus 150/180 for raw-RAG, a +16.67-point lift. The hierarchical bootstrap,
which resamples workflow time clusters and then paired cases, produced a 95%
interval of +10.0 to +24.44 points. All five batches had positive lift.
Continuum retained zero unsafe proposals, unsafe memory exposures, unsafe
citation adoptions, false promotions, duplicate effects, cleanup residuals, and
cross-scope leaks. raw-RAG produced 30 unsafe proposals and false promotions,
112 unsafe memory exposures, and 37 unsafe citation adoptions.

The same 36 incident definitions recur in all five batches. Therefore the
180-execution exact p-value is labeled descriptive only; the cluster-aware
interval and five-batch direction consistency are the primary statistical
evidence. See the
[time-distributed receipt](evidence/2026-08-09-time-distributed-real-provider-replication.md).

## Pre-registered blind multi-provider holdout

The next evidence layer removes the recurring-case coupling left by the
time-distributed guardian. An independent Bedrock job generates 60 new GitHub
and S3 incident renderings and seals the label-free challenge plus separate
labels in content-addressed S3 before either arm runs. The candidate AWS
identity has an explicit deny on the labels object; raw-RAG and Continuum emit
120 unscored traces from the same challenge. A separate evaluator opens labels
only after both arms complete and requires an expected-action match, verified
provider post-state, provider receipt digest, and outcome-evidence digest for
success.

The implementation and exact claim boundary are specified in
[BLIND_HOLDOUT.md](BLIND_HOLDOUT.md). Live metrics remain HOLD until the
main-only OIDC workflow succeeds and its exact-head artifact is bound into the
release envelope.
