# Audited control plane, 60-query retrieval, and pooling live evidence

**Evidence date:** 2026-08-02 KST  
**Deployment head:** `972d003915051147ac4ed1d3b7b8fd204ffe88dd`  
**Live workflow:** [run 30708752765, attempt 2](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30708752765/attempts/2)

## Result

The exact deployment head completed the fixed-egress migration, Amazon Titan
evaluation, authenticated remote MCP smoke, and migration-capability cleanup.
GitHub CI and the dedicated AWS identity proof also passed for the same head.

The first workflow attempt is retained as fail-closed history. It ran after a
prior failed bootstrap had already removed the temporary SQL role options, so
`continuum_migrator` could not create the control-plane roles. The participant
granted `CREATEROLE CREATELOGIN` once through the Cockroach SQL Shell, then
attempt 2 completed and the application removed both options in its `finally`
guard.

## Tenant authority and database isolation

- migration version: `15`
- tenant control plane active: `true`
- binding event/version: `bound` / `1`
- control-plane canonical-memory read denied: `true`
- bootstrap options revoked by the cutover: `true`
- every visible canonical-memory, incident, and retrieval-audit row matched the
  resolved tenant and incident
- direct `row_security=off` and canonical-memory update attempts were denied
- forbidden memory visible: `false`
- post-run SQL Shell check: both `continuum_control_plane` and
  `continuum_migrator` reported `options = []`

This is the implemented authority chain:

`verified Cognito caller -> active versioned DB binding -> recomputed scope SQL role -> matching URL login -> same-scope RLS`

## Semantic retrieval

The live suite used `amazon.titan-embed-text-v2:0/512` over 60 queries: ten each
for paraphrase, terse, typo, negation, misleading-scope, and multi-intent.

| Metric | Result |
|---|---:|
| Recall@1 | 0.8667 |
| Recall@3 | 0.9833 |
| Recall@5 | 1.0000 |
| Cross-scope leaked documents | 0 |
| Leakage rate | 0.0 |
| p50 end-to-end latency | 250.306 ms |
| p95 end-to-end latency | 282.870 ms |
| Maximum latency | 293.519 ms |

The single Recall@3 miss was the `q08-negation` variant; its expected memory
appeared by rank 5. This points to negation handling as a quality opportunity,
not an authorization failure: no foreign-scope memory was returned.

## Pool and query-plan evidence

The deployed health endpoint reports `database_connections = bounded-pools-1-4`
and `authorization_mode = audited-tenant-control-plane`. The process owns a
separate lazy min-1/max-4 pool for the control-plane identity and each scope SQL
identity; metrics never include connection URLs or passwords.

The runtime scope identity executed read-only `SHOW INDEXES` and
`EXPLAIN (REDACT)`. The result proved:

- expected visible index: `canonical_memories_embedding_idx`
- declared columns: `tenant_id`, `incident_id`, `embedding`
- prefix contract match: `true`
- full-scan signal: `false`
- redacted plan lines: `25`
- redacted plan SHA-256:
  `311ace71343e76919f09a1f5c485d52a24683d6d5c6220aaf42c939ae6dd0f04`
- optimizer selected the vector index: `false`

The last value is intentionally not rewritten as a performance claim. With only
20 evaluation documents, CockroachDB's cost-based optimizer did not naturally
select ANN. The index contract is valid, but representative-scale vectors and a
new natural-plan comparison are required before claiming index acceleration.

## Public judge and submission state

- [one-click read-only verifier](https://yonghwan2161.github.io/continuum-memory-firewall/verify.html)
  passed every gate after Pages run `30709120218`
- the Devpost connector returned project `1362701` as `published`
- the CockroachDB x AWS relationship remained `submitted`, with submission
  `1121568` recorded in the public evidence bundle
- the project video remained `https://youtu.be/raad44nJj5I`

The verifier uses public HTTP GET only. It never requests a Cognito token and
cannot write to MCP or CockroachDB.

## Managed MCP key lifecycle

[Rotation run 30709230016](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30709230016)
replaced the AWS Secrets Manager value with the staged v3 key, waited 310
seconds to exceed the Lambda cache bound, passed `list_databases` and
`list_tables`, and again denied `insert_rows` before secret use. The workflow's
failure trap would have restored the prior AWS secret. After success, the exact
v2 Cockroach provider key was deleted, the Console showed only v3, and the
temporary GitHub Actions secret was removed. No secret value entered source,
chat, or command output.
