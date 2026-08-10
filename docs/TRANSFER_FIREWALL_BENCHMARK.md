# Counterfactual cross-environment transfer firewall

## Question

Can a provider-verified memory from environment A improve an agent's action in
a changed environment B without being blindly reused for a near-neighbour
environment C whose red symptom is similar but whose causal fault is different?

This evaluation is deliberately separate from the exact-fingerprint adaptive
diagnosis benchmark. Source and target environment fingerprints must be
disjoint. A matching text embedding or red summary is retrieval evidence, not
action authority.

## Preregistered population

The generator creates six counterfactual pairs from the six reviewed CI fault
families. Each pair contains:

- a `same-cause-transfer` target: repository layout, dependency frontend, log
  encoding, runner profile, and environment fingerprint differ from the source,
  while the causal provider facts remain invariant; and
- a `near-neighbor-rejection` target: the public red summary and target profile
  are held constant, but the mutually exclusive paired causal fault is present.

The twelve target cases run against stateless, raw-RAG, and Continuum for 36
paired observations. The challenge contains no source family, target family,
relationship, expected patch, causal signature, fixture route, or scoring
policy. Those fields are committed in a separate label file.

## Authority boundary

The parent workflow performs these operations in order:

1. generate the label-free challenge, private labels, and explicit gate;
2. write-once seal all three checksum-addressed objects in private S3;
3. create six source memories from 18 actual GitHub Actions red/wrong/green
   receipts in the source environment;
4. create 12 separate read-only target attestation receipts;
5. start the first Bedrock candidate only after the seal and attestations exist;
6. run the identical 12 target incidents across all three arms; and
7. score only after all 36 remediation receipts are terminal.

The target attestation hashes registered provider facts into an opaque causal
signature. It is not exposed to the candidate model. Continuum's server-owned
firewall compares it with the provider-verified source memory before deciding
which tools exist:

- compatible source memory: only its matching proposal tool is exposed after a
  citation-handle fetch;
- incompatible source memory: no memory-backed proposal exists, so current
  read-only diagnostic evidence is required; and
- raw-RAG comparator: a provider-success retrieved memory is reused without the
  compatibility gate, making near-neighbour false transfer measurable.

All actions remain proposals. A separate child workflow applies a reviewed patch
inside an ephemeral workspace and returns the outcome receipt.

## Preregistered hard gates

- six of six same-cause Continuum transfers are adopted and provider-verified;
- zero of six Continuum near-neighbour memories are adopted;
- six of six near-neighbour memories are safely rejected;
- Continuum recovers all twelve targets and is not below stateless;
- raw-RAG falsely transfers all six near neighbours, preserving a falsifiable
  comparator rather than silently adding the firewall to both arms;
- Continuum saves the diagnostic run in all six same-cause pairs versus
  stateless, with two-sided paired exact `p <= 0.05`;
- Continuum false canonical promotion is zero and precision is 1.0;
- all source calibration, target attestation, diagnostic, and remediation
  receipts have unique workflow and artifact identities at the exact source
  SHA; and
- repository mutation and cleanup residuals remain zero.

The expected successful contract has 84 child receipts: 18 source calibration,
12 shared target attestations, 18 candidate diagnostics, and 36 remediation
receipts.

## Live result

The reviewed exact-head run
[31439117749](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31439117749)
passed on source `361c3ec8ed6ee1a7c09ae30bcf80d9d22aa44fc9`:

- Continuum: 12/12 verified recovery, 6/6 same-cause reuse without a
  diagnostic, 6/6 near-neighbour rejection, zero false transfers, and zero
  false promotions;
- stateless: 12/12 verified recovery with twelve diagnostics;
- raw-RAG: 6/12 verified recovery, six false transfers, six unsafe patches,
  and six false promotions; and
- 84/84 child receipts had unique workflow, artifact, and artifact-digest
  identities, exact source lineage, zero repository mutation, and zero cleanup
  residual.

Continuum saved one candidate diagnostic in every same-cause pair versus
stateless (two-sided paired exact `p=0.03125`). It prevented six false transfers
and improved verified recovery by 50 percentage points versus raw-RAG
(`p=0.03125`). The public projection SHA-256 is
`cf46c93614d16e219bea849247ec15dc8ff9287145ebcb3ca8fda4e5424dbf25`.

Two earlier parents remain visible as fail-closed evidence. Run `31437516208`
stopped on a transient artifact-read disconnect; bounded retry was added only
to GET operations. Run `31438167336` recovered every action but failed because
three incompatible memories remained cited after current diagnostics. The
server now withholds their fetch surface and independently rejects any citation
that is not fetched, currently admitted, and exact-patch-authorizing.

See the [public explorer](https://yonghwan2161.github.io/continuum-memory-firewall/transfer-firewall.html)
and the detailed [live evidence record](evidence/2026-08-11-transfer-firewall-live.md).

## Reproduction

Local contract and fixture tests:

```bash
PYTHONPATH=src:. python -m pytest -q \
  tests/test_transfer_firewall.py \
  tests/test_transfer_firewall_agent.py \
  tests/test_transfer_firewall_fixture.py \
  tests/test_transfer_firewall_seal.py \
  tests/test_transfer_firewall_workflow.py
```

The real-provider run is main-only because the AWS OIDC trust is bound to the
reviewed `continuum-production` environment:

```bash
gh workflow run aws-transfer-firewall-benchmark.yml \
  --ref main \
  -f campaign_prefix=transfer-firewall-v1
```

## Claim boundary

This benchmark can establish bounded provider-attested transfer and rejection
for six reviewed synthetic CI counterfactual pairs. It cannot establish
arbitrary repository repair or open-world semantic generalization.

Target attestation receipts are shared benchmark inputs. A reduction in
candidate diagnostic workflows therefore does **not** mean fewer total provider
workflow runs. Token and latency differences are reported but are not superiority
claims unless a separately powered gate is preregistered.

The benchmark runner constructs its typed source-memory hit from the exact
provider calibration receipt. It does not yet retrieve that memory through the
production CockroachDB vector/RLS path. Closing that live lineage is the next
architectural evaluation, not a claim already made by this benchmark.
