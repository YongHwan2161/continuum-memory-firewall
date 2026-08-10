# Devpost submission checklist

This document is the single source of truth for submission readiness. Check an
item only when its evidence exists and is linked. The participant must personally
complete attestations and organizer agreements.

## Participation

- [x] Hackathon registration confirmed through Devpost on 2026-07-25
- [x] Required participant eligibility and organizer agreements confirmed by
      the participant on 2026-08-02
- [x] Live challenge requirements rechecked on 2026-07-29: public repository,
      functional demo, public video under three minutes, at least two qualifying
      CockroachDB tools, and at least one AWS service

## Repository and provenance

- [x] Public open-source repository:
      <https://github.com/YongHwan2161/continuum-memory-firewall>
- [x] Apache-2.0 license included
- [x] Prior-work/new-work boundary documented in
      [PRIOR_WORK.md](PRIOR_WORK.md)
- [x] Local unit and disposable CockroachDB integration instructions included in
      the root README
- [x] Live cloud setup and teardown instructions completed in
      [CLOUD_DEPLOYMENT_RUNBOOK.md](CLOUD_DEPLOYMENT_RUNBOOK.md)

## Working product evidence

- [x] Logged-out interactive proof console deployed:
      <https://yonghwan2161.github.io/continuum-memory-firewall/>
- [x] Simulated policy interactions are labelled separately from live,
      exact-receipt metric and verifier claims
- [x] Reviewer demo URL opens without a sign-in gate; Browser verification on
      2026-07-29 exercised rejection and failover controls
- [x] CockroachDB transaction integration tests run in GitHub Actions
- [x] Tenant-scoped vector write, search, and retrieval-audit integration tests included
- [x] Versioned migration replay, checksum drift, lease exclusion, and synthetic
      live-database smoke path verified against disposable CockroachDB
- [x] Read-only standard MCP `search`/`fetch` contract and protocol tests included
- [x] Participant-owned CockroachDB Basic cluster provisioned on AWS Singapore
      with the free-resource monthly limits and a fixed AWS egress `/32`
- [x] Live cluster state rechecked on 2026-08-02: migration version 17,
      CockroachDB RLS on three scope-bearing tables, least-privilege negative
      tests, and exactly one AWS Elastic IP `/32` SQL rule
- [x] Functional cloud-backed application demo URL:
      <https://47-131-98-12.sslip.io/healthz> with authenticated MCP at
      <https://47-131-98-12.sslip.io/mcp>
- [x] Live CockroachDB Cloud promotion and vector retrieval evidence; see
      [2026-08-01-live-sql-vector-smoke.md](evidence/2026-08-01-live-sql-vector-smoke.md)
- [x] Authenticated public repository MCP endpoint and reproducible remote smoke
      test; see
      [2026-08-01-authenticated-remote-mcp-smoke.md](evidence/2026-08-01-authenticated-remote-mcp-smoke.md)
- [x] Five-minute Cognito caller identity, audited caller binding, matching SQL
      role, Titan v2 semantic evaluation, RLS, and remote cross-scope denial;
      60 queries measured Recall@1/3/5 = 0.8667/0.9833/1.0 with zero leaked
      documents and p50/p95 = 248.149/279.012 ms; see
      [2026-08-02-control-plane-eval-pooling-live.md](evidence/2026-08-02-control-plane-eval-pooling-live.md)
- [x] One-click read-only judge verifier checks exact workflow/head, live MCP
      health, Devpost Submitted, control-plane denial, bounded pools, RLS, and
      vector-index metadata:
      <https://yonghwan2161.github.io/continuum-memory-firewall/verify.html>
- [x] Public per-episode paired explorer binds the same 180 incidents across
      stateless, raw-RAG, and Continuum, with scoped search, handle fingerprints,
      typed proposal, provider outcome evidence, and promotion decision:
      <https://yonghwan2161.github.io/continuum-memory-firewall/episodes.html>
- [x] Real-provider guardian completed 36 exact paired incidents per arm through
      Bedrock, CockroachDB, and disposable GitHub Releases drafts. Continuum
      completed 36/36 with zero unsafe proposals, exposure, false promotion,
      duplicate effect, cleanup residual, or scope leak; the public paired page
      is checksum-bound at
      <https://yonghwan2161.github.io/continuum-memory-firewall/release-guardian.html>
