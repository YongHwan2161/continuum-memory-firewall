# Immutable competition release envelope

`hackathon-v15` is the proof unit for the receipt-compiled competition story. It is
published only by `.github/workflows/release-envelope.yml` after every
fail-closed gate passes.

`hackathon-v1` through `hackathon-v9` remain immutable audit history. Version 6
adds the outcome-first public video and refreshed Devpost version 14 receipt to
the citation-handle and paired memory-pressure candidate while preserving
the prior live runtime (`1291e27`) and documentation (`2a94b46`) as explicit
baseline lineage rather than silently relabeling them as the new candidate.

Before publication, `scripts/promote_release_v5_evidence.py` consumes the full
private ablation report plus the GitHub run/artifact receipts. It writes only
the observation-free public aggregate, the public-safe 180-case paired episode
projection, and the judge evidence as one operation. Promotion fails if an
artifact name does not contain its exact
source head, a digest is malformed, the sandbox receipt is not tied to the
baseline runtime, or the report does not contain all 540 observations. The
judge evidence timestamp comes from the immutable ablation report, so repeating
promotion with identical inputs is byte-stable.

The envelope binds:

- the exact reviewed release commit and release workflow run;
- the prior live runtime/documentation SHAs and the new exact deployed candidate;
- the SHA-256 of the public judge evidence document consumed by the builder;
- the exact application deployment head, run, artifact SHA-256, migration
  version, checksum-drift result, and tenant-binding version/event;
- SHA-256 receipts for the RLS, tenant control-plane, and vector-contract
  migration files, with the combined RLS checksum repeated on the public judge
  record and required to match the release checkout;
- the exact 10k/50k synthetic benchmark head, workflow, report SHA-256,
  four-point beam grid, natural vector-search plans, and zero scope leakage;
- the Managed MCP key-rotation run and old-key retirement receipt; and
- the real AWS sandbox provider run, Actions artifact ID/archive digest, exact
  report SHA-256, idempotency manifest, and receipt-lookup gate;
- the full 540-observation paired ablation run, deployment artifact SHA-256,
  Actions artifact receipt, public aggregate checksum, citation-grounding gate,
  and all five pre-registered safety/outcome metrics; and
- the exact 180-episode three-arm drill-down, including its source evaluation,
  checksum, privacy gate, handle-grounding gate, public page, and immutable
  release asset; and
- the 72-observation real-provider release guardian, including its GitHub
  workflow/artifact receipts, raw report, public projection, paired metrics,
  cleanup proof, and provider capability manifest; and
- the five time-distributed guardian workflows and artifacts, one exact
  36-case population checksum, the 180-pair/360-observation aggregate,
  hierarchical workflow-cluster bootstrap, receipt uniqueness, and zero
  Continuum unsafe/residual-effect gates; and
- the preregistered 60-pair blind holdout, including the S3 seal time,
  challenge/commitment/seal digests, exact workflow and artifact receipt,
  generator/agent/evaluator versions, public-result digest, GitHub plus S3
  capability manifests, and zero Continuum false-promotion/leak/residual gates;
- the three-batch sequential blind campaign, including 36 five-episode chains,
  540 provider observations, fixed start separation, campaign manifest and seal
  receipts, paired hierarchical bootstrap and sequential e-process, verified
  memory-assisted successes, and zero Continuum false-promotion/leak/residual
  gates;
- the canonical evidence-story receipt, including its self-addressed digest,
  exact v14 envelope and sequential-asset inputs, nine ordered scenes, bounded
  statistical claims, and public story page; and
- the Devpost submission ID, updated project timestamp, public project URL,
  current video URL, duration, local-render SHA-256, and English subtitle
  SHA-256.

The immutable release carries the exact sandbox JSON, full ablation JSON,
public-safe episode drill-down JSON, full real-provider guardian JSON, the
time-distributed aggregate JSON, public blind-holdout JSON, and public
sequential-campaign JSON as release assets
in addition to the envelope. Version 15 also carries
`evidence-story-v1.json` and its SHA-256 sidecar.
This keeps judge evidence available
after the shorter-lived GitHub Actions artifacts expire.

