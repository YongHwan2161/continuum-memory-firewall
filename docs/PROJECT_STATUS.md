# Project status

**Status date:** 2026-07-27
**Current milestone:** P2B — managed-cloud deployment readiness
**Overall state:** the local promotion-to-retrieval vertical slice, repository
MCP contract, and cost-bounded AWS-to-CockroachDB Managed MCP deployment package
are implemented and locally verified. Participant-owned cloud accounts,
credentials, live provisioning, and final submission evidence remain.

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
| Synthetic live-DB smoke | Implemented and integration-tested on disposable CockroachDB | The production smoke path migrates, promotes, embeds, retrieves, audits, fetches, and deletes only its generated rows |
| Tenant and incident integrity | Implemented | Composite foreign keys and query predicates bind candidates, canonical memory, actions, and retrieval audit to the same scope |
| Vector write and retrieval | Implemented for disposable DB | Deterministic 512-dimensional test/demo embeddings are persisted; CockroachDB cosine search is prefix-scoped by tenant and incident |
| Retrieval audit | Implemented | Search transaction records model, query digest, policy digest, evaluated IDs, and accepted IDs |
| Standard MCP boundary | Implemented and protocol-tested | Official Python MCP SDK exposes only read-only `search` and `fetch`; in-memory client tests validate schemas and structured responses |
| Secure configuration guard | Implemented | Public citation base URL must be HTTPS; remote database URLs must use `sslmode=verify-full`; tenant and incident scope are server configuration, not tool input |
| Cloud deployment runbook | Implemented | One SSOT procedure separates automated checks from participant-owned account, credit, MFA, key-copy, evidence, and teardown steps |
| CockroachDB Basic provisioning guard | Implemented locally, not executed | Dry-by-default `ccloud` script pins Basic/AWS/Singapore/spend-limit 0 and aborts if the installed CLI no longer supports the limit flag |
| AWS Managed MCP worker | Implemented locally, not deployed | Lambda client pins the official HTTPS endpoint, caps input/output, retrieves one Secrets Manager ARN, and rejects Managed MCP write tools before credential access |
| AWS infrastructure and package | Implemented and locally verified, not deployed | CloudFormation defines budget alerts, minimum IAM, concurrency 1, 30-second timeout, seven-day logs, and no public endpoint/VPC/NAT; the Python 3.12 manylinux zip builds and passes integrity checks |
| Public reviewer experience | Deployed simulation | Browser proof console demonstrates policy outcomes and replay behavior |
| Live CockroachDB Cloud | Not implemented | No cloud cluster or cloud connection evidence in this repository |
| Public MCP endpoint | Not deployed | The server contract exists, but no authenticated, stable HTTPS MCP deployment has been verified |
| CockroachDB Managed MCP | Client boundary only; no live evidence | The AWS worker is prepared for the managed service, but no participant API key or successful cloud response has been used |
| AWS service use | Deployment-ready only; no live evidence | Lambda/Secrets Manager/Budgets/Logs/S3 definitions and package exist, but no AWS stack has been created |
| Exactly-once external effect | Not guaranteed | The database claim is idempotent; an external provider call and acknowledgement are not yet coordinated |
| Production security and resilience | Not implemented | No workload identity, secret rotation, tenant RLS, multi-region test, or worker-crash reconciliation evidence |

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
- Passing migration and live-DB smoke pull-request workflow:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30257673569>
- GitHub Actions workflow:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/workflows/ci.yml>
- Public proof console:
  <https://continuum-memory-firewall.ant713800.chatgpt.site>
- Devpost draft: <https://devpost.com/software/continuum-memory-firewall>

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

The shortest path to competition evidence is now operational rather than a new
feature:

1. **Confirm account economics and identity:** capture the actual CockroachDB
   credit/free allowance, configure AWS SSO/MFA, and verify the intended AWS
   billing account.
2. **Create and migrate the disposable database:** create CockroachDB Basic,
   run the versioned migrator and synthetic DB smoke, and retain only the
   reviewer evidence row if needed.
3. **Create the Managed MCP identity and deploy AWS:** store its key directly in
   AWS Secrets Manager, then run one successful
   `list_databases` invocation and one denied `insert_rows` invocation. Retain
   only redacted, non-secret evidence.

The exact commands and stop conditions are in
[CLOUD_DEPLOYMENT_RUNBOOK.md](CLOUD_DEPLOYMENT_RUNBOOK.md).

## Remaining blockers

- Organizer eligibility attestations beyond the confirmed Devpost registration
  remain participant-owned.
- Cloud credentials, account-specific credit verification, and participant
  approval are required before the prepared deployment can be executed.
- The challenge requires at least two qualifying CockroachDB tools and one AWS
  service. The repository proves Distributed Vector Indexing locally and
  prepares `ccloud`, Managed MCP, and AWS paths, but live use evidence is still
  required.
- The Devpost submission still needs a cloud-backed demo, architecture diagram,
  short public video, and final narrative. See
  [DEVPOST_CHECKLIST.md](DEVPOST_CHECKLIST.md).
- The versioned migration and real-engine smoke paths are implemented, but have
  not yet been executed against the participant's CockroachDB Cloud cluster.
