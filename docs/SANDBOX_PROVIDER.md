# AWS sandbox provider

The sandbox is an actual provider boundary used to validate the transactional
outbox contract without changing a production service. `AwsLambdaSandboxProvider`
invokes one project-owned Lambda. The function records only the action payload
SHA-256, a deterministic receipt, and a one-day TTL in an encrypted DynamoDB
table; it never stores or performs the requested remediation.

Its capability manifest is:

```json
{
  "supports_idempotency": true,
  "receipt_lookup": true,
  "reconciliation_timeout_seconds": 30,
  "schema_version": 1
}
```

The same manifest is copied into the durable CockroachDB outbox row when a
proposal is enqueued. Reconciliation fails closed if a worker presents a
different manifest. After an `after_send` crash, the worker polls lookup until
the declared timeout. It may retry send after that timeout only because the
manifest guarantees an idempotent key; a lookup-only non-idempotent provider
instead becomes `AMBIGUOUS`.

The `aws-sandbox-provider-proof` workflow is restricted to the reviewed
`continuum-production` GitHub environment and `main`. It deploys the Lambda and
table, calls send twice with one key, looks up the receipt, and retains a
private evidence artifact proving two requests, one logical effect, and one
receipt. The retained stack is a low-volume hackathon sandbox, not a claim that
an arbitrary external provider implements the same guarantees.
