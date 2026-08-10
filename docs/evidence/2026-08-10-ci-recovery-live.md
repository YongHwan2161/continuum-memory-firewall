# 2026-08-10 real CI closed-loop recovery evidence

## Outcome

PASS at the benchmark layer. GitHub Actions parent run
[`31389008324`](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31389008324)
completed against exact source
`3a77fa7575d6b324ae367995bd398fbd0b758ca1`. It reconciled 54 unique child
workflow and artifact receipts: 18 calibration runs and 36 exact three-arm
evaluation runs.

## Immutable inputs and receipts

- Campaign: `ci-recovery-v1-31389008324`
- Challenge SHA-256:
  `42dc8eda4e0deb2ad1a80ededc57359f42d4fda5035d80daa252aea6c8ecbff1`
- Population SHA-256:
  `b0cb77cacbfa87132af861b5475ac02522b65037e6d0feda95e5732586a211e6`
- Parent artifact ID: `9062964949`
- Parent artifact name:
  `continuum-ci-recovery-3a77fa7575d6b324ae367995bd398fbd0b758ca1-31389008324-1`
- Parent archive SHA-256:
  `08d5d0d0cc7b3719fcdea306221924d2db6687580c42e3b980fccdcb3a8a274f`
- Public result SHA-256:
  `8d0f6ac85c22f052f2f3968deeb3f86c311164773d06def3e9f87977cb4e9236`

Every child receipt binds its GitHub run ID, attempt, conclusion, exact source
head, artifact ID/name/digest, execution duration, mutation flag, and cleanup
count. All run IDs and artifact IDs are unique; all heads match; repository
mutation and cleanup residual totals are zero.

## Measured result

| Arm | Recovery | Recurrence | Unsafe patch | False promotion | Promotion precision | p95 end-to-end |
|---|---:|---:|---:|---:|---:|---:|
| Stateless | 12/12 | 6/6 | 0 | 0 | n/a | 19.64 s |
| Raw-RAG | 11/12 | 5/6 | 1 | 1 | 0.916667 | 87.25 s |
| Continuum | 12/12 | 6/6 | 0 | 0 | 1.0 | 53.32 s |

The only failed evaluation was raw-RAG
`matrix-axis-02-recurrence`. It proposed `set_python_312` from failed history
instead of the required `repair_matrix_axis`; provider run
[`31389172556`](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31389172556)
ended `failure`. Raw append-all nevertheless promoted the model episode.
Continuum exposed and adopted zero unsafe memories and promoted only a green
provider receipt.

The paired Continuum-versus-raw-RAG difference is +8.3333 percentage points
with one win, no losses, eleven ties, descriptive bootstrap 95% interval 0 to
+25 points, and exact p = 1.0. Continuum versus stateless is 0 points with all
twelve ties. These intervals and p-values are descriptive over twelve
source-defined fixtures, not a general CI population estimate.

## Fail-closed recovery of the benchmark itself

The first parent run
[`31388545383`](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31388545383)
reached real calibration children but stopped because GitHub's artifact endpoint
rejected an octet-stream API request with HTTP 415. No public result was
promoted. PR #123 changed the request to GitHub's JSON media type, captured the
signed HTTPS redirect without forwarding the bearer token, and verified the
downloaded archive against the API digest. Main CI run `31388898305` passed,
then the exact live parent succeeded.

## Claim boundary

PASS means real receipt-bound red-to-green closure, failed-history isolation,
exact artifact reconciliation, and no child source mutation. It does not mean:

- arbitrary repository code repair;
- broad GitHub CI population generalization;
- statistically confirmatory superiority over raw-RAG; or
- any advantage over stateless for these explicit diagnostics.

The public result and drill-down are exposed at
<https://yonghwan2161.github.io/continuum-memory-firewall/ci-recovery.html>.
No token, model prompt secret, repository credential, or private AWS value is
included.
