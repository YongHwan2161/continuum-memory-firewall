# Continuum Memory Firewall

Continuum Memory Firewall is a reference implementation for durable, auditable
memory promotion in long-running AI agents. It separates untrusted candidate
memories from canonical memory and makes every promotion decision explicit,
deterministic, and transactionally durable.

**Live judge path:** [run the public product proof](https://yonghwan2161.github.io/continuum-memory-firewall/)
or [verify every bound receipt](https://yonghwan2161.github.io/continuum-memory-firewall/verify.html).
In the incident-response story, trusted telemetry becomes durable memory,
poisoned model output remains quarantined, a later agent retrieves the accepted
resolution, and CockroachDB grants exactly one action owner.

The current milestone is **P2B: authenticated managed-cloud competition
slice**. In addition to the transactional promotion and retrieval boundary, a
private, cost-bounded AWS Lambda client for CockroachDB Cloud Managed MCP and a
public TLS repository MCP service are deployed. Live smoke tests proved two
Managed MCP read tools, a pre-secret write-tool denial, all fifteen
participant-cluster migrations, audited caller-to-scope bindings, matching
RLS-confined SQL identities, bounded per-identity connection pools, fixed AWS
SQL egress, five-minute Cognito caller tokens, Bedrock Titan embeddings, and an
authenticated cross-scope vector flow across all seventeen migrations. The
60-query adversarial live evaluation
measured Recall@1 = 0.8667, Recall@3 = 0.9833, Recall@5 = 1.0, zero cross-scope
leakage, p50 = 248.149 ms, and p95 = 279.012 ms. A separate 10k/50k synthetic
benchmark proved natural CockroachDB vector-search plans with no full scan and
zero foreign rows. At 50k, beam 512 measured Recall@10 = 0.96875 with warm
p50/p95 = 216.445/314.273 ms, versus exact primary-scan p50/p95 =
1168.187/1362.044 ms. These remain bounded competition results rather than
broad production-quality claims.

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

The policy-replay interactions are simulations, while the live metric cards and
read-only verifier load exact public receipts for the participant deployment,
60-query Titan evaluation, and 10k/50k vector benchmark. The verifier never
receives a token or database credential. The executable database evidence is
the integration suite and linked exact-head workflows in
[Project Status](docs/PROJECT_STATUS.md).

The redacted private-worker deployment proof is recorded in
[Live AWS and Managed MCP evidence](docs/evidence/2026-07-31-cloud-live-smoke.md).
The redacted participant-cluster migration and vector proof is recorded in
[Live CockroachDB SQL and vector evidence](docs/evidence/2026-08-01-live-sql-vector-smoke.md).
The least-privilege SQL, fixed-egress, authenticated HTTPS, and remote
cross-scope proof is recorded in
[Authenticated remote MCP evidence](docs/evidence/2026-08-01-authenticated-remote-mcp-smoke.md).
The exact-head Cognito, Titan, RLS, and cross-scope evaluation is recorded in
[OIDC, Titan, and RLS live evidence](docs/evidence/2026-08-01-oidc-titan-rls-live-smoke.md).
The representative-scale vector plan, Recall, latency, and isolation proof is
recorded in
[10k/50k vector-scale live evidence](docs/evidence/2026-08-02-vector-scale-live.md).
The main-only OIDC cutover, actual AWS sandbox receipt proof, and
five-replication 540-observation ablation are recorded in
[Main OIDC, AWS sandbox, and five-replication evidence](docs/evidence/2026-08-07-main-oidc-sandbox-five-seed-ablation.md).
The outcome-first public video, English captions, and refreshed Devpost receipt
are recorded in
[Outcome-first video and Devpost v4 evidence](docs/evidence/2026-08-07-outcome-video-devpost-v4.md).

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
