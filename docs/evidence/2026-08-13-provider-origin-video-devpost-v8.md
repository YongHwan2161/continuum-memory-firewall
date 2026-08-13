# Provider-origin video and Devpost delivery receipt

**Captured:** 2026-08-13

**Scope:** public delivery of the receipt-compiled provider-origin story

**Source proof:** immutable release `hackathon-v27`

## Result

The provider-origin judge story is public on YouTube and is the current Devpost
video. The authenticated Devpost project remains published and its CockroachDB
AWS hackathon relationship remains submitted. The media is rebuilt from
machine-validated evidence rather than manually transcribed metrics.

This receipt deliberately separates two planes:

- `hackathon-v27` remains immutable and proves the provider-origin outcome,
  release transaction, network attestations, and zero-API judge delivery.
- The YouTube upload and Devpost version 23 are later mutable delivery records.
  They are **not** claimed as retroactive members of v27. A new successor
  envelope is required to bind these external delivery receipts immutably.

## Compiled source

- Story source:
  `public-demo/evidence/provider-origin-story-v1.json`
- Story kind/schema: `continuum.provider-origin-video-story` / `1`
- Story gate: `PASS`
- Story receipt SHA-256:
  `f3cafd7db4ba6c4657f2751c022ab609612e84776fc39d3c656e17f6c57676e8`
- Immutable source release: `hackathon-v27`
- Source target:
  `dbb4942afd45f5bc06cbc08441d43ce155c75f05`
- Coordinator workflow run: `31653469203`
- Coordinator artifact digest:
  `sha256:b2d2a54892b8c11135ac13d63f7517aa4067a0ca373430b280814ee1400fa074`
- Pages workflow run: `31653536847`
- Frozen online checks: `44`
- Network attestations: one author plus one platform countersignature
- Judge GitHub API requests: `0`

The compiler reuses the production outcome-proof, public terminal-receipt, and
release-envelope validators. It fails closed on source digest drift, failed
authority checks, negative outcome rows, missing RLS denial, network-signature
mismatch, or an expanded claim boundary.

## YouTube receipt

- Video ID: `cENOZu3prgs`
- Public URL: <https://youtu.be/cENOZu3prgs>
- Title: `Continuum Memory Firewall — Provider-Origin Outcome Proof | CockroachDB + AWS`
- Local render duration: `99.93` seconds; YouTube display duration: `1:40`
- Resolution/codec: `1280x720`, H.264 High, AAC mono
- File size: `2,135,642` bytes
- MP4 SHA-256:
  `af5a689017cc2c39deae2a6368ff0616d580dfabf909bf2918fafa7223cdace7`
- English SRT SHA-256:
  `4611757b3f074b4c6014f9c9085444c444ebbd6ea2c298a38ba0ac938f9262c7`
- Visibility: `Public`
- Audience: not made for kids
- English timed captions: published
- YouTube copyright check: no issues found
- Anonymous oEmbed read: title, author `김용환`, provider `YouTube`, and type
  `video` returned successfully on 2026-08-13.

The narration's admitted claim is one retained S3-backed proposal proving
provider-origin admission, exact binding, five-minute expiry, atomic
consumption, replay, RLS, immutable publication, and credential-free judge
delivery. It excludes a population-level effect estimate and durable signing
key custody or rotation continuity.

## Devpost receipt

- Project ID: `1362701`
- Project slug: `continuum-memory-firewall`
- Public page: <https://devpost.com/software/continuum-memory-firewall>
- Authenticated update version: `23`
- Updated at: `2026-08-13T08:10:05.381-04:00`
- State after update: `published`
- Current video URL: <https://youtu.be/cENOZu3prgs>
- Hackathon slug: `cockroachdb-ai`
- Submission ID: `1121568`
- Original `submitted_at`: `2026-08-01T11:22:19.310-04:00`
- Authenticated relationship read: `registered`, `submitted`
- Hackathon phase at recheck: `submissions_open`

Devpost project edits automatically propagate to the existing submission. The
post-update read confirmed the non-null original submission timestamp, so the
current project content is submitted without creating a second submission.

## Local verification

- Provider-origin focused tests: `29 passed`
- Full repository suite after delivery-document synchronization: `431 passed,
  18 skipped`
- Media duration gate: within the required 90–120 second range
- Audio scan: mean `-20.3 dB`, maximum `-3.5 dB`, no silence of at least one
  second below `-45 dB`
- Visual review: opening, architecture, detailed replay, and closing frames
  showed no clipping
- Changed-path secret scan: `PASS`
- Story redaction gate: `PASS`

## Successor boundary

The next immutable release should bind the story receipt, MP4/SRT digests,
public YouTube metadata receipt, Devpost version/submission receipt, source SHA,
coordinator run, and Pages run as one successor delivery envelope. That work
must create a new release epoch; it must not edit or backfill v27.
