# Browser-verified KMS release v32

`hackathon-v32` is the successful immutable successor to the preserved v31
candidate-browser failure. These values were read back after publication on
2026-08-15 KST.

## Source and immutable release

- PR: `#166`
- Release target: `e6feff309250640f799f37fb505e9d5ca7257d92`
- Release workflow run: `31817889554` (`success`)
- Release: `hackathon-v32` (`immutable=true`, `draft=false`)
- Envelope SHA-256: `e0919694dc7b3d3fc8c496151f1fd36ef37ee9c3d693eb399eb63da053847492`
- Offline capsule asset SHA-256: `1fba0a72291a62ae2176ff164d65bca6d2aee30feb984d98c2799c9198063c63`
- Offline capsule receipt SHA-256: `d1d0862b798af7d42dc9fec5961c24d0fdd2c56570ebe0b4130ad04ef8d20cbd`
- Coordinator artifact ID: `9225755695`
- Coordinator artifact digest: `sha256:f0f4bf1f754e8b65e85b16d89d16fba05d08dbd7b3d2e2ca41ef6ae84e2bc58c`
- Coordinator receipt SHA-256: `f84d9c6e6ea1ccb11fde14e9af306e1bf734174b87eaf794bd39d24ea31503c5`

The capsule relays the exact immutable v31 asset
`9b6352ecaad6f56f2dae746586c44aa33144a7c246a4f265c4cc35c8c581e712`
and receipt
`4021f07027371f77ae864ad8bb872a9bfdedec060f9ab0aab55ebf9960832ee0`.
Its semantic predecessor remains `hackathon-v30`, failed Pages run
`31816052617` remains a failure, and
`failed_epoch_promoted_to_pass=false`.

## Browser transaction

- Pages workflow run: `31817947957` (`success`)
- Candidate browser artifact ID: `9225809173`
- Candidate browser artifact digest: `sha256:c256c7085169750ae678a2e603d1490ae3ccd1a178e85e1059e76feccfadee71`
- Browser receipt SHA-256: `04652e965f7feaeaa817748a5efe59c796097625130c7b58f838ac4b9950bade`
- Final browser artifact ID: `9225816376`
- Final browser artifact digest: `sha256:d6ca2cce68f18358e91872cb03aebef0fa6acf9b10bf006c4b3c16b9fcb2228d`
- Public bundle SHA-256: `31dc866423de1b02b7560cc7e483d410a2664d8436a7fb237eecc9d29bdf8719`
- Terminal transaction receipt SHA-256: `d228325dbf1409459bbba9758c8745bfb35cf49819523f16181001fba75b1c60`
- Terminal state: `BROWSER_VERIFIED`
- Fresh Chromium result: 39/39 rows, eight same-origin GETs, zero GitHub
  API requests, and zero console errors

The public in-app-browser readback independently rendered
`PASS · browser verified · 0 GitHub API requests` and 39 PASS rows.

## Live monitor and Devpost boundary

The first post-release local readback exposed one verifier-only defect: the
unchanged 10k/50k vector-scale contract was accidentally enumerated through
schema 18 instead of schema 19. PR `#167` replaced that brittle list with a
bounded schema predicate and boundary tests. Main SHA
`2517fc82edafb02b5fbe161c40475e553533272e` passed all eight CI jobs.

Judge monitor run `31818543603` then re-read the deployed public and provider
evidence and passed 47/47 checks. Its artifact ID is `9225996751`, artifact
digest is
`sha256:572598fe51eee058bdd81b7040ff415ccc5931b3368ee3af3f9dbcdf07a70b32`,
and report SHA-256 is
`39a2d3050057842da1cf34897eca405b71ac40911a9d237ec82677c1788b2169`.

Devpost project version 28 was saved after v32 publication with the KMS,
39-row browser, v31-failure, and relay story. The live project remains
published and retains its original `submitted_at` value. That editable prose
postdates the immutable v32 Devpost snapshot and is deliberately reported as a
separate live readback, not retroactively inserted into v32.
