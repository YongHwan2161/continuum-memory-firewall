# Provider-origin outcome attestation live receipt

**Observed:** 2026-08-13

**Implementation PR:** [#148](https://github.com/YongHwan2161/continuum-memory-firewall/pull/148)

**Workflow:** [31650943912](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31650943912)

**Exact head:** `43d63f0ab3af16f83733e2950cffb2954c532582`

**Artifact ID:** `9162583114`

**Artifact name:** `continuum-outcome-replay-cas-43d63f0ab3af16f83733e2950cffb2954c532582-31650943912-1`

**Artifact archive digest:** `sha256:682b46d1f4ab60905407208ae562a8223fe936ac1341d75962c4f4d4823e0bf9`

## Result

The reviewed main-only OIDC workflow deployed exact artifact
`3ece49e3652a48e902577106e58acacea9cfcedccc32f1d4282c31603648ace8`,
applied migrations 34 and 35 to the participant CockroachDB cluster, granted
temporary bounded S3 proof authority, and revoked that authority on the
workflow's always path.

The S3 adapter performed seven fresh `HeadObject` plus `GetObject` receipt
lookups. After the accepted lookup, the verifier issued one five-minute
HMAC-SHA256 handle under issuer `s3-provider-origin-verifier-v1`, policy
`s3-receipt-lookup-v1`, and non-secret key identifier `126997c9c34efa07`.
Its claims bound the exact proposal, provider, idempotency key, receipt ID and
digest, success status, policy, issuer, nonce, issue time, and expiry.

CockroachDB consumed the handle digest and nonce in the same serializable
transaction as exactly one provider outcome and one canonical promotion.
There was one attestation row and one atomic attestation/outcome/promotion join.
The raw handle was never persisted. Exact replay returned the existing durable
outcome and promotion; a different real S3 receipt produced the typed
`OUTCOME_REPLAY_CONFLICT` path without replacing them.

## Fail-closed matrix

| Attempt | Result |
|---|---|
| Missing handle | `OUTCOME_ATTESTATION_REQUIRED` |
| Forged signature | `OUTCOME_ATTESTATION_INVALID` |
| Expired handle | `OUTCOME_ATTESTATION_EXPIRED` |
| Cross-proposal reuse | `OUTCOME_ATTESTATION_BINDING_MISMATCH` |
| Cross-provider reuse | `OUTCOME_ATTESTATION_BINDING_MISMATCH` |
| Receipt mismatch | `OUTCOME_ATTESTATION_BINDING_MISMATCH` |

All six negative paths produced zero provider-outcome rows. The scoped
NOBYPASSRLS identity saw one in-scope attestation row and all three in-scope
reconciliation journal rows, but direct attestation insertion failed with
`SQLSTATE 42501`.

## Public and private commitments

- Private report SHA-256:
  `37d192b1e63382c41bce59d1cad6a546be39d4e767b8e240c2c7108e5bf19927`
- Public projection SHA-256:
  `47934505d780123aa2a6bfd5bb8567712dd4e93776363a7cde3bb9cd15e8673b`
- Accepted object SHA-256:
  `500f4e6fbb4b225386f60c353ae9a8693652c7eb5d40bce122e07d6ffde562e2`
- Accepted receipt SHA-256:
  `d2cf982bb36442e92270e90d6f6ac8094c3abbe5af77eabc76260f2d57bd51e3`
- Conflicting object SHA-256:
  `4fd9b5d2743eba1052c64bff4696ddf5d90c37344ae2dd3291c93b4053fb6def`
- Conflicting receipt SHA-256:
  `990fe696b3c113b691ab47eb70f855077d5113658d363a42a619c8120e792acc`
- Stored handle digest:
  `ad1d2c66233650da3b2afa691e5a2fc81215b4ae29c5e76f784b53998e0356df`
- Stored nonce digest:
  `b24444a244460d3fd207003f034dc81f8ec5d194227e131a3032af5d2a1bcebc`
- Reconciliation chain tip:
  `630999002aada8d5d53b63570b6d0ec3091069f031943935ce75186609f7cf14`
- Combined RLS migration checksum:
  `24fad1758967acec5865f253cbea59d10f092e65fc072bcd7485f6ac8844432f`

The projection excludes database credentials, URLs, buckets, object keys, and
raw signed handles. No AWS Budget increase was needed for this bounded proof.

## Claim boundary

This proves the provider-origin admission protocol, fresh lookup ordering,
short expiry, claim binding, atomic consumption, replay behavior, and database
authorization boundary for one retained S3-backed proposal. It is not a
population estimate and does not yet prove signing-key custody or rotation
continuity across verifier restarts. The live run used a process-scoped HMAC
authority; durable asymmetric KMS custody is the next authority-lifecycle P0.

## Immutable publication gate

The public projection and updated RLS checksum are staged for the next fresh
immutable successor. `hackathon-v24` remains the current public proof until a
new coordinator run reaches `PAGES_MATERIALIZED`, strict network verification,
headed-browser PASS, and authenticated freshness monitoring. A consumed or
failed release epoch will not be edited or backfilled.
