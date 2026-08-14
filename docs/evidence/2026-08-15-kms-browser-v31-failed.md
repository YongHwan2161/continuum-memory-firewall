# Preserved v31 candidate-browser failure

`hackathon-v31` is an immutable failed delivery epoch. It must not be retried,
backfilled, or edited.

- Release target: `42184fc4b4f08c85a338658c0ff6a72b39f3874a`
- Release coordinator run: `31815952803` (`success`)
- Pages candidate run: `31816052617` (`failure`)
- Failure step: `Run the fresh-context candidate browser gate`
- Observed browser state: `FAIL`; expected `CANDIDATE_PASS`

The KMS receipt, workflow, artifact, CockroachDB evidence, release asset, and
signed envelope were valid. The failure was a delivery-contract version skew:
the page introduced `kmsAuthority` as row 39, while the content-addressed v30
offline judge program still projected a 38-row predecessor capsule and required
`required_ui_check_count === 38`. It therefore failed closed before the release
transaction could advance from the candidate publication to
`BROWSER_VERIFIED`.

The v32 successor does not weaken this gate. It publishes new content-addressed
JavaScript that fetches the KMS receipt as an eighth same-origin static object,
checks its public and canonical hashes, lifecycle and database invariants, and
signed-envelope binding, then requires all 39 rows. The old v31 release and
script bytes remain unchanged as audit history.

Because v31 never reached `BROWSER_VERIFIED`, v32 does not compile a fresh PASS
from that failed receipt. Instead it downloads the exact immutable v31 capsule
asset (`9b6352ecaad6f56f2dae746586c44aa33144a7c246a4f265c4cc35c8c581e712`),
checks its self-receipt
(`4021f07027371f77ae864ad8bb872a9bfdedec060f9ab0aab55ebf9960832ee0`),
verifies v31 immutability and the failed Pages run, and relays the last
successful v30 semantic snapshot. The signed v32 envelope and browser program
bind that relay with `failed_epoch_promoted_to_pass=false` before performing a
new fresh-context candidate and final browser verification.