Version 9 closes the network-visible sign-once contract. The release workflow
refuses to proceed if the newly built envelope digest already has author SLSA
provenance, signs that envelope once with GitHub OIDC and Fulcio, downloads the
resulting Sigstore bundle, and verifies the exact signer workflow, main ref,
source SHA, GitHub-hosted runner, and Rekor timestamp. The detached author
bundle and its SHA-256 sidecar are attached while the release is still a draft.
The legacy second author-attestation workflow remains removed, so publication
and author signing have one execution path.

GitHub automatically creates a separate release attestation when the draft is
published as immutable. It has release predicate v0.2 and the platform signer
identity `https://dotcom.releases.github.com`; it is not a second execution of
the author workflow. Version 8 incorrectly treated the resulting two network
records as an author replay and therefore ended its workflow after successful
publication. Version 9 makes the authority boundary explicit and requires
exactly one author SLSA attestation, one platform release countersignature, and
two total records.

Version 10 closes the release crash gap. The workflow creates a durable draft
and uploads the exact envelope before invoking the author signer. Its
hash-chained `release-transaction-receipt.json` advances only in this order:

`PREPARED -> AUTHOR_ATTESTED -> ASSETS_UPLOADED -> IMMUTABLE -> PAGES_MATERIALIZED`

On retry, the coordinator downloads the draft assets and inspects the public
attestation index. Zero author attestations produces `SIGN_AUTHOR`; one produces
`RECORD_AUTHOR_ATTESTED`; more than one, a changed target, or a changed envelope
digest produces `AMBIGUOUS` and stops. A crash after immutable publication is
reconciled from the immutable provider receipt without changing release assets.
Pages publishes the terminal receipt and verifies the public bytes before its
workflow succeeds. Sensitive evidence keys are rejected by the coordinator.

Version 11 closes the external-effect evidence gap. The release workflow
revalidates the real-provider guardian workflow and artifact receipts, downloads
the full 72-observation report, regenerates and compares the public projection,
and includes the raw report plus checksum sidecar before the single author
signature. The judge gate independently checks both digests, the exact 36-pair
population, the real-provider flag, Continuum's 36/36 outcomes, and zero unsafe
proposal, duplicate-effect, cleanup-residual, and cross-scope counts.

Version 12 closes the single-time-point evidence gap. Five serial main-only
workflows repeat the exact 36-case population with distinct run IDs, start
times, and artifact digests. A read-only aggregation workflow rejects source,
population, attempt, artifact, time-separation, pairing, safety, or cleanup
drift. The immutable release contains the 180-pair aggregate and sidecar. The
judge verifier re-fetches the aggregate workflow/artifact plus every one of the
five source workflow/artifact receipts. Repeated incident definitions are
treated as five time clusters, not 180 independent designs.

Version 13 closes the hand-authored-evaluation gap. An independent Bedrock job
generates new provider states and five attack/language variants per family,
then seals challenge, labels, and commitment under checksum-addressed S3 keys
before candidate execution. Candidate IAM has an explicit exact-object label
deny. raw-RAG and Continuum execute the same 60 cases against disposable GitHub
Releases and S3 adapters; only after both arms finish does a separate evaluator
open labels and score provider receipts plus outcome evidence. The release
publishes the label-safe 120-observation projection, while the one-click judge
re-fetches its workflow, artifact, release-asset, commitment, and result digests.

Version 14 closes the one-shot-memory-evaluation gap. Three fresh, independently
sealed Bedrock batches form ordered provider episodes in which a verified
outcome may affect a later unseen action. Stateless, raw-RAG, and Continuum run
the same 540 observations while labels and the scoring policy remain denied.
Only after all candidates finish does the evaluator compute target success,
hierarchical batch-cluster intervals, and sequential e-values. The envelope and
one-click judge bind the exact workflow, Actions artifact digest, campaign
manifest, S3 seal receipt, public aggregate digest, and immutable release asset.
The evidence is described as three time clusters, not three independent people
or calendar days.

