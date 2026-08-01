# Project status

**Status date:** 2026-08-01
**Current milestone:** P2B — live managed-cloud and SQL data-plane evidence; public application pending
**Overall state:** the local promotion-to-retrieval vertical slice and repository
MCP contract are implemented and tested. A private, cost-bounded AWS Lambda
worker is deployed and has completed two live read-only CockroachDB Cloud
Managed MCP calls while rejecting a write tool before credential access. The
participant cluster now has all eight versioned migrations, and its synthetic
promotion, 512-dimensional vector retrieval, retrieval audit, fetch, and cleanup
path passed live. A public authenticated application endpoint and final
submission materials remain.

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
| Standard MCP boundary | Implemented and protocol-tested | Official Python MCP SDK exposes only read-only `search` and `fetch`; in-memory client tests validate schemas and structured responses |
| Secure configuration guard | Implemented | Public citation base URL must be HTTPS; remote database URLs must use `sslmode=verify-full`; tenant and incident scope are server configuration, not tool input |
| Cloud deployment runbook | Implemented | One SSOT procedure separates automated checks from participant-owned account, credit, MFA, key-copy, evidence, and teardown steps |
| CockroachDB Basic provisioning | Provisioned through the Cloud Console; CLI guard not executed | Participant console verification on 2026-07-30 shows the cluster available on Basic in AWS Singapore, with usage below the displayed 50M RU and 10 GiB monthly limits |
| AWS Managed MCP worker | Deployed and live-smoked | Private direct-invoke Lambda returned `ok: true` for `list_databases` and `list_tables`; `insert_rows` returned `INVALID_REQUEST` before secret access |
| AWS infrastructure and package | Deployed and verified | Separate Budget and worker stacks are `CREATE_COMPLETE`; the worker has minimum secret/log IAM, 256 MiB memory, 30-second timeout, seven-day logs, no public endpoint/VPC/NAT, and an account-compatible optional concurrency reservation |
| Reviewer experience | Deployed public simulation | GitHub Pages opens without login and Browser verification exercised policy rejection plus one-owner failover; it remains explicitly separate from live cloud evidence |
| Live CockroachDB Cloud | Migrated and vector-smoked | Eight migrations reached current version 8 without adoption; the promotion/retrieval/audit/fetch path passed, synthetic rows were removed, and the IP allowlist was reduced to zero entries on 2026-08-01 |
| Public MCP endpoint | Not deployed | The server contract exists, but no authenticated, stable HTTPS MCP deployment has been verified |
| CockroachDB Managed MCP | Live read-only evidence complete | A cluster-scoped `Cluster Operator` service account initialized the managed server, advertised 12 tools, listed the `continuum` database, and returned zero tables in the historical pre-migration snapshot through the deployed Lambda |
| AWS service use | Live deployment evidenced | Lambda, Secrets Manager, S3, CloudWatch Logs, CloudFormation, and AWS Budgets are active in Singapore; the private package object is encrypted and expires after seven days, and the USD 5 monthly budget has forecast-at-80% and actual-at-100% email alerts |
| Exactly-once external effect | Not guaranteed | The database claim is idempotent; an external provider call and acknowledgement are not yet coordinated |
| Production security and resilience | Partial | Lambda uses a generated minimum-IAM workload role and one-secret scope, but API-key rotation, a least-privilege application/migrator SQL identity, RLS, multi-region testing, and worker-crash reconciliation are not complete |

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
- Current live-evidence Draft PR:
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

The AWS, Managed MCP, and participant-cluster SQL evidence gates are closed. The
shortest remaining path to a competition submission is:

1. **Expose the application boundary:** deploy the repository `search`/`fetch`
   MCP service behind authenticated HTTPS with fixed tenant/incident scope, or
   keep the submission claim explicitly limited to the private operational
   evidence worker.
2. **Harden SQL identities:** separate schema migration from runtime access,
   grant only the required database privileges, and capture vector query-plan
   evidence without reopening a broad network rule.
3. **Package the judge flow:** record a two-to-three minute video showing one
   accepted path, one rejected path, live Managed MCP evidence, and the explicit
   local-versus-live boundary; then complete the participant attestations and
   final Devpost submission.

The exact commands and stop conditions are in
[CLOUD_DEPLOYMENT_RUNBOOK.md](CLOUD_DEPLOYMENT_RUNBOOK.md).

## Remaining blockers

- Organizer eligibility attestations beyond the confirmed Devpost registration
  remain participant-owned.
- The deployed long-lived service-account API key has no automatic rotation.
  Rotate or delete it and tear down the worker resources after judging.
- The live SQL smoke used the participant-created console identity. Separate
  least-privilege migrator and runtime roles, then rotate the bootstrap
  credential before any persistent application deployment.
- The private Lambda proves AWS-to-Managed-MCP integration but is intentionally
  not a functional public application URL. The repository MCP service is not
  deployed behind authenticated HTTPS.
- The Devpost submission still needs a short public video, screenshots, the
  final narrative, participant attestations, and submission confirmation. See
  [DEVPOST_CHECKLIST.md](DEVPOST_CHECKLIST.md).
- The AWS console session is live, but the local AWS CLI session was expired at
  the last check. Refresh it before any further CLI-based deployment, rotation,
  or teardown verification.
