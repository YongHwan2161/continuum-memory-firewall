# 10k/50k CockroachDB vector-scale live evidence

## Outcome

PASS on the participant CockroachDB cluster. Workflow run
[30735058404](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30735058404)
executed the synthetic benchmark from exact trusted head
`7900248121188284c1a9e7cdc57aa40bdd9c337e`, uploaded the raw report, and
removed the one-command Secrets Manager permission.

Raw report SHA-256:
`f8847c7d08518642240566c26d7a90f4ce216a17bd61cc970d1fe3f903bf25c5`.
The byte-identical public copy is
[`public-demo/evidence/vector-scale.json`](../../public-demo/evidence/vector-scale.json).

## Claim boundary

- The table contains only deterministic, non-sensitive, 512-dimensional
  synthetic vectors. No application memory row was read or written.
- Each scale contains 90% allowed-scope rows and 10% foreign-scope rows.
- Sixteen stable allowed-scope query vectors are compared with exact
  primary-index results at each scale.
- “First pass” includes a fresh SQL connection. It does not claim a physical
  CockroachDB Cloud cache flush. “Warm” is the immediate repeat on that same
  connection.

## Measured result

| Rows | Beam | Recall@1 | Recall@5 | Recall@10 | Fresh p50/p95 ms | Warm p50/p95 ms |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10,000 | 1 | 0.9375 | 0.2250 | 0.1250 | 59.105 / 71.003 | 10.779 / 13.729 |
| 10,000 | 32 | 1.0000 | 0.5625 | 0.5250 | 92.019 / 131.282 | 36.979 / 47.514 |
| 10,000 | 128 | 1.0000 | 0.9750 | 0.9750 | 108.735 / 145.285 | 61.031 / 90.639 |
| 10,000 | 512 | 1.0000 | 0.9750 | 0.9750 | 109.009 / 122.070 | 58.362 / 89.584 |
| 50,000 | 1 | 0.4375 | 0.1000 | 0.0500 | 59.180 / 72.415 | 11.269 / 14.662 |
| 50,000 | 32 | 0.9375 | 0.3250 | 0.2375 | 95.527 / 107.452 | 37.640 / 54.841 |
| 50,000 | 128 | 1.0000 | 0.5500 | 0.5000 | 138.061 / 159.365 | 86.424 / 114.621 |
| 50,000 | 512 | 1.0000 | 0.9750 | 0.96875 | 282.020 / 393.963 | 216.445 / 314.273 |

The exact 50k primary-index ground-truth scan measured p50/p95
`1168.187/1362.044 ms`. The natural ANN plan therefore reduced warm p95 to
`314.273 ms` at beam 512 while retaining Recall@10 `0.96875`; beam 32 reduced
warm p95 to `54.841 ms` but Recall@10 fell to `0.2375`. This is the intended
accuracy/latency curve, not a single cherry-picked setting.

## Plan and isolation gates

At both scales and all four beams:

- `SHOW INDEXES` reported the exact prefix/vector contract
  `(tenant_id, incident_id, embedding_model, embedding)`;
- the natural redacted plan rendered
  `continuum_vector_benchmark_embedding_idx` and reported vector search;
- no full-scan signal was present; and
- cross-scope leaked rows were exactly zero, including 5,000 retained foreign
  rows at the 50k scale.

## Retained failure history

- Run `30732642417` exposed an incomplete plan-name detector.
- Run `30733150995` proved the original three-column prefix caused natural full
  scans because `embedding_model` was filtered but absent from the vector-index
  prefix.
- Run `30734506267` proved the corrected four-column vector plan at both scales,
  but held because the first gate incorrectly demanded Recall@10 >= 0.75 from
  every low-cost beam.

Those failures produced PRs #25, #26, and #30. The final gate requires the
complete four-point trade-off, vector search and zero leakage at every beam,
and Recall@10 >= 0.75 only at the highest beam.
