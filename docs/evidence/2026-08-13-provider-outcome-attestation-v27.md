# Provider-origin outcome attestation — immutable v27 publication

**Observed:** 2026-08-13 09:10–09:18 KST

**Repository:** `YongHwan2161/continuum-memory-firewall`

**Release:** [`hackathon-v27`](https://github.com/YongHwan2161/continuum-memory-firewall/releases/tag/hackathon-v27)

**Exact release target:** `dbb4942afd45f5bc06cbc08441d43ce155c75f05`

## Result

PASS. The live participant-cluster proof that only a fresh provider lookup may
authorize a successful outcome is now bound into an immutable release, a
terminal release transaction, two network-visible attestations, and two
credential-free browser paths. The dedicated outcome page remains usable when
the anonymous GitHub API quota is exhausted.

This publication closes four distinct boundaries:

1. a caller cannot promote a bare self-asserted success;
2. CockroachDB consumes the provider-origin handle with the outcome and
   canonical memory in one transaction;
3. the live bytes are bound to an immutable exact-head release; and
4. a judge can recompute both the broad capsule and the focused outcome proof
   without credentials or GitHub API availability.

## Live provider and database proof

Main-only OIDC workflow
[`31650943912`](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31650943912)
ran on core implementation `43d63f0ab3af16f83733e2950cffb2954c532582`
and applied migrations 34 and 35 to the participant CockroachDB cluster.

- provider adapter: S3 `HeadObject` + `GetObject`
- fresh provider lookups: 7
- accepted attestation rows: 1
- outcome rows: 1
- canonical promotions: 1
- atomic attestation/outcome/memory joins: 1
- raw signed handles persisted: 0
- negative outcome rows: 0
- blocked authority paths: 6/6 — missing, forged, expired, cross-proposal,
  cross-provider, and receipt mismatch
- RLS: scope identity saw one attestation row; insert failed with
  `SQLSTATE 42501`
- replay CAS journal: `accepted → exact_replay → conflict`

Workflow artifact `9162583114` is
`continuum-outcome-replay-cas-43d63f0ab3af16f83733e2950cffb2954c532582-31650943912-1`
with archive digest
`sha256:682b46d1f4ab60905407208ae562a8223fe936ac1341d75962c4f4d4823e0bf9`.
The redacted public proof is
`sha256:47934505d780123aa2a6bfd5bb8567712dd4e93776363a7cde3bb9cd15e8673b`.
It excludes credentials, connection URLs, bucket names, object keys, and raw
signed handles.

## Reviewed change and release chain

- PR [`#148`](https://github.com/YongHwan2161/continuum-memory-firewall/pull/148)
  implemented provider-origin handles, atomic consumption, migrations, RLS,
  and negative tests.
- PR [`#149`](https://github.com/YongHwan2161/continuum-memory-firewall/pull/149)
  bound the live proof and made Pages workflow-dispatch-only so a source merge
  cannot publish a mixed evidence epoch.
- PR [`#150`](https://github.com/YongHwan2161/continuum-memory-firewall/pull/150)
  advanced the release capsule after v25 published the new proof.
- PR [`#151`](https://github.com/YongHwan2161/continuum-memory-firewall/pull/151)
  changed the dedicated outcome page to five same-origin static resources and
  removed its GitHub workflow/artifact API calls.

`hackathon-v25` and `hackathon-v26` are preserved immutable intermediate
successors. v27 is the first epoch whose predecessor capsule contains the
provider-origin closure and whose dedicated outcome page is quota-independent.
No consumed release was repaired or backfilled.

## v27 release transaction

- coordinator run:
  [`31653469203`](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31653469203)
- coordinator artifact: `9163463052`
- coordinator artifact digest:
  `sha256:b2d2a54892b8c11135ac13d63f7517aa4067a0ca373430b280814ee1400fa074`
- Pages run:
  [`31653536847`](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31653536847)
- terminal state: `PAGES_MATERIALIZED`
- immutable envelope SHA-256:
  `b61aac892fdabf1310e6799aba1fecbe3b58555eb1a293bcf2b8e755385a9acd`
- offline capsule SHA-256:
  `881b12e833c471086b639733bcaf9693d3d8e18fecdd9fe93cfdd792b5afc983`
- capsule self receipt:
  `0e545518342eda3d15a763f2ced9e1b4c0436ee3eac4e0179d9a16c4c86cf8cf`
- terminal transaction receipt:
  `1b313677df1029da3689291e06114556ccb12866bd682adbf343cb055a4ba714`
- complete public receipt file SHA-256:
  `ad5dee71d8e93898d637e2499416f40519a48ea5152bad69ce8e8e3b44b4eb07`
- predecessor release: `hackathon-v26`
- frozen online checks: 44/44
- projected judge rows: 37/37

Strict network-visible sign-once verification passed every policy check:

- author attestations: 1
- GitHub immutable-release countersignatures: 1
- verified author attestations: 1
- author bundle SHA-256:
  `ee2285e87719f8ad428c9574ff6d89b0ca692b4e1eb0aec7dd62cb8b5fb0a87d`
- public two-attestation bundle SHA-256:
  `0cbb15af9c2e87bf503c932b9d6c7ab5614640c3dc46b62b3e7cb3bce8ba4037`

Fresh monitor run
[`31653861653`](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31653861653)
passed all 44 checks and retained artifact `9163587639` with digest
`sha256:39f6d5d7a63d42f3ec6fc2b8007a37f12467aae5e363ba8ead5b544befa2a016`.

## Headed-browser verification under exhausted API quota

The anonymous GitHub API endpoint was already returning HTTP 403 for quota
exhaustion. In that state, a fresh real browser produced:

| Public path | Result | Static GETs | GitHub API requests | Console errors/warnings |
|---|---:|---:|---:|---:|
| [`verify.html`](https://yonghwan2161.github.io/continuum-memory-firewall/verify.html) | PASS | 6 | 0 | 0 / 0 |
| [`outcome-replay-cas.html`](https://yonghwan2161.github.io/continuum-memory-firewall/outcome-replay-cas.html) | PASS | 5 | 0 | 0 / 0 |

The focused page rendered
`PASS · PROVIDER ORIGIN + ATOMIC PROMOTION BOUND` and recomputed seven S3
lookups, six of six blocked authority paths, one outcome, one canonical
promotion, and one atomic join from the same-origin public proof, judge record,
envelope, capsule, and terminal receipt.

## Verification baseline

- complete Python suite: `419 passed, 16 skipped`
- focused provider/outcome/browser-contract suite: `55 passed`
- inline browser JavaScript syntax check: PASS
- secret scan over changed evidence and documentation: PASS
- PR checks: 8/8 PASS on each of `#149`, `#150`, and `#151`

## Claim boundary and next authority seam

This is one retained S3-backed proposal and proves the provider-origin
admission protocol, exact binding, expiry, fresh lookup ordering, atomic
consumption, replay behavior, database authorization, immutable publication,
and credential-free judge delivery. It is not a population estimate.

The live issuer used a process-scoped HMAC key. Durable signer custody and
rotation continuity across verifier restarts are not yet claimed. The next
fundamental P0 is a versioned asymmetric AWS KMS issuer, a verifier-only signing
role, a pinned public-key keyring at promotion, dual-key overlap, and a negative
proof that the action worker cannot call `kms:Sign`.

No AWS Budget increase was needed for this bounded proof.
