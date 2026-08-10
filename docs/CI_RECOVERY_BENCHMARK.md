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
