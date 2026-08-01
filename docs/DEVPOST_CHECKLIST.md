# Devpost submission checklist

This document is the single source of truth for submission readiness. Check an
item only when its evidence exists and is linked. The participant must personally
complete attestations and organizer agreements.

## Participation

- [x] Hackathon registration confirmed through Devpost on 2026-07-25
- [ ] Required participant eligibility and organizer agreements confirmed
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
      with the free-resource monthly limits and a restricted temporary SQL network
- [x] Live cluster state rechecked on 2026-08-01: all eight migrations applied,
      synthetic vector smoke passed, generated rows cleaned up, and the SQL IP
      allowlist reduced to zero entries
- [ ] Functional cloud-backed application demo URL
- [x] Live CockroachDB Cloud promotion and vector retrieval evidence; see
      [2026-08-01-live-sql-vector-smoke.md](evidence/2026-08-01-live-sql-vector-smoke.md)
- [ ] Authenticated public repository MCP endpoint and reproducible remote smoke test
- [x] CockroachDB Cloud Managed MCP evidenced on 2026-07-31 through the private
      AWS worker: `list_databases` returned the `continuum` database
- [x] Second CockroachDB Managed MCP read tool evidenced: `list_tables` returned
      the live cluster's historical pre-migration empty application schema
- [x] AWS services deployed and evidenced: private Lambda, one scoped Secrets
      Manager secret, encrypted private S3 package, CloudWatch Logs,
      CloudFormation, and AWS Budgets
- [x] Cost-bounded AWS deployment and negative boundary evidenced:
      `insert_rows` was rejected before secret resolution; see
      [2026-07-31-cloud-live-smoke.md](evidence/2026-07-31-cloud-live-smoke.md)
- [ ] External action delivery/reconciliation evidence, if included in the final claim

## Submission materials

- [x] Devpost project page published with the current implementation boundary
- [ ] Project submitted to the CockroachDB x AWS hackathon
- [x] Architecture diagram distinguishes locally implemented, live deployed,
      and planned application components
- [ ] Two-to-three minute demo video
- [ ] Screenshots or GIFs for promotion, rejection, replay, and retrieval
- [ ] Problem, approach, architecture, and technical challenge narrative
- [ ] Measured results for policy, idempotency, retrieval, and recovery claims
- [ ] Final list of technologies limited to technologies actually used
- [ ] Repository, demo, video, and documentation links tested in a logged-out browser

## Final integrity review

- [x] `PROJECT_STATUS.md` matches the 2026-08-01 deployed and SQL-smoked state
- [x] No secret, token, connection string, or personal credential is committed
      in the deployment evidence commit
- [x] No planned application component is described as implemented
- [ ] Pricing, credit, and organizer-support claims are rechecked against current official sources
- [ ] Participant performs final submission and retains confirmation evidence
