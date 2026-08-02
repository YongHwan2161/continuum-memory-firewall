# Episode, outcome-learning, and outbox live evidence

**Evidence date:** 2026-08-02 UTC / 2026-08-03 KST  
**Scope:** participant CockroachDB Cloud cluster and the dedicated AWS evidence
role; non-sensitive synthetic incidents and a non-effecting provider only

## Implemented boundaries

- [PR #45](https://github.com/YongHwan2161/continuum-memory-firewall/pull/45)
  added the durable `agent_runs`, `retrieved_citations`,
  `proposed_actions`, and `outcome_evidence` contract plus a bounded Bedrock
  Converse orchestrator. The model receives server-scoped memory reads and an
  allowlisted proposal tool, never provider execution authority.
- [PR #46](https://github.com/YongHwan2161/continuum-memory-firewall/pull/46)
  added approval evidence, unique provider receipts, outcome-gated
  canonical promotion, and the identical 36-case three-arm experiment.
- [PR #48](https://github.com/YongHwan2161/continuum-memory-firewall/pull/48)
  added the transactional action outbox and the
  `pending`/`leased`/`dispatching`/`sent`/`acknowledged`/`ambiguous` state
  machine. Participant schema version 30 contains all episode and outbox
  migrations.
- [PR #50](https://github.com/YongHwan2161/continuum-memory-firewall/pull/50)
  replaced the broad memory-tool choice with the server-enforced phase
  sequence `search-only -> fetch-or-propose -> propose-only` and retained
  bounded failure codes with real model-turn/tool-call progress.
- [PR #51](https://github.com/YongHwan2161/continuum-memory-firewall/pull/51)
  made newly granted Secrets Manager access tolerate only bounded IAM
  `AccessDeniedException` propagation. It does not retry unrelated errors and
  never logs or persists the secret value.

## Transactional outbox fault proof

Workflow [30754765994](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30754765994)
ran at trusted deployment head `afa32b513c722d4c27c7327fabdf79de256fa5df`.
The private artifact `outbox-faults.json` is 1,729 bytes and has SHA-256
`97551ca98bb4b0f70a3c3e09f9db4077fcf5f513fd7d4c4ae112f04560232380`.

| Injected boundary | Provider contract | Terminal state | Logical effects | Duplicate effects | Canonical |
|---|---|---:|---:|---:|---:|
| before send | idempotent | acknowledged / succeeded | 1 | 0 | yes |
| after send | idempotent | acknowledged / succeeded | 1 | 0 | yes |
| before acknowledgement | idempotent | acknowledged / succeeded | 1 | 0 | yes |
| after send | non-idempotent | ambiguous / ambiguous | 1 | 0 | no |

The evidence provider is in-memory and non-effecting while the outbox and
episode transitions are durable in the participant database. This proves the
crash state machine and the no-blind-resend decision; it does not claim that an
arbitrary production provider offers exactly-once effects.

## Three-arm live ablation

The first validly shaped run,
[30754256328](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30754256328),
reported 9/36 stateless successes and 0/36 for both memory arms. It retained
zero leakage and zero false promotion, but exposed a causal harness defect:
`search_memory` and `fetch_memory` were offered together, so a cold-start model
could select an invalid fetch and never create the verified memory needed by a
later recurrence. The private first-run report SHA-256 is
`3778ef01339bfb21b01026bb44718db513c1815dd6abb73a00a7a7bc08305d6f`.
The result is retained as failure history and is not used as product evidence.

After PRs #50 and #51, workflow
[30755531853](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30755531853)
ran 36 identical cases in each arm at trusted exact head
`af5db16c4fc8e0e94714038fef677f0ab72b4c0e`. The private 108-observation
artifact is 51,921 bytes with SHA-256
`2c91cd8d320b4cf9c717f85b0e483f0b76eaddfe26d5dcc67f78366122e523c5`.

| Arm | Verified successes | Wilson 95% | p50 / p95 ms | Canonical promotions | False promotions | Leakage |
|---|---:|---:|---:|---:|---:|---:|
| stateless | 9/36 (25.0%) | 13.8%–41.1% | 839.744 / 1244.486 | 9 | 0 | 0 |
| raw-RAG | 20/36 (55.6%) | 39.6%–70.5% | 2659.656 / 4248.135 | 20 | 0 | 0 |
| Continuum | 21/36 (58.3%) | 42.2%–72.9% | 1916.149 / 3166.664 | 21 | 0 | 0 |

Continuum improved by 33.333 percentage points over stateless. In the paired
case comparison it won 13, lost 1, and tied 22 (exact two-sided sign-test
`p=0.001831`). Against raw-RAG it won 3, lost 2, and tied 31 (`p=1.0`), so the
observed 2.778-point lift is not evidence of superiority at this sample size.
Among episodes that passed the proposal contract and reached the provider,
receipt success was 9/23 stateless, 20/27 raw-RAG, and 21/21 Continuum. This
suggests a useful safety/availability split: canonical-only memory made accepted
proposals precise in this corpus, but schema-contract rejection reduced overall
coverage. The all-36 denominator remains the primary metric.

The most informative variant split is adversarial: Continuum succeeded on 3/6 poison
and 4/6 stale cases versus raw-RAG 2/6 and 2/6. Raw-RAG was stronger on the
six later recurrences (4/6 versus 2/6). Both cache-action families scored 0/6
in every arm. Every one of the 12 Continuum cache cases was rejected for
forbidden parameters; raw-RAG had six such rejections and otherwise chose the
wrong action. Continuum also had three citations outside the returned search
set; raw-RAG had three. These are model/schema-alignment failures that the
firewall correctly rejected, not provider failures or cross-scope leaks.

## Deployment and public boundary

Two fail-closed attempts are retained:

- [30755115371](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30755115371)
  dispatched from untrusted `main`; OIDC role assumption failed and no DB/model
  experiment ran.
- [30755318089](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30755318089)
  deployed the exact head but reached the instance before the temporary IAM
  read grant propagated; no experiment ran and cleanup revoked the grant.

The successful run used the existing trusted branch and dedicated deployment
role, deployed the exact package, revoked its temporary inline policy, and
deleted the staging object. After the run, public health returned `200` with
audited tenant-control-plane and bounded-pool metadata; unauthenticated `/mcp`
returned `401`.

## Explicit non-claims

- The 36 cases are labeled synthetic incidents and the verifier is
  deterministic and non-effecting; no production remediation provider was
  called.
- The Continuum-versus-raw result is statistically unresolved and must not be
  presented as a proven lift.
- The report is bound to the workflow head by the immutable artifact name and
  Actions metadata; the JSON schema does not yet repeat `source_head` inside
  the payload.
- Judge UX, per-memory pages, and a replacement 120-second video were outside
  this implementation slice and remain subsequent work.
