# Preregistered ambiguity-first adaptive diagnosis live evidence

**Evidence date:** 2026-08-11 KST

**Provider:** GitHub Actions child workflows; AWS Bedrock agent; private S3
write-once preregistration

**Admitted source:** `a8274319e548c91a6eb2910ca8345011aa6f2c3e`

**Parent:** [workflow 31400622882](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31400622882), attempt 1, `success`

**Artifact:** ID `9067731798`,
`continuum-adaptive-diagnosis-a8274319e548c91a6eb2910ca8345011aa6f2c3e-31400622882-1`
**Artifact archive SHA-256:**
`7164eb8e07a0ebe600004c80b848ebe32fedfabda12f14ccbdbac978a45b7485`

## Conclusion

PASS, with a bounded claim. In the registered twelve-case population, all
three arms recovered 12/12. Continuum used six actual diagnostic child
workflows versus twelve for stateless and twelve for raw-RAG. On the six exact-
fingerprint recurrence pairs, Continuum used zero probes in 6/6 while stateless
used one in 6/6; the preregistered two-sided paired exact test is `p=0.03125`.
Continuum retained canonical precision `1.0`, false promotion `0`, repository
mutation `0`, and cleanup residual `0`.

This is evidence that verified memory can substitute for repeated external
evidence acquisition under the exact-fingerprint contract. It is not evidence
of higher recovery accuracy—every arm recovered every case—and not evidence of
semantic transfer to a changed environment.

## Preregistration and label firewall

Before the first candidate model call, the controller wrote challenge, labels,
and commitment as separate checksum-addressed objects with S3
`If-None-Match:*`:

| Object | SHA-256 |
|---|---|
| challenge | `7140741f3511691f8ad5e7182e0dd20358f21f6f2cc55f9aeefe94584010a40a` |
| evaluator labels | `de1c9bf0e05a88eeb0c00fd79696feef77bd0c8b90299f34333042cd1f9b2ef2` |
| commitment | `98d022d629c484de36aea2e62a18d871a84b323d2b5202591f696f18d548bd84` |
| seal receipt | `10e25917d38fb53e2f3b10d76c94c8d285e0ee7e3ed5d773552c2eb919f88356` |

Candidate-visible label fields were `0`. The model received the same opaque red
summary and two-probe budget in each arm. Only the controller retained labels
for fixture routing and post-run scoring.

## Receipt cardinality and integrity

The public projection contains:

- 18 calibration child receipts: reviewed baseline red, wrong-patch red, and
  correct-patch green across six families;
- 30 read-only diagnostic child receipts;
- 36 remediation child receipts; and
- 84 unique workflow IDs and 84 unique artifact IDs in total.

Every accepted child receipt binds the admitted source, a GitHub artifact
digest, repository mutation `false`, and cleanup residual `0`. The deterministic
public projection is byte-bound at SHA-256
`290144361304edc08484d8ba2cef1df4013d12c84b717520ae22a7dac0d635c7`.

## Measured result

| Metric | Stateless | raw-RAG | Continuum |
|---|---:|---:|---:|
| verified recovery | 12/12 | 12/12 | 12/12 |
| diagnostic child workflows | 12 | 12 | 6 |
| recurrence diagnostic workflows | 6 | 6 | 0 |
| recurrence zero-probe cases | 0 | 0 | 6 |
| canonical promotion precision | n/a | 1.0 | 1.0 |
| false canonical promotions | 0 | 0 | 0 |
| input tokens | 22,711 | 46,411 | 34,487 |
| observed E2E p50 / p95 | 39,119 / 48,369 ms | 38,071 / 144,128 ms | 21,711 / 42,236 ms |

Versus stateless, Continuum saved a mean `0.5` probes per case with a paired
10,000-resample bootstrap 95% interval `[0.25, 0.75]`. Six recurrence pairs
favored Continuum, zero favored stateless, and zero tied. Recovery lift was
`0.0` percentage points.

The token result is an explicit counterweight: Continuum used 11,776 more input
tokens than stateless. The admitted claim is lower external diagnostic work and
observed recurrence latency, not lower total token cost or universal latency.

## Fail-closed predecessor

[Workflow 31398666306](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31398666306)
completed 116 child workflows but remained failed. Continuum reduced probes in
five of six recurrence pairs, yielding `p=0.0625`, above the registered `0.05`
gate. The threshold and labels were not changed. Review instead moved phase
authority to a server-owned evidence router: an exact successful memory or one
current provider fact exposes only the matching discriminated proposal schema.
A fresh source generated and sealed a fresh challenge before the admitted run.

## Public verification

- Result page:
  <https://yonghwan2161.github.io/continuum-memory-firewall/adaptive-diagnosis.html>
- Complete credential-free verifier:
  <https://yonghwan2161.github.io/continuum-memory-firewall/verify.html>
- Immutable evidence release:
  <https://github.com/YongHwan2161/continuum-memory-firewall/releases/tag/hackathon-v19>

The v19 release workflow re-downloads the exact Actions artifact, reconstructs
the public projection from the private report, checks all 84 receipt identities,
and publishes the public result with its SHA-256 sidecar. Release publication,
Pages materialization, and the terminal transaction receipt are independently
verified runtime gates; they are never inferred from source or unit tests.
