# Live CockroachDB SQL and vector evidence — 2026-08-01

This is the redacted, non-secret evidence record for the participant-owned
CockroachDB Basic cluster. It intentionally omits the cluster ID, host, SQL URL,
SQL password, workstation IP, cookies, and provider request identifiers.

This record captures the earlier cleanup smoke. It is superseded for current
network and retained-demo state by
[2026-08-01-authenticated-remote-mcp-smoke.md](2026-08-01-authenticated-remote-mcp-smoke.md):
the later deployment retains two synthetic scopes and one AWS Elastic IP `/32`
for the authenticated remote service.

## Credential and TLS handling

- The participant regenerated the dedicated SQL user's password in the
  CockroachDB Cloud console and copied it once.
- One local PowerShell process read the password from the system clipboard and
  cleared the clipboard before opening the database connection.
- That process URL-encoded the password, assembled the SQL URL in memory, and
  exposed it only as a process-scoped `CONTINUUM_DATABASE_URL` to the smoke-test
  child process.
- A CockroachDB CA certificate was installed in the operating system's
  PostgreSQL trust location outside the repository, and the connection used
  `sslmode=verify-full`.
- A `finally` cleanup removed the process environment variable and released the
  password, encoded password, and URL variables. The password and SQL URL were
  not printed, placed in shell history, written to a file, or committed.
- The system clipboard was empty at the end of the run.

## Live execution result

The repository's production smoke entry point, `python -m continuum.db_smoke`,
ran against the participant cluster and returned success:

| Check | Result |
|---|---:|
| Overall live smoke | PASS |
| Current migration version | 8 |
| Newly applied migrations | 8 |
| Existing-schema adoption | `false` |
| Promotion transaction | PASS |
| Deterministic embedding persisted | PASS (`VECTOR(512)`) |
| Tenant-and-incident-scoped vector retrieval | PASS |
| Retrieval audit | PASS |
| Fetch by evidence ID | PASS |
| Expected evidence IDs present | PASS |
| Synthetic rows retained | `false` |

The run took approximately 74 seconds. Because `retained` was `false`, the
smoke path removed only the randomly generated candidate, canonical, action,
embedding, and retrieval-audit rows after verification. The versioned schema
and migration history remain as the intended durable result.

## Network cleanup

Before the run, the IP allowlist contained exactly one named temporary
workstation `/32` rule and no broad `0.0.0.0/0` rule. After the successful smoke,
that exact temporary rule was deleted in the CockroachDB Cloud console. The
console then showed `0 / 200 entries`.

No post-deletion SQL denial was attempted because the one-time credential had
already been cleared. The verified claim is therefore that the console
allowlist is empty, not that a second connection attempt was observed failing.

## Boundary of this evidence

This proves the packaged schema, promotion, deterministic vector persistence,
scoped retrieval, audit, fetch, and cleanup path on the participant cluster. It
does not prove a public authenticated application or MCP endpoint, a production
semantic embedding model, row-level database authorization, or external-effect
delivery and reconciliation.

The earlier pre-migration Managed MCP snapshot remains recorded in
[2026-07-31-cloud-live-smoke.md](2026-07-31-cloud-live-smoke.md). Its empty-table
result is historical evidence of the state before these eight migrations.
