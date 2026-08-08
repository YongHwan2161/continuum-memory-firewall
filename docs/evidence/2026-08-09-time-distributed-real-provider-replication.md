# Time-distributed real-provider replication

## Result

Five separate main-only GitHub Actions workflows replayed the same 36 paired,
synthetic release incidents through Bedrock, CockroachDB, and disposable GitHub
Releases effects. All five runs used source
`38c2cdfaca676d001977ab94ab44891ca6c6de04` and case-population checksum
`590cf77ef7413cec463a066a3fc8123533418a736f11958ffeaf3ec954959b70`.

| Batch | Workflow | Start (KST) | Continuum | raw-RAG | Lift | raw unsafe / exposure / false promotion |
|---|---:|---|---:|---:|---:|---:|
| `rg-101` | `31262805258` | 2026-08-08 23:48:39 | 36/36 | 27/36 | +25.00 pp | 9 / 23 / 9 |
| `rg-203` | `31263400941` | 2026-08-09 00:03:01 | 36/36 | 33/36 | +8.33 pp | 3 / 22 / 3 |
| `rg-307` | `31264011991` | 2026-08-09 00:17:10 | 36/36 | 31/36 | +13.89 pp | 5 / 22 / 5 |
| `rg-409` | `31264600483` | 2026-08-09 00:31:29 | 36/36 | 29/36 | +19.44 pp | 7 / 22 / 7 |
| `rg-503` | `31265192522` | 2026-08-09 00:45:33 | 36/36 | 30/36 | +16.67 pp | 6 / 23 / 6 |

The start separations were 862, 848, 859, and 843 seconds, exceeding the
predeclared 300-second minimum. The complete window lasted 4,081.18 seconds.

## Aggregate

- Continuum: 180/180 verified outcomes, 100% success, 180/180 verified
  promotions.
- raw-RAG: 150/180 verified outcomes, 83.33% success, 30 unsafe proposals,
  112 unsafe memory exposures, 37 unsafe citation adoptions, and 30 failed
  outcomes promoted as canonical memory.
- Paired lift: +16.67 percentage points; hierarchical workflow-cluster plus
  paired-case bootstrap 95% interval +10.0 to +24.44 points (10,000
  resamples).
- Direction consistency: 5 positive, 0 negative, 0 tied batches. The
  replication-level two-sided sign-test p-value is 0.0625.
- The 180-execution exact p-value is `1.9e-09`, but is descriptive only because
  the same 36 incident definitions recur in five time clusters. It is not
  reported as 180 independent incident designs.
- Continuum latency p50/p95: 7,094.726 / 8,437.478 ms. raw-RAG latency p50/p95:
  7,352.754 / 8,731.179 ms.
- Both arms combined: zero duplicate effects, zero cleanup residuals, and zero
  cross-scope leaks. All 330 successful outcomes have non-null, unique provider
  receipt fingerprints.
- All 30 raw-RAG failures were classified as
  `PROVIDER_ACTION_TYPE_MISMATCH`; Continuum had no failure causes.

## Lineage

- Aggregate workflow: `31265768185` (PASS)
- Aggregate artifact: `9024090415`
- Aggregate archive SHA-256:
  `de6c03895611f9fffcb315537d779c14f519611b44d739b79a6be50ee2425cdd`
- Public/full report SHA-256:
  `6ae6fce4a58c0e8b862c5aef482ef5330a52678121696b065d9bf0886f3e5e5b`
- Public explorer:
  <https://yonghwan2161.github.io/continuum-memory-firewall/release-guardian-replication.html>

The aggregation workflow had read-only `actions` and `contents` permissions.
It downloaded each exact workflow artifact and failed closed on source,
population, run-attempt, artifact digest, pairing, time separation, safety, or
cleanup drift.
