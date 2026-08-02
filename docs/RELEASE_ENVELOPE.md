# Immutable competition release envelope

`hackathon-v1` is the single proof unit for the competition build. It is
published only by `.github/workflows/release-envelope.yml` after every
fail-closed gate passes.

The envelope binds:

- the exact reviewed release commit and release workflow run;
- the SHA-256 of the public judge evidence document consumed by the builder;
- the exact application deployment head, run, artifact SHA-256, migration
  version, checksum-drift result, and tenant-binding version/event;
- SHA-256 receipts for the RLS, tenant control-plane, and vector-contract
  migration files;
- the exact 10k/50k synthetic benchmark head, workflow, report SHA-256,
  four-point beam grid, natural vector-search plans, and zero scope leakage;
- the Managed MCP key-rotation run and old-key retirement receipt; and
- the Devpost submission ID, updated project timestamp, public project URL,
  current video URL, duration, and local-render SHA-256.

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
gh release download hackathon-v1 --pattern 'continuum-release-envelope-v1.json*'
sha256sum -c continuum-release-envelope-v1.json.sha256
```

GitHub documents that immutable releases automatically receive a release
attestation, verifiable with `gh release verify` and `gh release verify-asset`.
Because that automatic attestation can be temporarily unavailable after
publication, `.github/workflows/attest-release-envelope.yml` independently
downloads the already-immutable envelope, compares it to the release API digest,
generates signed SLSA build provenance with `actions/attest@v4`, and verifies it
in the same run. Consumers can verify that exact downloaded asset with:

```bash
gh attestation verify continuum-release-envelope-v1.json \
  --repo YongHwan2161/continuum-memory-firewall
```

The JSON `gates.checks` object is the machine-readable explanation of why the
release was admitted. Any missing lineage, checksum mismatch, incomplete beam
grid, foreign row, stale Devpost receipt, or incomplete key retirement stops
publication.
