# Online CockroachDB memory-lineage live evidence

## Conclusion

The real provider → canonical CockroachDB memory → Titan/RLS retrieval →
durable proposal → later provider action → verified outcome → next canonical
memory chain is live-complete for one preregistered same-cause/near-neighbour
pair. The candidate evaluator crashed after both external actions. A separate
main-only reconciler completed the database side from the exact retained
artifact with **zero provider-action redispatch**.

This is an end-to-end architectural proof over two targets. It is not a new
population-level superiority estimate.

## Exact lineage

| Evidence                   | Value                                                                                    |
| -------------------------- | ---------------------------------------------------------------------------------------- |
| Candidate source           | `9fed05095f2283d919915387d02198bf4faa677f`                                               |
| Failed candidate run       | `31503686643`                                                                            |
| Failed candidate artifact  | `9106222400` / `sha256:845695021e3c67c6392aeab487427631a124c98089811fc32a01e31ca68866f8` |
| Provider action runs       | `31503922040`, `31503923725`                                                             |
| Reconciler source          | `9bfb9017e03b33b56fa0af942ed111b4362336d9`                                               |
| Successful recovery run    | `31506117708`                                                                            |
| Recovery artifact          | `9107135049` / `sha256:7d23ab01720c9fca14c1cfc4fabd9e3af16d6603ee7beafd63df316c5c158bf0` |
| Raw report receipt         | `dd249605d58884391cb5adca45f48f871593435381307624f73b5573b98e6929`                       |
| RLS combined checksum      | `69a168e1e55440bf563483947f5438855e93a715a56eb702f49a845d360b4e02`                       |
| Public projection checksum | `28e41475fc66cf43e5ef05b1cdaed9908f4aff8cf5618bca7f78566b02cd0f9d`                       |

## Measured result

| Target                   | Prior memory selected | Current diagnostic | Exact patch              | Provider outcome | Next promotion |
| ------------------------ | --------------------: | -----------------: | ------------------------ | ---------------- | -------------- |
| Same cause               |                     1 |                  0 | `set_python_312`         | succeeded        | yes            |
| Near-neighbour rejection |                     0 |                  1 | `normalize_package_root` | succeeded        | yes            |

Additional hard gates:

- source provider outcome canonical and Titan-indexed: PASS;
- durable proposal before both provider actions: PASS;
- retrieval audit IDs and complete database episode joins: PASS;
- expected non-bypass scope role: PASS;
- foreign-scope rows visible: 0;
- attempts to disable RLS or update canonical, candidate, or action rows: all
  denied;
- repository mutations and cleanup residuals across all six provider receipts:
  0;
- provider action reexecutions during recovery: 0.

## Fail-closed history

The result retains four failures rather than rewriting them as successes:

1. `31501325773` stopped before provider/DB/model work on a missing CA-path
   deployment contract.
2. `31501943324` stopped before proposals because the private host package
   omitted the runner.
3. `31503686643` completed proposals and external actions but failed before
   target DB finalization on an evaluator field-path bug.
4. `31505581790` validated the predecessor artifact but stopped before DB access
   because a same-step `GITHUB_ENV` value was unavailable.

Every path revoked temporary EC2 authority. The admitted recovery had
`actions: read` and no provider-dispatch implementation, so it could not turn
the evaluator retry into a duplicate external effect.

## Public boundary

The committed public projection deliberately excludes tenant ID, incident ID,
the SQL role name, secrets, and connection material. It retains hashed caller
and role identities, the RLS receipt, provider receipts, and the synthetic
memory/retrieval/proposal/outcome identifiers needed to audit the episode.

- Judge episode page:
  <https://yonghwan2161.github.io/continuum-memory-firewall/online-memory-lineage.html>
- Full read-only verifier:
  <https://yonghwan2161.github.io/continuum-memory-firewall/verify.html>
- Recovery workflow:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31506117708>

The public URLs become authoritative only after the reviewed source PR, Pages
deployment, immutable v21 release, and credential-free verifier all pass.

## Next fundamental P0

Move exact replay identity into CockroachDB. The current outcome replay path
returns an existing proposal outcome without first comparing the incoming
provider, receipt ID, status, and receipt digest. Add proposal-scoped
compare-and-set plus an append-only reconciliation journal so an exact replay
returns the same outcome, while any mismatched replay becomes a typed conflict
and cannot promote memory. The successful workflow validation should be
defence in depth, not the only owner of this invariant.
