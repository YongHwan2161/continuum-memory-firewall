# OIDC, Titan, RLS, and remote MCP live evidence — 2026-08-01

This redacted record binds the security and semantic claims to exact GitHub and
AWS executions. It contains no SQL password, JWT, client secret, database URL,
AWS account identifier, service-account secret, cookie, or session material.

## Exact-head evidence boundary

- Deployed source: `a108fce249466aaf56e1112eef3e49df3090d5ea`.
- Live AWS/DB/MCP run:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30695164483>.
- Exact-head CI runs:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30695165845>
  and <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30695164485>.
- Dedicated deployer identity proof:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30695164473>.

All four runs completed successfully against the same commit. The deployment
run removed its one-command migration policy and independently reported
`migration_capability_absent=true` before succeeding.

## Caller identity and database enforcement

The public MCP no longer accepts the legacy static bearer. Cognito issues a
client-credentials token whose observed lifetime is 300 seconds. The server
verifies the RS256 signature through Cognito JWKS and checks issuer, audience,
required scope, and maximum lifetime. A server-owned caller registry maps the
verified client identity to a tenant/incident scope and deterministic
`NOBYPASSRLS` SQL login; scope identifiers are not accepted as MCP tool input.

Migration version 11 enables and forces CockroachDB row-level security on:

- `canonical_memories`;
- `incidents`;
- `retrieval_audit`.

The live cutover reported that all visible rows in all three tables matched the
caller scope, the forbidden memory was invisible, and the deterministic scope
identity was reused rather than recreated. The negative checks proved that the
runtime could neither disable row security nor update canonical memory. The
temporary role-creation options used for the one-time cutover were revoked;
the final CockroachDB console result for `continuum_migrator` was `options=[]`.

## Semantic retrieval result

Bedrock Titan Text Embeddings v2 ran in `ap-northeast-2`, while the fixed-egress
host and CockroachDB cluster remained in `ap-southeast-1`. This split was
required because the selected Titan v2 model was not available in the host
region. The instance role is limited to the exact Titan v2 model ARN in Seoul.

| Metric | Live result |
|---|---:|
| Model | `amazon.titan-embed-text-v2:0` |
| Dimensions | 512 |
| Evaluation queries | 4 |
| K | 3 |
| Recall@3, each query | 1.0 |
| Mean Recall@3 | 1.0 |
| Cross-scope leaked documents | 0 |
| Cross-scope leakage rate | 0.0 |

The corpus intentionally covers migration integrity, memory poisoning,
cost control, and idempotent-worker recovery. This is a bounded synthetic
competition evaluation, not a claim of broad production relevance quality.

## Remote MCP result

| Check | Result |
|---|---:|
| `GET /healthz` | `200` |
| unauthenticated `POST /mcp` | `401` |
| observed token lifetime | 300 seconds |
| MCP protocol | `2025-11-25` |
| advertised tools | exactly `search`, `fetch` |
| semantic search hits | 2 |
| allowed fetch | PASS |
| direct cross-scope fetch | denied |

The test executed from the fixed-egress AWS host. CockroachDB networking
retained exactly one SQL rule, `47.131.98.12/32`, and no broad or workstation
rule. The application database URL uses CockroachDB's pinned private CA with
`sslmode=verify-full`.

## AWS authority and cost boundary

GitHub Actions assumed `continuum-hackathon-deployer` with a repository and
branch subject using immutable numeric GitHub identifiers. The session maximum
is one hour. Explicit denies block modification of the deployer role and the
bootstrap stack. The AWS Root console session was logged out before these
exact-head executions.

The account budget was raised to USD 10 with forecast-at-80% and
actual-at-100% email notifications. The budget is an alert, not a hard service
stop. The live host remains one SSM-managed `t3.micro` instance with no SSH and
one Elastic IP; it must remain only through judging and then be deleted with
the guarded teardown procedure.

## Remaining acceptance gates

- Rotate the long-lived Managed MCP API key, prove both read tools using the new
  version, and revoke the old CockroachDB key.
- Capture secret-free screenshots and a public video under three minutes.
- Complete participant-owned eligibility and organizer attestations and retain
  the Devpost submission receipt.
- After judging, run `scripts/teardown_after_judging.sh --after-judging --apply`
  through the dedicated deployer identity and retain the stack/EIP deletion
  receipt.

