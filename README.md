# Continuum Memory Firewall

Continuum Memory Firewall is a reference implementation for durable, auditable
memory promotion in long-running AI agents. It separates untrusted candidate
memories from canonical memory and makes every promotion decision explicit,
deterministic, and transactionally durable.

The current milestone is **P2B: authenticated managed-cloud competition
slice**. In addition to the transactional promotion and retrieval boundary, a
private, cost-bounded AWS Lambda client for CockroachDB Cloud Managed MCP and a
public TLS repository MCP service are deployed. Live smoke tests proved two
Managed MCP read tools, a pre-secret write-tool denial, all eleven
participant-cluster migrations, deterministic per-scope RLS-confined SQL
roles, fixed AWS SQL egress, five-minute Cognito caller tokens, Bedrock Titan
embeddings, and an authenticated cross-scope vector flow. The four-query live
evaluation measured Recall@3 = 1.0 with zero cross-scope leakage; it remains a
bounded competition result rather than a broad production-quality claim.

For the authoritative project state and evidence, see
[Project Status](docs/PROJECT_STATUS.md). For implementation order and exit
criteria, see [Roadmap](docs/ROADMAP.md).

## Why this exists

Long-running agents receive observations from tools, users, and other agents.
Writing every observation directly into durable memory creates three coupled
risks:

- poisoned or out-of-scope data can become authoritative;
- retries can create duplicate state or duplicate actions;
- later reviewers cannot reconstruct why a memory was accepted or rejected.

Continuum addresses those risks with a staged authority model:

```text
untrusted input
    -> candidate memory
    -> deterministic policy decision
    -> CockroachDB promotion transaction
    -> canonical memory + audit event
    -> scoped vector retrieval + retrieval audit
    -> read-only MCP search/fetch
    -> idempotent action claim
```

The policy code decides what may be promoted. CockroachDB is the durable source
of truth for whether the promotion and action claim committed.

## Repository map

- `src/continuum/memory.py` — deterministic candidate policy kernel
- `src/continuum/store.py` — CockroachDB transaction and retry boundary
- `src/continuum/retrieval.py` — embedding persistence, scoped vector search, and retrieval audit
- `src/continuum/mcp_server.py` — read-only standard MCP `search`/`fetch` surface
- `src/continuum/aws_mcp_worker.py` — private read-only Managed MCP Lambda client
- `src/continuum/migrations/` — versioned durable schema SSOT
- `src/continuum/migrate.py` — checksum, lease, retry, adoption, and validation runner
- `src/continuum/db_smoke.py` — synthetic live-database promotion/retrieval smoke path
- `infra/aws/` — cost-bounded CloudFormation and Lambda dependency manifest
- `scripts/` — dry-by-default CockroachDB/AWS preflight, packaging, and deployment
- `tests/` — policy, retry, promotion, replay, retrieval, MCP, and concurrency tests
- `docs/` — SSOT documents for status, roadmap, architecture, submission, and cost

The complete documentation ownership map is in
[docs/README.md](docs/README.md).

## Local verification

Run the dependency-free unit tests:

```bash
make test
```

Run the CockroachDB integration tests with an available PostgreSQL-compatible
connection and the optional driver installed:

```bash
python -m pip install "psycopg[binary]>=3.2,<4"
export CONTINUUM_DATABASE_URL='postgresql://...'
make integration
```

Apply the versioned schema and run a synthetic smoke test:

```bash
export CONTINUUM_DATABASE_URL='postgresql://...?...&sslmode=verify-full'
make migrate
make db-smoke
```

Validate the MCP protocol contract:

```bash
python -m pip install -e ".[mcp]"
make mcp-test
```

Build and verify the Linux/Python 3.12 Lambda package without deploying:

```bash
make cloud-package
```

Run the tool-only MCP server at `/mcp` after applying the migrations and seeding
accepted memory. The following legacy bearer configuration is retained for
local compatibility tests; the live AWS deployment uses Cognito OIDC and a
server-owned caller registry:

```bash
export CONTINUUM_DATABASE_URL='postgresql://...?...&sslmode=verify-full'
export CONTINUUM_TENANT_ID='00000000-0000-0000-0000-000000000000'
export CONTINUUM_INCIDENT_ID='00000000-0000-0000-0000-000000000000'
export CONTINUUM_MCP_BEARER_TOKEN='generate-at-least-32-random-characters'
export CONTINUUM_PUBLIC_BASE_URL='https://your-public-memory-view.example/'
continuum-mcp
```

The GitHub Actions workflow starts an ephemeral CockroachDB node and runs the
unit, MCP-contract, and database-integration suites. This verification path does
not require a paid cloud account. Deterministic hashing embeddings keep CI
repeatable; the participant deployment separately evaluates Bedrock Titan Text
Embeddings v2 against a versioned semantic dataset.

## Public proof console

The logged-out browser proof console is available at:

<https://yonghwan2161.github.io/continuum-memory-firewall/>

It is an interactive simulation of the policy and replay semantics for review
and presentation. It is **not** evidence of a live CockroachDB Cloud connection.
The executable database evidence is the integration test suite and CI run
linked from [Project Status](docs/PROJECT_STATUS.md). The original Sites
deployment remains an access-gated backup because this workspace does not allow
internet-public Sites access.

The redacted private-worker deployment proof is recorded in
[Live AWS and Managed MCP evidence](docs/evidence/2026-07-31-cloud-live-smoke.md).
The redacted participant-cluster migration and vector proof is recorded in
[Live CockroachDB SQL and vector evidence](docs/evidence/2026-08-01-live-sql-vector-smoke.md).
The least-privilege SQL, fixed-egress, authenticated HTTPS, and remote
cross-scope proof is recorded in
[Authenticated remote MCP evidence](docs/evidence/2026-08-01-authenticated-remote-mcp-smoke.md).
The exact-head Cognito, Titan, RLS, and cross-scope evaluation is recorded in
[OIDC, Titan, and RLS live evidence](docs/evidence/2026-08-01-oidc-titan-rls-live-smoke.md).

## Safety boundary

Use synthetic data and disposable infrastructure. Do not commit database URLs,
tokens, or credentials, and do not connect the current pre-production code to
production remediation systems.

## Documentation

- [Project Status](docs/PROJECT_STATUS.md) — current capability and evidence SSOT
- [Roadmap](docs/ROADMAP.md) — implementation priority and acceptance gates SSOT
- [Architecture](docs/ARCHITECTURE.md) — trust boundaries and component ownership
- [Transaction Model](docs/TRANSACTION_MODEL.md) — transaction and retry semantics
- [Database Migrations](docs/MIGRATIONS.md) — ordered DDL, drift, lease, adoption, and recovery contract
- [MCP Contract](docs/MCP_CONTRACT.md) — tool schema, scope, transport, and deployment boundary
- [Evaluation](docs/EVALUATION.md) — 60-query adversarial suite, metric definitions, and live gate
- [Devpost Checklist](docs/DEVPOST_CHECKLIST.md) — submission readiness SSOT
- [Cost Safety](docs/COST_SAFETY.md) — spending assumptions and guardrails
- [Cloud Deployment Runbook](docs/CLOUD_DEPLOYMENT_RUNBOOK.md) — participant-owned setup, guarded deployment, proof, and teardown
- [Prior Work](docs/PRIOR_WORK.md) — project provenance and new-work boundary

## License

Apache-2.0. See [LICENSE](LICENSE).
