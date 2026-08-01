# Authenticated remote MCP and least-privilege SQL evidence — 2026-08-01

This is the redacted evidence record for the repository MCP deployment. It
omits SQL passwords, bearer tokens, database URLs, AWS account identifiers,
secret values, cookies, and provider session material.

## Reviewed starting point

- Pull request 11 was reviewed after its exact-head unit, package, syntax, and
  secret-pattern checks passed.
- It was converted from draft and squash-merged as commit `afb6abe`.
- The new deployment work began from the updated `main`, rather than from the
  superseded draft head.

## SQL identity boundary

The live `continuum` database now separates migration and runtime authority:

| Identity | Effective authority | Negative evidence |
|---|---|---|
| `continuum_migrator_role` / `continuum_migrator` | owns the database, public schema, migration tables, and application tables; may replay versioned DDL | not used by the public service and stored in a separate offline secret |
| `continuum_runtime_role` / `continuum_runtime` | connect, schema usage, `SELECT` on incidents and canonical memory, and `INSERT` on retrieval audit | schema creation and canonical-memory update both returned SQLSTATE `42501` |

The first negative test found that revoking direct `CREATE` grants was
insufficient: CockroachDB's inherited `public` role still allowed the runtime
identity to create a table. The live correction revoked `CREATE` on both the
database and public schema from `public`, then granted it only to the migrator
role. The test table was removed, the migration replay stayed at version 8
with zero new migrations, and both runtime denial checks passed.

## Deployed AWS boundary

The authenticated service is live at:

<https://47-131-98-12.sslip.io/mcp>

Its public health endpoint is:

<https://47-131-98-12.sslip.io/healthz>

The deployment uses one `t3.micro` EC2 instance in Singapore with an Elastic
IP, encrypted `gp3` root storage, IMDSv2-required metadata, no SSH ingress, SSM
management, Nginx, and a valid Let's Encrypt certificate. The instance role can
read exactly one runtime secret and exactly one private S3 artifact object. The
offline migrator secret is not readable by the instance.

The package builder is deterministic. The deployment uploads the private
artifact, binds its SHA-256 to the CloudFormation stack and instance tag,
downloads through the exact-object IAM grant, verifies the full hash before
installation, and updates the existing host through SSM. The verified deployed
artifact SHA-256 was:

`3ece49e3652a48e902577106e58acacea9cfcedccc32f1d4282c31603648ace8`

## Public protocol and authorization result

Post-deployment checks returned:

| Check | Result |
|---|---:|
| TLS certificate verification | PASS |
| `GET /healthz` without credentials | `200` |
| `POST /mcp` without credentials | `401` |
| `POST /mcp` with a wrong bearer token | `401` |
| Authenticated MCP initialization | PASS, protocol `2025-11-25` |
| Advertised tools | exactly `search`, `fetch` |
| Allowed-scope vector search | one expected result |
| Denied-scope memory exposed by search | no |
| Allowed-scope fetch | PASS |
| Cross-scope direct fetch | denied |

The allowed and denied scopes used distinct tenant, incident, and memory IDs.
The authenticated search persisted retrieval evidence: before network cleanup,
the allowed scope had three audit rows, two containing accepted hits.

The deterministic demo embedder also exposed an important quality boundary. A
natural-language query (`continuum migration smoke`) fell below the default
similarity threshold, while the canonical synthetic payload query returned the
expected vector hit. This is not an authorization failure; it confirms that the
hashing embedder proves storage, scope, ranking, and audit mechanics but is not
a production semantic retrieval model.

## Fixed egress and cleanup

During role provisioning, CockroachDB temporarily allowed the operator
workstation `/32`. Before the final smoke, the AWS Elastic IP `/32` was added as
`continuum-mcp-aws-egress`. After the authenticated cross-scope smoke:

- the exact temporary workstation rule was deleted;
- the console showed `1 / 200 entries`, containing only
  `47.131.98.12/32`;
- a new workstation SQL connection attempt failed;
- the remote HTTPS MCP flow continued to pass through the retained AWS egress.

The process-local staging file that had held generated SQL passwords and the
bearer token was then deleted. Credentials were never printed, committed, or
placed in repository files. Runtime material remains only in AWS Secrets
Manager, and the migrator credential remains in its separate offline secret.

## Failure findings converted into controls

Three live failures produced durable fixes:

1. systemd initially required an environment file before `ExecStartPre` could
   create it; the unit now marks that file optional for the pre-start boundary;
2. FastMCP rejected the public proxy host with HTTP `421`; DNS-rebinding
   protection remains enabled and now allows only the configured HTTPS host and
   origin;
3. the first in-place install reused a stale setuptools build directory; the
   deployment now removes only that bounded build directory, uses a
   deterministic package, verifies its hash, and waits for service health after
   restart.

## Remaining non-claims

This proves a single-scenario, fixed-scope, bearer-authenticated competition
deployment. It does not prove production multi-tenant identity, short-lived
OAuth/JWT credentials, database row-level security, semantic retrieval quality,
connection-pool resilience, or exactly-once external effects. Those remain the
next product-hardening gates.
