# Project status

**Status date:** 2026-08-15
**Current milestone:** P2D — separated KMS outcome authority browser-reconciled
**Overall state:** the local promotion-to-retrieval vertical slice and repository
MCP contract are implemented and tested. A private, cost-bounded AWS Lambda
worker is deployed and has completed two live read-only CockroachDB Cloud
Managed MCP calls while rejecting a write tool before credential access. The
participant cluster is at migration version 35. A verified caller resolves
through an audited, versioned database binding to a matching NOBYPASSRLS SQL
identity; database-native row policies enforce the same tenant and incident
scope. The public `/mcp` endpoint accepts only five-minute Cognito
client-credentials tokens and uses Bedrock Titan Text Embeddings v2. A
60-query, six-variant live evaluation measured Recall@1/3/5 =
0.8667/0.9833/1.0, zero cross-scope leakage, and p50/p95 =
248.149/279.012 ms. Remote search/fetch and direct cross-scope denial passed.
The participant cluster also completed a five-replication, 180-case-per-arm
Bedrock experiment after strengthening stale, poison, and conflict pressure:
verified provider outcomes were 44.4% stateless, 52.8% raw-RAG, and 100%
Continuum. Continuum improved over raw-RAG by 47.222 percentage points
(10,000-resample paired cluster-bootstrap 95% CI +30.556 to +63.889), with
zero cross-scope rows, zero unsafe proposals, zero poison exposure, and zero
false canonical promotions. Crash
injection proved idempotent reconciliation with zero duplicate effects and an
explicit non-idempotent `ambiguous` terminal state.
An external-validity run then executed 36 paired incidents per arm against real
GitHub Releases drafts. Continuum completed 36/36 verified outcomes with zero
unsafe proposals, unsafe memory exposures, false promotions, duplicate effects,
cleanup residuals, or cross-scope rows; raw-RAG completed 31/36 and produced
five unsafe proposals, 23 unsafe memory exposures, and five false promotions.
The Devpost entry is submitted to the CockroachDB x AWS hackathon as submission
`1121568`. The submission remains editable while submissions are open; the
current deadline is 2026-08-19 06:00 KST.

The current judge-closure P0 uses schema 19 and successor `hackathon-v32`. It preserves the sequential v14
story as historical evidence and separately binds the current provider-origin
story to a 99.93-second public video with deterministic burned-in English
captions, Devpost project version 26, and the retained submission receipt. The
landing-page first screen derives 48 versus 0 false promotions, 114/144 versus
102/144 future successes, and 6/6 blocked authority attacks from signed public
evidence. Immutable v28 passed all 45 online checks, but the post-publication
headed-browser audit correctly found one false-negative row: its JavaScript
omitted the canonical trailing LF used by the provider-story self-receipt.
Those v28 bytes were not changed. v29 fixes the production hash function,
executes that exact JavaScript function in CI, freezes all 45 predecessor
checks, and revalidates the current delivery tuple against the signed successor
envelope before rendering 38 PASS rows. v30 additionally makes that browser
result a release state: content-addressed/SRI script bytes, fresh isolated
Chromium, 38/38 rows, zero GitHub API requests, and zero console/page errors are
bound into the hash-chained `BROWSER_VERIFIED` receipt before final Pages
publication. Immutable v31 added the 39th KMS row but its headed candidate audit
correctly failed because the content-addressed v30 judge program still expected
38 rows. Those bytes remain unchanged. v32 adds the KMS receipt as an eighth
same-origin GET and binds all 39 rows without changing v30 or v31. See
[the v30 browser-verified contract](evidence/2026-08-13-browser-verified-release-v30.md),
[the preserved v31 audit](evidence/2026-08-15-kms-browser-v31-failed.md), and
[the KMS authority proof](evidence/2026-08-15-kms-outcome-authority-live.md).

The real GitHub Actions closed-loop recovery run is also complete. Across six
fault families, 18 calibration and 36 paired evaluation children produced 54
unique run/artifact receipts with zero repository mutation and zero cleanup
residual. Continuum and stateless each recovered 12/12; raw-RAG recovered
11/12 after failed append-all history poisoned one recurrence. Continuum kept
canonical precision 1.0 and false promotion 0 versus raw-RAG precision
0.916667 and one false promotion. Because stateless also reached 12/12, the
evidence is explicitly bounded to receipt closure and failed-memory isolation.

The preregistered ambiguity-first follow-up is also complete. Parent run
`31400622882` sealed challenge and labels before the first model call and bound
84 unique GitHub workflow/artifact receipts. Stateless, raw-RAG, and Continuum
all recovered 12/12, while Continuum reduced diagnostic child workflows from
12 to 6 and used zero probes in all six recurrence pairs (`p=0.03125`) with
canonical precision 1.0 and false promotion 0. The admitted claim is exact-
fingerprint information value, not semantic transfer or lower token cost.

