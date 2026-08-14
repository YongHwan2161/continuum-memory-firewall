# KMS outcome-authority lifecycle — live evidence

## Admitted claim

One retained participant-account run proves that the action worker can execute
an effect but cannot cryptographically certify its own success. A separate
verifier re-reads the provider receipt, owns the only KMS signing authority,
and issues a proposal-bound attestation. CockroachDB persists the verification
algorithm, authority epoch, and key-ARN digest—not a reusable raw handle—and
can verify an old outcome after restart without another signature.

This is an architectural closure, not a population-level reliability estimate.

## Exact provider receipts

- Source: `b02ca33e0c0b0a8d02629f0a4280d1613ad47806`
- GitHub Actions run: `31813682371`, attempt `1`, conclusion `success`
- Artifact: `9224227375`
- Artifact name:
  `continuum-kms-authority-b02ca33e0c0b0a8d02629f0a4280d1613ad47806-31813682371-1`
- Artifact archive SHA-256:
  `66f3a5e4a8a9e39f40f4f8b70845e2a086b54078ed6f6404e7b92a3d0727b9d4`
- Public receipt SHA-256:
  `9492eb130053e2b496e58695eeb9c110f423934be18888cbe320f810dda353d2`
- Canonical receipt SHA-256:
  `a48e601612ba59edfd4f97b45b76e8873629a53e8f88fa1791ac2fe5dabfa38c`
- Deployment artifact SHA-256:
  `3ece49e3652a48e902577106e58acacea9cfcedccc32f1d4282c31603648ace8`

## Measured lifecycle

- AWS region: `ap-southeast-1`
- Keys: two `ECC_NIST_P256` verifier keys
- Algorithm: `ECDSA_SHA_256`
- KMS operations: four `Sign`, two `GetPublicKey`
- Provider verification: four S3 `HeadObject+GetObject` re-reads
- Worker signing attempt: `AccessDenied`
- Authority transitions: activate key A, rotate to key B, rollback to key A
- Persisted authority epochs: `1, 2, 3`
- CockroachDB migration: `38`
- Retained rows: three attestations, three outcomes, three canonical memories
- Scoped visibility: three rows; runtime attestation insert denied with
  `SQLSTATE 42501`
- Exact replay: one old handle verified after restart without re-signing
- Private handoff objects after independent cleanup: `0`

All 18 fail-closed checks passed, including dual-key overlap, keyring hash-chain,
provider lookup before signing, worker sign denial, rotation and rollback epoch
commit, offline restart, exact replay, RLS, absent raw handle, zero handoff
residue, and forged/expired/unknown-epoch rejection.

## Public judge contract

Schema 19 binds the public receipt to the exact workflow and artifact APIs,
archive digest, immutable `hackathon-v32` release asset, signed release
envelope, and terminal browser receipt. The dedicated
`kms-authority.html` page uses four same-origin static GETs and no credentials;
the full verifier adds one explicit KMS authority row for 39 total checks and
uses eight same-origin GETs in its browser-gated offline path.

No key ARN, raw handle, credential, bucket name, object key, database URL, or
database row is included in the public receipt.