- [x] Five time-distributed real-provider batches completed with separate
      workflow and artifact receipts. The 180-pair aggregate reports Continuum
      180/180 versus raw-RAG 150/180, cluster bootstrap 95% +10.0 to +24.44
      percentage points, positive lift in 5/5 batches, and zero Continuum
      unsafe or residual effects. Public explorer:
      <https://yonghwan2161.github.io/continuum-memory-firewall/release-guardian-replication.html>
- [x] Three independently sealed time clusters completed the sequential blind
      memory-compounding contract: 36 five-episode chains, three arms, and 540
      GitHub/S3 observations. Continuum reached 114/144 future-target successes
      versus stateless 105/144 and raw-RAG 102/144; raw-RAG admitted 48 false
      canonical promotions versus zero for Continuum. The +8.33-point paired
      lift over raw-RAG had a sealed-batch bootstrap 95% interval of +3.47 to
      +14.58 and sequential e-value 637.15. The stateless comparison remains
      directional because its interval crossed zero. Public explorer:
      <https://yonghwan2161.github.io/continuum-memory-firewall/sequential-blind.html>
- [x] Real closed-loop CI benchmark completed 54 unique GitHub Actions child
      runs across six calibrated fault families. Continuum and stateless each
      recovered 12/12; raw-RAG recovered 11/12 and promoted one failed outcome.
      Exact parent/artifact/public digests, zero repository mutation, and zero
      cleanup residual are judge-verifiable at
      <https://yonghwan2161.github.io/continuum-memory-firewall/ci-recovery.html>.
- [x] S3-preregistered ambiguity-first diagnosis completed 84 unique GitHub
      Actions child receipts: 18 calibration, 30 read-only diagnostics, and 36
      remediations. All three arms recovered 12/12; Continuum used six probes
      versus twelve for stateless and skipped all six recurrence probes
      (`p=0.03125`) with canonical precision 1.0, false promotion 0, repository
      mutation 0, and cleanup residual 0. The page discloses the higher input-
      token cost and exact-fingerprint/non-transfer boundary:
      <https://yonghwan2161.github.io/continuum-memory-firewall/adaptive-diagnosis.html>.
- [x] S3-preregistered counterfactual transfer firewall completed 84 unique
      GitHub Actions child receipts across six source calibrations, twelve
      disjoint-fingerprint targets, three arms, and separate target
      attestations. Continuum recovered 12/12, transferred all six compatible
      memories without a diagnostic, rejected all six near neighbours, and
      retained zero false promotions. raw-RAG recovered 6/12 and falsely
      transferred/promoted all six near neighbours. The paired probe reduction
      and recovery lift gates each reached `p=0.03125`; the page preserves the
      shared-attestation and non-open-world boundary:
      <https://yonghwan2161.github.io/continuum-memory-firewall/transfer-firewall.html>.
- [x] Network-visible sign-once release flow refuses a second author
      attestation, attaches the one verified Fulcio/Rekor author bundle before
      release immutability, serves identical bundle bytes through Pages, and
      separately identifies GitHub's immutable-release countersignature. The
      strict command binds author workflow, main ref, source SHA, hosted runner,
      Rekor timestamp, and the one-author/one-platform authority cardinality.
- [x] Release transaction coordinator creates the durable draft before signing,
      reuses an existing author attestation after a crash, verifies every asset
      digest, fails closed on `AMBIGUOUS`, and publishes a hash-chained terminal
      `PAGES_MATERIALIZED` receipt through the one-click judge page.
- [x] Byte-identical 10k/50k non-sensitive vector benchmark report proves the
      complete `1/32/128/512` beam trade-off, natural vector-search plan, no
      full scan, and zero foreign rows; at 50k/beam 512 Recall@10 was 0.96875
      and warm p50/p95 was 216.445/314.273 ms; run
      <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30735058404>
      and [evidence](evidence/2026-08-02-vector-scale-live.md)
- [x] CockroachDB Cloud Managed MCP evidenced on 2026-07-31 through the private
      AWS worker: `list_databases` returned the `continuum` database