The counterfactual cross-environment transfer firewall is live-complete on
exact source `361c3ec8`. Parent run `31439117749` sealed challenge and labels
before the first candidate call and bound 84 unique provider workflow,
artifact, and digest identities. Continuum recovered 12/12, reused all six
same-cause memories without a diagnostic, rejected all six different-cause near
neighbours, and retained zero false promotions. Stateless recovered 12/12 with
twelve diagnostics. raw-RAG recovered 6/12 and falsely transferred and promoted
all six near neighbours. The paired same-cause diagnostic reduction and
Continuum recovery lift over raw-RAG each reached exact `p=0.03125`. See
[TRANSFER_FIREWALL_BENCHMARK.md](TRANSFER_FIREWALL_BENCHMARK.md).

The online CockroachDB memory-lineage seam is live-complete. Candidate run
`31503686643` promoted and Titan-indexed a real provider-success source outcome,
proved non-bypass RLS isolation, executed actual Bedrock scoped search/fetch,
stored two proposals, and then executed provider action runs `31503922040` and
`31503923725`. Its evaluator failed before target outcome promotion, so the
candidate remains FAIL. Recovery run `31506117708` used the exact predecessor
artifact under `actions: read`, dispatched zero additional provider actions,
and completed both verified outcomes and canonical promotions. Same cause used
the source memory with zero diagnostics; the near neighbour selected no memory
and used one current diagnostic. Every gate passed, including database episode
joins, retrieval audit IDs, exact patches, zero cross-scope rows, zero cleanup
residuals, and RLS checksum `69a168e1…b4e02`. The result is one architectural
pair/two targets, not a population-level superiority estimate. See
[ONLINE_MEMORY_LINEAGE.md](ONLINE_MEMORY_LINEAGE.md).

The proposal-scoped outcome replay boundary is now live-complete. Main run
`31546885169` applied migrations 32 and 33 on the participant cluster, accepted
one real disposable S3 receipt, replayed that exact receipt idempotently, and
rejected a second real S3 receipt for the same proposal with typed
`OUTCOME_REPLAY_CONFLICT`. CockroachDB retained exactly one outcome, one
canonical promotion, and a three-row SHA-256 reconciliation journal with
decisions `accepted → exact_replay → conflict`; the conflict row committed
before the error returned. The scoped SQL role saw exactly the three in-scope
rows. Artifact `9122846707` is bound by archive digest
`a951eed8…a6cd`; public proof SHA-256 is `7218a296…42b9c`. This is one
retained-proposal architectural closure, not a population estimate. See
[2026-08-12-outcome-replay-cas-live.md](evidence/2026-08-12-outcome-replay-cas-live.md).

Provider-origin admission is now live-complete as well. PR `#148` merged as
`43d63f0ab3af16f83733e2950cffb2954c532582`; main-only OIDC run
`31650943912` applied migrations 34 and 35, performed seven fresh S3
`HeadObject`/`GetObject` lookups, and issued one five-minute HMAC-SHA256 handle
bound to the exact proposal, provider, idempotency key, receipt, success
status, policy, issuer, key ID, nonce, and expiry. CockroachDB consumed the
handle digest and nonce in the same transaction as one outcome and one
canonical promotion. Missing, forged, expired, cross-proposal, cross-provider,
and receipt-mismatched handles all failed with zero negative outcome rows. The
raw handle was not persisted; the scope SQL role saw one attestation row but
could not insert one (`SQLSTATE 42501`). Artifact `9162583114` has archive
digest `sha256:682b46d1…e0bf9`; the public projection is
`sha256:47934505…8673b`. See
[2026-08-13-provider-outcome-attestation-live.md](evidence/2026-08-13-provider-outcome-attestation-live.md).

The stronger KMS-backed outcome-authority lifecycle is live-complete. Exact
main run `31813682371` at source
`b02ca33e0c0b0a8d02629f0a4280d1613ad47806` used two P-256 KMS keys and a
verifier-only signing role. The action worker's direct `kms:Sign` call failed
with `AccessDenied`; the verifier performed four real S3 `HEAD+GET` re-reads
and four KMS signatures across `ACTIVATE_KEY_A → ROTATE_TO_KEY_B →
ROLLBACK_TO_KEY_A`. CockroachDB migration 38 retained three attestations,
outcomes, and canonical memories, with epochs 1/2/3 and key-ARN digests but no
raw handle. Restart verification and exact old-handle replay required zero new
signatures; forged, expired, and unknown-epoch inputs failed closed. An
independent deployer confirmed zero private handoff objects after cleanup.
Artifact `9224227375` is bound by archive SHA-256
`66f3a5e4…72b9d4`; public receipt SHA-256 is `9492eb13…353d2`, and all
18 lifecycle gates passed. See
[2026-08-15-kms-outcome-authority-live.md](evidence/2026-08-15-kms-outcome-authority-live.md).

