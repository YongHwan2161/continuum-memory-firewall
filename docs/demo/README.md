# Competition demo package

These artifacts are secret-free reviewer materials captured from the local
render of the public proof console after its live-evidence copy was updated.
They contain no provider console, credential, token, database URL, AWS account
identifier, or private participant information.

## Artifacts

- `continuum-live-overview.png` — product thesis and exact-head live-proof badge.
- `continuum-policy-rejection.png` — a high-similarity, untrusted model memory
  fails closed as `UNTRUSTED_SOURCE`.
- `continuum-cockroach-live-memory.png` — redacted live SQL Shell aggregate
  proving eight canonical memories, forty retrieval audits, and schema version
  11 without row identifiers or participant identity.
- `continuum-idempotent-failover.png` — one worker claims authority and the
  concurrent worker returns `DUPLICATE`.
- `continuum-memory-firewall-demo.mp4` — sub-three-minute, 1280×720 narrated
  demo assembled from the proof frames, live SQL result, and measured metrics.
- `DEMO_NARRATION.md` — narration source.
- `DEMO_NARRATION_V2.md` — 90–120 second narration for the rebuilt judge path:
  verifier, authorization architecture, 60-query evaluation, isolation denial,
  representative-scale ANN proof, and key rotation.

The browser console is an executable simulation of the policy and concurrency
contract. The OIDC, RLS, Titan, Recall@3, and leakage statements shown in its
live badge/card are backed separately by the exact-head workflow linked from
`docs/evidence/2026-08-01-oidc-titan-rls-live-smoke.md`.

## Rebuild

Create a WAV narration from `DEMO_NARRATION.md`, install Pillow and
`imageio-ffmpeg`, then run:

```powershell
python scripts/build_demo_video.py `
  --frames-dir docs/demo `
  --narration-wav docs/demo/continuum-demo-narration.wav `
  --output docs/demo/continuum-memory-firewall-demo.mp4
```

The WAV is a disposable build input and is intentionally not committed.

The current video is rebuilt only after the public demo and read-only verifier
are live. Capture those two pages without credentials, generate the disposable
WAV from `DEMO_NARRATION_V2.md`, then run:

```powershell
python scripts/build_demo_video_v2.py `
  --judge-evidence public-demo/evidence/judge-verification.json `
  --scale-evidence public-demo/evidence/vector-scale.json `
  --demo-screenshot build/demo-v2/demo.png `
  --verifier-screenshot build/demo-v2/verifier.png `
  --narration-wav build/demo-v2/narration.wav `
  --output build/demo-v2/continuum-memory-firewall-demo-v2.mp4
```

The builder fails closed unless the scale evidence is `PASS` and the narration
duration is between 90 and 120 seconds. The output remains a release artifact;
the source, narration, and rebuild command are the reviewed repository inputs.
