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

With a current GitHub CLI, a judge can verify the published release and a
downloaded envelope asset:

```bash
gh release verify hackathon-v1
gh release download hackathon-v1 --pattern 'continuum-release-envelope-v1.json*'
gh release verify-asset hackathon-v1 continuum-release-envelope-v1.json
sha256sum -c continuum-release-envelope-v1.json.sha256
```

The JSON `gates.checks` object is the machine-readable explanation of why the
release was admitted. Any missing lineage, checksum mismatch, incomplete beam
grid, foreign row, stale Devpost receipt, or incomplete key retirement stops
publication.