Its immutable, quota-independent publication is now live-complete. PR `#149`
bound the fresh public proof and made Pages coordinator-owned; PR `#150`
advanced the predecessor capsule; PR `#151` removed all GitHub API requests
from the dedicated outcome page. Immutable release `hackathon-v27` targets
`dbb4942afd45f5bc06cbc08441d43ce155c75f05`. Coordinator run `31653469203`
and Pages run `31653536847` reached `PAGES_MATERIALIZED`; monitor run
`31653861653` passed all 44 online checks. The envelope is
`sha256:b61aac89…a9acd`, capsule `sha256:881b12e8…fc983`, canonical terminal
receipt `1b313677…a714`, and two-attestation network bundle
`sha256:0cbb15af…4037`. Under an exhausted anonymous GitHub API quota, a fresh
headed browser passed the main judge page with six static GETs and the outcome
page with five static GETs, both with zero GitHub API requests and no console
errors. See
[the exact v27 evidence](evidence/2026-08-13-provider-outcome-attestation-v27.md).

Outcome-CAS publication is complete. PR `#143` merged as exact release target
`8481ac3804bf38b69e87086a9257a895d8f3b124`; coordinator run `31548463634`
published immutable `hackathon-v22`, and Pages run `31548509773` materialized
the terminal receipt. Its state is `PAGES_MATERIALIZED`, receipt SHA-256 is
`3f386203…a1d19`, immutable envelope SHA-256 is `0b6cd0ee…39f71`, and
coordinator artifact `9123349934` has digest `sha256:adec921a…a1c8`.
Network-visible sign-once verification found exactly one author SLSA
attestation and one GitHub release countersignature. Credential-free monitor
run `31548582748` passed every gate, including `outcome_replay_cas_closure`,
and retained artifact `9123384105` (`sha256:2c9f02ca…8d8e`). The live
outcome page independently rendered `PASS · NETWORK + DB CHAIN BOUND`.

Quota-independent judge delivery is now live-complete. PR `#145` introduced a
release-compiled capsule; the first immutable v23 browser epoch exposed a CSP
block and remains unchanged as failed audit history. PR `#146` corrected the
same-origin script policy and merged as exact v24 target
`d2e3c1f80515c221ccca67a113cbaaf593baa391`. Coordinator run `31611395093`
published immutable `hackathon-v24`; Pages run `31611493199` reached
`PAGES_MATERIALIZED`; and a fresh headed browser passed all 37 rows using six
same-origin GETs and zero GitHub API requests. Capsule SHA-256 is
`9dd2b05f…a9487d`, envelope SHA-256 is `a1c538d9…8b545f`, and terminal receipt
is `e9ee7ed1…9bdae6`. Authenticated freshness monitor run `31611785532` passed
all 44 online checks and retained artifact `9147494855`
(`sha256:9c693617…00c0e`). See
[the exact v24 evidence](evidence/2026-08-13-zero-api-judge-v24.md).

That v24 epoch remains immutable history; the current successor is v27 as
described above. No v24-v26 asset or receipt was mutated or backfilled.

The prior online-lineage publication is also complete. PR `#139` merged as `0ac85de1`; release
coordinator run `31510629746` published immutable `hackathon-v21` at exact
target `0ac85de1835c3235634e963d313e62fa82ed63da`, and Pages run `31510716374`
materialized the terminal receipt. Its state is `PAGES_MATERIALIZED`, receipt
SHA-256 is `54131428…aae2f5`, and it binds coordinator artifact `9108919996`
with digest `sha256:c17af791…3f816`. Credential-free monitor run `31511054570`
then passed all 42 public judge checks from the same source; monitor artifact
`9109067285` has digest `sha256:82d8737a…f4030`.

This document is the single source of truth for current capability, verification
evidence, and explicit non-claims.

## Capability matrix

