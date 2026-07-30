# Live AWS and CockroachDB Managed MCP evidence — 2026-07-31

This is the redacted, non-secret evidence record for the participant-owned
deployment. It intentionally omits AWS account IDs, ARNs, CockroachDB cluster
and service-account IDs, API keys, SQL credentials, cookies, and request IDs.

## Tested lineage

- Repository source before the concurrency compatibility change:
  `e343e5457bd548e7c006c7447030bd8fa2b0c73a`
- Lambda ZIP SHA-256:
  `EDD0D7EB3E04D31DC8C21313B97884198DAE28C9D32BB147BCEE9F3423C19835`
- Region: AWS Singapore (`ap-southeast-1`)
- Test date: 2026-07-31

The concurrency template change recorded with this evidence was deployed from
the same working-tree bytes before they were committed. Application code in the
Lambda ZIP was unchanged by that template-only correction.

## CockroachDB Cloud

- `continuum-ai` is a Basic cluster hosted on AWS Singapore.
- The dedicated `continuum-aws-managed-mcp` service account retains its default
  Organization Member role and has the minimum documented `Cluster Operator`
  role scoped only to `continuum-ai`.
- Direct Managed MCP protocol initialization returned HTTP 200 using protocol
  `2025-11-25`.
- `tools/list` advertised 12 tools and included `list_databases`.
- A direct `list_databases` call succeeded after the cluster-scoped role was
  assigned.

The initial authenticated tool call returned `unauthorized` while the service
account had only its default Organization Member role. That result was useful:
it proved authentication and MCP transport separately from cluster
authorization. No broader Organization or Cluster Admin role was added.

## AWS controls

- Budget stack: `continuum-hackathon-budget`, `CREATE_COMPLETE`.
- Monthly budget: USD 5, with one subscriber at forecasted 80% and actual 100%.
- Worker stack: `continuum-hackathon`, `CREATE_COMPLETE`.
- Lambda: `continuum-hackathon-managed-mcp-worker`, Active, Python 3.12,
  256 MiB, 30-second timeout, direct invocation only.
- The new AWS account has an account concurrency quota of 10. Because AWS
  requires at least 10 unreserved executions, the template omits a per-function
  reservation at this quota and still accepts `1` when a future quota can retain
  the minimum unreserved pool.
- Lambda has no Function URL and no API Gateway, VPC, or NAT Gateway.
- The generated role can read exactly one Secrets Manager secret and can write
  only to its CloudWatch log stream.
- The log group retains events for seven days.
- The private S3 deployment object uses server-side AES256 encryption, matches
  the local ZIP SHA-256, blocks public access, and expires under the `lambda/`
  prefix after seven days.
- The Managed MCP API key is stored as JSON under the secret name
  `continuum/cockroach/managed-mcp-api-key`; rotation is currently disabled.

AWS Budgets is an alert, not a spending hard stop. Secrets Manager and retained
AWS resources can still incur charges until teardown.

## Live Lambda smoke

| Invocation | AWS invoke | Worker result | Evidence |
|---|---:|---:|---|
| `list_databases` | HTTP 200, no FunctionError | `ok: true` | `continuum` database observed |
| `list_tables` with `database=continuum` | HTTP 200, no FunctionError | `ok: true` | response was `{"rows":[]}` |
| `insert_rows` | HTTP 200, no FunctionError | `ok: false`, `INVALID_REQUEST` | rejected by the local allowlist before secret resolution |

Every response contained an AWS request ID. IDs and provider response payloads
were not copied into this document.

## Repository and deployment validation

- 54 local tests passed; 10 live-SQL integration tests were skipped because no
  participant-cluster SQL URL was placed in the environment.
- The CloudFormation template passed local JSON parsing and AWS
  `validate-template`.
- The deployed worker template is structurally equal to
  `infra/aws/template.json`.
- The active Lambda `CodeSha256` equals the local package SHA-256.
- Both deployment shell scripts passed Git Bash syntax validation.
- `git diff --check` passed, and the repository secret-pattern scan found no
  credential-shaped value.

## What this does not prove

- No participant-cluster SQL password was transferred to the repository or
  shell history.
- The eight application migrations and live vector smoke have not run on this
  cluster; the empty `list_tables` response confirms that gap.
- The private Lambda is operational evidence, not an authenticated public
  application or tenant authorization boundary.
- A temporary workstation `/32` SQL network rule remains pending the migration
  smoke and must then be removed.
- API-key rotation, final teardown, public demo video, and Devpost submission
  remain explicit follow-up gates.
