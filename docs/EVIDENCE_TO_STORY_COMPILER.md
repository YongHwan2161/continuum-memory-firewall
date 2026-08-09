# Evidence-to-story compiler

The v16 judge delivery is generated from immutable receipts. It is not an editable
second copy of the evaluation result.

## Purpose

The compiler turns the v14 sequential blind campaign into one canonical JSON
contract consumed by the narration, video renderer, public story page,
read-only judge verifier, and release envelope. This removes the failure mode in
which the implementation is current but a video, caption, or Devpost paragraph
still cites an older experiment.

The source campaign remains `hackathon-v14`. Version 15 introduced the compiler
without rerunning or
reinterpret its 540 provider observations. It binds that immutable source to the
current public explanation and delivery receipts.

## Required inputs

- immutable v14 sequential public aggregate, SHA-256
  `f34c2d9f7695b5b6bb333c5b23bcd7b5b924f71e68970c64220ed6ef116f8f3d`;
- immutable v14 envelope, SHA-256
  `8c880fa4908e0405084155387a7f01bbf0bc9f22b2a11b8b7b3de5072a733a07`;
- v14 target `5b75dedff551137d7d8ec72726e8b2cba6dedb99`;
- terminal `PAGES_MATERIALIZED` release-transaction receipt;
- public judge record containing the matching sequential and submission
  lineage.

The canonical output is `public-demo/evidence/evidence-story-v1.json`. Its
self-addressed receipt is
`13a9cb3c0cb58689e95de3666108e43c155ddca254652427a551e969013899f0`;
the exact public file SHA-256 is
`114fd7d425c8403be9aa1729d75220adefcbb336a4b49d98d272413b5ecf6027`.

## Fail-closed gates

Compilation stops unless all of the following remain true:

1. Three sealed batches contain 36 chains, 540 arm observations, and 144 target
   episodes per arm, with labels and scoring denied until candidate completion.
2. Target successes are exactly 105 stateless, 102 raw-RAG, and 114 Continuum.
3. raw-RAG has 48 false canonical promotions and 89 unsafe-memory exposures;
   Continuum has zero of both, zero leakage, zero duplicate effects, and zero
   cleanup residuals.
4. The paired raw-RAG interval is above zero and its sequential e-process crosses
   the preregistered evidence threshold.
5. The stateless comparison is labeled directional, and latency is labeled
   measured rather than superior.
6. Evaluator reconciliation names the exact failed candidate run and artifact;
   it must not claim a regenerated candidate or repeated provider effect.
7. Every source release, workflow, artifact, and public digest matches the
   immutable receipt.

The story output contains nine ordered scenes. Each scene names the evidence
paths supporting its narration and caption. `receipt_sha256` is calculated over
canonical JSON with that field removed, so an independent verifier can detect
any post-compilation edit.

## Delivery binding

The v16 promotion step binds the story to:

- public video <https://youtu.be/QQxfQaDVz9c>;
- 97.02-second local H.264/AAC render SHA-256
  `30518452bf16d46ad33d3500d98731f89273789d4b3b7b75bddd032194a7bed4`;
- English SRT SHA-256
  `f95c60536851fd6cfa8f05441e15ed069da35457aba779977e91024835bbd98b`;
- Devpost project version 20 and its authenticated update timestamp;
- immutable `hackathon-v16` envelope and story release assets.

The release builder recomputes the story receipt and public file digest, checks
the source v14 lineage, then compares its video, subtitle, and Devpost fields to
the promoted judge record. The browser verifier and Python read-only verifier
repeat these checks from public bytes.

The browser computes the self-receipt from the original canonical bytes after
removing the unique `receipt_sha256` field. It must not parse and reserialize the
payload: JavaScript normalizes a JSON numeric lexeme such as `1.0` to `1`, which
would produce a false digest mismatch despite identical evidence. This
cross-language regression is covered by the public-story contract test.

## Claim boundary

The supported competition claim is causal and bounded:

- Continuum has a confirmed paired advantage over raw-RAG on this preregistered
  campaign: +8.33 percentage points, batch-cluster 95% interval +3.47 to +14.58,
  sequential e-value 637.15.
- The +6.25-point estimate over stateless is directional, not confirmatory: its
  interval crosses zero and its e-value does not cross the threshold.
- Latency was measured, but superiority is not claimed.
- The campaign establishes behavior for the tested Bedrock generator and
  disposable GitHub/S3 provider contracts, not every model, provider, or
  production incident distribution.

## Verification

Run the focused contract suite before release:

```bash
python -m unittest tests.test_evidence_story tests.test_promote_evidence_story_v7 tests.test_release_envelope
```

After publication, use the logged-out page or strict command:

```bash
python scripts/judge_readonly_verify.py
python scripts/verify_network_sign_once.py --release-tag hackathon-v16
```

Public paths:

- <https://yonghwan2161.github.io/continuum-memory-firewall/evidence-story.html>
- <https://yonghwan2161.github.io/continuum-memory-firewall/verify.html>