| Area | State | Verified evidence |
|---|---|---|
| Deterministic promotion policy | Implemented | Unit tests cover scope, lineage, expiry, provenance, approval, payload size, and deterministic hashes |
| Candidate-to-canonical promotion | Implemented | CockroachDB integration test commits the candidate decision and canonical memory in one transaction |
| Idempotent replay | Implemented | Replaying the same source event returns the existing canonical record without duplication |
| Serializable retry handling | Implemented | SQLSTATE `40001` is retried at the transaction boundary; unit tests exercise retry and exhaustion |
| Concurrent action claim | Implemented | Two concurrent workers produce one `CLAIMED` result and one `DUPLICATE` result |
| CockroachDB schema migrations | Implemented, integration-tested, and live at v35 | Thirty-five packaged single-statement migrations include `VECTOR(512)`, the complete vector prefix, tenant/control-plane RLS, the four-table episode contract, approval/receipt integrity, the transactional outbox, proposal-scoped outcome CAS, its reconciliation journal, provider-origin attestations, and attestation RLS; CI verifies initial apply and replay |
| Migration integrity and recovery | Implemented and integration-tested | SHA-256 history rejects drift and gaps; durable pre-DDL intent resumes the DDL/history crash gap; a renewable lease excludes a second owner; `XXA00` fails closed |
| Existing-schema adoption | Implemented and fail-closed | Unmanaged tables are refused by default; explicit adoption validates required columns, indexes, and composite scope foreign keys |
| Semantic live-DB evaluation | Live-smoked on participant CockroachDB Cloud | Titan v2 ran 60 adversarial and similar-meaning queries across six variant classes; Recall@1/3/5 = 0.8667/0.9833/1.0, zero forbidden-scope rows, p50 = 248.149 ms, p95 = 279.012 ms |
| Bedrock episode contract | Implemented, integration-tested, and live-evaluated | Durable runs, frozen citations, allowlisted proposals, verified outcomes, and server-owned scope are coupled to a phased `search -> optional fetch -> proposal` tool contract; rejected runs retain bounded failure codes and progress |
| Outcome-gated three-arm ablation | 180 identical paired cases per arm completed live | Five isolated replications of 36 stale/poison/conflict-aware cases produced 540 observations. Verified provider outcomes: stateless 80/180, raw-RAG 95/180, Continuum 180/180. Continuum beat raw-RAG by 47.222 points (paired cluster-bootstrap 95% +30.556 to +63.889); Continuum retained zero unsafe proposals, poison exposure, cross-scope rows, false promotions, and ambiguous outcomes |
| Real-provider release guardian | 36 exact paired incidents per arm completed live | Run `31245814421` produced 72 Bedrock/CockroachDB/GitHub observations. Continuum: 36/36 verified outcomes and zero unsafe proposals, exposure, false promotions, duplicate effects, cleanup residuals, and scope leaks. raw-RAG: 31/36, five unsafe proposals, 23 unsafe exposures, and five false promotions. The +13.889-point lift has paired bootstrap 95% +2.778 to +25.0; exact p = 0.0625 is reported without overclaiming. |
| Time-distributed real-provider replication | Five exact workflows and artifacts completed live | Runs `31262805258`, `31263400941`, `31264011991`, `31264600483`, and `31265192522` replayed one checksum-bound 36-case population. Aggregate run `31265768185`: Continuum 180/180 versus raw-RAG 150/180 (+16.67 pp), cluster bootstrap 95% +10.0 to +24.44 pp, positive lift in 5/5 batches, 330/330 unique successful receipt fingerprints, and zero Continuum unsafe proposals, exposures, false promotions, duplicate effects, residuals, or leaks. The repeated-case statistical boundary is explicit. |
| Closed-loop CI recovery | Live GitHub Actions benchmark complete; public projection and immutable release bound | Parent run `31389008324` produced 18 calibration plus 36 evaluation children: 54 unique workflow/artifact receipts, exact head `3a77fa7`, no repository mutation, and zero cleanup residual. Continuum 12/12, stateless 12/12, raw-RAG 11/12; raw-RAG admitted one false canonical promotion while Continuum admitted zero. Public SHA-256 `8d0f6ac8…9236`. The result proves failed-memory isolation, not superiority over stateless. See [CI_RECOVERY_BENCHMARK.md](CI_RECOVERY_BENCHMARK.md). |
| Ambiguity-first adaptive diagnosis | Live S3-preregistered three-arm benchmark complete; v19 publication-gated | Exact-head run `31400622882` produced 18 calibration, 30 read-only diagnostic, and 36 remediation receipts: 84 unique run/artifact identities, no repository mutation, and zero cleanup residual. Every arm recovered 12/12. Continuum used 6 diagnostics versus 12 for stateless and skipped all 6 recurrence probes; paired exact `p=0.03125`, canonical precision 1.0, false promotion 0. Public SHA-256 `29014436…d635c7`; transfer and lower-token-cost claims remain excluded. See [ADAPTIVE_DIAGNOSIS_BENCHMARK.md](ADAPTIVE_DIAGNOSIS_BENCHMARK.md). |
| Counterfactual cross-environment transfer firewall | Live S3-preregistered benchmark complete; immutable v20 and Pages bound | Exact-head run `31439117749` produced 18 source calibration, 12 target attestation, 18 diagnostic, and 36 remediation receipts: 84 unique run/artifact/digest identities, disjoint source/target fingerprints, no repository mutation, and zero cleanup residual. Continuum recovered 12/12, transferred 6/6 same-cause memories, rejected 6/6 near neighbours, and promoted zero failed outcomes. raw-RAG recovered 6/12 with six false transfers and six false promotions. Public SHA-256 `cf46c936…dbf25`; release `hackathon-v20`, coordinator `31441863985`, Pages `31441902936`, and monitor `31442028079` passed. Open-world and total-provider-call claims remain excluded. See [TRANSFER_FIREWALL_BENCHMARK.md](TRANSFER_FIREWALL_BENCHMARK.md). |
| Online CockroachDB memory lineage | Live provider/Bedrock/CockroachDB recovery complete; immutable v21, Pages, and monitor bound | Candidate `31503686643` durably stored two proposals before two successful provider actions, then failed before DB finalization. Read-only recovery `31506117708` consumed its exact artifact, reexecuted zero provider actions, joined both outcomes and promotions, retained retrieval-audit IDs, passed RLS and four negative SQL checks, and produced report receipt `dd249605…e6929` plus artifact digest `7d23ab01…58bf0`. Same-cause selected one canonical memory with zero diagnostics; near-neighbour selected none with one diagnostic. Public SHA `28e41475…0f9d` is identical on Pages and immutable release `hackathon-v21`; coordinator `31510629746`, Pages `31510716374`, and monitor `31511054570` passed. This is a one-pair architectural closure, not a new comparative estimate. |
| Pre-registered blind multi-provider holdout | Live label-denied GitHub/S3 benchmark complete and release-bound | Run `31300283080` scored 60 pairs/120 observations only after both arms finished. Candidate label fields were zero and the candidate process did not open labels. Continuum completed 45/60 versus raw-RAG 43/60, with zero Continuum false promotion, cross-scope leak, duplicate effect, or cleanup residual; raw-RAG recorded 16 false promotions. Public SHA-256 `0a0791b1…abba2e74`. |
| Per-episode paired drill-down | Implemented, live-generated, and checksum-bound | The exact-head `2ef2247` rerun projects 540 observations into 180 three-arm incidents. Each arm exposes scoped search results, SHA-256 citation-handle fingerprints, typed proposal, provider outcome evidence, and promotion decision. Projection gates: exact pairing PASS, issued handles only PASS, Continuum unsafe proposals 0, cross-scope rows 0, private identifier keys 0 |
| Network-visible sign-once | Implemented and publicly verifiable | `hackathon-v10` is durable-draft-first, author-signed, and published in one main-only workflow. It emits exactly one Fulcio/Rekor author bundle, verifies exact workflow/ref/source/runner policy, includes the bundle before immutability, and serves the two-authority network bundle through Pages. The gate separately requires GitHub's one immutable-release countersignature, so platform signing is not misreported as an author replay. |
| Release transaction coordinator | Implemented, fault-injection tested, and publicly gated | A hash-chained receipt advances through `PREPARED`, `AUTHOR_ATTESTED`, `ASSETS_UPLOADED`, `IMMUTABLE`, `PAGES_MATERIALIZED`, and `BROWSER_VERIFIED`. Reruns adopt the exact draft and existing author attestation; changed target/digest or duplicate signatures become fail-closed `AMBIGUOUS`. The judge path binds the terminal receipt, Pages run, release target, browser workflow/artifact digest, content-addressed/SRI script, and public attestation-bundle digest. |
| Provider-origin promotion admission | Implemented, integration-tested, participant-cluster live-proven, and immutable-v27 bound | A verifier performs a fresh provider lookup before issuing a five-minute signed handle. CockroachDB atomically consumes its digest and nonce with the outcome and promotion. Six negative classes produced typed rejection and zero outcome rows; the runtime scope role cannot mint database attestation rows. Live run `31650943912`, artifact `9162583114`, public SHA-256 `47934505…8673b`; v27 coordinator `31653469203`, Pages `31653536847`, monitor `31653861653`, and both zero-API browser paths passed. |
| Transactional outbox | Implemented, integration-tested, and participant-cluster fault-smoked | Before-send, idempotent after-send, and before-ack crashes converged to one logical effect and zero duplicates; a non-idempotent after-send crash became `ambiguous`, was not resent, and did not promote memory |
| Tenant and incident integrity | Implemented | Composite foreign keys and query predicates bind candidates, canonical memory, actions, and retrieval audit to the same scope |
| Vector write and retrieval | Implemented and participant-cluster live-smoked | Deterministic local embeddings remain for tests; the live deployment uses `amazon.titan-embed-text-v2:0` with 512 dimensions and mandatory tenant/incident scope |
| Retrieval audit | Implemented | Search transaction records model, query digest, policy digest, evaluated IDs, and accepted IDs |
| Standard MCP boundary | Implemented, deployed, and remotely smoked | Official Python MCP SDK exposes only read-only `search` and `fetch`; a TLS client initialized protocol `2025-11-25`, listed exactly those tools, and completed allowed/denied scope calls |
| Caller authentication and scope binding | Implemented and live-verified | Cognito client credentials issue 300-second RS256 JWTs; after issuer, audience, scope, lifetime, and JWKS verification, an active versioned database binding selects the server-owned tenant, incident, and deterministic SQL role; bind/rebind/disable events are audited |
| SQL workload separation and RLS | Implemented and live-verified | Each deterministic scope login is `NOBYPASSRLS`; RLS policies confine canonical memory, incidents, and retrieval audit. Attempts to disable row security or update canonical memory fail, and the temporary migrator role options were restored to `[]` |
| Cloud deployment runbook | Implemented | One SSOT procedure separates automated checks from participant-owned account, credit, MFA, key-copy, evidence, and teardown steps |
| CockroachDB Basic provisioning | Provisioned through the Cloud Console; CLI guard not executed | Participant console verification on 2026-07-30 shows the cluster available on Basic in AWS Singapore, with usage below the displayed 50M RU and 10 GiB monthly limits |
| AWS Managed MCP worker | Deployed and live-smoked | Private direct-invoke Lambda returned `ok: true` for `list_databases` and `list_tables`; `insert_rows` returned `INVALID_REQUEST` before secret access |
| AWS infrastructure and package | Deployed and verified | Budget, private Lambda, and authenticated-MCP stacks are complete. The EC2 host has no SSH, requires IMDSv2, reads one runtime secret and one exact S3 object, verifies a deterministic artifact hash, and is managed through SSM |
| Reviewer experience | Deployed public simulation and read-only verifier | GitHub Pages opens without login; `verify.html` checks the public exact-head workflow, 60-query metrics, MCP health, Devpost receipt, RLS, control plane, bounded pools, vector-index contract, and exactly one network-visible Sigstore subject using HTTP GET only. Full signature verification is available as one CLI command. |
| Live CockroachDB Cloud | Migrated, semantically evaluated, RLS-confined, and egress-restricted | Migration version 35 is current; all visible rows in each protected table matched the caller scope; the allowlist contains only the AWS Elastic IP `/32` |
| Public MCP endpoint | Deployed and cross-scope-smoked | `https://47-131-98-12.sslip.io/mcp` has valid TLS, health `200`, missing auth `401`, five-minute OIDC, allowed search/fetch PASS, hidden forbidden memory, and cross-scope fetch denial |
| CockroachDB Managed MCP | Live read-only evidence and guarded v3 rotation complete | Run `30709230016` replaced the AWS secret, waited beyond the five-minute cache bound, passed `list_databases` and `list_tables`, and retained pre-secret write denial; the v2 provider key and temporary GitHub secret were then deleted |
| AWS service use | Live deployment evidenced | Lambda, EC2, Elastic IP, SSM, Secrets Manager, S3, CloudWatch Logs, CloudFormation, Cognito, Bedrock, IAM OIDC, and AWS Budgets are active; the USD 20 judging-window budget retains forecast-at-80% and actual-at-100% email alerts |
| AWS deployment authority | Keyless dedicated role | GitHub Actions assumes `continuum-hackathon-deployer` through the immutable numeric repository prefix plus the reviewed `continuum-production` environment; that environment admits only `main`. Sessions last at most one hour, explicit denies block self-modification and bootstrap-stack mutation, and negative dispatches fail at role assumption |
| AWS sandbox provider | Deployed and live-proven | Actual Lambda and encrypted DynamoDB implement an explicit idempotency/receipt-lookup manifest. Two sends with one key produced one logical effect, lookup returned the same receipt, and the staging artifact was removed in run `31112544426` |
| External-effect crash semantics | Implemented for the bounded adapter contract; universal exactly-once not claimed | The durable outbox reconciles idempotent providers, reuses stored receipts before acknowledgement, and fails non-idempotent after-send uncertainty to `ambiguous` without blind resend |
| Database connection and plan evidence | Implemented and live-verified | Lazy bounded pools use min 1/max 4 separately for the control-plane and scope SQL identities. Exact 10k/50k synthetic ground truth versus natural ANN proved the four-column prefix, vector-search operator, no full scan, zero foreign rows, and the full `1/32/128/512` Recall/latency curve |
| Production security and resilience | Partial | Minimum IAM, audited caller-derived SQL identities, RLS, TLS, fixed egress, short-lived JWTs, bounded pools, semantic embeddings, negative-capability tests, worker-crash reconciliation, a non-effecting AWS sandbox, and bounded real GitHub draft effects are live; a customer remediation provider and multi-region failover are not complete |

