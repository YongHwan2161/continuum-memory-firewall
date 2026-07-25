# Continuum Memory Firewall

Persistent memory that survives crashes, rejects poison, and prevents duplicate
actions.

Continuum is an evidence-first memory layer for long-running AI agents. The
initial demonstration is an autonomous incident responder that can lose a
worker, resume from the last accepted state, reject untrusted memories, and
prevent two workers from committing conflicting actions.

This repository is being developed for the
[CockroachDB × AWS Hackathon](https://cockroachdb-ai.devpost.com/).

## North star

An agent should be able to forget a worker without forgetting—or falsifying—its
past.

Most agent-memory systems optimize retrieval relevance. Continuum adds an
acceptance boundary between retrieved or generated memory and memory that is
allowed to influence future actions:

```text
observation -> candidate memory -> policy validation -> canonical memory -> action
                                      |
                                      +-> quarantine
```

CockroachDB is the system of record for incident state, candidate and canonical
memory, embeddings, action history, and rejection evidence. A small,
deterministic policy kernel decides whether a candidate may become canonical.
The model proposes; it does not grant trust.

## Competition-aligned architecture

- **CockroachDB Cloud Basic**
  - transactional incident and task state
  - distributed vector index for similar incidents and runbooks
  - Managed MCP Server for bounded agent reads and candidate writes
- **AWS**
  - Lambda for disposable responder workers
  - Bedrock for analysis and embedding generation
  - CloudWatch and EventBridge for synthetic incident triggers
  - S3 for raw artifacts and postmortems
- **Continuum policy kernel**
  - tenant and incident scope checks
  - expected-parent validation
  - expiry and provenance checks
  - approval gates for destructive actions
  - deterministic acceptance and rejection codes

The cost-safe reference path avoids EKS, NAT Gateway, provisioned model
throughput, and paid CockroachDB tiers.

## Current milestone: P1 transactional authority

Implemented:

- deterministic candidate evaluation
- explicit rejection codes
- canonical event hashing
- stale-parent, cross-tenant, expiry, provenance, and approval policies
- CockroachDB schema with relational and vector memory
- SERIALIZABLE candidate promotion with SQLSTATE `40001` retries
- idempotent candidate replay and one-canonical-row enforcement
- transactional duplicate action-claim prevention
- optional live CockroachDB integration tests
- CI and local unit tests
- prior-work and cost-safety disclosures

Not yet claimed:

- a live CockroachDB Cloud connection
- a live AWS deployment
- cryptographic signatures
- multi-region failure tolerance
- measured poisoning-defense or retrieval results

## Quick start

Requires Python 3.11 or newer.

```bash
make test
```

No cloud account, API key, or paid service is required for the policy and retry
tests.

To verify the transaction path against a disposable CockroachDB cluster:

```bash
python -m pip install -e '.[cockroach]'
export CONTINUUM_DATABASE_URL='postgresql://...'
make integration
```

Do not commit the database URL. It commonly contains credentials.

## Repository map

```text
src/continuum/          deterministic policy kernel
tests/                  executable invariants
db/schema.sql           CockroachDB schema draft
docs/ARCHITECTURE.md    trust and authority boundaries
docs/TRANSACTION_MODEL.md durable promotion and action-claim semantics
docs/COST_SAFETY.md     zero-to-low-cost deployment constraints
docs/PRIOR_WORK.md      pre-existing work disclosure
docs/DEVPOST_CHECKLIST.md submission requirements and evidence
```

## Planned three-minute proof

1. A synthetic service emits an incident.
2. A responder retrieves trusted prior incidents and runbooks.
3. The active worker is terminated; a replacement resumes without repeating an
   accepted action.
4. A highly relevant but untrusted memory is injected and quarantined.
5. Two workers propose conflicting actions; only one canonical transition is
   accepted.
6. The evidence timeline shows what the agent remembered, rejected, and acted
   on.

## Security position

Persistent memory is an attack surface. Similarity is not authority, database
presence is not provenance, and model confidence is not evidence. Continuum
keeps candidate memory separate from canonical memory and requires explicit
policy validation before a memory can affect future actions.

Do not connect the current P0 code to production infrastructure. Destructive
remediation will remain sandboxed and human-approved throughout the hackathon.

## License

Apache-2.0. See [LICENSE](LICENSE).
