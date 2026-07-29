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

- [x] Interactive proof console deployed:
      <https://continuum-memory-firewall.ant713800.chatgpt.site>
- [x] Proof console explicitly labelled as a simulation rather than a live cloud claim
- [ ] Reviewer demo URL opens without the current Sign in with ChatGPT gate
- [x] CockroachDB transaction integration tests run in GitHub Actions
- [x] Tenant-scoped vector write, search, and retrieval-audit integration tests included
- [x] Versioned migration replay, checksum drift, lease exclusion, and synthetic
      live-database smoke path verified against disposable CockroachDB
- [x] Read-only standard MCP `search`/`fetch` contract and protocol tests included
- [ ] Functional cloud-backed application demo URL
- [ ] Live CockroachDB Cloud promotion and vector retrieval evidence
- [ ] Authenticated public repository MCP endpoint and reproducible remote smoke test
- [ ] CockroachDB Cloud Managed MCP evidence
- [ ] Second qualifying CockroachDB tool evidenced
- [ ] At least one AWS service deployed and evidenced
- [x] Cost-bounded AWS Lambda/Secrets Manager/Budgets/Logs deployment package
      and negative-boundary tests implemented locally
- [ ] External action delivery/reconciliation evidence, if included in the final claim

## Submission materials

- [x] Devpost project page published with the current implementation boundary
- [ ] Project submitted to the CockroachDB x AWS hackathon
- [ ] Architecture diagram distinguishing implemented and planned components
- [ ] Two-to-three minute demo video
- [ ] Screenshots or GIFs for promotion, rejection, replay, and retrieval
- [ ] Problem, approach, architecture, and technical challenge narrative
- [ ] Measured results for policy, idempotency, retrieval, and recovery claims
- [ ] Final list of technologies limited to technologies actually used
- [ ] Repository, demo, video, and documentation links tested in a logged-out browser

## Final integrity review

- [ ] `PROJECT_STATUS.md` matches the final deployed state
- [ ] No secret, token, connection string, or personal credential is committed
- [ ] No planned component is described as implemented
- [ ] Pricing, credit, and organizer-support claims are rechecked against current official sources
- [ ] Participant performs final submission and retains confirmation evidence
