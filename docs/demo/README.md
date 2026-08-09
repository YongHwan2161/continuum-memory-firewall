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
- `DEMO_NARRATION_V6.md` — real-provider narration: failed-action memory
  problem, 36 paired GitHub incidents, outcome-gated promotion, failed-first
  identity repair, immutable release, and one-click proof.
- `DEMO_NARRATION_V7.md` — compiler-generated narration from the immutable v14
  sequential receipt: 144 future targets per arm, false-promotion mechanism,
  exact-artifact reconciliation, architecture, and public proof.
- `continuum-memory-firewall-v4.en.srt` — exact English captions for the
  public 100.918-second outcome demo.
- `continuum-memory-firewall-v5.en.srt` — exact English caption source for the
  public 101.674-second crash-reconciliation demo. The rendered video includes
  the captions directly; its public URL is <https://youtu.be/NOkD8YaTyAo>.
- `build/demo-v6/continuum-memory-firewall-v6.en.srt` — generated English (US)
  captions published with the 99.53-second real-provider video at
  <https://youtu.be/OEPYF7cVpbs>.
- `build/demo-v7/continuum-memory-firewall-demo-v7.srt` — receipt-compiled
  English (US) captions published with the 97.02-second judge video at
  <https://youtu.be/QQxfQaDVz9c>.

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

For the real-provider v6 entry, download the public terminal receipt, capture
the completed verifier, synthesize nine disposable narration segments, and run:

```powershell
powershell -File scripts/synthesize_demo_narration_v4.ps1 `
  -Narration docs/demo/DEMO_NARRATION_V6.md `
  -OutputDirectory build/demo-v6/narration `
  -Rate 4

python scripts/build_demo_video_v6.py `
  --judge-evidence public-demo/evidence/judge-verification.json `
  --guardian-evidence public-demo/evidence/release-guardian-v1.json `
  --transaction-evidence build/demo-v6/release-transaction-receipt.json `
  --verifier-screenshot build/demo-v6/verifier-pass.png `
  --narration-text docs/demo/DEMO_NARRATION_V6.md `
  --narration-dir build/demo-v6/narration `
  --subtitles build/demo-v6/continuum-memory-firewall-v6.en.srt `
  --output build/demo-v6/continuum-memory-firewall-demo-v6.mp4
```

The v6 builder requires judge schema v8, a 36-pair/72-observation real-provider
guardian `PASS`, and a five-event `PAGES_MATERIALIZED` transaction receipt. It
also enforces the 90–120 second competition duration.

For the receipt-compiled v7 entry, first compile the immutable v14 source into a
canonical story receipt and narration. Synthesize the nine disposable segments,
then build the captioned video:

```powershell
python scripts/compile_evidence_story_v7.py `
  --judge public-demo/evidence/judge-verification.json `
  --sequential public-demo/evidence/sequential-blind-v1.json `
  --release-receipt build/demo-v7/release-transaction-receipt-v14.json `
  --source-release-tag hackathon-v14 `
  --source-release-target 5b75dedff551137d7d8ec72726e8b2cba6dedb99 `
  --source-release-envelope-sha256 8c880fa4908e0405084155387a7f01bbf0bc9f22b2a11b8b7b3de5072a733a07 `
  --source-release-sequential-sha256 f34c2d9f7695b5b6bb333c5b23bcd7b5b924f71e68970c64220ed6ef116f8f3d `
  --output public-demo/evidence/evidence-story-v1.json `
  --narration-output docs/demo/DEMO_NARRATION_V7.md

powershell -File scripts/synthesize_demo_narration_v4.ps1 `
  -Narration docs/demo/DEMO_NARRATION_V7.md `
  -OutputDirectory build/demo-v7/narration `
  -Rate 4

python scripts/build_demo_video_v7.py `
  --story public-demo/evidence/evidence-story-v1.json `
  --narration-text docs/demo/DEMO_NARRATION_V7.md `
  --narration-dir build/demo-v7/narration `
  --subtitles build/demo-v7/continuum-memory-firewall-demo-v7.srt `
  --output build/demo-v7/continuum-memory-firewall-demo-v7.mp4
```

The compiler rejects mutable or mismatched release inputs and overclaims. The
video builder accepts only a valid self-addressed story receipt and enforces the
90–120 second duration. WAV files, the MP4, and the upload SRT remain local build
artifacts; the source, story JSON, narration, and rebuild scripts are reviewed.
