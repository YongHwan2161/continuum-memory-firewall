# Zero-API judge capsule v24 live evidence

## Outcome

The public judge button now completes without a GitHub token or GitHub API
request. The release coordinator performs the complete authenticated online
verification, freezes its individual results in an immutable capsule, and
binds that capsule to the next signed release envelope. The browser recomputes
the capsule self receipt, envelope binding, author/platform bundle subjects,
and terminal Pages receipt from same-origin static files.

## Reviewed delivery

- Core capsule PR: [#145](https://github.com/YongHwan2161/continuum-memory-firewall/pull/145), merged as `bd5b8ecda23978ecdab7b05c64ac216b590cc5c3`.
- Browser CSP correction PR: [#146](https://github.com/YongHwan2161/continuum-memory-firewall/pull/146), merged as `d2e3c1f80515c221ccca67a113cbaaf593baa391`.
- Local suite: `413 passed, 16 skipped`; focused verifier/release suite: `43 passed` before publication.
- Main CI: [31611261854](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31611261854), all four jobs passed at the v24 target.

The first immutable successor, `hackathon-v23`, correctly remained unchanged
after a real headed-browser check found that the page CSP blocked the new
same-origin external script. Its browser epoch is therefore retained as failed
audit history, not repaired or relabelled. The reviewed CSP correction was
published through the fresh `hackathon-v24` epoch.

## Immutable v24 receipt

- Release: [`hackathon-v24`](https://github.com/YongHwan2161/continuum-memory-firewall/releases/tag/hackathon-v24), immutable and non-draft.
- Exact target: `d2e3c1f80515c221ccca67a113cbaaf593baa391`.
- Coordinator run: [31611395093](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31611395093).
- Coordinator artifact: `9147359843`, digest `sha256:c1ed86ae0edecd572cf273c8f5ccede6414ac761133ab060335abae6ef63bcb4`.
- Pages run: [31611493199](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31611493199).
- Envelope SHA-256: `a1c538d92351ad1159a95c674ee66604de4ff5fae156c9fd0606763f378b545f`.
- Offline capsule SHA-256: `9dd2b05fb61732fd935c5db4eae917e7d83d3f84264f9381ec1401caf8a9487d`.
- Capsule self receipt: `8c943305434bbdca4da01d32b25d98bc4c91cba9b30542dfe79e3605327427f9`.
- Public terminal state: `PAGES_MATERIALIZED`.
- Public terminal receipt: `e9ee7ed14d8670c11712ca3e0dbdd3c418a54804cd5e9edb3177ed33749bdae6`.
- Detached author bundle SHA-256: `8b2f22bef79b26e4e3c7032dab3eae42338482d7e10c017e850388edd70e09c3`.
- Public two-authority network bundle SHA-256: `c717f36aeffa8b075e3413ebf31ed6d81b426369c66c5a59f89f65cc5c0cff89`.

The public capsule and envelope bytes are byte-identical to their immutable
release assets. Strict network verification passed with one author SLSA
attestation, one GitHub release countersignature, and completed cryptographic
verification of the exact author identity, main ref, source SHA, subject
digest, and Rekor material.

## Browser and freshness proof

A fresh headed Playwright session opened the public page, clicked the primary
button, and observed:

- UI status `PASS · 0 GitHub API requests`;
- `github_api_requests = 0` and no `api.github.com` performance resource;
- exactly six same-origin static GETs in the click contract;
- all 44 frozen online verifier checks and all 37 judge rows passed;
- release target `d2e3c1f80515c221ccca67a113cbaaf593baa391`;
- capsule and envelope digests matching the immutable v24 assets; and
- zero browser console errors or warnings.

The independent authenticated freshness monitor then passed all 44 online
checks in run [31611785532](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31611785532). Artifact `9147494855` has digest
`sha256:9c693617865cd2147327e7dacb34af6f8178d9f22acd468beb40a69e7df00c0e`.

## Claim boundary and next P0

The capsule proves what the full verifier observed when the successor release
was compiled. It deliberately does not claim that a static browser click is a
fresh provider query; the scheduled authenticated monitor owns later
freshness. The browser validates hashes, subjects, and visible verification
material locally, while the coordinator and CLI perform cryptographic Sigstore
verification.

The next fundamental P0 is provider-origin outcome attestation admission.
`record_outcome_and_promote` now enforces proposal-scoped replay CAS in
CockroachDB, but its API can still receive a caller-constructed successful
`ProviderOutcome`. A server-issued, single-use attestation handle should bind
proposal ID, provider, action/idempotency identity, provider lookup result,
receipt digest, status, verifier policy/version, nonce, and expiry. The same
CockroachDB transaction that accepts the first outcome must consume that
handle before canonical promotion. Fake, stale, cross-proposal, cross-provider,
and replayed handles must fail closed; GitHub and S3 adapters should prove the
same contract. This closes an authority boundary rather than adding another
benchmark.
