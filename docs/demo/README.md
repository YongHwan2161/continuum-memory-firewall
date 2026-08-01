# Competition demo package

These artifacts are secret-free reviewer materials captured from the local
render of the public proof console after its live-evidence copy was updated.
They contain no provider console, credential, token, database URL, AWS account
identifier, or private participant information.

## Artifacts

- `continuum-live-overview.png` — product thesis and exact-head live-proof badge.
- `continuum-policy-rejection.png` — a high-similarity, untrusted model memory
  fails closed as `UNTRUSTED_SOURCE`.
- `continuum-idempotent-failover.png` — one worker claims authority and the
  concurrent worker returns `DUPLICATE`.
- `continuum-memory-firewall-demo.mp4` — 58-second, 1280×720 narrated demo
  assembled from the three frames and live metrics.
- `DEMO_NARRATION.md` — narration source.

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
