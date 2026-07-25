# Continuum Memory Firewall

Continuum Memory Firewall is a reference implementation for durable, auditable
memory promotion in long-running AI agents. It separates untrusted candidate
memories from canonical memory and makes every promotion decision explicit,
deterministic, and transactionally durable.

The current milestone is **P1: transactional authority**. The policy kernel,
CockroachDB-backed promotion transaction, idempotent replay, and concurrent
action-claim behavior are implemented and exercised in CI against a disposable
CockroachDB instance. A live CockroachDB Cloud deployment, Managed MCP
integration, vector retrieval, and external side-effect execution remain planned
work.

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
    -> idempotent action claim
```

The policy code decides what may be promoted. CockroachDB is the durable source
of truth for whether the promotion and action claim committed.

## Repository map

- `src/continuum/memory.py` — deterministic candidate policy kernel
- `src/continuum/store.py` — CockroachDB transaction and retry boundary
- `db/schema.sql` — durable authority, audit, action, and retrieval schema
- `tests/` — policy, retry, promotion, replay, and concurrency tests
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

The GitHub Actions workflow starts an ephemeral CockroachDB node and runs both
test suites. The integration path does not require a paid cloud account.

## Public proof console

The browser proof console is available at:

<https://continuum-memory-firewall.ant713800.chatgpt.site>

It is an interactive simulation of the policy and replay semantics for review
and presentation. It is **not** evidence of a live CockroachDB Cloud connection.
The executable database evidence is the integration test suite and CI run linked
from [Project Status](docs/PROJECT_STATUS.md).

## Safety boundary

Use synthetic data and disposable infrastructure. Do not commit database URLs,
tokens, or credentials, and do not connect the current pre-production code to
production remediation systems.

## Documentation

- [Project Status](docs/PROJECT_STATUS.md) — current capability and evidence SSOT
- [Roadmap](docs/ROADMAP.md) — implementation priority and acceptance gates SSOT
- [Architecture](docs/ARCHITECTURE.md) — trust boundaries and component ownership
- [Transaction Model](docs/TRANSACTION_MODEL.md) — transaction and retry semantics
- [Devpost Checklist](docs/DEVPOST_CHECKLIST.md) — submission readiness SSOT
- [Cost Safety](docs/COST_SAFETY.md) — spending assumptions and guardrails
- [Prior Work](docs/PRIOR_WORK.md) — project provenance and new-work boundary

## License

Apache-2.0. See [LICENSE](LICENSE).
