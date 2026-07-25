# Documentation ownership

This index defines which document is authoritative for each kind of project
information. Other documents should link to the owner instead of duplicating
changing status, dates, or priorities.

| Information | Single source of truth |
|---|---|
| Current implementation, evidence, and non-claims | [PROJECT_STATUS.md](PROJECT_STATUS.md) |
| Milestones, priorities, and exit criteria | [ROADMAP.md](ROADMAP.md) |
| Trust boundaries and component responsibilities | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Promotion, replay, and retry semantics | [TRANSACTION_MODEL.md](TRANSACTION_MODEL.md) |
| MCP tools, scope, transport, and deployment contract | [MCP_CONTRACT.md](MCP_CONTRACT.md) |
| Devpost readiness and participant-owned blockers | [DEVPOST_CHECKLIST.md](DEVPOST_CHECKLIST.md) |
| Cost assumptions and spending controls | [COST_SAFETY.md](COST_SAFETY.md) |
| CockroachDB Cloud/AWS provisioning, proof, and teardown procedure | [CLOUD_DEPLOYMENT_RUNBOOK.md](CLOUD_DEPLOYMENT_RUNBOOK.md) |
| Prior-work and hackathon-work provenance | [PRIOR_WORK.md](PRIOR_WORK.md) |

## Maintenance rules

1. Update `PROJECT_STATUS.md` when verified capability or evidence changes.
2. Update `ROADMAP.md` when implementation order or an acceptance gate changes.
3. Keep the root `README.md` as a stable overview; do not copy detailed status
   tables or backlogs into it.
4. Label planned architecture explicitly. A design diagram is not implementation
   evidence.
5. Every completed checklist item must point to repository or deployment
   evidence. Participant attestations stay unchecked until the participant
   completes them.
6. Keep commands and operator-owned cloud steps in
   `CLOUD_DEPLOYMENT_RUNBOOK.md`; status and price documents should link to it
   instead of copying the procedure.
