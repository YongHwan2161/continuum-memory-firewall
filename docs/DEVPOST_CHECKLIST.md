# Devpost submission checklist

Official deadline: 2026-08-18 17:00 Eastern Time
(2026-08-19 06:00 Korea Standard Time).

Internal deadline: 2026-08-18 21:00 Korea Standard Time.

## Eligibility and registration

- [ ] Register for the hackathon
- [ ] Confirm team composition
- [ ] Confirm entrant type and country
- [ ] Accept official rules, eligibility, and Devpost terms

## Required build

- [ ] Agentic application uses CockroachDB as persistent memory
- [ ] Deployed on AWS
- [ ] Uses at least two qualifying CockroachDB tools
- [ ] Managed MCP Server is used meaningfully
- [ ] Distributed Vector Indexing is used meaningfully
- [ ] Uses at least one AWS service meaningfully

## Required submission evidence

- [ ] Public open-source GitHub repository
- [x] Open-source license file
- [ ] Complete setup and run instructions
- [ ] Functional demo URL
- [ ] Public video under three minutes
- [ ] CockroachDB tool use explained
- [ ] AWS service use explained
- [x] Pre-existing work disclosure started
- [ ] Architecture diagram

## Technical evidence

- [x] Deterministic P0 policy tests
- [x] CockroachDB v26.2.3 disposable-node schema migration test
- [x] SERIALIZABLE candidate promotion and idempotent replay test
- [ ] Vector query plan evidence
- [ ] Worker-kill and resume test
- [x] Conflicting-worker action-claim test
- [ ] Memory-poisoning evaluation
- [ ] Cost report
- [ ] Dependency and secret scan
