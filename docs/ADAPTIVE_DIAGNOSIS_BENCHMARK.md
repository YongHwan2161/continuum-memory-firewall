# Ambiguity-first adaptive diagnosis benchmark

This document owns the executable contract for the preregistered adaptive CI
diagnosis benchmark. Exact live receipts and the publication status belong in
[PROJECT_STATUS.md](PROJECT_STATUS.md).

## Question

Does provider-verified memory reduce the evidence-acquisition work required to
recover an otherwise ambiguous recurring CI incident, without reducing recovery
or admitting a failed outcome as canonical memory?

The prior closed-loop benchmark cannot answer that question. Its initial red
summary identifies values such as Python `3.10` or a missing `gate.status`, so a
stateless model can select the patch without acquiring information.

## Preregistered ambiguity contract

An independent deterministic compiler creates twelve opaque cases: six fault
families, each rendered as novel and recurrence. Challenge and evaluator labels
are separate canonical JSON byte streams. A commitment binds both SHA-256
digests, and all three objects are written to private S3 with
`If-None-Match:*` before the first candidate model call.

The candidate receives no family, fixture, expected patch, wrong patch, fault
probe, label, or scoring-policy field. Within every ambiguity-group/variant
cell, both possible families have exactly the same initial `provider_state`.
The only recurrence key is an opaque environment fingerprint.

The benchmark has three ambiguity groups:

| Group | Mutually exclusive families | Registered read-only probes |
|---|---|---|
| bootstrap resolution | runtime version / package root | runtime manifest / package settings |
| dependency expansion | dependency lock / matrix axis | lock entries / matrix manifest |
| evidence publication | artifact path / report schema | artifact tree / report keys |

One probe is sufficient: an anomaly identifies the inspected family; a normal
result identifies the other family by exclusion. Each arm nevertheless receives
the same hard budget of at most two probes.

## Evidence acquisition and action boundary

The Bedrock model can use only phased tools. The server, rather than the model,
owns the transition between phases:

1. memory-enabled arms perform one server-scoped search;
2. a dynamic citation handle may fetch a returned memory;
3. without exact verified support, an arm may dispatch one of the two registered
   read-only probes; and
4. the server compiles either the fetched verified outcome or the current probe
   fact into exactly one admissible action-specific `propose_*` schema.

An exact-fingerprint successful Continuum memory therefore exposes only
`search -> fetch -> matching proposal`; a diagnostic probe exposes only its
evidence-consistent proposal. A second low-value probe and the other five action
schemas are not offered to the model. This is a fail-closed evidence router, not
an evaluator-label lookup: the probe-to-action mapping is part of the public
challenge policy, while the responsible fixture and expected label remain in
the sealed evaluator object.

The server rejects a proposal unless it is supported by either:

- a fetched and cited successful provider receipt for the exact environment
  fingerprint and proposed patch; or
- at least one actual read-only GitHub Actions probe receipt.

A proposal never executes a patch. The controller owns the sealed fixture route,
dispatches a separate remediation child workflow, re-reads its terminal run and
artifact, and only then records the provider outcome. Failed raw-RAG episodes may
be appended by the raw baseline; Continuum promotes only green provider outcomes.

## Real-provider population

Before candidate execution, eighteen separate GitHub Actions calibration runs
prove baseline red, reviewed-wrong red, and reviewed-correct green for all six
families. During candidate execution, every requested diagnostic becomes a new
read-only child run. After proposals, thirty-six additional child runs execute
the selected remediations.

All children run under an ephemeral workspace. They cannot write repository
contents. Red remediation runs remain red; `if: always()` preserves their
receipts. Every accepted receipt binds the exact source SHA, run ID, artifact ID,
archive digest, inner receipt digest, repository-mutation flag, and cleanup count.

## Primary metrics and hard gate

The primary comparison is paired Continuum versus stateless, not raw recovery
rate alone:

- verified recovery within the identical two-probe budget;
- diagnostic child runs and probes per case;
- recurrence zero-probe cases;
- model turns, tool calls, and input/output tokens;
- diagnostic-provider, episode, remediation, and end-to-end p50/p95 latency;
- unsafe patches, failed-memory exposure/adoption;
- canonical promotion precision and false promotions; and
- repository mutation and cleanup residuals.

