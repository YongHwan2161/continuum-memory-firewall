# Project status

**Status date:** 2026-08-01
**Current milestone:** P2B — authenticated managed-cloud slice deployed; submission packaging pending
**Overall state:** the local promotion-to-retrieval vertical slice and repository
MCP contract are implemented and tested. A private, cost-bounded AWS Lambda
worker is deployed and has completed two live read-only CockroachDB Cloud
Managed MCP calls while rejecting a write tool before credential access. The
participant cluster now has all eight versioned migrations, and its synthetic
promotion, 512-dimensional vector retrieval, and audit path passed live. A
separate least-privilege runtime identity now serves the authenticated public
`/mcp` endpoint through fixed AWS egress, and a remote client proved allowed
search/fetch plus cross-scope denial. Final submission materials remain.

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
| CockroachDB schema migrations | Implemented and integration-tested | Eight packaged single-statement migrations apply `VECTOR(512)` and vector-index DDL; CI verifies initial apply and replay |
| Migration integrity and recovery | Implemented and integration-tested | SHA-256 history rejects drift and gaps; durable pre-DDL intent resumes the DDL/history crash gap; a renewable lease excludes a second owner; `XXA00` fails closed |
| Existing-schema adoption | Implemented and fail-closed | Unmanaged tables are refused by default; explicit adoption validates required columns, indexes, and composite scope foreign keys |
| Synthetic live-DB smoke | Live-smoked on participant CockroachDB Cloud | The production smoke path applied eight migrations, promoted, embedded, retrieved, audited, fetched, and deleted only its generated rows on 2026-08-01 |
| Tenant and incident integrity | Implemented | Composite foreign keys and query predicates bind candidates, canonical memory, actions, and retrieval audit to the same scope |
| Vector write and retrieval | Implemented and participant-cluster live-smoked | Deterministic 512-dimensional test/demo embeddings were persisted and retrieved with mandatory tenant and incident prefixes |
| Retrieval audit | Implemented | Search transaction records model, query digest, policy digest, evaluated IDs, and accepted IDs |
| Standard MCP boundary | Implemented, deployed, and remotely smoked | Official Python MCP SDK exposes only read-only `search` and `fetch`; a TLS client initialized protocol `2025-11-25`, listed exactly those tools, and completed allowed/denied scope calls |
| Secure configuration guard | Implemented and live-verified | HTTPS, `sslmode=verify-full`, a minimum-length bearer token, exact-host DNS-rebinding protection, and server-configured tenant/incident scope fail closed |
| SQL workload separation | Implemented and live-verified | The migrator owns DDL objects; runtime has only required reads and retrieval-audit insert. Runtime schema creation and canonical update both failed with `42501`, including after inherited `public` privileges were removed |
| Cloud deployment runbook | Implemented | One SSOT procedure separates automated checks from participant-owned account, credit, MFA, key-copy, evidence, and teardown steps |
| CockroachDB Basic provisioning | Provisioned through the Cloud Console; CLI guard not executed | Participant console verification on 2026-07-30 shows the cluster available on Basic in AWS Singapore, with usage below the displayed 50M RU and 10 GiB monthly limits |
| AWS Managed MCP worker | Deployed and live-smoked | Private direct-invoke Lambda returned `ok: true` for `list_databases` and `list_tables`; `insert_rows` returned `INVALID_REQUEST` before secret access |
| AWS infrastructure and package | Deployed and verified | Budget, private Lambda, and authenticated-MCP stacks are complete. The EC2 host has no SSH, requires IMDSv2, reads one runtime secret and one exact S3 object, verifies a deterministic artifact hash, and is managed through SSM |
| Reviewer experience | Deployed public simulation | GitHub Pages opens without login and Browser verification exercised policy rejection plus one-owner failover; it remains explicitly separate from live cloud evidence |
| Live CockroachDB Cloud | Migrated, vector-smoked, and egress-restricted | Eight migrations reached version 8; retained allowed/denied demo scopes support the remote smoke; the allowlist now contains only the AWS Elastic IP `/32`, and a workstation retry was blocked |
| Public MCP endpoint | Deployed and cross-scope-smoked | `https://47-131-98-12.sslip.io/mcp` has valid TLS, health `200`, missing/wrong auth `401`, allowed search/fetch PASS, denied-scope search hidden, and cross-scope fetch denied |
| CockroachDB Managed MCP | Live read-only evidence complete | A cluster-scoped `Cluster Operator` service account initialized the managed server, advertised 12 tools, listed the `continuum` database, and returned zero tables in the historical pre-migration snapshot through the deployed Lambda |
| AWS service use | Live deployment evidenced | Lambda, EC2, Elastic IP, SSM, Secrets Manager, S3, CloudWatch Logs, CloudFormation, and AWS Budgets are active in Singapore; the USD 5 budget retains forecast-at-80% and actual-at-100% email alerts |
| Exactly-once external effect | Not guaranteed | The database claim is idempotent; an external provider call and acknowledgement are not yet coordinated |
| Production security and resilience | Partial | Minimum IAM, separate SQL identities, exact-host protection, TLS, fixed egress, and negative-capability tests are live; short-lived identity, RLS, semantic embeddings, pooling, rotation, multi-region testing, and worker-crash reconciliation are not complete |

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
- Published Devpost project page (not submitted to the hackathon):
  <https://devpost.com/software/continuum-memory-firewall>
