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
- [x] Proof console explicitly labelled as a simulation rather than a live cloud claim
- [x] Reviewer demo URL opens without a sign-in gate; Browser verification on
      2026-07-29 exercised rejection and failover controls
- [x] CockroachDB transaction integration tests run in GitHub Actions
- [x] Tenant-scoped vector write, search, and retrieval-audit integration tests included
- [x] Versioned migration replay, checksum drift, lease exclusion, and synthetic
      live-database smoke path verified against disposable CockroachDB
- [x] Read-only standard MCP `search`/`fetch` contract and protocol tests included
- [x] Participant-owned CockroachDB Basic cluster provisioned on AWS Singapore
      with the free-resource monthly limits and a fixed AWS egress `/32`
- [x] Live cluster state rechecked on 2026-08-01: migration version 11,
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
- [x] Five-minute Cognito caller identity, caller-derived SQL role, Titan v2
      semantic evaluation, RLS, and remote cross-scope denial; Recall@3 = 1.0
      across four queries with zero leaked documents; see
      [2026-08-01-oidc-titan-rls-live-smoke.md](evidence/2026-08-01-oidc-titan-rls-live-smoke.md)
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
- [x] AWS monthly alert budget raised to USD 10 with forecast-at-80% and
      actual-at-100% notifications
- [x] Managed MCP API key rotation completed; new key passed `list_databases`
      and `list_tables`, old key was revoked, and the temporary GitHub secret
      was deleted; run
      <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30695651609>
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
- [x] Secret-free 72-second narrated demo video generated at
      [docs/demo/continuum-memory-firewall-demo.mp4](demo/continuum-memory-firewall-demo.mp4)
- [x] Secret-free screenshots captured for the live overview, policy rejection,
      and one-owner failover in [docs/demo/](demo/)
- [x] Demo video uploaded publicly to YouTube and embedded on Devpost:
      <https://youtu.be/raad44nJj5I>
- [x] Problem, approach, architecture, and technical challenge narrative
      rendered on the public Devpost project page
- [x] Measured retrieval/isolation results recorded; broader latency and
      production-quality statistics remain explicit non-claims
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