## Evidence

- Repository: <https://github.com/YongHwan2161/continuum-memory-firewall>
- Merged P1 implementation PR:
  <https://github.com/YongHwan2161/continuum-memory-firewall/pull/1>
- P2A retrieval and MCP implementation PR:
  <https://github.com/YongHwan2161/continuum-memory-firewall/pull/2>
- P2B cloud deployment readiness PR:
  <https://github.com/YongHwan2161/continuum-memory-firewall/pull/3>
- Passing P2B pull-request workflow:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30151446778>
- P2B merged commit:
  <https://github.com/YongHwan2161/continuum-memory-firewall/commit/807909b2dd7a0ac3ce76f0861787356f1e86383d>
- Versioned migration and live-DB smoke implementation PR:
  <https://github.com/YongHwan2161/continuum-memory-firewall/pull/5>
- Passing migration and live-DB smoke final-head workflow:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30257855572>
- Versioned migration and live-DB smoke merged commit:
  <https://github.com/YongHwan2161/continuum-memory-firewall/commit/3fe0c047ac4b0b35f010f2a630f54f50db9b39e7>
- GitHub Actions workflow:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/workflows/ci.yml>
- Public proof console:
  <https://yonghwan2161.github.io/continuum-memory-firewall/>
- Passing public-demo deployment:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30464165943>
- Submitted Devpost project page; submission `1121568` returned `Submitted` at
  2026-08-02 00:22 KST:
  <https://devpost.com/software/continuum-memory-firewall>
