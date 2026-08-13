# Continuum Memory Firewall

Continuum Memory Firewall is a reference implementation for durable, auditable
memory promotion in long-running AI agents. It separates untrusted candidate
memories from canonical memory and makes every promotion decision explicit,
deterministic, and transactionally durable.

**Live judge path:** [run the public product proof](https://yonghwan2161.github.io/continuum-memory-firewall/),
[verify every bound receipt](https://yonghwan2161.github.io/continuum-memory-firewall/verify.html),
[inspect the same 180 incidents across all three memory policies](https://yonghwan2161.github.io/continuum-memory-firewall/episodes.html),
or [inspect 36 paired incidents with real GitHub effects](https://yonghwan2161.github.io/continuum-memory-firewall/release-guardian.html),
then [inspect all five time-distributed real-provider batches](https://yonghwan2161.github.io/continuum-memory-firewall/release-guardian-replication.html)
and the [three-batch sequential blind memory-compounding proof](https://yonghwan2161.github.io/continuum-memory-firewall/sequential-blind.html),
inspect the [S3-preregistered ambiguity-first adaptive diagnosis proof](https://yonghwan2161.github.io/continuum-memory-firewall/adaptive-diagnosis.html),
run the [counterfactual cross-environment transfer firewall](https://yonghwan2161.github.io/continuum-memory-firewall/transfer-firewall.html),
inspect the [online CockroachDB memory-lineage closure](https://yonghwan2161.github.io/continuum-memory-firewall/online-memory-lineage.html),
or recompute the [participant-cluster outcome replay CAS journal](https://yonghwan2161.github.io/continuum-memory-firewall/outcome-replay-cas.html).
In the incident-response story, trusted telemetry becomes durable memory,
poisoned model output remains quarantined, a later agent retrieves the accepted
resolution, and CockroachDB grants exactly one action owner.

The current milestone is **P2B: authenticated managed-cloud competition
slice**. In addition to the transactional promotion and retrieval boundary, a
private, cost-bounded AWS Lambda client for CockroachDB Cloud Managed MCP and a
public TLS repository MCP service are deployed. Live smoke tests proved two
Managed MCP read tools, a pre-secret write-tool denial, all thirty-five
participant-cluster migrations, audited caller-to-scope bindings, matching
RLS-confined SQL identities, bounded per-identity connection pools, fixed AWS
SQL egress, five-minute Cognito caller tokens, Bedrock Titan embeddings, and an
authenticated cross-scope vector flow on the current schema. The
60-query adversarial live evaluation
measured Recall@1 = 0.8667, Recall@3 = 0.9833, Recall@5 = 1.0, zero cross-scope
leakage, p50 = 248.149 ms, and p95 = 279.012 ms. A separate 10k/50k synthetic
benchmark proved natural CockroachDB vector-search plans with no full scan and
zero foreign rows. At 50k, beam 512 measured Recall@10 = 0.96875 with warm
p50/p95 = 216.445/314.273 ms, versus exact primary-scan p50/p95 =
1168.187/1362.044 ms. These remain bounded competition results rather than
broad production-quality claims.

A separate external-validity run executed 36 exact paired incidents per arm
through Bedrock, CockroachDB, and real disposable GitHub Releases drafts.
Continuum completed 36/36 verified outcomes with zero unsafe proposals, unsafe
memory exposures, false promotions, duplicate effects, cleanup residuals, or
scope leaks. raw-RAG completed 31/36, with five unsafe proposals, 23 unsafe
memory exposures, and five false promotions.

For the authoritative project state and evidence, see
[Project Status](docs/PROJECT_STATUS.md). For implementation order and exit
criteria, see [Roadmap](docs/ROADMAP.md).

## Why this exists

Long-running agents receive observations from tools, users, and other agents.
Writing every observation directly into durable memory creates three coupled
risks:

- poisoned or out-of-scope data can become authoritative;
- retries can create duplicate state or duplicate actions;
- later reviewers cannot reconstruct why a memory was accepted or rejected.

Continuum addresses those risks with a staged authority model:

```text
untrusted input
    -> candidate memory
    -> deterministic policy decision
    -> CockroachDB promotion transaction
    -> canonical memory + audit event
    -> scoped vector retrieval + retrieval audit
    -> read-only MCP search/fetch
    -> idempotent action claim
```

The policy code decides what may be promoted. CockroachDB is the durable source
of truth for whether the promotion and action claim committed.

## Repository map

- `src/continuum/memory.py` — deterministic candidate policy kernel
- `src/continuum/store.py` — CockroachDB transaction and retry boundary
- `src/continuum/retrieval.py` — embedding persistence, scoped vector search, and retrieval audit
- `src/continuum/mcp_server.py` — read-only standard MCP `search`/`fetch` surface
- `src/continuum/aws_mcp_worker.py` — private read-only Managed MCP Lambda client
- `src/continuum/migrations/` — versioned durable schema SSOT
- `src/continuum/migrate.py` — checksum, lease, retry, adoption, and validation runner
- `src/continuum/db_smoke.py` — synthetic live-database promotion/retrieval smoke path
- `src/continuum/ci_recovery.py` — real GitHub Actions red-to-green recovery contract and metrics
- `src/continuum/outcome_attestation.py` — short-lived provider-origin promotion handle contract
- `src/continuum/outcome_replay_proof.py` — public-safe outcome CAS and journal-chain verifier
- `infra/aws/` — cost-bounded CloudFormation and Lambda dependency manifest
- `scripts/` — dry-by-default CockroachDB/AWS preflight, packaging, and deployment
- `tests/` — policy, retry, promotion, replay, retrieval, MCP, and concurrency tests
- `docs/` — SSOT documents for status, roadmap, architecture, submission, and cost

The complete documentation ownership map is in
[docs/README.md](docs/README.md).

## Local verification

Run the dependency-free unit tests:

```bash
make test
```

Run the CockroachDB integration tests with an available PostgreSQL-compatible
connection and the optional driver installed:

```bash
python -m pip install "psycopg[binary]>=3.2,<4"
export CONTINUUM_DATABASE_URL='postgresql://...'
make integration
```

Apply the versioned schema and run a synthetic smoke test:

```bash
export CONTINUUM_DATABASE_URL='postgresql://...?...&sslmode=verify-full'
make migrate
make db-smoke
```

Validate the MCP protocol contract:

```bash
python -m pip install -e ".[mcp]"
make mcp-test
```

Build and verify the Linux/Python 3.12 Lambda package without deploying:

```bash
make cloud-package
```

Run the tool-only MCP server at `/mcp` after applying the migrations and seeding
accepted memory. The following legacy bearer configuration is retained for
local compatibility tests; the live AWS deployment uses Cognito OIDC and a
server-owned caller registry:

```bash
export CONTINUUM_DATABASE_URL='postgresql://...?...&sslmode=verify-full'
export CONTINUUM_TENANT_ID='00000000-0000-0000-0000-000000000000'
export CONTINUUM_INCIDENT_ID='00000000-0000-0000-0000-000000000000'
export CONTINUUM_MCP_BEARER_TOKEN='generate-at-least-32-random-characters'
export CONTINUUM_PUBLIC_BASE_URL='https://your-public-memory-view.example/'
continuum-mcp
```

The GitHub Actions workflow starts an ephemeral CockroachDB node and runs the
unit, MCP-contract, and database-integration suites. This verification path does
not require a paid cloud account. Deterministic hashing embeddings keep CI
repeatable; the participant deployment separately evaluates Bedrock Titan Text
Embeddings v2 against a versioned semantic dataset.

## Public proof console

The logged-out browser proof console is available at:

<https://yonghwan2161.github.io/continuum-memory-firewall/>

The [closed-loop CI recovery proof](https://yonghwan2161.github.io/continuum-memory-firewall/ci-recovery.html)
binds 54 unique real GitHub Actions child receipts. Continuum recovered 12/12
with no false promotion; raw-RAG recovered 11/12 and promoted its failed
recurrence; stateless also recovered 12/12. The explicit stateless result keeps
the claim honest: the benchmark proves failed-memory isolation and provider
receipt closure, not general repair superiority.

The [ambiguity-first adaptive diagnosis proof](https://yonghwan2161.github.io/continuum-memory-firewall/adaptive-diagnosis.html)
starts every arm from the same non-identifying red summary and seals challenge,
labels, and commitment in S3 before the first model call. Across twelve paired
cases and 84 unique GitHub Actions child receipts, all three arms recovered
12/12. Continuum reused exact provider-verified memory on all six recurrences,
reducing diagnostic workflows from 12 to 6 and reaching zero probes on 6/6
recurrences (two-sided exact paired `p=0.03125`) with canonical precision 1.0,
zero false promotions, zero repository mutations, and zero cleanup residuals.
The claim is deliberately bounded: input-token cost increased, and this exact-
fingerprint benchmark does not prove transfer to changed environments.

The [counterfactual transfer firewall](https://yonghwan2161.github.io/continuum-memory-firewall/transfer-firewall.html)
changes every source/target environment fingerprint and hides relationship,
expected patch, causal signatures, and scoring policy from the candidate.
Across six same-cause and six similar-symptom different-cause targets, Continuum
recovered 12/12, reused 6/6 provider-attested compatible memories without a
diagnostic, rejected 6/6 near neighbours, and produced zero false promotions.
Stateless recovered 12/12 with twice the candidate diagnostics; raw-RAG
recovered 6/12 and falsely transferred and promoted all six near neighbours.
The result binds 84 unique exact-head workflow, artifact, and digest receipts.
It proves this reviewed causal-transfer contract, not arbitrary repair or
open-world semantic generalization.

The [online memory-lineage proof](https://yonghwan2161.github.io/continuum-memory-firewall/online-memory-lineage.html)
then drives one real provider-success outcome through canonical CockroachDB
promotion, Titan embedding, non-bypass RLS search, server-side causal admission,
durable proposal, a later provider action, and verified target promotion. The
same-cause target selected the exact source memory with zero diagnostics; the
near neighbour selected none and used one current diagnostic. The candidate
evaluator failed after both actions, so a separate `actions: read` reconciler
completed only the database side with zero provider redispatch. This is a
one-pair architectural closure, not a new comparative effect estimate.

The [outcome promotion proof](https://yonghwan2161.github.io/continuum-memory-firewall/outcome-replay-cas.html)
now closes both provider-origin admission and replay split-brain on the
participant cluster. Seven fresh S3 `HeadObject`/`GetObject` lookups exercised
one short-lived signed handle: CockroachDB consumed its digest and nonce in the
same transaction as exactly one outcome and one canonical promotion. Missing,
forged, expired, cross-proposal, cross-provider, and receipt-mismatched handles
all failed with zero negative outcome rows. Exact replay returned the same
identity; a second real S3 receipt committed `OUTCOME_REPLAY_CONFLICT` to a
three-entry SHA-256 journal. The raw handle was never persisted, and the scope
SQL identity could read its one attestation row but could not insert one
(`SQLSTATE 42501`). This is one retained-proposal architectural closure, not a
population estimate.

The current receipt-compiled 99.93-second provider-origin judge demo is public
at <https://youtu.be/cENOZu3prgs>. Its nine scenes are generated from the
immutable v27 outcome asset, judge capsule, terminal transaction, and two
network-visible attestations rather than copied from hand-edited metric text.
It shows seven fresh S3 lookups, the five-minute proposal-bound promotion
handle, one atomic CockroachDB attestation/outcome/canonical-memory join, six
blocked authority attacks, `SQLSTATE 42501`, replay conflict journaling, and the
44-check zero-API public proof. The exact MP4 SHA-256 is
`af5a689017cc2c39deae2a6368ff0616d580dfabf909bf2918fafa7223cdace7`,
the English SRT SHA-256 is
`4611757b3f074b4c6014f9c9085444c444ebbd6ea2c298a38ba0ac938f9262c7`,
and the self-addressed story receipt is
`f3cafd7db4ba6c4657f2751c022ab609612e84776fc39d3c656e17f6c57676e8`.
The [focused public proof](https://yonghwan2161.github.io/continuum-memory-firewall/outcome-replay-cas.html)
and [delivery receipt](docs/evidence/2026-08-13-provider-origin-video-devpost-v8.md)
preserve the one-proposal claim boundary. The uploaded video and Devpost
version 23 are post-v27 mutable delivery records, not retroactive members of the
immutable v27 envelope.

The policy-replay interactions are simulations, while the live metric cards and
read-only verifier load exact public receipts for the participant deployment,
60-query Titan evaluation, and 10k/50k vector benchmark. The verifier never
receives a token or database credential. The executable database evidence is
the integration suite and linked exact-head workflows in
[Project Status](docs/PROJECT_STATUS.md).

The current v27 release envelope receives exactly one author-controlled signature in
the same main-only workflow that publishes it. Its Fulcio/Rekor Sigstore bundle
is an immutable release asset and a byte-identical Pages resource. GitHub also
adds one distinguishable immutable-release countersignature; the verifier
classifies the two authorities instead of miscounting the platform receipt as
a second author signing operation. Perform strict cryptographic policy
verification of the author signature with:

```bash
python scripts/verify_network_sign_once.py --release-tag hackathon-v27
```

Version 27 binds the provider-origin outcome proof and makes both public judge
paths quota-independent. The release coordinator runs the complete
authenticated online verifier, freezes all 44 PASS checks in a self-addressed
capsule, and binds it to the signed envelope. A fresh headed browser then
validated 37 judge rows from six same-origin static GETs and the outcome proof
from five same-origin static GETs, with zero GitHub API requests on both pages
while the anonymous API quota was exhausted. It is published at
<https://github.com/YongHwan2161/continuum-memory-firewall/releases/tag/hackathon-v27>.
Coordinator run `31653469203`, Pages run `31653536847`, and freshness monitor
run `31653861653` passed on exact target
`dbb4942afd45f5bc06cbc08441d43ce155c75f05`. Envelope SHA-256 is
`b61aac89…a9acd`; capsule SHA-256 is `881b12e8…fc983`; public terminal receipt
is `1b313677…a714`; and the network bundle is `0cbb15af…4037`. See
[the exact v27 evidence](docs/evidence/2026-08-13-provider-outcome-attestation-v27.md).

Versions 25 and 26 are preserved as immutable intermediate successors. Version
25 first published the provider-origin bytes; version 26 froze those checks in
the predecessor capsule. Version 27 additionally removes GitHub API dependence
from the dedicated outcome page. No consumed release epoch was edited or
backfilled.

Version 23 is preserved as immutable failed browser-validation history. Its
release transaction succeeded, but the first real headed-browser check found
that CSP blocked the new same-origin external verifier script. No v23 asset was
modified or backfilled; reviewed PR #146 created the v24 successor.

Version 22 preserves the v21 evidence and adds the participant-cluster outcome
replay CAS proof, two real S3 receipt commitments, the three-entry database
journal, public chain recomputation, and release-asset binding. It is published
at
<https://github.com/YongHwan2161/continuum-memory-firewall/releases/tag/hackathon-v22>.
Coordinator run `31548463634`, Pages run `31548509773`, and credential-free
monitor run `31548582748` passed on exact target
`8481ac3804bf38b69e87086a9257a895d8f3b124`. The terminal receipt is
`3f386203…a1d19`; immutable envelope SHA-256 is `0b6cd0ee…39f71`, and the
outcome-CAS release asset is `sha256:7218a296…42b9c`.

Version 21 preserves the v20 evidence and adds the exact failed candidate,
successful cross-head reconciler, both Actions artifacts, two non-reexecuted
provider actions, raw report receipt, redacted online-memory projection,
CockroachDB/Titan/RLS episode lineage, judge page, and immutable release asset.
It is published at
<https://github.com/YongHwan2161/continuum-memory-firewall/releases/tag/hackathon-v21>.
Coordinator run `31510629746`, Pages run `31510716374`, and credential-free
monitor run `31511054570` passed on exact target
`0ac85de1835c3235634e963d313e62fa82ed63da`. The terminal
`PAGES_MATERIALIZED` receipt is `5413142863…aae2f5`; the immutable envelope
asset is `sha256:dd776c07…41f0e7`, and the online-lineage asset is
`sha256:28e41475…0f9d`.

Version 20 preserves the v19 evidence and adds the S3-sealed counterfactual
transfer parent, artifact archive digest, challenge/labels/commitment/seal
receipts, deterministic public projection, 84 unique provider receipts,
disjoint source/target fingerprint gate, exact paired transfer/rejection
metrics, bounded claim, judge page, and immutable release asset.
It is published at
<https://github.com/YongHwan2161/continuum-memory-firewall/releases/tag/hackathon-v20>;
the release coordinator, Pages materializer, and credential-free monitor all
passed on exact source `16a84d10`.

Version 19 preserves the v18 recovery proof and adds the S3-sealed adaptive
diagnosis parent, artifact archive digest, challenge/labels/commitment/seal
receipts, deterministic public projection, 84 unique provider receipts, paired
information-value statistics, bounded non-transfer claim, judge page, and
immutable release asset. The one-click verifier independently re-reads the
parent workflow, Actions artifact, public bytes, and release-asset digest.

Version 18 preserves the v17 story delivery and additionally binds the exact
closed-loop CI parent workflow, artifact archive digest, deterministic public
projection, 54 child receipts, bounded claim, and release asset. The public
verifier re-reads the parent run and artifact before accepting the result.

Version 17 preserves the v16 browser fix and makes the scheduled read-only judge
monitor load both repository scripts and the `src` package explicitly. The same
credential-free verifier now runs interactively, from the documented CLI, and
on the six-hour monitor without relying on an ambient Python import path.

Version 16 preserves the v15 evidence and fixes the public self-receipt verifier
to hash the original canonical JSON bytes. This keeps Python's `1.0` numeric
lexeme from being normalized to JavaScript's `1` before hashing. The release
therefore binds both the immutable story receipt and the browser-visible PASS at
the same exact head.

Version 15 preserves the immutable v14 evaluation unchanged and adds a
fail-closed evidence-to-story receipt. That receipt binds the exact v14 envelope
and sequential-asset digests, nine ordered scenes, statistical claim boundaries,
the 97.02-second video and English subtitle SHA-256 values, and Devpost project
version 20. The release workflow refuses publication if any story number,
source receipt, media digest, or submission receipt diverges.

Version 14 preserves the time-distributed v12 and blind-holdout v13 proofs, and
additionally binds a three-batch sequential blind campaign that tests whether a
provider-verified outcome improves a later unseen episode. Stateless, raw-RAG,
and Continuum face the same 36 five-episode GitHub/S3 chains, producing 540
provider observations. Labels and the scoring policy remain denied until all
three batches finish; the public aggregate exposes paired hierarchical
bootstrap intervals and sequential e-values while requiring zero Continuum
false promotion, scope leakage, duplicate effect, and cleanup residual.

The sealed live result is directional and bounded rather than inflated:
Continuum succeeded on 114/144 future target episodes (79.17%), versus 105/144
for stateless (72.92%) and 102/144 for raw-RAG (70.83%). Against raw-RAG the
paired lift was +8.33 points, the batch-cluster bootstrap 95% interval was
+3.47 to +14.58 points, and the preregistered sequential e-value was 637.15.
Against stateless the +6.25-point estimate remained uncertain (95% interval
-2.08 to +18.75; e-value 7.95), so it is not presented as confirmatory. raw-RAG
promoted 48 failed outcomes as canonical memory; Continuum promoted zero and
recorded 113 provider-verified memory-assisted target successes.

Version 13 introduced a
fresh 60-pair blind holdout generated by Bedrock, checksum-addressed in S3
before execution, hidden from both candidate arms, executed against disposable
GitHub and S3 providers, and scored by a separate evaluator. Its public result
shows 0 Continuum false canonical promotions versus 16 for raw-RAG, with 0
cross-scope leaks, duplicate effects, or cleanup residuals. The durable draft advances a
hash-chained release receipt through `PREPARED`, `AUTHOR_ATTESTED`,
`ASSETS_UPLOADED`, `IMMUTABLE`, and `PAGES_MATERIALIZED`. A retry adopts the
exact draft bytes and any existing author attestation instead of rebuilding or
signing a second envelope. Contradictory provider state is reported as
`AMBIGUOUS` and publication stops.

The redacted private-worker deployment proof is recorded in
[Live AWS and Managed MCP evidence](docs/evidence/2026-07-31-cloud-live-smoke.md).
The redacted participant-cluster migration and vector proof is recorded in
[Live CockroachDB SQL and vector evidence](docs/evidence/2026-08-01-live-sql-vector-smoke.md).
The least-privilege SQL, fixed-egress, authenticated HTTPS, and remote
cross-scope proof is recorded in
[Authenticated remote MCP evidence](docs/evidence/2026-08-01-authenticated-remote-mcp-smoke.md).
The exact-head Cognito, Titan, RLS, and cross-scope evaluation is recorded in
[OIDC, Titan, and RLS live evidence](docs/evidence/2026-08-01-oidc-titan-rls-live-smoke.md).
The representative-scale vector plan, Recall, latency, and isolation proof is
recorded in
[10k/50k vector-scale live evidence](docs/evidence/2026-08-02-vector-scale-live.md).
The main-only OIDC cutover, actual AWS sandbox receipt proof, and
five-replication 540-observation ablation are recorded in
[Main OIDC, AWS sandbox, and five-replication evidence](docs/evidence/2026-08-07-main-oidc-sandbox-five-seed-ablation.md).
The outcome-first public video, English captions, and refreshed Devpost receipt
are recorded in
[Outcome-first video and Devpost v4 evidence](docs/evidence/2026-08-07-outcome-video-devpost-v4.md).
The exact-head 540-observation rerun and checksum-bound 180-episode public
drill-down are recorded in
[per-episode paired drill-down evidence](docs/evidence/2026-08-07-per-episode-paired-drilldown.md).
The 36-pair real-provider results, capability manifest, cleanup proof, and
failed-first strong-identity correction are recorded in
[real-provider release guardian evidence](docs/evidence/2026-08-08-real-provider-release-guardian.md).
The five time-cluster run receipts, aggregate statistics, and explicit repeated-
case boundary are recorded in
[time-distributed real-provider evidence](docs/evidence/2026-08-09-time-distributed-real-provider-replication.md).
The 54-run GitHub Actions recovery benchmark, first-parent fail-closed incident,
and bounded three-arm interpretation are recorded in
[closed-loop CI recovery evidence](docs/evidence/2026-08-10-ci-recovery-live.md).
The sealed challenge, failed predecessor, 84-receipt PASS run, and bounded
information-value interpretation are recorded in
[adaptive diagnosis evidence](docs/evidence/2026-08-11-adaptive-diagnosis-live.md).
The counterfactual pairs, two failed predecessors, corrected exact-head
84-receipt PASS run, and bounded transfer interpretation are recorded in
[counterfactual transfer evidence](docs/evidence/2026-08-11-transfer-firewall-live.md).

## Safety boundary

Use synthetic data and disposable infrastructure. Do not commit database URLs,
tokens, or credentials, and do not connect the current pre-production code to
production remediation systems.

## Documentation

- [Project Status](docs/PROJECT_STATUS.md) — current capability and evidence SSOT
- [Roadmap](docs/ROADMAP.md) — implementation priority and acceptance gates SSOT
- [Architecture](docs/ARCHITECTURE.md) — trust boundaries and component ownership
- [Transaction Model](docs/TRANSACTION_MODEL.md) — transaction and retry semantics
- [Database Migrations](docs/MIGRATIONS.md) — ordered DDL, drift, lease, adoption, and recovery contract
- [MCP Contract](docs/MCP_CONTRACT.md) — tool schema, scope, transport, and deployment boundary
- [Evaluation](docs/EVALUATION.md) — 60-query adversarial suite, metric definitions, and live gate
- [Blind holdout firewall](docs/BLIND_HOLDOUT.md) — preregistration, label-denied candidate execution, and post-arm evaluation
- [Sequential blind evaluation](docs/SEQUENTIAL_BLIND.md) — sealed three-arm episode chains, paired inference, and future-episode promotion proof
- [Closed-loop CI recovery](docs/CI_RECOVERY_BENCHMARK.md) — actual failed/green GitHub Actions receipts and three-arm recovery metrics
- [Ambiguity-first adaptive diagnosis](docs/ADAPTIVE_DIAGNOSIS_BENCHMARK.md) — preregistered label-free red summaries, 84 actual provider receipts, and a paired memory information-value gate
- [Counterfactual transfer firewall](docs/TRANSFER_FIREWALL_BENCHMARK.md) — disjoint source/target environments, provider-attested causal compatibility, and near-neighbour false-transfer rejection
- [Online CockroachDB memory lineage](docs/ONLINE_MEMORY_LINEAGE.md) — real provider receipt through Titan/RLS retrieval, durable proposal, crash reconciliation, and next promotion
- [Devpost Checklist](docs/DEVPOST_CHECKLIST.md) — submission readiness SSOT
- [Cost Safety](docs/COST_SAFETY.md) — spending assumptions and guardrails
- [Cloud Deployment Runbook](docs/CLOUD_DEPLOYMENT_RUNBOOK.md) — participant-owned setup, guarded deployment, proof, and teardown
- [Prior Work](docs/PRIOR_WORK.md) — project provenance and new-work boundary

## License

Apache-2.0. See [LICENSE](LICENSE).
