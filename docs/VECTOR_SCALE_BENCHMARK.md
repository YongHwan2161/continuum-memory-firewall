# Representative-scale vector benchmark

This benchmark is a competition evidence lane, not application data. It owns
only `continuum_vector_benchmark`, fills it with deterministic non-sensitive
512-dimensional vectors, and leaves the 50k-row final corpus available through
judging. It does not read or write `canonical_memories`.

The same equality-prefix contract used by application retrieval is exercised:

```sql
WHERE tenant_id = $1 AND incident_id = $2
ORDER BY embedding <=> $3::VECTOR
LIMIT 10
```

At 10k and 50k total rows, 10% of rows are placed in a foreign synthetic scope.
Sixteen stable target vectors are evaluated. For each query, a primary-index
scan supplies the exact top 10 and natural optimizer-selected ANN is evaluated
at beam sizes 1, 4, 16, and 32. The report includes Recall@1/5/10, zero-prefix-
leakage checks, exact latency, fresh-connection first-pass p50/p95, same-
connection immediate-repeat p50/p95, and a SHA-256 of each redacted plan.

The “first pass” is deliberately named rather than presented as a physical
server-cache flush: it includes a fresh SQL connection, while the immediate
repeat uses the same connection and vector. This makes the measured boundary
reproducible without claiming control over CockroachDB Cloud host caches.

Run the `aws-vector-scale-benchmark` workflow only from the reviewed OIDC-trusted
branch. It grants the fixed-egress host access to exactly one SQL secret, sends
the committed script through SSM, uploads the redacted JSON report, and revokes
the temporary IAM policy in an `always()` step.

The live gate fails unless:

- both 10k and 50k reports exist;
- CockroachDB naturally selects the prefixed vector index at every beam;
- Recall@10 is at least 0.75 at every scale and beam; and
- no foreign-scope row is returned.