- Redacted live AWS and CockroachDB evidence:
  [2026-07-31-cloud-live-smoke.md](evidence/2026-07-31-cloud-live-smoke.md)
- Redacted live SQL migration and vector evidence:
  [2026-08-01-live-sql-vector-smoke.md](evidence/2026-08-01-live-sql-vector-smoke.md)
- Authenticated remote MCP and least-privilege SQL evidence:
  [2026-08-01-authenticated-remote-mcp-smoke.md](evidence/2026-08-01-authenticated-remote-mcp-smoke.md)
- Merged live-evidence PR:
  <https://github.com/YongHwan2161/continuum-memory-firewall/pull/11>

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
8. MCP clients can search and fetch only the fixed server-side scope.
9. A separately packaged AWS worker can call only an explicit read-only subset
   of CockroachDB Cloud Managed MCP; it cannot expose a public Lambda URL and
   cannot retrieve any other Secrets Manager resource under its generated role.
10. Database schema state is reproducible from immutable ordered migrations;
    replay is a no-op, checksum drift is rejected, an interrupted DDL/history
    boundary resumes from durable intent, and concurrent owners cannot proceed
    together.

These guarantees apply to the repository code and tested database boundary. They
do not extend to an unimplemented external API call.

## Immediate participant focus

The AWS, Managed MCP, participant-cluster SQL, least-privilege runtime, fixed
egress, and authenticated remote MCP gates are closed. The shortest remaining
path to a competition submission is:

1. **Package the judge flow:** record a two-to-three minute video showing one
   accepted path, one rejected path, live Managed MCP evidence, and the explicit
   simulation-versus-live boundary.
2. **Complete submission evidence:** add screenshots, measured retrieval and
   policy results, final technology list, participant attestations, and the
   Devpost confirmation receipt.
3. **Harden beyond the competition slice:** replace the deterministic hashing
   embedder with a bounded semantic model, capture query-plan/latency evidence,
   and replace the static bearer/fixed scope with short-lived identity-derived
   authorization.

The exact commands and stop conditions are in
[CLOUD_DEPLOYMENT_RUNBOOK.md](CLOUD_DEPLOYMENT_RUNBOOK.md).

## Remaining blockers

- Organizer eligibility attestations beyond the confirmed Devpost registration
  remain participant-owned.
- The deployed long-lived service-account API key has no automatic rotation.
  Rotate or delete it and tear down the worker resources after judging.
- The public MCP uses one static bearer and one fixed synthetic scope. It is not
  production multi-tenant authorization; add short-lived OAuth/JWT identity and
  database-native policy before expanding access.
- The deterministic hashing embedder proved vector mechanics but missed the
  natural-language smoke query at the default similarity threshold. A semantic
  model and measured relevance evaluation remain required for quality claims.
- Live memory citation URLs do not yet provide durable reviewer-visible detail
  pages, and connection pooling/query-plan evidence remains incomplete.
- The Devpost submission still needs a short public video, screenshots, the
  final narrative, participant attestations, and submission confirmation. See
  [DEVPOST_CHECKLIST.md](DEVPOST_CHECKLIST.md).
- AWS CLI authentication was refreshed and used for the verified deployment.
  Replace root-driven operations with a dedicated deployment role before the
  next long-lived environment change.
