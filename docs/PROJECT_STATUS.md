# Project status

**Status date:** 2026-08-08
**Current milestone:** P2C — authenticated managed-cloud slice submitted; iterative hardening open
**Overall state:** the local promotion-to-retrieval vertical slice and repository
MCP contract are implemented and tested. A private, cost-bounded AWS Lambda
worker is deployed and has completed two live read-only CockroachDB Cloud
Managed MCP calls while rejecting a write tool before credential access. The
participant cluster is at migration version 31. A verified caller resolves
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
| CockroachDB schema migrations | Implemented, integration-tested, and live at v31 | Thirty-one packaged single-statement migrations include `VECTOR(512)`, the complete vector prefix, tenant/control-plane RLS, the four-table episode contract, approval/receipt integrity, and the transactional outbox; CI verifies initial apply and replay |
| Migration integrity and recovery | Implemented and integration-tested | SHA-256 history rejects drift and gaps; durable pre-DDL intent resumes the DDL/history crash gap; a renewable lease excludes a second owner; `XXA00` fails closed |
| Existing-schema adoption | Implemented and fail-closed | Unmanaged tables are refused by default; explicit adoption validates required columns, indexes, and composite scope foreign keys |
| Semantic live-DB evaluation | Live-smoked on participant CockroachDB Cloud | Titan v2 ran 60 adversarial and similar-meaning queries across six variant classes; Recall@1/3/5 = 0.8667/0.9833/1.0, zero forbidden-scope rows, p50 = 248.149 ms, p95 = 279.012 ms |
| Bedrock episode contract | Implemented, integration-tested, and live-evaluated | Durable runs, frozen citations, allowlisted proposals, verified outcomes, and server-owned scope are coupled to a phased `search -> optional fetch -> proposal` tool contract; rejected runs retain bounded failure codes and progress |
| Outcome-gated three-arm ablation | 180 identical paired cases per arm completed live | Five isolated replications of 36 stale/poison/conflict-aware cases produced 540 observations. Verified provider outcomes: stateless 80/180, raw-RAG 95/180, Continuum 180/180. Continuum beat raw-RAG by 47.222 points (paired cluster-bootstrap 95% +30.556 to +63.889); Continuum retained zero unsafe proposals, poison exposure, cross-scope rows, false promotions, and ambiguous outcomes |
| Real-provider release guardian | 36 exact paired incidents per arm completed live | Run `31245814421` produced 72 Bedrock/CockroachDB/GitHub observations. Continuum: 36/36 verified outcomes and zero unsafe proposals, exposure, false promotions, duplicate effects, cleanup residuals, and scope leaks. raw-RAG: 31/36, five unsafe proposals, 23 unsafe exposures, and five false promotions. The +13.889-point lift has paired bootstrap 95% +2.778 to +25.0; exact p = 0.0625 is reported without overclaiming. |
| Per-episode paired drill-down | Implemented, live-generated, and checksum-bound | The exact-head `2ef2247` rerun projects 540 observations into 180 three-arm incidents. Each arm exposes scoped search results, SHA-256 citation-handle fingerprints, typed proposal, provider outcome evidence, and promotion decision. Projection gates: exact pairing PASS, issued handles only PASS, Continuum unsafe proposals 0, cross-scope rows 0, private identifier keys 0 |
| Network-visible sign-once | Implemented and publicly verifiable | `hackathon-v10` is durable-draft-first, author-signed, and published in one main-only workflow. It emits exactly one Fulcio/Rekor author bundle, verifies exact workflow/ref/source/runner policy, includes the bundle before immutability, and serves the two-authority network bundle through Pages. The gate separately requires GitHub's one immutable-release countersignature, so platform signing is not misreported as an author replay. |
| Release transaction coordinator | Implemented, fault-injection tested, and publicly gated | A hash-chained receipt advances through `PREPARED`, `AUTHOR_ATTESTED`, `ASSETS_UPLOADED`, `IMMUTABLE`, and `PAGES_MATERIALIZED`. Reruns adopt the exact draft and existing author attestation; changed target/digest or duplicate signatures become fail-closed `AMBIGUOUS`. The judge path binds the terminal receipt, Pages run, release target, and public attestation-bundle digest. |
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
| Live CockroachDB Cloud | Migrated, semantically evaluated, RLS-confined, and egress-restricted | Migration version 31 is current; all visible rows in each protected table matched the caller scope; the allowlist contains only the AWS Elastic IP `/32` |
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
- Public 99.53-second real-provider demonstration video embedded by Devpost:
  <https://youtu.be/OEPYF7cVpbs> (SHA-256
  `d5d7cc82bcce93e5db736cfef7331f64ce667eb4ff9055315c8b697717f09f8f`)
- YouTube, public judge, and final Devpost delivery receipt:
  [2026-08-08-real-provider-video-devpost-v6.md](evidence/2026-08-08-real-provider-video-devpost-v6.md)
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
highest-value work before the submission deadline is:

1. **Lead with the real-provider differentiator:** keep the 36-pair explorer and
   exact receipts above the older retrieval-only metrics on the judge page,
   video, and Devpost description.
2. **Preserve statistical honesty:** present the 540-observation synthetic
   ablation as breadth and the 72-observation GitHub run as external validity;
   do not merge their confidence claims.
3. **Burn in the signed judge path:** monitor the Pages author bundle, immutable
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
- The Devpost entry is submitted and editable while submissions remain open.
  Material edits must be followed by a fresh judge-path check and confirmation
  that the submission card still reports `Submitted`.
- The OIDC trust is restricted to the reviewed `continuum-production`
  environment, and that environment's deployment branch policy admits only
  `main`. Changing either side requires a fresh positive and negative identity
  proof.
