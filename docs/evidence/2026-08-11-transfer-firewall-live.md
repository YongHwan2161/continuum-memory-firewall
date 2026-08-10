# Preregistered counterfactual cross-environment transfer firewall live evidence

**Evidence date:** 2026-08-11 KST

**Providers:** GitHub Actions child workflows; AWS Bedrock candidate; private
S3 write-once preregistration

**Admitted source:** `361c3ec8ed6ee1a7c09ae30bcf80d9d22aa44fc9`

**Parent:** [workflow 31439117749](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31439117749), attempt 1, `success`

**Artifact:** ID `9082282513`,
`continuum-transfer-firewall-361c3ec8ed6ee1a7c09ae30bcf80d9d22aa44fc9-31439117749-1`

**Artifact archive SHA-256:**
`1c103f9e454e6886ebf09f23b494f44d2755696aa1d6b5ca7b779125118add71`

## Conclusion

PASS, with a bounded claim. Across six reviewed counterfactual pairs,
Continuum recovered all twelve changed-environment targets. It reused all six
provider-attested same-cause memories without a diagnostic workflow and safely
rejected all six semantically similar, different-cause near neighbours before
running one current diagnostic. Stateless also recovered 12/12 but required
twelve diagnostics. raw-RAG recovered 6/12, falsely transferred all six near
neighbours, proposed six unsafe patches, and promoted six failed outcomes.

Continuum therefore saved one diagnostic in 6/6 same-cause pairs versus
stateless (two-sided paired exact `p=0.03125`) while maintaining false transfer
`0`, false canonical promotion `0`, and canonical promotion precision `1.0`.
Against raw-RAG, it prevented six false transfers and improved verified
recovery by 50 percentage points (`p=0.03125`).

## Counterfactual and label firewall

Each of six source fault families generated two targets:

- a changed-environment target with the same provider-observed cause; and
- a target with the same public red summary and environment profile but a
  mutually exclusive causal fault.

Source and target environment fingerprints are disjoint. Before the first
candidate call, the controller wrote the label-free challenge, evaluator-only
labels, and commitment as separate checksum-addressed S3 objects using
`If-None-Match:*`.

| Object | SHA-256 |
|---|---|
| challenge | `21e1804532cc179696c7a97ea193aab52f7965672035174a447f0eaf772dccb2` |
| evaluator labels | `7a92f508ce2ea8adce0b8d788dada628794abd1f83941189fdba224a85f5c1ac` |
| commitment | `d0db8201ff3aeb6938ed30e72192b49bd7eccc7b30d8541b09f7f264846bf94f` |
| seal receipt | `e9d1281b4746cbc160c77154d588b84ed03a9c39a93be9bca57e7a9842d92fbf` |

Candidate-visible label fields were `0`. Target attestations registered an
opaque causal signature from a separate read-only provider run. The candidate
could not read the signature or evaluator relationship. In the Continuum arm,
the server exposed a memory-backed proposal only when source outcome and target
attestation authorized the same exact patch.

## Receipt cardinality and integrity

The public projection contains:

- 18 source calibration child receipts;
- 12 shared target attestation child receipts;
- 18 candidate diagnostic child receipts;
- 36 remediation child receipts; and
- 84 unique workflow IDs, artifact IDs, and artifact digests.

Every receipt binds the admitted source SHA, reports repository mutation
`false`, and reports cleanup residual count `0`. The deterministic public
projection is byte-bound at SHA-256
`cf46c93614d16e219bea849247ec15dc8ff9287145ebcb3ca8fda4e5424dbf25`.

## Measured result

| Metric | Stateless | raw-RAG | Continuum |
|---|---:|---:|---:|
| verified recovery | 12/12 | 6/12 | 12/12 |
| diagnostic child workflows | 12 | 0 | 6 |
| same-cause verified transfers | 0/6 | 6/6 | 6/6 |
| near-neighbour safe rejections | 6/6 | 0/6 | 6/6 |
| near-neighbour false transfers | 0 | 6 | 0 |
| unsafe patches | 0 | 6 | 0 |
| false canonical promotions | 0 | 6 | 0 |
| canonical promotion precision | n/a | 0.5 | 1.0 |

Target attestations are shared benchmark inputs. The six candidate diagnostic
workflows saved by Continuum do not imply fewer total provider workflow runs.
Observed token and latency values remain descriptive because superiority gates
for those metrics were not preregistered.

## Failed predecessors and correction

[Workflow 31437516208](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31437516208)
failed after a transient read-only artifact download disconnect. Retry was
added only around GET operations; provider dispatch and effects were not
retried.

[Workflow 31438167336](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31438167336)
recovered all actions but correctly failed its evidence gate because three
incompatible retrieved memories remained in the final citation arrays after a
current diagnostic. The correction made memory fetch availability
server-admission-owned and rejected any citation that was not fetched,
currently admitted, and authorizing the exact proposed patch. The corrected
source passed 367 tests with 16 integration skips before the admitted run.

This history matters: successful actions alone are not sufficient evidence if
their cited authority is stale or incompatible.

## Public verification

- Result page:
  <https://yonghwan2161.github.io/continuum-memory-firewall/transfer-firewall.html>
- Complete credential-free verifier:
  <https://yonghwan2161.github.io/continuum-memory-firewall/verify.html>
- Exact parent workflow:
  <https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31439117749>
- Immutable evidence release:
  <https://github.com/YongHwan2161/continuum-memory-firewall/releases/tag/hackathon-v20>

Release coordinator
[31441863985](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31441863985)
re-downloaded the exact Actions artifact, rebuilt the public projection from
the private report, validated all 84 receipt identities, and published immutable
`hackathon-v20` at exact target `16a84d10c6fce8af5e82a39b7c67b24c27603327`.
The release asset digest is the same public SHA-256 shown above. Pages run
[31441902936](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31441902936)
reached `PAGES_MATERIALIZED`; its public terminal receipt SHA-256 is
`454b29f515b4504b8b72bc1c4f0c5b98553736a7bcfd530ecde3abb05d326bb6`.
Credential-free monitor
[31442028079](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31442028079)
then passed every judge check from the exact published source. Strict network
verification also found exactly one author attestation and one GitHub platform
countersignature.

## Claim boundary and next architectural question

This benchmark establishes bounded provider-attested transfer and rejection
for six reviewed synthetic CI fault pairs. It does not establish arbitrary
repository repair or open-world semantic generalization.

The source-memory payload in this runner is assembled from the exact provider
calibration receipt and supplied as a typed `MemoryToolHit`; it is not loaded
through the production CockroachDB vector/RLS path. The next fundamental P0 is
therefore an online CockroachDB memory-lineage closure: provider receipt to
canonical promotion, scoped vector retrieval, server admission, target action,
verified outcome, and next promotion must form one independently verifiable
chain in the live decision loop.
