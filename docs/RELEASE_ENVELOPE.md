# Immutable competition release envelope

`hackathon-v7` is the next proof unit for the competition build. It is
published only by `.github/workflows/release-envelope.yml` after every
fail-closed gate passes.

`hackathon-v1` through `hackathon-v5` remain immutable audit history. Version 6
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
- the Devpost submission ID, updated project timestamp, public project URL,
  current video URL, duration, and local-render SHA-256.

The immutable release carries the exact sandbox JSON, full ablation JSON, and
public-safe episode drill-down JSON as release assets in addition to the
envelope. This keeps judge evidence available after the shorter-lived GitHub
Actions artifacts expire.

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
gh release download hackathon-v7 --pattern 'continuum-release-envelope-v2.json*'
sha256sum -c continuum-release-envelope-v2.json.sha256
```

GitHub documents that immutable releases automatically receive a release
attestation, verifiable with `gh release verify` and `gh release verify-asset`.
Because that automatic attestation can be temporarily unavailable after
publication, `.github/workflows/attest-release-envelope.yml` independently
downloads the already-immutable envelope, compares it to the release API digest,
generates signed SLSA build provenance with `actions/attest@v4`, and verifies it
in the same run. Consumers can verify that exact downloaded asset with:

```bash
gh attestation verify continuum-release-envelope-v2.json \
  --repo YongHwan2161/continuum-memory-firewall
```

The JSON `gates.checks` object is the machine-readable explanation of why the
release was admitted. Any missing lineage, checksum mismatch, incomplete beam
grid, foreign row, stale Devpost receipt, or incomplete key retirement stops
publication.
