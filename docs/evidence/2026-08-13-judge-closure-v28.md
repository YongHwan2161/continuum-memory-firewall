# Judge closure v28

## Outcome

`hackathon-v28` closes the gap between the strongest provider-origin proof and
what a judge actually receives. The release coordinator must bind one exact
source target to the current video, retained Devpost submission receipt,
provider-origin story, release assets, predecessor zero-API capsule, and
terminal Pages receipt. No mutable page may silently select an older video.

## Delivery inputs

- YouTube: <https://youtu.be/9mxeQBt20WI>
- Duration: 99.93 seconds
- Burned-in-caption MP4 SHA-256:
  `a9b3312f51cb9775c02cdf53d570130b65099c83d86885bf33433c47cc383f91`
- Source English SRT SHA-256:
  `4611757b3f074b4c6014f9c9085444c444ebbd6ea2c298a38ba0ac938f9262c7`
- Provider-origin story receipt:
  `f3cafd7db4ba6c4657f2751c022ab609612e84776fc39d3c656e17f6c57676e8`
- Provider-origin public file SHA-256:
  `c57b32cee7c66e6a7a894fb76f36ead18d873fa4056eb134216e3e1524a3a671`
- Devpost project version: `25`
- Devpost submission: `1121568`, status `Submitted`, original submission time
  `2026-08-01T11:22:19.310-04:00`

The MP4 contains visible English narration captions. YouTube caption-track
availability is therefore not part of the delivery claim and cannot make the
release pass or fail.

## Fail-closed contract

Schema 17 preserves the older sequential evidence story as historical evidence
and introduces `provider_origin_story` as the current delivery authority. The
release fails unless:

1. the story's normalized public bytes and self-receipt verify;
2. its v27 source envelope, target, provider proof, RLS denial, and six negative
   authority controls remain intact;
3. video URL, duration, MP4 digest, and source SRT digest match the submission;
4. Devpost project version, update time, submission ID, and retained submission
   time match the delivery receipt;
5. the provider-origin file and sidecar are present in the immutable v28 release;
6. the online verifier validates all 45 checks directly, while the zero-API
   browser path combines the predecessor capsule's 44 checks with the current
   signed envelope's provider-delivery check into 38 visible rows.

The predecessor capsule is intentional. A release cannot freeze the result of
verifying itself before it exists. v28 therefore keeps the already immutable
v27 provider snapshot and adds only the current delivery tuple through the v28
envelope, Sigstore attestations, and terminal transaction. This removes the
otherwise unbounded need for a v29 merely to certify v28.

## Judge-first projection

The landing page derives, rather than hard-codes, four first-screen results from
`sequential-blind-v1.json` and `outcome-replay-cas-v1.json`:

- raw-RAG false canonical promotions: `48`;
- Continuum false canonical promotions: `0`;
- future provider successes: `114/144` versus `102/144`;
- invalid authority paths blocked: `6/6`, with zero negative outcomes.

Publication workflow IDs, immutable asset digests, signature bundles, capsule
receipt, and terminal Pages receipt live in the v28 release itself. This file
does not predeclare values that only GitHub can issue after publication.
