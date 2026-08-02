# Representative-scale vector benchmark

This benchmark is a competition evidence lane, not application data. It owns
only `continuum_vector_benchmark`, fills it with deterministic non-sensitive
512-dimensional vectors, and leaves the 50k-row final corpus available through
judging. It does not read or write `canonical_memories`.

The same equality-prefix contract used by application retrieval is exercised:

```sql
WHERE tenant_id = $1 AND incident_id = $2 AND embedding_model = $3
ORDER BY embedding <=> $4::VECTOR
LIMIT 10
```

`embedding_model` is deliberately the third prefix column. CockroachDB vector
acceleration supports filters that match vector-index prefixes; leaving this
equality filter outside the prefix caused the first two honest 10k/50k runs to
choose a primary full scan. The benchmark and application index now express
the complete retrieval predicate in the index contract.

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
- `SHOW INDEXES` verifies the expected visible prefix/vector contract and the
  natural redacted plan reports a vector-search operator without a full scan at
  every beam (CockroachDB does not always render the index name in this plan);
- Recall@10 is at least 0.75 at every scale and beam; and
- no foreign-scope row is returned.
