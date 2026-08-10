# Closed-loop CI recovery benchmark

This document owns the executable contract for the real GitHub Actions
closed-loop recovery benchmark. Current live status and exact receipts remain
owned by [PROJECT_STATUS.md](PROJECT_STATUS.md).

## Question

Can provider-verified recovery memory help an agent choose a reviewed fix for
a later CI failure without admitting failed attempts as canonical memory?

This is deliberately narrower than arbitrary code repair. The model can select
one of six action-specific proposal tools. It cannot write source, choose a
repository/ref, dispatch a workflow, declare success, or promote memory. The
server owns those transitions.

## Real provider boundary

Every source-defined fault family has three calibration runs:

1. `no_patch` must produce a separate GitHub Actions run whose terminal
   conclusion is `failure`;
2. a known-wrong reviewed patch must produce another terminal `failure`; and
3. the family-specific reviewed patch must produce a terminal `success`.

The paired evaluation then runs the same twelve novel/recurrence incidents for
`stateless`, `raw_rag`, and `continuum`. Each proposal dispatches a new child
workflow. The coordinator accepts an outcome only after it re-reads the child
run, exact head SHA, terminal conclusion, artifact ID, artifact archive digest,
and the receipt inside that archive.

The child workflow does not use `continue-on-error`. A failed fixture leaves
the workflow red. Its receipt is still uploaded with `if: always()`, so failure
cannot disappear from the evaluated population.

## Memory arms

| Arm | Candidate-visible history | Promotion rule |
|---|---|---|
| `stateless` | none | none |
| `raw_rag` | the actual failed calibration attempt and actual green recovery | append every model episode, including a failed provider outcome |
| `continuum` | only the provider-verified green recovery | promote only a GitHub Actions `success` receipt |

The existing phased Bedrock tool contract is reused. Memory-enabled arms must
search before proposing. Citation IDs are server-issued handles from that one
search, and patch proposals use discriminated, parameter-free tools.

## Registered fixtures

The population is six families with a novel and recurrence rendering for each:

- Python 3.10 versus the reviewed 3.12 runtime contract;
- a missing pinned dependency record;
- a renamed workflow matrix axis;
- a generated artifact at the wrong upload path;
- a top-level result status instead of `gate.status`; and
- an `app` package root in a `src`-layout repository.

The child runner builds each fixture under a temporary directory and runs a
real `python -m unittest` command. A child run never pushes a branch, edits the
repository checkout, publishes a release, or touches production data. Runner
workspace removal must leave zero residuals.

## Metrics and hard gates

The report records, per arm:

- verified recovery rate and recurrence success rate;
- unsafe patch rate;
- provider failure count;
- canonical promotions, false promotions, and promotion precision;
- exposure and citation adoption of a real failed-attempt memory;
- model turns, tool calls, and model/provider/end-to-end p50/p95 latency; and
- bounded orchestration failure codes.

Publication fails closed unless all 54 child workflow run IDs are unique, all
18 calibration red/green receipts match their registered conclusion, all 36
paired observations exist, Continuum recovers at least 75%, Continuum false
promotion is zero, Continuum promotion precision is 1.0, and repository
mutation/cleanup residual counts are zero. Superiority over either baseline is
measured but is not a release gate.

## Statistical and product boundary

The twelve fixtures are source-defined synthetic incidents. Paired bootstrap
intervals and exact p-values are descriptive; they do not establish performance
over the population of arbitrary GitHub projects. The new evidence is stronger
than a local replay because both red and green conclusions come from separately
addressable GitHub Actions runs, but it does not replace customer-repository or
human-operator validation.

## Execution

Only reviewed `main` through the `continuum-production` environment may assume
the AWS deployment role and invoke Bedrock:

```text
workflow_dispatch: aws-ci-recovery-benchmark.yml
  -> 18 calibration child workflows
  -> three-arm Bedrock proposals
  -> 36 evaluation child workflows
  -> exact run/artifact reconciliation
  -> private + public benchmark artifacts
```

The workflow creates no AWS infrastructure and keeps the existing USD 20
budget alert unchanged. The only incremental AWS use is bounded Nova Micro
inference.

## Live result — 2026-08-10

The reviewed parent workflow
[`31389008324`](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31389008324)
completed on source `3a77fa7575d6b324ae367995bd398fbd0b758ca1`.
Its exact artifact is ID `9062964949`, name
`continuum-ci-recovery-3a77fa7575d6b324ae367995bd398fbd0b758ca1-31389008324-1`,
archive SHA-256
`08d5d0d0cc7b3719fcdea306221924d2db6687580c42e3b980fccdcb3a8a274f`,
and public-result SHA-256
`8d0f6ac85c22f052f2f3968deeb3f86c311164773d06def3e9f87977cb4e9236`.

All 54 child workflow run IDs and artifact IDs were unique. Every child ran at
the exact source head, reported no repository mutation, and left zero cleanup
residuals. The six calibrations each produced the registered red, wrong-red,
and green conclusions.

| Arm | Verified recovery | Recurrence | False promotion | Canonical precision | Provider p95 | End-to-end p95 |
|---|---:|---:|---:|---:|---:|---:|
| Stateless | 12/12 | 6/6 | 0 | n/a | 19.0 s | 19.64 s |
| Raw-RAG | 11/12 | 5/6 | 1 | 0.916667 | 86.0 s | 87.25 s |
| Continuum | 12/12 | 6/6 | 0 | 1.0 | 52.0 s | 53.32 s |

The one raw-RAG failure was `matrix-axis-02-recurrence`. Append-all history
exposed and adopted the failed `set_python_312` memory, although the required
tool was `repair_matrix_axis`; child run
[`31389172556`](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31389172556)
ended red. Continuum exposed no failed memory and promoted only successful
provider receipts.

Continuum's descriptive lift over raw-RAG was +8.3333 percentage points, with
one win, no losses, eleven ties, bootstrap 95% interval 0 to +25 points, and
paired exact p = 1.0. It had no lift over stateless: all twelve pairs tied.
Therefore the supported claim is failed-memory isolation under a real
closed-loop provider, not general recovery superiority or a statistically
confirmatory treatment effect.

The first parent attempt
[`31388545383`](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31388545383)
failed closed after GitHub changed the artifact-download media contract. The
reviewed fix switched the API request to JSON media type, followed only the
unsigned HTTPS location without forwarding the bearer token, and verified the
downloaded archive against GitHub's advertised digest. Main CI and the second
parent run then passed. This incident is retained because it is itself an
observed recovery boundary, not deleted from the narrative.