- Public 99.93-second provider-origin judge video embedded by Devpost:
  <https://youtu.be/cENOZu3prgs> (local render SHA-256
  `af5a689017cc2c39deae2a6368ff0616d580dfabf909bf2918fafa7223cdace7`;
  English subtitle SHA-256
  `4611757b3f074b4c6014f9c9085444c444ebbd6ea2c298a38ba0ac938f9262c7`;
  self-addressed story receipt
  `f3cafd7db4ba6c4657f2751c022ab609612e84776fc39d3c656e17f6c57676e8`)
- Public evidence-story receipt and nine-scene judge page:
  <https://yonghwan2161.github.io/continuum-memory-firewall/evidence-story.html>
  The v16 browser gate hashes the original canonical bytes, preserving numeric
  lexemes across Python and JavaScript.
- Devpost authenticated update receipt: project version `23`, updated at
  `2026-08-13T08:10:05.381-04:00`, state `published`, video URL
  <https://youtu.be/cENOZu3prgs>, with submission `1121568` retaining its
  original non-null `submitted_at` receipt. The authenticated hackathon read
  returned both `registered` and `submitted` while submissions remained open.
- Provider-origin video and Devpost delivery receipt, including the explicit
  post-v27 boundary:
  [2026-08-13-provider-origin-video-devpost-v8.md](evidence/2026-08-13-provider-origin-video-devpost-v8.md)
