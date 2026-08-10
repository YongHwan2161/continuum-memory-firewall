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

The Bedrock model can use only phased tools:

1. memory-enabled arms perform one server-scoped search;
2. a dynamic citation handle may fetch a returned memory;
3. any arm may dispatch one of the two registered read-only probes; and
4. the model finishes with one action-specific `propose_*` tool.

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

The implementation contract and deterministic tests are complete. Live metrics,
public judge integration, and a release-envelope claim remain HOLD until the
main-only workflow produces a passing artifact.
