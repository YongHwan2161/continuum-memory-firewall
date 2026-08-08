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
- `DEMO_NARRATION_V3.md` — story-first 90–120 second narration that adds the
  live checkout incident and measured 10/25/50-agent pressure result.
- `DEMO_NARRATION_V4.md` — outcome-first narration that compares the three
  paired arms before explaining the episode contract and one-click proof.
- `DEMO_NARRATION_V5.md` — crash-first narration: immutable release preserved,
  zero re-signatures, automatic reconciliation, and public coordinator proof.
- `continuum-memory-firewall-v4.en.srt` — exact English captions for the
  public 100.918-second outcome demo.

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

For the story-first v3 entry, capture the fixed live incident and the completed
public verifier, generate a disposable WAV from `DEMO_NARRATION_V3.md`, then
run:

```powershell
python scripts/build_demo_video_v3.py `
  --judge-evidence public-demo/evidence/judge-verification.json `
  --scale-evidence public-demo/evidence/vector-scale.json `
  --pressure-evidence public-demo/evidence/agent-pressure.json `
  --story-screenshot build/demo-v3/live-story.png `
  --verifier-screenshot build/demo-v3/verifier-pass.png `
  --narration-wav build/demo-v3/narration.wav `
  --output build/demo-v3/continuum-memory-firewall-demo-v3.mp4
```

The v3 builder additionally fails closed unless the agent-pressure evidence is
`PASS`.

For the outcome-first v4 entry, synthesize nine disposable narration segments
and build from the exact paired-ablation, pressure, live-incident, and verifier
inputs:

```powershell
powershell -File scripts/synthesize_demo_narration_v4.ps1 `
  -Narration docs/demo/DEMO_NARRATION_V4.md `
  -OutputDirectory build/demo-v4/narration `
  -Rate 4

python scripts/build_demo_video_v4.py `
  --judge-evidence public-demo/evidence/judge-verification.json `
  --ablation-evidence public-demo/evidence/agent-ablation-v3.json `
  --pressure-evidence public-demo/evidence/agent-pressure.json `
  --story-screenshot build/demo-v4/live-story.png `
  --verifier-screenshot build/demo-v4/verifier-pass.png `
  --narration-text docs/demo/DEMO_NARRATION_V4.md `
  --narration-dir build/demo-v4/narration `
  --subtitles build/demo-v4/continuum-memory-firewall-v4.en.srt `
  --output build/demo-v4/continuum-memory-firewall-demo-v4.mp4
```

The builder refuses evidence other than judge schema v5, the 180-case-per-arm
ablation schema v3, pressure `PASS`, and Continuum's 100% verified-outcome / zero
false-promotion result. It also enforces a 90–120 second narration duration.

For the crash-reconciliation v5 entry, download the public terminal receipt,
retain the disposable fault-matrix report, capture the final verifier, and run:

```powershell
powershell -File scripts/synthesize_demo_narration_v4.ps1 `
  -Narration docs/demo/DEMO_NARRATION_V5.md `
  -OutputDirectory build/demo-v5/narration `
  -Rate 4

python scripts/build_demo_video_v5.py `
  --judge-evidence public-demo/evidence/judge-verification.json `
  --transaction-evidence build/demo-v5/release-transaction-receipt.json `
  --fault-matrix-evidence build/demo-v5/github-release-fault-matrix.json `
  --ablation-evidence public-demo/evidence/agent-ablation-v3.json `
  --verifier-screenshot build/demo-v5/verifier-pass.png `
  --narration-text docs/demo/DEMO_NARRATION_V5.md `
  --narration-dir build/demo-v5/narration `
  --subtitles build/demo-v5/continuum-memory-firewall-v5.en.srt `
  --output build/demo-v5/continuum-memory-firewall-demo-v5.mp4
```

The v5 builder requires a five-event `PAGES_MATERIALIZED` receipt containing a
coordinator run and artifact digest, a non-signing disposable fault-matrix
`PASS`, judge schema v7 or later, and the 180-case-per-arm ablation report.