- Redacted live AWS and CockroachDB evidence:
  [2026-07-31-cloud-live-smoke.md](evidence/2026-07-31-cloud-live-smoke.md)
- Redacted live SQL migration and vector evidence:
  [2026-08-01-live-sql-vector-smoke.md](evidence/2026-08-01-live-sql-vector-smoke.md)
- Authenticated remote MCP and least-privilege SQL evidence:
  [2026-08-01-authenticated-remote-mcp-smoke.md](evidence/2026-08-01-authenticated-remote-mcp-smoke.md)
- Merged live-evidence PR:
  <https://github.com/YongHwan2161/continuum-memory-firewall/pull/11>
- Short-lived identity, Titan, and RLS implementation PR:
  <https://github.com/YongHwan2161/continuum-memory-firewall/pull/13>
- Exact-head live AWS/DB/MCP proof:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30695164483>
- Exact-head CI proofs:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30695165845>
  and <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30695164485>
- Dedicated AWS identity proof:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30695164473>
- Managed MCP rotation and current two-tool proof:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30695651609>
- Latest guarded v3 rotation and rollback-capable two-tool proof:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30709230016>
- Redacted OIDC, Titan, RLS, and remote-smoke evidence:
  [2026-08-01-oidc-titan-rls-live-smoke.md](evidence/2026-08-01-oidc-titan-rls-live-smoke.md)
- Exact-head audited control-plane, 60-query, pooling, query-plan, and remote MCP
  proof:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30708752765/attempts/2>
- Redacted evidence summary:
  [2026-08-02-control-plane-eval-pooling-live.md](evidence/2026-08-02-control-plane-eval-pooling-live.md)
- One-click public judge verifier:
  <https://yonghwan2161.github.io/continuum-memory-firewall/verify.html>
- Public closed-loop CI recovery explorer and exact parent workflow:
  <https://yonghwan2161.github.io/continuum-memory-firewall/ci-recovery.html>
  and <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31389008324>
- Redacted closed-loop CI recovery evidence:
  [2026-08-10-ci-recovery-live.md](evidence/2026-08-10-ci-recovery-live.md)
- Public adaptive diagnosis explorer and exact parent workflow:
  <https://yonghwan2161.github.io/continuum-memory-firewall/adaptive-diagnosis.html>
  and <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31400622882>
- Preregistered adaptive diagnosis evidence:
  [2026-08-11-adaptive-diagnosis-live.md](evidence/2026-08-11-adaptive-diagnosis-live.md)
- Public counterfactual transfer explorer and exact parent workflow:
  <https://yonghwan2161.github.io/continuum-memory-firewall/transfer-firewall.html>
  and <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31439117749>
- Preregistered counterfactual transfer evidence:
  [2026-08-11-transfer-firewall-live.md](evidence/2026-08-11-transfer-firewall-live.md)
- Exact-head 10k/50k vector benchmark workflow:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30735058404>
- Byte-identical vector-scale evidence summary:
  [2026-08-02-vector-scale-live.md](evidence/2026-08-02-vector-scale-live.md)
- Episode contract, paired three-arm ablation, and transactional outbox live
  evidence:
  [2026-08-02-episode-ablation-outbox-live.md](evidence/2026-08-02-episode-ablation-outbox-live.md)
- Final phase-machine ablation workflow:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30755531853>
- Outbox fault-injection workflow:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30754765994>
- Main-only OIDC, actual AWS sandbox, and five-replication ablation evidence:
  [2026-08-07-main-oidc-sandbox-five-seed-ablation.md](evidence/2026-08-07-main-oidc-sandbox-five-seed-ablation.md)
- Actual AWS sandbox provider proof:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31112544426>
- Exact-head five-replication 540-observation live ablation and drill-down:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31162961883>
- Public paired episode explorer:
  <https://yonghwan2161.github.io/continuum-memory-firewall/episodes.html>