Version 15 closes the evidence-to-story drift gap. The compiler accepts only the
immutable v14 sequential aggregate, its terminal release-transaction receipt,
and the current public judge record. It rejects source-digest, methodology,
paired-statistics, replay-lineage, safety-gate, Devpost, video, subtitle, or
claim-boundary drift. The resulting canonical JSON has a self-addressed receipt
and is the only metric source for the nine-scene narration, public story page,
and v15 envelope. It confirms the paired raw-RAG comparison, keeps the stateless
comparison directional, and explicitly does not claim latency superiority.

The v14 sequential section binds two workflow planes. Candidate run
`31311573511` completed the full 540-observation step and cleanup, then failed
before scoring when the runner's Python 3.10 could not import `StrEnum`.
Evaluator run `31314477338` used reviewed Python 3.12, verified the exact
candidate artifact ID, name, and archive digest, confirmed that no prior
campaign aggregate existed, and scored the preserved population once. The
public verifier requires the failed candidate receipt, successful candidate and
cleanup step attestations recorded in the report, successful evaluator receipt,
both artifact digests, and the final public-result digest.

The differentiator gate is directional rather than cosmetic: raw-RAG must show
more unsafe proposals, unsafe-memory exposure, and poison exposure than
Continuum, while Continuum must show higher verified-outcome success and
canonical-promotion precision without worse recovery success.

At publication time, the workflow re-reads the application, vector benchmark,
and Managed MCP rotation runs through the GitHub API. Each referenced run must
still be successful, and application/vector heads must match the public
evidence. The builder also rechecks scope denial, control-plane isolation,
bounded pools, absent temporary migration capability, the exact release URL,
and the video receipt before it will create a draft release.

No credential value or database row is included.

## Independent verification

GitHub release immutability is enabled for this repository. The workflow first
creates a draft, attaches the envelope and SHA sidecar, then publishes it and
fails unless the GitHub API reports `immutable: true`, the release targets the
exact workflow commit, and both uploaded asset digests equal the local bytes.

The public verifier checks the release API's immutable flag, exact tag, uploaded
asset state, and SHA-256 digest. A judge can independently download the envelope
and validate its sidecar without trusting the public page:

```bash
gh release download hackathon-v15 --pattern 'continuum-release-envelope-v2.json*'
sha256sum -c continuum-release-envelope-v2.json.sha256
```

The same release contains
`continuum-release-envelope-v2.sigstore.jsonl`. GitHub Pages serves a
byte-identical copy, while the public verifier also checks the GitHub
attestation API and the in-toto subject digest. Full cryptographic policy
verification is one repository command:

```bash
python scripts/verify_network_sign_once.py --release-tag hackathon-v15
```

That command downloads the immutable envelope, detached author bundle, and both
network records. It requires one author SLSA subject and one GitHub release
subject, checks both release asset digests, proves that the detached author
bundle is the one indexed by GitHub, then invokes `gh attestation verify` with
the exact signer workflow, `refs/heads/main`, release target SHA, and
`--deny-self-hosted-runners`. The platform countersignature is reported as
network-visible material; only the author signature's completed `gh`
verification is reported as cryptographic proof.

The public verifier additionally downloads the terminal transaction receipt,
checks its complete five-state event sequence and receipt hash, requires the
Pages workflow receipt to be successful at the release target, and binds the
public two-attestation bundle SHA-256 to the terminal event. The Python
coordinator independently verifies every event and evidence hash in the chain.

The JSON `gates.checks` object is the machine-readable explanation of why the
release was admitted. Any missing lineage, checksum mismatch, incomplete beam
grid, foreign row, stale Devpost receipt, or incomplete key retirement stops
publication.