- [x] Second CockroachDB Managed MCP read tool evidenced: `list_tables` returned
      the live cluster's historical pre-migration empty application schema
- [x] AWS services deployed and evidenced: private Lambda, authenticated EC2,
      Elastic IP, SSM, scoped Secrets Manager secrets, encrypted private S3
      package, CloudWatch Logs, CloudFormation, Cognito, Bedrock, IAM OIDC, and
      AWS Budgets
- [x] AWS Root console session ended; exact-head deployment uses the one-hour,
      repository/branch-bound `continuum-hackathon-deployer` role
- [x] AWS monthly alert budget raised to USD 20 with forecast-at-80% and
      actual-at-100% notifications
- [x] Managed MCP API key rotation completed; new key passed `list_databases`
      and `list_tables`, old key was revoked, and the temporary GitHub secret
      was deleted; run
      <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30695651609>
- [x] Guarded v3 rotation repeated on 2026-08-02; the AWS secret replacement,
      cache-bound wait, two-tool validation, and pre-secret write denial passed,
      then the v2 provider key and temporary GitHub secret were deleted; run
      <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30709230016>
- [x] Cost-bounded AWS deployment and negative boundary evidenced:
      `insert_rows` was rejected before secret resolution; see
      [2026-07-31-cloud-live-smoke.md](evidence/2026-07-31-cloud-live-smoke.md)
- [ ] External action delivery/reconciliation evidence, if included in the final claim

## Submission materials

- [x] Devpost project page published with the current implementation boundary
- [x] Project submitted to the CockroachDB x AWS hackathon on 2026-08-02;
      Devpost submission `1121568` returned `Submitted`
- [x] Architecture diagram distinguishes locally implemented, live deployed,
      and planned application components
- [x] Updated secret-free 90–120 second narrated demo generated from the live
      incident, verifier, 10k/50k ANN, and 10/25/50-agent pressure evidence
- [x] Secret-free screenshots captured for the live overview, policy rejection,
      and one-owner failover in [docs/demo/](demo/)
- [x] Receipt-compiled judge demo uploaded publicly to YouTube and embedded on
      Devpost: <https://youtu.be/QQxfQaDVz9c>; 97.02 seconds; local-render
      SHA-256
      `30518452bf16d46ad33d3500d98731f89273789d4b3b7b75bddd032194a7bed4`.
      It leads with the failed-outcome memory problem, compares the same 144
      future target episodes per arm, shows 48 raw-RAG false promotions versus
      zero for Continuum, proves exact-artifact evaluator reconciliation, and
      ends at public PASS. English (US) SRT SHA-256
      `f95c60536851fd6cfa8f05441e15ed069da35457aba779977e91024835bbd98b`,
      public visibility, and a no-issues copyright check were confirmed on
      2026-08-09.
- [x] Devpost description reflects the sealed 540-observation sequential blind
      result, its raw-RAG and stateless comparison boundaries, exact evaluator
      recovery, real-provider paired guardian, immutable release transaction,
      and current public judge path. The authenticated update returned project
      version `20`; the post-submit re-read stabilized at
      `2026-08-09T10:54:00.418-04:00`. Submission `1121568` retained its
      original `submitted_at` receipt and the project remained `published`.
- [x] Measured 60-query, 10k/50k, and 10/25/50-agent results recorded;
      production-quality generalization remains an explicit non-claim
- [x] Final technology inventory limited to deployed/tested components in
      `PROJECT_STATUS.md` and copied into Devpost
- [x] Repository, demo, video, and documentation links tested without project
      credentials

## Final integrity review

- [x] `PROJECT_STATUS.md` matches the 2026-08-01 OIDC/Titan/RLS live-smoked state
- [x] No secret, token, connection string, or personal credential is committed
      in the deployment evidence commit
- [x] No planned application component is described as implemented
- [ ] Pricing, credit, and organizer-support claims are rechecked against current official sources
- [x] Participant-owned attestations were selected and final submission receipt
      retained: submission `1121568`, `Submitted` at 2026-08-02 00:22 KST
- [ ] After judging, dedicated-role teardown deletes the authenticated MCP EC2
      stack and confirms the Elastic IP release
