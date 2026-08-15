# Preserved v33 attestation-index failure

`hackathon-v33` is an immutable failed delivery epoch. It is not retried,
backfilled, deleted, or promoted to PASS.

- Release target: `a98388350c95bf4cd1e549244c2e391b2b32a3fc`
- Release workflow run: `31861001817` (`failure`)
- Release: `hackathon-v33` (`immutable=true`, `draft=false`)
- Immutable assets: `37`
- Failure step: `Publish or adopt the immutable provider receipt`
- Provider response: attestation index returned HTTP `404` immediately after
  release publication

The release, assets, and author signature were created, but the workflow shell
used `set -e`. The first not-yet-materialized attestation-index lookup exited
the step before its bounded twelve-attempt reconciliation loop could continue.
No `IMMUTABLE` coordinator artifact or terminal Pages receipt was published for
this epoch.

The v34 successor preserves all proof gates and changes only the polling
boundary: a transient missing attestation index is represented as an empty
attestation set inside the existing bounded loop. Exact counts of two total,
one author, and one platform attestation remain hard terminal requirements.