Publication fails closed unless Continuum recovery is not below stateless,
Continuum uses fewer probes in at least five of six recurrence pairs, the paired
two-sided exact sign-test p-value is at most `0.05`, Continuum false promotions
are zero, Continuum canonical precision is `1.0`, all provider receipts are
unique and exact-head, and mutation/residual counts are zero.

The paired bootstrap interval and exact test apply only to this registered
twelve-case population. They do not establish performance over arbitrary
repositories.

## Execution

Only reviewed `main` through the `continuum-production` environment can assume
the AWS role and invoke Bedrock:

```text
aws-adaptive-diagnosis-benchmark.yml
  -> generate challenge + labels + commitment
  -> write-once S3 seal
  -> 18 real calibration workflows
  -> concurrent three-arm Bedrock episodes
       -> actual read-only child workflow per requested probe
  -> 36 real remediation workflows
  -> post-run scoring and fail-closed public projection
```

The reviewed main-only workflow has now produced a passing artifact. Parent run
[31400622882](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31400622882)
at source `a8274319e548c91a6eb2910ca8345011aa6f2c3e` is the admitted candidate.
Its Actions artifact is `9067731798`, with archive SHA-256
`7164eb8e07a0ebe600004c80b848ebe32fedfabda12f14ccbdbac978a45b7485`.

## Live result

The campaign created 18 calibration, 30 diagnostic, and 36 remediation child
workflows: 84 unique run IDs and 84 unique artifact IDs, all exact-source, all
non-mutating, and all with zero cleanup residual. The result was:

| Metric | Stateless | raw-RAG | Continuum |
|---|---:|---:|---:|
| verified recovery | 12/12 | 12/12 | 12/12 |
| diagnostic workflows | 12 | 12 | 6 |
| recurrence diagnostic workflows | 6/6 | 6/6 | 0/6 |
| recurrence zero-probe cases | 0/6 | 0/6 | 6/6 |
| false canonical promotions | 0 | 0 | 0 |
| input tokens | 22,711 | 46,411 | 34,487 |
| observed end-to-end p50 / p95 | 39,119 / 48,369 ms | 38,071 / 144,128 ms | 21,711 / 42,236 ms |

Continuum saved a mean `0.5` diagnostic workflows per case versus stateless;
the paired bootstrap 95% interval is `[0.25, 0.75]`. In the six registered
recurrence pairs, all six favored Continuum, none favored stateless, and the
two-sided exact sign-test is `p=0.03125`. Recovery lift is zero because all arms
recovered every case. Continuum canonical promotion precision is `1.0`.

This proves bounded information value for exact provider-verified environment
fingerprints. It does not prove semantic transfer across changed repository
layouts, tool versions, or near-neighbor faults. It also does not prove lower
total model cost: Continuum used 11,776 more input tokens than stateless because
memory search and fetch replaced external diagnostic workflows. Latency values
are reported as observed measurements, not as an independently powered latency
superiority claim.

The public projection has SHA-256
`290144361304edc08484d8ba2cef1df4013d12c84b717520ae22a7dac0d635c7`.
The public [adaptive diagnosis page](https://yonghwan2161.github.io/continuum-memory-firewall/adaptive-diagnosis.html)
and [one-click verifier](https://yonghwan2161.github.io/continuum-memory-firewall/verify.html)
bind the parent, artifact, commitment, S3 seal, all receipt identities, metrics,
and immutable v19 release asset.

## Fail-closed validation history

The first complete exact-head run after S3-seal validation was
[31398666306](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31398666306)
at source `b593ba65b1daf546f59fbf32e3c2cb1bb3ad86f3`. It preserved 116 child
workflow receipts and correctly refused publication: Continuum reduced
recurrence probes in five of six pairs, but the preregistered two-sided exact
test was `p=0.0625`, above the `0.05` gate. The run also showed that a model
could ignore exact verified memory and request a redundant probe when both
tools remained available.

The response is architectural, not statistical threshold relaxation. The
server now compiles verified memory and provider facts into discriminated tool
schemas as described above. The failed run remains immutable evidence; only a
new source SHA with a newly generated and S3-sealed challenge may qualify for
publication.
