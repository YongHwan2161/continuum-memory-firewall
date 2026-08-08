# Real-provider release guardian evidence

## Result

GitHub Actions run
[`31245814421`](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31245814421)
completed 36 exact paired incidents per arm, 72 observations total, through the
participant AWS/CockroachDB runtime and the real GitHub Releases API.

| Metric | raw-RAG | Continuum |
| --- | ---: | ---: |
| Verified provider outcomes | 31/36 (86.111%) | 36/36 (100%) |
| Unsafe proposals | 5 | 0 |
| Unsafe memory exposures | 23 | 0 |
| False canonical promotions | 5 | 0 |
| Duplicate provider effects | 0 | 0 |
| Cleanup residuals | 0 | 0 |
| Cross-scope leaked rows | 0 | 0 |
| p50 / p95 | 7,600.794 / 8,909.193 ms | 6,889.681 / 8,546.881 ms |

Continuum's paired verified-outcome lift is **+13.8889 percentage points**.
There were five Continuum wins, zero raw-RAG wins, and 31 ties. The
10,000-resample paired bootstrap interval is +2.7778 to +25.0 points; the
two-sided paired exact p-value is 0.0625. The practical effect is strong, but
the 36-pair real-provider run is external-validity evidence rather than a
standalone claim of conventional p < 0.05 significance.

## What was real and what was synthetic

- Incident inputs were synthetic and non-sensitive.
- Bedrock Nova Micro generated action-specific tool calls.
- Titan v2 retrieval and CockroachDB canonical-memory promotion ran on the
  participant deployment.
- GitHub draft releases and assets were actually created, inspected, renamed,
  adopted, or deleted according to each case.
- No evaluation release was published and no Git tag ref was created.
- Every disposable draft was removed; an independent namespace query found
  zero residual releases after the workflow.

The provider capability manifest records idempotency support, provider receipt
lookup, and a 30-second reconciliation timeout. Repository, target commit,
release, tag, and asset identities were server-owned; the model could choose
only one of six parameter-free, action-specific proposal tools.

## Immutable receipts

- Source head: `a23792cdc30c0936057169b886c7e1f64530c7ab`
- Deployment artifact SHA-256:
  `3ece49e3652a48e902577106e58acacea9cfcedccc32f1d4282c31603648ace8`
- Actions artifact ID: `9018594439`
- Actions archive digest:
  `sha256:5137bbb1a1099b896935f9d65fda0334e3336aca763eee4b5ea12e49d32ca814`
- Raw report SHA-256:
  `27ab9c92b44bcac021e789a91c157b292cd283a9f61d7adbd9d1bffecaba262c`
- Public projection SHA-256:
  `ba9a6e5c981142e20c63b474ff0bbcb1bb000f9ca8df17f2c1e33a696aefcfb1`

The workflow token was staged through a temporary Secrets Manager value without
appearing in SSM commands or logs. Its instance policy was removed after the
run, the value was tombstoned, and the staging S3 object was deleted. The
judging-window AWS Budget alert is USD 20; it is an alert, not a hard cap.

## Failed-first evidence

Run `31245390534` failed closed on the first provider case because a newly
created draft was not immediately visible through the releases collection. The
draft nevertheless existed. PR #89 changed provider identity to the
server-issued immutable release ID and added a stale-list regression test. The
single residual draft from the failed run was verified as draft-only, deleted by
exact release ID, and independently rechecked at zero.

This failure materially improved the architecture: effect identity now comes
from the provider's creation receipt, not from an eventually consistent list
query.
