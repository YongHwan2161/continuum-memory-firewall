# Devpost submission checklist

This document is the single source of truth for submission readiness. Check an
item only when its evidence exists and is linked. The participant must personally
complete attestations and organizer agreements.

## Participation

- [ ] Hackathon registration completed by the participant
- [ ] Required participant eligibility and organizer agreements confirmed
- [ ] Submission deadline and judging requirements rechecked on the live event page

## Repository and provenance

- [x] Public open-source repository:
      <https://github.com/YongHwan2161/continuum-memory-firewall>
- [x] Apache-2.0 license included
- [x] Prior-work/new-work boundary documented in
      [PRIOR_WORK.md](PRIOR_WORK.md)
- [x] Local unit and disposable CockroachDB integration instructions included in
      the root README
- [ ] Live cloud setup and teardown instructions completed

## Working product evidence

- [x] Public interactive proof console:
      <https://continuum-memory-firewall.ant713800.chatgpt.site>
- [x] Proof console explicitly labelled as a simulation rather than a live cloud claim
- [x] CockroachDB transaction integration tests run in GitHub Actions
- [ ] Functional cloud-backed application demo URL
- [ ] Live CockroachDB Cloud promotion and vector retrieval evidence
- [ ] Managed MCP tool endpoint and reproducible smoke test
- [ ] External action delivery/reconciliation evidence, if included in the final claim

## Submission materials

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