- Evidence-to-story compiler contract and rebuild instructions:
  [EVIDENCE_TO_STORY_COMPILER.md](EVIDENCE_TO_STORY_COMPILER.md)

`main` is the authoritative code. The linked workflows cover the reviewed P2B
and migration implementation commits; the pull request records final-head
checks and remains the review record.

## What the current implementation establishes

The current implementation establishes a narrow durable authority and retrieval
boundary:

1. A candidate record is read and locked.
2. The deterministic policy evaluates the candidate.
3. The decision and audit evidence are written transactionally.
4. Accepted data becomes canonical exactly once for the same source identity.
5. A later action claim uses a unique idempotency key to select one database
   winner.
6. Accepted canonical payloads can be embedded outside a retryable transaction,
   persisted with model identity, and searched with mandatory tenant and incident
   prefixes.
7. Every search persists evaluated and accepted memory IDs with policy evidence
   in the same transaction as the read.
8. MCP clients can search and fetch only the scope selected from the verified
   caller identity by a server-owned registry and enforced again by the SQL
   login's database policies.
9. A separately packaged AWS worker can call only an explicit read-only subset
   of CockroachDB Cloud Managed MCP; it cannot expose a public Lambda URL and
   cannot retrieve any other Secrets Manager resource under its generated role.
10. Database schema state is reproducible from immutable ordered migrations;
    replay is a no-op, checksum drift is rejected, an interrupted DDL/history
    boundary resumes from durable intent, and concurrent owners cannot proceed
    together.

11. Every model episode freezes the input scope, retrieved evidence, proposal,
    approval, and provider outcome as separate auditable records.
12. Only a verified successful provider receipt can become canonical memory;
    failed and ambiguous outcomes cannot teach the next episode.
13. Approved proposals enter a transactional outbox. Crashes reconcile through
    provider idempotency or durable receipts, while unknowable non-idempotent
    after-send outcomes stop as `ambiguous` without blind resend.

These guarantees apply to the repository code, participant database, synthetic
evaluation verifier, non-effecting AWS sandbox, and disposable GitHub Releases
draft provider. They do not establish production behavior for an arbitrary
customer remediation provider.

## Immediate participant focus

The AWS, Managed MCP, participant-cluster SQL, least-privilege runtime, fixed
egress, authenticated remote MCP, and Devpost submission gates are closed. The
receipt-compiled judge story is now the primary public path. The highest-value
work before the submission deadline is:

1. **Lead with causal memory compounding:** keep the sealed 540-observation
   sequential result, 48-versus-zero false-promotion mechanism, and exact
   evaluator replay ahead of older retrieval-only metrics.
2. **Preserve statistical honesty:** claim the paired advantage over raw-RAG;
   describe the stateless comparison as directional and latency as measured but
   not superior.
3. **Burn in the two-plane judge path:** monitor the zero-API browser capsule,
   authenticated provider-freshness job, Pages author bundle, immutable
   release asset, public attestation index, Rekor proof, platform release
   countersignature, and strict verifier through the judging window. Alert on a
   second author provenance, a missing platform receipt, or digest divergence.

The exact commands and stop conditions are in
[CLOUD_DEPLOYMENT_RUNBOOK.md](CLOUD_DEPLOYMENT_RUNBOOK.md).

## Remaining blockers

- The guarded workflow automatically replaces the AWS secret, waits out the
  Lambda cache, proves both read tools, and restores the prior AWS secret on
  failure. Cockroach Cloud still requires a user-authenticated Console/ccloud
  session to mint and retire provider API keys, so fully unattended provider
  rotation is not claimed.
- The 60-query semantic suite and 10k/50k random-vector benchmark are meaningful
  competition evidence but are not a statistically broad production workload.
  “First pass” includes a fresh SQL connection, not a server cache flush.
- The five-replication agent ablation uses a synthetic non-effecting provider.
  The separate GitHub suite now verifies real external effects, but it contains
  only 36 pairs: +13.889 points, paired bootstrap 95% +2.778 to +25.0, exact
  p = 0.0625. Together they provide breadth plus external validity, not a claim
  about every provider or incident distribution.
- The outbox proof establishes safe reconciliation for a bounded provider
  contract. A production provider must declare idempotency and receipt-lookup
  capabilities before it may use the automatic retry path.
- Live memory citation URLs do not yet provide durable reviewer-visible
  per-memory detail pages.
- The live provider-origin proof uses one process-scoped HMAC authority for a
  bounded run. It proves the admission protocol, binding, expiry, atomic
  consumption, and RLS boundary, but not durable signer custody or rotation
  continuity across verifier restarts. A versioned asymmetric KMS issuer and
  public verification keyring remain the next authority-lifecycle P0.
- The Devpost entry is submitted and editable while submissions remain open.
  Material edits must be followed by a fresh judge-path check and confirmation
  that the submission card still reports `Submitted`.
- The OIDC trust is restricted to the reviewed `continuum-production`
  environment, and that environment's deployment branch policy admits only
  `main`. Changing either side requires a fresh positive and negative identity
  proof.
