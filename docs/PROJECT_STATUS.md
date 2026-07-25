# Project status

**Status date:** 2026-07-25  
**Current milestone:** P1 — transactional authority  
**Overall state:** local implementation and CockroachDB integration evidence are
ready; cloud-backed vertical-slice and submission work remain.

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
| CockroachDB schema | Implemented and integration-tested | CI applies `db/schema.sql` to CockroachDB v26.2.3, including `VECTOR(512)` and the vector index DDL |
| Public reviewer experience | Deployed simulation | Browser proof console demonstrates policy outcomes and replay behavior |
| Live CockroachDB Cloud | Not implemented | No cloud cluster or cloud connection evidence in this repository |
| Managed MCP tool boundary | Not implemented | No MCP server or deployed MCP endpoint |
| Vector write and retrieval | Schema only | Vector column and index exist; no embedding ingestion, query, recall evaluation, or query-plan evidence |
| AWS/Bedrock path | Not implemented | No Lambda, Bedrock, or AWS deployment evidence |
| Exactly-once external effect | Not guaranteed | The database claim is idempotent; an external provider call and acknowledgement are not yet coordinated |
| Production security and resilience | Not implemented | No workload identity, secret rotation, tenant RLS, multi-region test, or worker-crash reconciliation evidence |

## Evidence

- Repository: <https://github.com/YongHwan2161/continuum-memory-firewall>
- Current implementation PR: <https://github.com/YongHwan2161/continuum-memory-firewall/pull/1>
- Passing P1 CI run before this documentation update:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30144393994>
- Public proof console:
  <https://continuum-memory-firewall.ant713800.chatgpt.site>
- Devpost draft: <https://devpost.com/software/continuum-memory-firewall>

After PR #1 is merged, `main` and its post-merge workflow are the authoritative
code and CI evidence; the PR remains the review record.

## What P1 establishes

P1 establishes a narrow durable authority boundary:

1. A candidate record is read and locked.
2. The deterministic policy evaluates the candidate.
3. The decision and audit evidence are written transactionally.
4. Accepted data becomes canonical exactly once for the same source identity.
5. A later action claim uses a unique idempotency key to select one database
   winner.

These guarantees apply to the repository code and tested database boundary. They
do not extend to an unimplemented external API call.

## Immediate blockers outside the code

- Hackathon participation and required organizer agreements must be completed by
  the participant.
- Cloud credentials and spending controls are required before a live managed
  deployment can be verified.
- The Devpost submission needs a cloud-backed demo, architecture diagram, demo
  video, and final written narrative. See
  [DEVPOST_CHECKLIST.md](DEVPOST_CHECKLIST.md).
