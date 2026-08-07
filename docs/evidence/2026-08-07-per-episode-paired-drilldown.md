# Per-episode paired drill-down evidence

Date: 2026-08-07 18:03 KST
Claim boundary: non-sensitive synthetic incidents, real Bedrock tool-calling,
real participant CockroachDB episode storage/retrieval, and a non-effecting
synthetic receipt provider. This is not a production remediation-provider test.

## Exact live run

- Runtime/source head: `2ef224748ca0bd163e95cdb7d2e1eb755c521c5a`
- Workflow: <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31162961883>
- Workflow conclusion: `success`
- Actions artifact ID: `8988330323`
- Artifact name: `continuum-agent-ablation-2ef224748ca0bd163e95cdb7d2e1eb755c521c5a`
- Artifact archive SHA-256:
  `4a383dac9070dc201021f03121a865a6d3a40fd3282cf4e9c207534a0476f500`
- Full private report SHA-256:
  `561aefcade82a9f07d10c748b2890b176a0efe94812d0e2942816bcac8db2b20`
- Public drill-down SHA-256:
  `89e86e8b7f1f3a48d7c266838839b100de99878c61d2a842d5ad152b828d399f`

The workflow-generated public projection and an independently regenerated
projection from the downloaded full report were structurally identical.

## Population and gates

- 36 base incidents x 5 isolated replications x 3 arms = 540 observations
- 180 exact `(replication, case)` pairings
- Every pair contains exactly `stateless`, `raw_rag`, and `continuum`
- Continuum-over-raw-RAG verified-outcome advantage: 85/180 episodes
- Server-issued-handle subset gate: PASS
- Continuum unsafe proposal count: 0
- Cross-scope leaked row count: 0
- Raw tenant/incident/run/memory/proposal/outcome/provider receipt ID keys in
  public projection: 0

The aggregate result remained stable: stateless 80/180 (44.4%), raw-RAG 95/180
(52.8%), and Continuum 180/180 (100%) verified outcomes. Continuum's paired
lift over raw-RAG was +47.222 percentage points; the 36-cluster, 10,000-resample
paired bootstrap 95% interval was +30.556 to +63.889 points. Raw-RAG's unsafe
proposal rate under memory pressure was 88.9%, poison exposure was 94.4%, and
false append-all promotions were 85. Continuum remained 0%, 0%, and 0.

## Failure found and corrected

The first exact-head attempt
(<https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31162438281>)
failed before publication because the trace writer expected a canonical receipt
digest for failed provider outcomes. The episode contract deliberately returns
that digest only for verified success. PR #69 preserved verified receipt digests
and introduced a distinct deterministic `unverified_outcome_evidence` digest
for failed or ambiguous outcomes. Temporary AWS capability was revoked by the
failed workflow before the corrected rerun.

## Public judge path

- Paired explorer:
  <https://yonghwan2161.github.io/continuum-memory-firewall/episodes.html>
- One-click verifier:
  <https://yonghwan2161.github.io/continuum-memory-firewall/verify.html>
- Public projection:
  <https://yonghwan2161.github.io/continuum-memory-firewall/evidence/episode-drilldown-v1.json>

The explorer defaults to causal-contrast episodes where raw-RAG failed and
Continuum succeeded, but all 180 paired incidents remain available through the
family, variant, replication, and text filters.
