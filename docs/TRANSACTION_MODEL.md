# Transaction model

This document is authoritative for promotion, replay, and retry semantics.
Current implementation state and future priorities live in
[PROJECT_STATUS.md](PROJECT_STATUS.md) and [ROADMAP.md](ROADMAP.md).

Continuum separates deterministic policy from durable authority.

## Candidate promotion

`CockroachMemoryStore.promote_candidate` runs one retryable SERIALIZABLE
transaction:

1. Lock the candidate and its incident.
2. Return the prior durable result if the candidate is already decided.
3. Evaluate the candidate with the incident's current canonical head.
4. Persist a stable rejection code, or compare-and-set the incident head.
5. Insert exactly one canonical memory for the source candidate.
6. Persist the accepted decision.

The transaction is retried in full when CockroachDB returns SQLSTATE `40001`.
The unique constraints on source candidate, event hash, and incident sequence
make replays fail closed rather than duplicate authority.

## Action claims

`claim_action` uses this durable idempotency key:

```text
(incident_id, expected_head, action_key)
```

Two workers racing for the same key can produce only one `action_attempts` row.
The winner receives `CLAIMED`; every other worker receives `DUPLICATE` and the
winner's durable attempt identifier.

This is **duplicate claim prevention**, not a claim of exactly-once external
effects. An external remediation API needs its own idempotency key or an outbox
and acknowledgement protocol to close the crash window between the external
effect and the database status update.

A production delivery path also needs a renewable worker lease, attempt count,
retry schedule with jitter, acknowledgement evidence, and reconciliation for an
ambiguous provider response. Those requirements are tracked in
[ROADMAP.md](ROADMAP.md).

## Failure semantics

- stale incident head: reject before an action is claimed
- cross-tenant access: reject inside the locked transaction
- SQLSTATE `40001`: retry the complete database-only transaction
- exhausted retry budget: fail closed and surface an operational error
- accepted candidate without a canonical row: raise an invariant violation

No model call or external side effect occurs inside a retryable transaction.

## Release transaction crash model

The release coordinator treats every provider write and every local receipt
advance as a separate crash boundary. Property-based tests permute all named
boundaries and require deterministic reconciliation, monotonic receipt state,
no second author signature, and `AMBIGUOUS` for conflicting identity or
attestation cardinality.

The disposable GitHub Release fault workflow complements the pure state model.
It creates an unsigned draft with a run-unique tag, loses the local
acknowledgement after provider create, asset upload, receipt upload, and delete,
then reconciles by stable provider identity. A duplicate asset upload must fail
without changing cardinality. The workflow succeeds only after the exact draft
and any tag reference are absent; it never publishes or requests an OIDC
attestation.
