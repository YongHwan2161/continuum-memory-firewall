# Sequential blind memory-compounding evaluation

## Result

Three fresh Bedrock-generated batches were sealed in S3 before any candidate
ran. Stateless, raw-RAG, and Continuum then executed the same 36 five-episode
GitHub Releases and S3 chains: 540 real provider observations and 144 paired
future target episodes per comparison. Labels and the scoring policy opened
only after all candidates completed.

| Arm | Target success | Rate | Unsafe proposals | Unsafe memory exposure / adoption | False promotions | Verified memory-assisted successes |
|---|---:|---:|---:|---:|---:|---:|
| Continuum | 114/144 | 79.17% | 38 | 0 / 0 | 0 | 113 |
| Stateless | 105/144 | 72.92% | 46 | 0 / 0 | 0 | 0 |
| raw-RAG | 102/144 | 70.83% | 50 | 89 / 43 | 48 | 64 |

The primary raw-RAG comparison produced 12 Continuum wins, zero raw-RAG wins,
and 132 ties: +8.33 percentage points, with a 10,000-resample hierarchical
sealed-batch bootstrap 95% interval of +3.47 to +14.58 points. Its sequential
e-value was 637.15, above the preregistered threshold of 20.

The stateless comparison produced 12 Continuum wins, three stateless wins, and
129 ties: +6.25 points. Its interval was -2.08 to +18.75 and its sequential
e-value was 7.95. This is favorable but not confirmatory and is reported as
such.

## Batch results

| Batch start (UTC) | Continuum | Stateless | raw-RAG | raw false promotions | Gate |
|---|---:|---:|---:|---:|---|
| 2026-08-09 11:48:37 | 36/48 | 36/48 | 33/48 | 18 | PASS |
| 2026-08-09 12:06:55 | 36/48 | 36/48 | 33/48 | 17 | PASS |
| 2026-08-09 12:25:40 | 42/48 | 33/48 | 36/48 | 13 | PASS |

Observed start separations were 1,098 and 1,125 seconds, above the fixed
300-second minimum. These are three sealed time clusters, not three independent
people or three calendar days.

## Data-quality and safety checks

- 540 observations and 540 unique `(arm, case_id)` keys; exactly 180 rows per
  arm.
- 270 GitHub and 270 S3 observations; exactly 108 observations for each of
  clean, paraphrase, poison, stale, and conflict.
- Twelve incident families each contributed 45 observations.
- Candidate files contained zero forbidden label/scoring fields.
- All three generation nonces and commitment digests were unique.
- All 405 successful provider outcomes had non-null, unique 64-hex receipt
  fingerprints.
- Continuum canonical promotion precision was 100%; false promotion,
  cross-scope leak, duplicate effect, and cleanup residual were all zero.
- All three batch gates and the aggregate campaign gate passed.

Target p50/p95 latency was 4,200.465/8,270.265 ms for Continuum,
2,360.209/7,023.084 ms for stateless, and 4,426.509/8,743.836 ms for raw-RAG.
Recovery was observed in 2/30 Continuum attempts, 9/39 stateless attempts, and
0/42 raw-RAG attempts. The campaign was not powered to claim recovery or
latency superiority; its confirmatory result is future-target success versus
raw-RAG plus zero false promotion.

## Crash-safe evaluator recovery

Candidate workflow `31311573511` (source
`067ba08bc549d38600d76644e748252633a8cc29`) completed all 540 candidates and
the final cleanup step. Its evaluator then failed before scoring because the
GitHub runner's Python 3.10 did not provide `enum.StrEnum`. The always-uploaded
candidate artifact contained the sealed inputs, labels opened after completion,
and raw observations, but no campaign report.

PR #112 pinned Python 3.12 and added a read-only evaluator replay. Replay
workflow `31314477338` (source
`716abb32e066419d9d67f635572890fb43e9d037`) verified the exact failed-run
boundary, successful candidate and cleanup steps, and candidate artifact before
scoring once. No candidate or label was regenerated.

## Lineage

- Candidate artifact: `9038202621`
- Candidate archive SHA-256:
  `47c53b4ee445ce8e86cf8638ee8d0fe3244d448961340896fe1e8c3c53d6bbc6`
- Evaluator artifact: `9038325962`
- Evaluator archive SHA-256:
  `f3c196a4283eee546db032b8b136a34e07c0c6672aea1183e053c8dd2245052f`
- Campaign manifest SHA-256:
  `6308ea9a944424dee863240e7717394ba2411e4e9eb6d2179711afe292005df3`
- Campaign seal receipt SHA-256:
  `c9b73adeac7fa80cedae4e515d7c09861a2ce33714d4bc96a56de8ea76b10649`
- Public result SHA-256:
  `f34c2d9f7695b5b6bb333c5b23bcd7b5b924f71e68970c64220ed6ef116f8f3d`
- Public explorer:
  <https://yonghwan2161.github.io/continuum-memory-firewall/sequential-blind.html>

The public one-click verifier independently fetches both workflow and artifact
planes, checks source/run attempts and digests, recomputes the public hash, and
requires the v14 immutable release asset to contain the same bytes.
